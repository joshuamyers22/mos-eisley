"""Actual offline processes distinguish terminal results from unfinished output."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError
from test_claude_subscription import encoded, events, request

from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.claude_event_progress import (
    MAX_INSPECTION_BYTES,
    MAX_INSPECTION_EVENTS,
    MAX_LINE_BYTES,
    ClaudeEventObserver,
    ClaudeEventReceipt,
)
from mos_eisley.providers.claude_subscription import (
    ClaudeSubscriptionClient,
    parse_result,
)
from mos_eisley.providers.codex_subscription import NativeProcessError, invoke

SECRET = "private-native-/tmp/secret-token"


def observer() -> ClaudeEventObserver:
    return ClaudeEventObserver(lambda raw: parse_result(raw, request()))


class EventObservationTests(unittest.TestCase):
    def test_fragmented_utf8_and_unterminated_eof_validate_same_response(self) -> None:
        raw = encoded(events("snowman: ☃ " + SECRET))
        state = observer()
        for i in range(0, len(raw), 3):
            state.observe(raw[i : i + 3], i)
        self.assertEqual(state.receipt().result_validation, "not_seen")
        self.assertGreater(state.receipt().pending_line_bytes, 0)
        state.observe(b"", 7000)
        receipt = state.receipt()
        self.assertEqual(receipt.result_validation, "valid")
        self.assertEqual(
            (receipt.init.count, receipt.assistant.count, receipt.result.count),
            (1, 1, 1),
        )
        self.assertEqual(receipt.stdout_eof_ms, 7000)
        self.assertEqual(receipt.pending_line_bytes, 0)
        state.discard_content()
        self.assertNotIn(SECRET, repr(state) + receipt.model_dump_json())
        self.assertLess(len(receipt.model_dump_json()), 2048)

    def test_marker_is_not_a_valid_response_and_trailing_events_remain_invalid(
        self,
    ) -> None:
        state = observer()
        state.observe(b'{"type":"result","subtype":"success"}\n', 1)
        self.assertEqual(state.receipt().result_validation, "invalid")
        state = observer()
        raw = encoded(events()) + b"\n"
        state.observe(raw, 2)
        self.assertEqual(state.receipt().result_validation, "valid")
        state.observe(b'{"type":"user","message":"' + SECRET.encode() + b'"}\n', 3)
        self.assertEqual(state.receipt().events_after_result, 1)
        with self.assertRaises(ProviderError):
            parse_result(raw + b'{"type":"user"}\n', request())

    def test_limits_malformed_input_and_unknown_values_are_visible_without_content(
        self,
    ) -> None:
        state = observer()
        state.observe(b"x" * (MAX_LINE_BYTES + 1) + b"\n", 1)
        state.observe(b"[]\n\xff\n", 2)
        state.observe(
            json.dumps({"type": SECRET, "subtype": SECRET}).encode() + b"\n", 3
        )
        state.observe(encoded(events()) + b"\n", 4)
        value = state.receipt()
        self.assertEqual(value.oversized_lines, 1)
        self.assertEqual(value.malformed_lines, 2)
        self.assertEqual(value.other_events, 1)
        self.assertEqual(value.result_validation, "unavailable")
        self.assertNotIn(SECRET, value.model_dump_json())
        state = observer()
        state.observe(b"{}\n" * (MAX_INSPECTION_EVENTS + 1), 1)
        self.assertTrue(state.receipt().inspection_limited)
        state = observer()
        state.observe(b"x" * (MAX_INSPECTION_BYTES + 1), 1)
        self.assertTrue(state.receipt().inspection_limited)
        state.observe(b'\n{"type":"result"}\n', 2)
        self.assertEqual(state.receipt().result_validation, "unavailable")

    def test_receipt_refuses_extra_fields_strings_and_invalid_numeric_values(
        self,
    ) -> None:
        original = observer().receipt().model_dump()
        for key, value in (
            ("text", SECRET),
            ("other_events", True),
            ("stdout_eof", "yes"),
            ("result_validation", SECRET),
        ):
            changed = {**original, key: value}
            with self.subTest(key=key), self.assertRaises(ValidationError):
                ClaudeEventReceipt.model_validate(changed)


CHILD = """import json,os,subprocess,sys,time
from pathlib import Path
root=Path(__file__).parent
if sys.argv[1:]==['--version']:
 print('2.1.283 (Claude Code)');sys.exit(0)
