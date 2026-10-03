"""Recorded Mos in a private real tmux server, also run from the installed wheel."""

import json
import os
import pty
import select
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import mos_eisley
from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.conversation_store import ConversationStore


class TmuxCompatibilityTests(TestCase):
    def setUp(self) -> None:
        executable = shutil.which("tmux")
        if executable is None:
            if os.environ.get("MOS_REQUIRE_TMUX") == "1":
                self.fail("MOS_REQUIRE_TMUX=1 requires tmux on PATH")
            self.skipTest("optional tmux compatibility requires tmux on PATH")
        assert executable is not None
        self.executable = executable
        temporary = TemporaryDirectory(prefix="mos-tmux-", dir="/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.socket = self.root / "socket"
        self.storage = self.root / "sessions"
        self.cassette = self.root / "cassette.json"
        self.cassette.write_bytes(canonical_bytes(demo_cassette()))
        assert mos_eisley.__file__ is not None
        self.environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.root),
            "TERM": "xterm-256color",
            "LANG": "en_US.UTF-8",
            "PYTHONPATH": str(Path(mos_eisley.__file__).resolve().parent.parent),
        }
        self.clients: list[tuple[subprocess.Popen[bytes], int, int]] = []
        self.addCleanup(self.stop_server)
        self.addCleanup(self.close_clients)

    def tmux(self, *arguments: str, check: bool = True) -> str:
        result = subprocess.run(
            [self.executable, "-S", str(self.socket), "-f", "/dev/null", *arguments],
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=5,
            check=check,
        )
        return result.stdout.strip()

    def stop_server(self) -> None:
        self.tmux("kill-server", check=False)

    def close_clients(self) -> None:
        for process, master, slave in self.clients:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            os.close(master)
            os.close(slave)

    def drain(self) -> None:
        for _, master, _ in self.clients:
            while select.select([master], [], [], 0)[0]:
                try:
                    if not os.read(master, 65536):
                        break
                except OSError:
                    break

    def wait_for(self, predicate: Callable[[], bool]) -> None:
        deadline = time.monotonic() + 10
        while not predicate():
            self.drain()
            if time.monotonic() >= deadline:
                self.fail("tmux compatibility condition timed out")
            time.sleep(0.02)
        self.drain()

    def launch(self, *arguments: str) -> None:
        command = [
            sys.executable,
            "-m",
            "mos_eisley.cli",
            *arguments,
            "--storage",
            str(self.storage),
            "-C",
            str(self.root),
            "--no-memory",
        ]
        self.pane = self.tmux(
            "new-session",
            "-d",
            "-s",
            "mos",
            "-x",
            "100",
            "-y",
            "35",
            "-c",
            str(self.root),
            "-P",
            "-F",
            "#{pane_id}",
            "exec " + shlex.join(command),
        )
        self.assertTrue(self.pane.startswith("%"), "tmux server did not create a pane")
        self.tmux("set-window-option", "-t", self.pane, "remain-on-exit", "on")
        self.wait_for(lambda: "Message" in self.screen())

    def screen(self) -> str:
        return self.tmux("capture-pane", "-p", "-t", self.pane)

    def key(self, *keys: str) -> None:
        self.tmux("send-keys", "-t", self.pane, *keys)

    def text(self, text: str) -> None:
        self.tmux("send-keys", "-t", self.pane, "-l", "--", text)

    def state(self) -> ConversationState:
        paths = list(self.storage.glob("*.json"))
        self.assertEqual(len(paths), 1)
        return ConversationState.model_validate_json(
            json.dumps(json.loads(paths[0].read_bytes())["state"])
        )

    def attach(self) -> subprocess.Popen[bytes]:
        master, slave = pty.openpty()
        process = subprocess.Popen(
            [self.executable, "-S", str(self.socket), "attach-session", "-t", "mos"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=self.environment,
            start_new_session=True,
        )
        self.clients.append((process, master, slave))
        self.wait_for(lambda: self.tmux("list-clients", "-F", "#{client_pid}") != "")
        return process

    def quit(self) -> None:
        self.key("C-d")
        self.wait_for(
            lambda: (
                self.tmux("display-message", "-p", "-t", self.pane, "#{pane_dead}")
                == "1"
            )
        )
        # tmux may close the pane PTY before it reaps the child and publishes
        # pane_dead_status (observed with tmux 3.4 on Ubuntu CI).
        self.wait_for(
            lambda: (
                self.tmux(
                    "display-message", "-p", "-t", self.pane, "#{pane_dead_status}"
                )
                != ""
            )
        )
        self.assertEqual(
            self.tmux("display-message", "-p", "-t", self.pane, "#{pane_dead_status}"),
            "0",
        )
        self.assertIn("conversation.saved", self.screen())
        self.assertEqual(
            self.tmux("display-message", "-p", "-t", self.pane, "#{alternate_on}"),
            "0",
        )

    def test_detach_reattach_resize_preserve_draft_and_process(self) -> None:
        self.launch("chat", "--cassette", str(self.cassette))
        client = self.attach()
        identity = self.tmux("display-message", "-p", "-t", self.pane, "#{pane_pid}")
        draft = "unsent café 界"
        self.text(draft)
        self.wait_for(lambda: draft in self.screen())
        self.tmux("detach-client", "-s", "mos")
        self.wait_for(lambda: client.poll() is not None)
        self.assertEqual(client.returncode, 0)
        self.assertFalse(self.state().entries)
        self.attach()
        self.tmux("set-window-option", "-t", self.pane, "window-size", "manual")
        self.tmux("resize-window", "-t", self.pane, "-x", "80", "-y", "28")
        sibling = self.tmux(
            "split-window", "-d", "-t", self.pane, "-P", "-F", "#{pane_id}", "sleep 60"
        )
        self.tmux("resize-pane", "-Z", "-t", self.pane)
        self.wait_for(lambda: draft in self.screen())
        self.tmux("resize-pane", "-Z", "-t", self.pane)
        self.tmux("kill-pane", "-t", sibling)
        self.assertEqual(
            self.tmux("display-message", "-p", "-t", self.pane, "#{pane_pid}"), identity
        )
        self.assertEqual(self.state().workspace, str(self.root))
        self.assertFalse(self.state().entries)
        self.key("C-u")
        self.text(DEMO_PROMPTS[0])
        self.key("Enter")
        self.wait_for(
            lambda: bool(self.state().entries and self.state().entries[0].answer)
        )
        self.assertEqual(self.state().entries[0].text, DEMO_PROMPTS[0])
        self.assertEqual(self.state().entries[0].answer, "The fixture boundary is ten.")
        self.quit()

    def test_paste_is_literal_and_stop_keeps_conversation_usable(self) -> None:
        self.launch("chat", "--cassette", str(self.cassette))
        # Deliver bracketed-paste framing through the pane's actual PTY input.
        self.text("\x1b[200~/quit\nUnicode café 界\x1b[201~")
        self.wait_for(lambda: "Unicode café 界" in self.screen())
        self.assertFalse(self.state().entries)
        self.key("C-u")
        self.text("\x1b[200~/quit\x1b[201~")
        self.key("Enter")
        self.wait_for(lambda: len(self.state().entries) == 1)
        self.assertEqual(self.state().entries[0].text, "/quit")
        self.assertEqual(
            self.tmux("display-message", "-p", "-t", self.pane, "#{pane_dead}"), "0"
        )
        self.key("C-c")
        self.text("/directory")
        self.key("Enter")
        self.wait_for(lambda: str(self.root) in self.screen())
        self.assertEqual(len(self.state().entries), 1)
        self.quit()

    def test_detached_resume_preserves_queue_and_rejects_second_writer(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(self.root, cassette)
        with ConversationStore(self.storage, state.session_id, self.root) as store:
            store.save(state)
            controller = ConversationController(state, cassette, store.save)
            controller.submit(DEMO_PROMPTS[0])
        self.launch("resume", state.session_id)
        client = self.attach()
        self.tmux("detach-client", "-s", "mos")
        self.wait_for(lambda: client.poll() is not None)
        before = self.state()
        self.assertEqual(before.entries[0].status, "queued")
        duplicate = subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "resume",
                state.session_id,
                "--storage",
                str(self.storage),
                "-C",
                str(self.root),
                "--plain",
            ],
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(duplicate.returncode, 2)
        self.assertEqual(self.state(), before)
        self.attach()
        self.text("/continue")
        self.key("Enter")
        self.wait_for(lambda: bool(self.state().entries[0].answer))
        self.assertEqual(self.state().entries[0].answer, "The fixture boundary is ten.")
        self.quit()

    def test_server_loss_releases_session_for_explicit_inspection(self) -> None:
        self.launch("chat", "--cassette", str(self.cassette))
        client = self.attach()
        self.text(DEMO_PROMPTS[0])
        self.key("Enter")
        self.wait_for(
            lambda: bool(self.state().entries and self.state().entries[0].answer)
        )
        saved = self.state()
        self.text("unsaved draft")
        self.wait_for(lambda: "unsaved draft" in self.screen())
        self.stop_server()
        self.wait_for(lambda: client.poll() is not None)
        self.assertEqual(self.state(), saved)

        def unlocked() -> bool:
            try:
                with ConversationStore(
                    self.storage, saved.session_id, self.root, create=False
                ):
                    return True
            except BlockingIOError:
                return False

        self.wait_for(unlocked)
        self.assertEqual(self.state(), saved)
