"""Exercise an installed Mos CLI in a private external tmux server (POSIX only)."""

import argparse
import fcntl
import json
import os
import platform
import pty
import select
import shutil
import struct
import subprocess
import termios
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class Client:
    def __init__(self, harness: "Harness", command: list[str] | None = None) -> None:
        self.master, self.slave = pty.openpty()
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 36, 140, 0, 0))
        self.original = termios.tcgetattr(self.slave)
        self.output = bytearray()
        self.process = subprocess.Popen(
            command or [*harness.prefix, "attach-session", "-t", "mos"],
            stdin=self.slave,
            stdout=self.slave,
            stderr=self.slave,
            env=harness.env,
            cwd=harness.root,
            start_new_session=True,
        )

    def pump(self) -> None:
        if select.select([self.master], [], [], 0.05)[0]:
            data = os.read(self.master, 65536)
            self.output.extend(data)
            del self.output[:-262144]
            if b"\x1b[6n" in data:
                os.write(self.master, b"\x1b[1;1R")

    def send(self, data: bytes) -> None:
        os.write(self.master, data)

    def detach(self) -> None:
        self.send(b"\x02d")
        deadline = time.monotonic() + 10
        while self.process.poll() is None and time.monotonic() < deadline:
            self.pump()
        require(self.process.poll() == 0, "tmux client did not detach cleanly")
        self.check_restoration()

    def check_restoration(self) -> None:
        restored = termios.tcgetattr(self.slave)
        restored[3] &= ~getattr(termios, "PENDIN", 0)
        self.original[3] &= ~getattr(termios, "PENDIN", 0)
        require(
            restored == self.original, "detached client left terminal modes changed"
        )
        require(b"\x1b[?1049l" in self.output, "client did not leave alternate screen")

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        os.close(self.master)
        os.close(self.slave)