if sys.argv[1:]==['auth','status']:
 print(json.dumps({'loggedIn':True,'authMethod':'claude.ai','apiProvider':'firstParty'}));sys.exit(0)
sys.stdin.buffer.read()
sys.stdout.buffer.write((root/'events').read_bytes());sys.stdout.buffer.flush()
mode=(root/'mode').read_text()
if mode=='clean':sys.exit(0)
if mode=='closed':os.close(1);os.close(2)
if mode=='descendant':
 subprocess.Popen([sys.executable,'-c',
  'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(20)'])
 os._exit(0)
time.sleep(20)
"""


@unittest.skipUnless(os.name == "posix", "owned native processes require POSIX")
class EventProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_output_limit_marks_incomplete_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = root / "client"
            child.write_text(f"#!{sys.executable}\n" + CHILD)
            child.chmod(0o700)
            (root / "mode").write_text("overflow")
            (root / "events").write_bytes(b"x" * (MAX_INSPECTION_BYTES + 1))
            client = ClaudeSubscriptionClient(
                child,
                root / "attempt",
                allow_data_transfer=True,
                allow_subscription_usage=True,
                timeout=2,
            )
            with self.assertRaises(NativeProcessError) as raised:
                await client.complete(request())
            self.assertEqual(raised.exception.process_reason, "output_limit")
            receipt = ClaudeEventReceipt.model_validate_json(
                (root / "attempt/event-progress.json").read_bytes()
            )
            self.assertTrue(receipt.inspection_limited)

    async def test_real_failure_receipts_distinguish_unfinished_terminal_and_exit_wait(
        self,
    ) -> None:
        for mode in ("unfinished", "result", "closed", "descendant"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                child = root / "client"
                child.write_text(f"#!{sys.executable}\n" + CHILD)
                child.chmod(0o700)
                (root / "mode").write_text(mode)
                records = events(SECRET)
                (root / "events").write_bytes(
                    encoded(records[:-1] if mode == "unfinished" else records) + b"\n"
                )
                client = ClaudeSubscriptionClient(
                    child,
                    root / "attempt",
                    allow_data_transfer=True,
                    allow_subscription_usage=True,
                    timeout=1,
                )
                with self.assertRaises(NativeProcessError):
                    await client.complete(request())
                receipt = ClaudeEventReceipt.model_validate_json(
                    (root / "attempt/event-progress.json").read_bytes()
                )
                failure = json.loads((root / "attempt/failure.json").read_bytes())
                self.assertEqual(
                    receipt.result_validation,
                    "not_seen" if mode == "unfinished" else "valid",
                )
                self.assertEqual(receipt.stdout_eof, mode == "closed")
                self.assertEqual(
                    failure["progress"]["phase"],
                    "exit" if mode == "closed" else "output",
                )
                self.assertEqual(
                    failure["progress"]["leader_exited_before_cleanup"],
                    mode == "descendant",
                )
                self.assertTrue(failure["progress"]["cleanup_completed"])
                self.assertNotIn(
                    SECRET, (root / "attempt/event-progress.json").read_text()
                )
                self.assertFalse((root / "attempt/completion.json").exists())
                with self.assertRaises(FileExistsError):
                    await client.complete(request())

    async def test_success_preserves_final_parser_and_records_eof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = root / "client"
            child.write_text(f"#!{sys.executable}\n" + CHILD)
            child.chmod(0o700)
            (root / "mode").write_text("clean")
            raw = encoded(events(SECRET))
            (root / "events").write_bytes(raw)
            state = observer()
            code, stdout, _ = await invoke(
                child,
                (),
                root,
                data=b"fixture",
                timeout=3,
                stdout_observer=state.observe,
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                parse_result(stdout, request()), parse_result(raw, request())
            )
            self.assertTrue(state.receipt().stdout_eof)
            self.assertEqual(state.receipt().result_validation, "valid")


if __name__ == "__main__":
    unittest.main()
