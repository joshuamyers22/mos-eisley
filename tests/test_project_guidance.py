"""Explicit guidance inspection pins inputs without activating their content."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance import (
    DESCRIPTOR_BYTES,
    MARKDOWN_BYTES,
    GuidanceSnapshot,
    inspect_guidance,
)
from mos_eisley.run.files import read_bounded


def descriptor(markdown: str, text: str = "Use pytest.") -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "advisory_project_guidance",
        "template_id": "python-practices",
        "version": "1.0.0",
        "source_revision": "local-v1",
        "content_sha256": digest(markdown.encode("utf-8")),
        "rules": [
            {
                "id": "ENG-001",
                "kind": "advisory",
                "text": text,
                "applies_when": "Python testing",
                "rationale": "Consistent local checks",
                "checks": ["Run the project's selected test suite."],
            }
        ],
    }


class GuidanceTests(TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.description = self.root / "guidance.json"
        self.markdown = self.root / "guidance.md"
        self.write("# Guidance\n\nUse pytest.\n")

    def write(self, markdown: str, text: str = "Use pytest.") -> None:
        self.markdown.write_text(markdown)
        self.description.write_text(json.dumps(descriptor(markdown, text), indent=2))

    def inspect(self) -> GuidanceSnapshot:
        return inspect_guidance(self.root, self.description, self.markdown)

    def test_complete_exact_snapshot_round_trip_is_unbound_advisory_and_read_only(
        self,
    ) -> None:
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        snapshot = self.inspect()
        self.assertEqual(snapshot.owner_uid, os.getuid())
        self.assertEqual(snapshot.workspace, str(self.root))
        self.assertEqual(snapshot.descriptor_json, self.description.read_text())
        self.assertEqual(snapshot.markdown, self.markdown.read_text())
        self.assertEqual(
            snapshot.descriptor_sha256, digest(self.description.read_bytes())
        )
        self.assertEqual(snapshot.rules[0].character_start, len("# Guidance\n\n"))
        self.assertEqual(snapshot.binding, "unbound")
        self.assertFalse(snapshot.accepted_requirements)
        self.assertFalse(snapshot.execution_authorized)
        self.assertFalse(snapshot.history_loading_authorized)
        restored = GuidanceSnapshot.model_validate_json(canonical_bytes(snapshot))
        self.assertEqual(restored, snapshot)
        self.assertEqual(restored.sha256, snapshot.sha256)
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)

    def test_workspace_and_owner_are_inspector_inputs_not_descriptor_authority(
        self,
    ) -> None:
        first = self.inspect()
        child = self.root / "nested"
        child.mkdir()
        second = inspect_guidance(child, self.description, self.markdown)
        self.assertNotEqual(first.sha256, second.sha256)
        with patch(
            "mos_eisley.project_guidance.os.getuid", return_value=os.getuid() + 1
        ):
            other_owner = self.inspect()
        self.assertNotEqual(first.sha256, other_owner.sha256)
        self.assertEqual(second.workspace, str(child))
        self.assertEqual(list(child.iterdir()), [])

    def test_retained_bytes_locations_and_authority_flags_reject_tampering(
        self,
    ) -> None:
        snapshot = self.inspect()
        for field, value in (
            ("markdown", "Different text"),
            ("descriptor_json", "{}"),
            ("descriptor_sha256", "0" * 64),
            ("binding", "attached"),
            ("accepted_requirements", True),
            ("execution_authorized", True),
            ("history_loading_authorized", True),
            ("workspace", "relative"),
        ):
            data = snapshot.model_dump(mode="json")
            data[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                GuidanceSnapshot.model_validate_json(json.dumps(data))
        data = snapshot.model_dump(mode="json")
        data["rules"][0]["character_start"] += 1
        with self.assertRaises(ValueError):
            GuidanceSnapshot.model_validate_json(json.dumps(data))
        changed = descriptor(snapshot.markdown)
        changed["version"] = "2.0.0"
        data = snapshot.model_dump(mode="json")
        data["descriptor_json"] = json.dumps(changed)
        data["descriptor_sha256"] = digest(data["descriptor_json"].encode())
        with self.assertRaisesRegex(ValueError, "does not match"):
            GuidanceSnapshot.model_validate_json(json.dumps(data))

    def test_declared_requirements_tools_storage_and_history_fields_are_rejected(
        self,
    ) -> None:
        for field, value in (
            ("tools", ["shell"]),
            ("storage", "/tmp/elsewhere"),
            ("accepted_requirements", True),
            ("history_file", "session.json"),
            ("owner_uid", os.getuid()),
            ("workspace", str(self.root)),
            ("kind", "conversation_history"),
            ("source_revision", "../escape"),
        ):
            data = descriptor(self.markdown.read_text())
            data[field] = value
            self.description.write_text(json.dumps(data))
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ValueError, "Invalid advisory"),
            ):
                self.inspect()
        data = descriptor(self.markdown.read_text())
        rules = cast(list[dict[str, object]], data["rules"])
        assert isinstance(rules, list)
        rules[0]["kind"] = "accepted_requirement"
        self.description.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.inspect()

    def test_duplicate_json_keys_invalid_utf8_and_deep_input_fail_without_disclosure(
        self,
    ) -> None:
        for payload in (
            b'{"template_id":"a","template_id":"PRIVATE CANARY"}',
            b'{"rules":[{"id":"a","id":"PRIVATE CANARY"}]}',
            b"\xff",
            b"[]",
            b"null",
            b"NaN",
            b"[" * 1500 + b"0" + b"]" * 1500,
        ):
            self.description.write_bytes(payload)
            with (
                self.subTest(payload=payload[:40]),
                self.assertRaises(ValueError) as raised,
            ):
                self.inspect()
            self.assertNotIn("PRIVATE CANARY", str(raised.exception))

    def test_duplicate_ids_missing_ambiguous_and_overlapping_text_reject(self) -> None:
        for markdown, rule in (
            ("Missing", "Use pytest."),
            ("Use pytest. Use pytest.", "Use pytest."),
            ("aaaa", "aa"),
        ):
            self.write(markdown, rule)
            with self.subTest(markdown=markdown), self.assertRaises(ValueError):
                self.inspect()
        self.write("Use pytest.")
        data = descriptor(self.markdown.read_text())
        rules = cast(list[dict[str, object]], data["rules"])
        assert isinstance(rules, list)
        rules.append(rules[0])
        self.description.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.inspect()

    def test_rule_limits_empty_checks_and_unchosen_versions_reject(self) -> None:
        invalid: tuple[tuple[str, object], ...] = (
            ("rules", []),
            ("version", "latest"),
            ("schema_version", 2),
        )
        for field, value in invalid:
            data = descriptor(self.markdown.read_text())
            data[field] = value
            self.description.write_text(json.dumps(data))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.inspect()
        for field, value in (
            ("text", " "),
            ("checks", []),
            ("checks", ["x"] * 9),
            ("rationale", "x" * 1001),
        ):
            data = descriptor(self.markdown.read_text())
            rules = cast(list[dict[str, object]], data["rules"])
            assert isinstance(rules, list)
            rules[0][field] = value
            self.description.write_text(json.dumps(data))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.inspect()

    def test_utf8_byte_bounds_and_descriptor_limits_are_enforced_before_snapshot(
        self,
    ) -> None:
        text = "Use pytest."
        self.write("x" * (MARKDOWN_BYTES - len(text)) + text)
        self.assertEqual(len(self.inspect().markdown.encode()), MARKDOWN_BYTES)
        self.write("é" * (MARKDOWN_BYTES // 2) + text)
        with self.assertRaisesRegex(ValueError, "byte limit"):
            self.inspect()
        self.write(text)
        self.description.write_bytes(
            self.description.read_bytes() + b" " * DESCRIPTOR_BYTES
        )
        with self.assertRaisesRegex(ValueError, "byte limit"):
            self.inspect()

    def test_changed_content_hash_and_non_utf8_markdown_reject(self) -> None:
        self.markdown.write_text("Use pytest. Changed")
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.inspect()
        self.markdown.write_bytes(b"Use pytest.\xff")
        with self.assertRaises(ValueError):
            self.inspect()

    def test_raw_descriptor_formatting_changes_snapshot_identity(self) -> None:
        first = self.inspect()
        self.description.write_bytes(self.description.read_bytes() + b"\n ")
        second = self.inspect()
        self.assertEqual(first.descriptor, second.descriptor)
        self.assertNotEqual(first.descriptor_sha256, second.descriptor_sha256)
        self.assertNotEqual(first.sha256, second.sha256)

    def test_content_changed_between_input_reads_rejects(self) -> None:
        calls = 0

        def changed(path: Path, limit: int) -> bytes:
            nonlocal calls
            calls += 1
            if calls == 2:
                self.markdown.write_text("Use pytest. Concurrent update")
            return read_bounded(path, limit)

        with (
            patch("mos_eisley.project_guidance.read_bounded", side_effect=changed),
            self.assertRaisesRegex(ValueError, "does not match"),
        ):
            self.inspect()

    def test_more_than_64_rule_ids_reject(self) -> None:
        data = descriptor(self.markdown.read_text())
        rules = cast(list[dict[str, object]], data["rules"])
        data["rules"] = [
            {**rules[0], "id": f"ENG-{number:03d}"} for number in range(65)
        ]
        self.description.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.inspect()

    def test_cli_rejection_does_not_echo_invalid_descriptor_content(self) -> None:
        self.description.write_text('{"tools":"PRIVATE CANARY"}')
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "guidance-inspect",
                "--descriptor",
                str(self.description),
                "--markdown",
                str(self.markdown),
                "-C",
                str(self.root),
                "--json",
            ],
            env={**os.environ, "HOME": str(self.root)},
            text=True,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("PRIVATE CANARY", result.stderr)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_links_are_data_and_only_two_explicit_files_are_read(self) -> None:
        secret = self.root / "private-session.json"
        secret.write_text("PRIVATE SESSION CANARY")
        self.write(
            "Use pytest.\n[history](private-session.json)\n[remote](https://example.invalid/)"
        )
        with patch(
            "mos_eisley.project_guidance.read_bounded", wraps=read_bounded
        ) as reads:
            snapshot = self.inspect()
        self.assertEqual(reads.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in reads.call_args_list],
            [self.description, self.markdown],
        )
        self.assertNotIn("PRIVATE SESSION CANARY", snapshot.model_dump_json())
        self.assertFalse(snapshot.history_loading_authorized)

    def test_final_symlinks_special_files_and_invalid_workspaces_reject(self) -> None:
        for path in (self.description, self.markdown):
            content = path.read_bytes()
            original = self.root / "original"
            original.write_bytes(content)
            path.unlink()
            path.symlink_to(original)
            with self.subTest(path=path.name), self.assertRaises((OSError, ValueError)):
                self.inspect()
            path.unlink()
            path.write_bytes(content)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            inspect_guidance(self.root, fifo, self.markdown)
        with self.assertRaises(ValueError):
            inspect_guidance(self.description, self.description, self.markdown)
        missing = self.root / "missing"
        with self.assertRaises(OSError):
            inspect_guidance(missing, self.description, self.markdown)
        self.assertFalse(missing.exists())

    def test_cli_json_and_plain_rendering_do_not_create_sessions_or_activate_guidance(
        self,
    ) -> None:
        self.write("# Guidance\nUse pytest.\n\x1b[31m Untrusted text")
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        for json_mode in (False, True):
            with self.subTest(json=json_mode):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "guidance-inspect",
                        "--descriptor",
                        str(self.description),
                        "--markdown",
                        str(self.markdown),
                        "-C",
                        str(self.root),
                        *(["--json"] if json_mode else []),
                    ],
                    env={**os.environ, "HOME": str(self.root)},
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("\x1b", result.stdout)
                if json_mode:
                    event = json.loads(result.stdout)
                    self.assertEqual(event["type"], "guidance.inspected")
                    snapshot = GuidanceSnapshot.model_validate_json(
                        json.dumps(event["snapshot"])
                    )
                    self.assertEqual(event["snapshot_sha256"], snapshot.sha256)
                else:
                    self.assertIn("inspected, unbound", result.stdout)
                    self.assertIn("ENG-001 (advisory)", result.stdout)
                    self.assertIn("Complete Markdown", result.stdout)
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)