class Harness:
    def __init__(self, root: Path, mos: Path, tmux: str) -> None:
        self.root, self.mos = root, mos
        self.prefix = [tmux, "-S", str(root / "tmux.sock"), "-f", "/dev/null"]
        self.env = {
            "PATH": os.defpath,
            "TERM": "xterm-256color",
            "LANG": "en_US.UTF-8",
            "LC_CTYPE": "UTF-8",
        }
        self.client: Client | None = None
        self.pane = ""
        self.checks: list[str] = []

    def tmux(self, *args: str) -> str:
        result = subprocess.run(
            [*self.prefix, *args],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )
        # Some tmux startup errors return zero; keep them visible at the source.
        require(not result.stderr.strip(), "tmux reported: " + result.stderr.strip())
        return result.stdout.strip()

    def wait(self, predicate: Callable[[], bool], description: str) -> None:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self.client:
                self.client.pump()
            if predicate():
                return
            time.sleep(0.02)
        raise RuntimeError("Timed out: " + description)

    def screen(self) -> str:
        return self.tmux("capture-pane", "-p", "-t", self.pane)

    def state(self) -> dict:
        files = list((self.root / "sessions").glob("*.json"))
        require(len(files) == 1, "expected one synthetic saved session")
        return json.loads(files[0].read_bytes())["state"]

    def start(self, arguments: list[str]) -> None:
        # Fixed wrapper observes normal Mos cleanup without executing input text.
        wrapper = (
            'stty -g > "$1"; before=$1; after=$2; result=$3; shift 3; '
            '"$@"; code=$?; stty -g > "$after"; '
            'printf "%s\\n" "$code" > "$result"; exit "$code"'
        )
        self.pane = self.tmux(
            "new-session",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-s",
            "mos",
            "-x",
            "140",
            "-y",
            "36",
            "-c",
            str(self.root),
            "/bin/sh",
            "-c",
            wrapper,
            "mos-tmux-smoke",
            str(self.root / "before"),
            str(self.root / "after"),
            str(self.root / "exit"),
            str(self.mos),
            *arguments,
        )
        self.tmux("set-option", "-w", "-t", self.pane, "remain-on-exit", "on")
        self.client = Client(self)
        self.wait(lambda: "Message" in self.screen(), "Mos composer")

    def send(self, data: bytes) -> None:
        assert self.client is not None
        self.client.send(data)

    def close(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
        subprocess.run(
            [*self.prefix, "kill-server"],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            timeout=10,
        )


def check_conversation(harness: Harness, python: Path) -> None:
    seed = """
import sys
from pathlib import Path
from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.run.conversation_store import ConversationStore
root = Path(sys.argv[1])
cassette = demo_cassette()
state = ConversationController.fresh(root, cassette, memory_disabled=True)
with ConversationStore(root / "sessions", state.session_id, root) as store:
    store.save(state)
    controller = ConversationController(state, cassette, store.save)
    controller.submit(DEMO_PROMPTS[0])
print(state.session_id)
"""
    session = subprocess.check_output(
        [str(python), "-I", "-c", seed, str(harness.root)],
        cwd=harness.root,
        env=harness.env,
        text=True,
        timeout=10,
    ).strip()
    arguments = [
        "resume",
        session,
        "--storage",
        str(harness.root / "sessions"),
        "--workspace",
        str(harness.root),
        "--no-memory",
    ]
    harness.start(arguments)
    harness.wait(lambda: "1 queued" in harness.screen(), "paused saved queue")
    require(harness.state()["workspace"] == str(harness.root), "wrong workspace")
    pane_pid = harness.tmux("display-message", "-p", "-t", harness.pane, "#{pane_pid}")
    draft = "Retained draft café 日本語"
    harness.send(draft.encode())
    harness.wait(lambda: draft in harness.screen(), "Unicode composer draft")
    snapshot = harness.state()
    assert harness.client is not None
    harness.client.detach()
    harness.client.close()
    harness.client = None
    require(harness.state() == snapshot, "detach changed saved queue or state")
    # A competing writer must fail even while the original client is detached.
    competitor = subprocess.run(
        [str(harness.mos), *arguments, "--plain"],
        cwd=harness.root,
        env=harness.env,
        input="/quit\n",
        text=True,
        capture_output=True,
        timeout=10,
    )
    require(competitor.returncode != 0, "competing controller acquired active session")
    require(harness.state() == snapshot, "competing controller changed state")
    harness.client = Client(harness)
    harness.wait(lambda: draft in harness.screen(), "draft after reattachment")
    require(
        harness.tmux("display-message", "-p", "-t", harness.pane, "#{pane_pid}")
        == pane_pid,
        "reattachment replaced process",
    )
    require(harness.state() == snapshot, "reattachment consumed queued work")
    harness.checks.extend(
        [
            "workspace",
            "unicode",
            "draft-and-queue-reattach",
            "exclusive-controller",
            "client-terminal-restoration",
        ]
    )
    sibling = harness.tmux(
        "split-window",
        "-d",
        "-h",
        "-l",
        "40",
        "-P",
        "-F",
        "#{pane_id}",
        "-t",
        harness.pane,
        "-c",
        str(harness.root),
        "/bin/sleep",
        "60",
    )
    harness.wait(lambda: draft in harness.screen(), "draft in split pane")
    harness.tmux("resize-pane", "-t", sibling, "-x", "30")
    harness.tmux("resize-pane", "-Z", "-t", harness.pane)
    harness.wait(lambda: draft in harness.screen(), "draft in zoomed pane")
    harness.tmux("resize-pane", "-Z", "-t", harness.pane)
    harness.send(b"\t\x1b[5~\x1b[6~\t")
    harness.wait(lambda: draft in harness.screen(), "draft after transcript navigation")
    harness.checks.extend(["split-resize-zoom", "transcript-navigation"])
    harness.send(b"\x03")
    harness.wait(
        lambda: harness.state()["entries"][0]["status"] == "cancelled",
        "Ctrl-C cancels queue",
    )
    require(harness.state()["exchanges_consumed"] == 0, "cancellation consumed attempt")
    harness.send(b"\x15Remember that the fixture boundary is ten.\r")
    harness.wait(
        lambda: harness.state()["entries"][-1]["status"] == "completed",
        "first recorded answer",
    )
    harness.send(b"What boundary did I give you?\r")
    harness.wait(
        lambda: (
            len(harness.state()["entries"]) == 3
            and harness.state()["entries"][-1]["status"] == "completed"
        ),
        "contextual follow-up",
    )
    harness.checks.append("queue-cancellation-and-follow-up")
    paste = harness.root / "paste.txt"
    for count, payload in enumerate(
        ("/quit", "/review", "/quit\n/review\nUnicode café 日本語"), start=3
    ):
        paste.write_text(payload)
        harness.tmux("load-buffer", "-b", "mos-fixture", str(paste))
        harness.tmux("paste-buffer", "-p", "-b", "mos-fixture", "-t", harness.pane)
        harness.wait(
            lambda payload=payload: payload.splitlines()[-1] in harness.screen(),
            "bracketed paste draft",
        )
        require(
            len(harness.state()["entries"]) == count,
            "paste executed before submission",
        )
        harness.send(b"\r")
        harness.wait(
            lambda count=count: len(harness.state()["entries"]) == count + 1,
            "literal paste submission",
        )
        entry = harness.state()["entries"][-1]
        require(entry["text"] == payload, "pasted text changed")
        require(entry.get("review_packet") is None, "paste became a review")
    require(
        harness.state()["exchanges_consumed"] == 2,
        "unsupported paste consumed an exhausted recording",
    )
    harness.checks.append("bracketed-paste-slash-isolation")
    harness.send(b"\x04")
    harness.wait(lambda: (harness.root / "exit").exists(), "clean Mos exit")
    require((harness.root / "exit").read_text().strip() == "0", "Mos exit failed")
    require(
        (harness.root / "before").read_text() == (harness.root / "after").read_text(),
        "Mos changed pane terminal modes",
    )
    require(
        harness.tmux("display-message", "-p", "-t", harness.pane, "#{alternate_on}")
        == "0",
        "Mos left alternate screen active",
    )
    harness.checks.append("mos-terminal-restoration")


def check_server_loss(harness: Harness) -> None:
    harness.start(
        [
            "chat",
            "--storage",
            str(harness.root / "sessions"),
            "--workspace",
            str(harness.root),
            "--no-memory",
        ]
    )
    harness.wait(
        lambda: len(list((harness.root / "sessions").glob("*.json"))) == 1,
        "saved session",
    )
    harness.send(b"Unsaved draft after server loss")
    harness.wait(
        lambda: "Unsaved draft after server loss" in harness.screen(), "loss-case draft"
    )
    before = harness.state()
    harness.tmux("kill-server")
    # The real CLI must recover the saved session without recreating the draft.
    recovered = subprocess.run(
        [
            str(harness.mos),
            "resume",
            before["session_id"],
            "--storage",
            str(harness.root / "sessions"),
            "--workspace",
            str(harness.root),
            "--no-memory",
            "--plain",
        ],
        cwd=harness.root,
        env=harness.env,
        input="/quit\n",
        text=True,
        capture_output=True,
        timeout=10,
    )
    require(
        recovered.returncode == 0, "saved session could not resume after server loss"
    )
    after = harness.state()
    require(
        after["session_id"] == before["session_id"]
        and after["entries"] == before["entries"],
        "server loss changed saved conversation",
    )
    harness.checks.append("server-loss-explicit-resume")


def check_without_tmux(harness: Harness) -> None:
    harness.env["PATH"] = str(harness.root)
    require(
        shutil.which("tmux", path=harness.env["PATH"]) is None,
        "fallback PATH unexpectedly contains tmux",
    )
    harness.client = Client(
        harness,
        [
            str(harness.mos),
            "chat",
            "--storage",
            str(harness.root / "sessions"),
            "--workspace",
            str(harness.root),
            "--no-memory",
        ],
    )
    harness.wait(lambda: b"Message" in harness.client.output, "ordinary Mos composer")
    harness.send(b"\x04")
    harness.wait(lambda: harness.client.process.poll() is not None, "ordinary Mos exit")
    # Drain the final alternate-screen reset after the child has exited.
    harness.client.pump()
    require(harness.client.process.returncode == 0, "ordinary Mos requires tmux")
    harness.client.check_restoration()
    harness.checks.append("ordinary-launch-without-tmux-on-path")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mos", type=Path, required=True, help="Installed wheel's mos executable"
    )
    parser.add_argument(
        "--python",
        type=Path,
        required=True,
        help="Python in the same wheel installation",
    )
    parser.add_argument("--tmux", default="tmux")
    args = parser.parse_args()
    tmux = shutil.which(args.tmux)
    require(tmux is not None, "tmux is not installed; ordinary Mos remains usable")
    assert tmux is not None
    mos, python = args.mos.absolute(), args.python.absolute()
    require(
        mos.is_file() and python.is_file(), "installed Mos/Python paths are required"
    )
    require(mos.parent == python.parent, "Mos and Python must share an installation")
    checks: list[str] = []
    for scenario in ("conversation", "server-loss", "without-tmux"):
        with TemporaryDirectory(prefix="mos-tmux-") as directory:
            harness = Harness(Path(directory).resolve(), mos, tmux)
            try:
                if scenario == "conversation":
                    check_conversation(harness, python)
                elif scenario == "server-loss":
                    check_server_loss(harness)
                else:
                    check_without_tmux(harness)
                checks.extend(harness.checks)
            finally:
                harness.close()
    print(
        json.dumps(
            {
                "platform": platform.system(),
                "architecture": platform.machine(),
                "tmux": subprocess.check_output([tmux, "-V"], text=True).strip(),
                "client_term": "xterm-256color",
                "checks": checks,
                "scope": (
                    "synthetic recorded conversation; "
                    "no live providers or embedded backend"
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
