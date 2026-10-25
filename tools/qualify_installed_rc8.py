"""Unpaid external-CLI qualification of the exact publisher-signed rc.8 runtime."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import pty
import re
import select
import signal
import sqlite3
import struct
import subprocess
import tempfile
import termios
import time
from pathlib import Path

SOURCE = "eadb415d31afd89b142e3229a8ccca72aca835ee"
VERSION = "0.1.0-rc.8"
PROMPT = "Remember that the fixture boundary is ten."


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv: list[str], env: dict[str, str], cwd: Path, data: str = "") -> str:
    result = subprocess.run(
        argv, env=env, cwd=cwd, input=data, capture_output=True, text=True, timeout=120
    )
    if result.returncode:
        raise ValueError(f"command {Path(argv[0]).name} failed: {result.stderr[-800:]}")
    return result.stdout


def result(raw: str) -> dict[str, object]:
    events = [json.loads(line) for line in raw.splitlines()]
    if not events or [e["sequence"] for e in events] != list(range(1, len(events) + 1)):
        raise ValueError("noncontiguous result events")
    if any(e["schema_version"] != 1 for e in events):
        raise ValueError("wrong event schema")
    terminal = [e for e in events if e["type"] == "exec.result"]
    if len(terminal) != 1 or terminal[0] != events[-1]:
        raise ValueError("missing or duplicate terminal result")
    return terminal[0]


def checkpoint(storage: Path, backend: str, session_id: str) -> tuple[int, object]:
    """Read synthetic fixture counters only after the product has closed its store."""
    if backend == "snapshot":
        state = json.loads((storage / f"{session_id}.json").read_text())["state"]
    else:
        with sqlite3.connect(
            (storage / "sessions.sqlite3").as_uri() + "?mode=ro", uri=True
        ) as database:
            row = database.execute(
                "SELECT header FROM sessions WHERE sid=?", (session_id,)
            ).fetchone()
            if row is None:
                raise ValueError("missing synthetic session header")
            state = json.loads(row[0])["body"]
    return state["exchanges_consumed"], state["recovery_journal"]


def terminal(executable: Path, base: Path, backend: str, env: dict[str, str]) -> None:
    workspace = base / "workspace"
    workspace.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.email", "qualification@example.invalid"],
        ["config", "user.name", "Synthetic qualification fixture"],
    ):
        run(["/usr/bin/git", *args], env, workspace)
    source = workspace / "one.txt"
    source.write_text("before\n")
    run(["/usr/bin/git", "add", "one.txt"], env, workspace)
    run(
        ["/usr/bin/git", "-c", "commit.gpgsign=false", "commit", "-qm", "base"],
        env,
        workspace,
    )
    source.write_text("after\n")
    master, slave = pty.openpty()
    original = termios.tcgetattr(slave)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    process = subprocess.Popen(
        [
            str(executable),
            "chat",
            "--no-memory",
            "--storage-backend",
            backend,
            "--storage",
            str(base / "sessions"),
            "-C",
            str(workspace),
        ],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=workspace,
        env=env,
        start_new_session=True,
    )
    output = bytearray()

    def wait_for(needle: bytes) -> None:
        deadline = time.monotonic() + 30
        redraw_at = time.monotonic() + 1
        redrawn = False
        while needle not in re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", output):
            if time.monotonic() >= deadline or len(output) > 4_000_000:
                raise ValueError(
                    f"terminal did not show {needle!r}: {bytes(output[-1000:])!r}"
                )
            if not redrawn and time.monotonic() >= redraw_at:
                # A differential repaint can retain old glyphs via cursor moves;
                # request a full screen before matching contiguous text.
                os.write(master, b"\x0c")
                redrawn = True
            readable, _, _ = select.select([master], [], [], 0.1)
            if readable:
                chunk = os.read(master, 16384)
                if not chunk:
                    raise ValueError("terminal closed before assertion")
                output.extend(chunk)
                if b"\x1b[6n" in chunk:
                    os.write(master, b"\x1b[1;1R")

    try:
        wait_for(b"Type a message")
        os.write(master, b"/diff\r")
        wait_for(b"+after")
        output.clear()
        os.write(master, b"\t\t\t" + b"\x1b[B" * 6 + b"\x1b[24~")
        wait_for(b"Frozen diff li")
        # Tab cycles from the patch back to the composer at this width.
        os.write(master, b"\tExplain this line")
        source.write_text("newer\n")
        output.clear()
        os.write(master, b"\r")
        wait_for(b"Recorded local chat")
        output.clear()
        os.write(master, b"\r")
        wait_for(b"Diff source changed")
        # Confirmation must refuse before dispatch, retaining the draft/excerpt.
        output.clear()
        os.write(master, b"\x07\x0c")
        wait_for(b"Explain this line")
        os.write(master, b"\x18")
        wait_for(b"Latest")
        os.write(master, b"\x15")
        wait_for(b"Unsent draft discarded")
        os.write(master, b"\x1b[21~")
        wait_for(b"Diff panel clos")
        # Bracketed pasted slash/Unicode/multiline text remains an unsent draft.
        output.clear()
        os.write(master, "\x1b[200~/review\nπ draft\x1b[201~".encode())
        wait_for("π draft".encode())
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 35, 80, 0, 0))
        os.kill(process.pid, signal.SIGWINCH)
        output.clear()
        os.write(master, b"\x0c")
        wait_for("π draft".encode())
        os.write(master, b"\x15")
        wait_for(b"Unsent draft discarded")
        output.clear()
        os.write(master, PROMPT.encode() + b"\r")
        wait_for(b"The fixture boundary is ten.")
        output.clear()
        os.write(master, b"\x04")
        wait_for(b"conversation.saved")
        if process.wait(timeout=15) != 0:
            raise ValueError("terminal exit failed")
        restored = termios.tcgetattr(slave)
        restored[3] &= ~getattr(termios, "PENDIN", 0)
        original[3] &= ~getattr(termios, "PENDIN", 0)
        if restored != original:
            raise ValueError("terminal modes were not restored")
        reopened = run(
            [
                str(executable),
                "resume",
                "--last",
                "--plain",
                "--no-memory",
                "--storage-backend",
                backend,
                "--storage",
                str(base / "sessions"),
                "-C",
                str(workspace),
            ],
            env,
            workspace,
            "What boundary did I give you?\n",
        )
        if "You gave me a boundary of ten." not in reopened:
            raise ValueError("terminal cold resume lost its context")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=15)
        os.close(master)
        os.close(slave)


def qualify(artifacts: Path, evidence: Path) -> None:
    metadata = artifacts / "release.json"
    payload = json.loads(metadata.read_text())["payload"]
    if (payload["source_commit"], payload["version"], payload["storage_epoch"]) != (
        SOURCE,
        VERSION,
        2,
    ):
        raise ValueError("candidate source/version/epoch mismatch")
    arch = "aarch64" if platform.machine().lower() in {"arm64", "aarch64"} else "x86_64"
    target = ("macos" if platform.system() == "Darwin" else "linux") + "-" + arch
    archive = artifacts / f"mos-{VERSION}-{target}.tar.gz"
    bootstrap = artifacts / f"mos-install-{target}"
    selected = next(a for a in payload["artifacts"] if a["platform"] == target)
    if sha(archive) != selected["sha256"] or archive.stat().st_size != selected["size"]:
        raise ValueError("candidate archive mismatch")
    if (
        f"{sha(bootstrap)}  {bootstrap.name}"
        not in (artifacts / "BOOTSTRAP_SHA256SUMS").read_text().splitlines()
    ):
        raise ValueError("bootstrap checksum mismatch")
    bootstrap.chmod(0o700)
    env = {
        k: v
        for k, v in os.environ.items()
        if k in {"TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT"}
    }
    env.update(
        PATH="/usr/bin:/bin:/usr/sbin:/sbin",
        TERM="xterm-256color",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL="/dev/null",
    )
    results: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="mos-signed-v1-") as temporary:
        base = Path(temporary).resolve()
        run(
            [
                str(bootstrap.resolve()),
                "--metadata",
                str(metadata.resolve()),
                "--archive",
                str(archive.resolve()),
                "--version",
                VERSION,
                "--channel",
                "preview",
                "--root",
                str(base / "app"),
                "--bin-dir",
                str(base / "bin"),
            ],
            env,
            base,
        )
        executable = base / "bin" / "mos"
        if (
            run([str(executable), "--version"], env, base).strip()
            != f"mos-eisley {VERSION}"
        ):
            raise ValueError("installed version mismatch")
        run(
            [str(executable), "update", "disable", "--root", str(base / "app")],
            env,
            base,
        )
        for backend in ("snapshot", "sqlite"):
            workspace = base / f"exec-{backend}"
            workspace.mkdir()
            common = ["--no-memory", "--storage-backend", backend, "-C", str(workspace)]
            for mode in ("positional", "stdin"):
                storage = base / f"{backend}-{mode}"
                args = [
                    str(executable),
                    "exec",
                    "--json",
                    *common,
                    "--storage",
                    str(storage),
                ]
                raw = run(
                    args + (["--stdin"] if mode == "stdin" else [PROMPT]),
                    env,
                    workspace,
                    PROMPT if mode == "stdin" else "",
                )
                value = result(raw)
                if (
                    any(
                        value.get(k) != v
                        for k, v in {
                            "status": "completed",
                            "exit_code": 0,
                            "answer": "The fixture boundary is ten.",
                            "persistence_status": "committed",
                            "effect_status": "completed",
                        }.items()
                    )
                    or not value.get("operation_id")
                    or not value.get("recovery_cursor")
                ):
                    raise ValueError("invalid committed exec result")
                session_id = str(value["session_id"])
                before = checkpoint(storage, backend, session_id)
                if before[0] != 1:
                    raise ValueError("unexpected initial consumed-attempt count")
                run(
                    [
                        str(executable),
                        "resume",
                        session_id,
                        "--plain",
                        *common,
                        "--storage",
                        str(storage),
                    ],
                    env,
                    workspace,
                    "/quit\n",
                )
                if checkpoint(storage, backend, session_id) != before:
                    raise ValueError(
                        "passive reopen changed attempts or operation history"
                    )
                answer = run(
                    [
                        str(executable),
                        "resume",
                        str(value["session_id"]),
                        "--plain",
                        *common,
                        "--storage",
                        str(storage),
                    ],
                    env,
                    workspace,
                    "What boundary did I give you?\n",
                )
                if "You gave me a boundary of ten." not in answer:
                    raise ValueError("exec cold resume failed")
                if checkpoint(storage, backend, session_id)[0] != 2:
                    raise ValueError(
                        "follow-up did not consume exactly one new attempt"
                    )
            for index, invalid in enumerate((b"", b"\xff", b"x" * 8001)):
                denied_storage = base / f"invalid-{backend}-{index}"
                denied = subprocess.run(
                    [
                        str(executable),
                        "exec",
                        "--json",
                        "--stdin",
                        *common,
                        "--storage",
                        str(denied_storage),
                    ],
                    env=env,
                    cwd=workspace,
                    input=invalid,
                    capture_output=True,
                    timeout=120,
                )
                rejected = result(denied.stdout.decode("utf-8"))
                if (
                    denied.returncode != 2
                    or rejected.get("status") != "invalid_input"
                    or rejected.get("exit_code") != 2
                    or denied_storage.exists()
                ):
                    raise ValueError(
                        "invalid input did not refuse before session creation"
                    )
            tty = base / f"tty-{backend}"
            tty.mkdir()
            terminal(executable, tty, backend, env)
            results[backend] = {
                "positional_stdin": True,
                "committed_recovery": True,
                "cold_resume": True,
                "passive_reopen_no_replay": True,
                "pty_diff_attach_stale_refusal": True,
                "unicode_multiline_paste_resize_draft": True,
                "terminal_modes_restored": True,
                "invalid_input_no_session": True,
            }
        run(
            [
                str(executable),
                "update",
                "uninstall",
                "--yes",
                "--root",
                str(base / "app"),
            ],
            env,
            base,
        )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps(
            {
                "schema": 1,
                "source_commit": SOURCE,
                "version": VERSION,
                "platform": target,
                "host": platform.platform(),
                "metadata_sha256": sha(metadata),
                "archive_sha256": sha(archive),
                "bootstrap_sha256": sha(bootstrap),
                "harness_sha256": sha(Path(__file__)),
                "publisher": "enrolled_production_root_unpatched",
                "paid_calls": 0,
                "cases": results,
                "publication_authorized": False,
            },
            sort_keys=True,
        )
        + "\n"
    )
    print(
        f"PASS {target}: both-store installed exec, cold resume and real terminal/diff"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    qualify(args.artifacts.resolve(), args.evidence.resolve())
