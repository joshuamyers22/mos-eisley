import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import patch

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance_binding import GuidanceBindingStore
from mos_eisley.project_guidance_override_store import (
    GuidanceOverrideStore,
    history_name,
    override_name,
)
from mos_eisley.project_guidance_overrides import (
    OVERRIDE_INPUT_BYTES,
    SavedOverrides,
    decode_profile,
)
from mos_eisley.project_guidance_storage import publish_file


class OverrideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "private"
        self.bindings = GuidanceBindingStore(self.storage)
        self.store = GuidanceOverrideStore(self.storage)
        self.descriptor = self.base / "guidance.json"
        self.markdown = self.base / "guidance.md"
        self.profile = self.base / "overrides.json"
        self.source()
        self.write_profile()

    def source(self, text: str = "Use the base convention.") -> None:
        self.markdown.write_text(text + "\nKeep the second rule.\n", encoding="utf-8")
        self.descriptor.write_text(
            json.dumps(
                {
                    "template_id": "engineering",
                    "version": "1.0.0",
                    "source_revision": "local-v1",
                    "content_sha256": digest(self.markdown.read_bytes()),
                    "rules": [
                        self.rule("ENG001", text),
                        self.rule("ENG002", "Keep the second rule."),
                    ],
                }
            )
        )

    def rule(self, rule_id: str, text: str) -> dict[str, object]:
        return {
            "id": rule_id,
            "text": text,
            "applies_when": "Writing code",
            "rationale": "Project needs",
            "checks": ["Review the result"],
        }

    def write_profile(
        self, *, text: str = "Use the project convention.", omit: bool = False
    ) -> None:
        self.profile.write_text(
            json.dumps(
                {
                    "overrides": [
                        {
                            "template_id": "engineering",
                            "rule_id": "ENG001",
                            "action": "omit" if omit else "replace",
                            "reason": "Reviewed project choice",
                            "replacement": None if omit else self.rule("ENG001", text),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def attach(self, workspace: Path | None = None, *, update: bool = False) -> None:
        workspace = self.workspace if workspace is None else workspace
        action = "update" if update else "attach"
        preview = self.bindings.change(
            workspace,
            action,
            "engineering",
            descriptor_path=self.descriptor,
            markdown_path=self.markdown,
        )
        self.bindings.change(
            workspace,
            action,
            "engineering",
            descriptor_path=self.descriptor,
            markdown_path=self.markdown,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )

    def apply(
        self, *, clear: bool = False, workspace: Path | None = None
    ) -> dict[str, object]:
        workspace = self.workspace if workspace is None else workspace
        path = None if clear else self.profile
        preview = self.store.change_overrides(workspace, path)
        return self.store.change_overrides(
            workspace, path, expected_sha256=cast(str, preview["preview_sha256"])
        )

    def record_path(self) -> Path:
        return self.storage / override_name(MappedDirectory.inspect(self.workspace))

    def test_unbound_unknown_or_duplicate_rules_cannot_create_storage(self) -> None:
        self.assertEqual(
            self.store.show_overrides(self.workspace, effective=True)["rules"], []
        )
        with self.assertRaises(ValueError):
            self.store.change_overrides(self.workspace, self.profile)
        self.assertFalse(self.storage.exists())
        self.attach()
        self.profile.write_text(self.profile.read_text().replace("ENG001", "UNKNOWN"))
        with self.assertRaises(ValueError):
            self.store.change_overrides(self.workspace, self.profile)
        self.write_profile()
        profile = json.loads(self.profile.read_bytes())
        profile["overrides"].append(profile["overrides"][0])
        with self.assertRaises(ValueError):
            decode_profile(json.dumps(profile).encode())
        self.assertFalse(self.record_path().exists())

    def test_review_effective_precedence_and_source_files_are_not_modified(
        self,
    ) -> None:
        self.attach()
        originals = {path: path.read_bytes() for path in self.storage.iterdir()}
        preview = self.store.change_overrides(self.workspace, self.profile)
        self.assertIn("Use the project convention", cast(str, preview["diff"]))
        self.assertFalse(preview["applied"])
        self.assertFalse(self.record_path().exists())
        self.assertEqual(
            {path: path.read_bytes() for path in self.storage.iterdir()}, originals
        )
        result = self.store.change_overrides(
            self.workspace,
            self.profile,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )
        self.assertTrue(result["applied"])
        effective = self.store.show_overrides(self.workspace, effective=True)
        rules = cast(list[dict[str, object]], effective["rules"])
        self.assertEqual(
            [item["source"] for item in rules],
            ["approved_project_override", "advisory_default"],
        )
        self.assertIn(
            "Use the project convention", json.dumps(rules[0]["effective_rule"])
        )
        self.assertIn("Use the base convention", json.dumps(rules[0]["base_rule"]))
        self.assertTrue(rules[0]["override_snapshot_sha256"])
        self.assertIsNone(rules[1]["override_snapshot_sha256"])
        for path, payload in originals.items():
            self.assertEqual(path.read_bytes(), payload)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_omit_and_clear_preserve_historical_versions(self) -> None:
        self.attach()
        self.write_profile(omit=True)
        self.apply()
        saved = SavedOverrides.model_validate_json(self.record_path().read_bytes())
        effective = self.store.show_overrides(self.workspace, effective=True)
        first = cast(list[dict[str, object]], effective["rules"])[0]
        self.assertTrue(first["omitted"])
        self.assertIsNone(first["effective_rule"])
        self.apply(clear=True)
        shown = self.store.show_overrides(self.workspace, effective=True)
        self.assertFalse(shown["stale"])
        self.assertEqual(
            cast(list[dict[str, object]], shown["rules"])[0]["source"],
            "advisory_default",
        )
        history = self.store.show_overrides(
            self.workspace, snapshot_sha256=saved.sha256
        )
        self.assertTrue(history["historical_snapshot"])
        self.assertIn("Reviewed project choice", json.dumps(history))
        self.assertEqual(
            SavedOverrides.model_validate_json(
                self.record_path().read_bytes()
            ).revision,
            2,
        )

    def test_independent_projects_users_and_nested_directories(self) -> None:
        self.attach()
        self.apply()
        original = self.record_path().read_bytes()
        second = self.base / "second"
        second.mkdir()
        self.attach(second)
        self.write_profile(text="Different project choice.")
        self.apply(workspace=second)
        self.assertEqual(self.record_path().read_bytes(), original)
        self.assertIn(
            "Different project choice",
            json.dumps(self.store.show_overrides(second, effective=True)),
        )
        nested = self.workspace / "nested"
        nested.mkdir()
        self.assertEqual(self.store.show_overrides(nested, effective=True)["rules"], [])
        saved = SavedOverrides.model_validate_json(original)
        with self.assertRaises(ValueError):
            self.store.show_overrides(second, snapshot_sha256=saved.sha256)
        with (
            patch("os.getuid", return_value=os.getuid() + 1),
            self.assertRaises(ValueError),
        ):
            self.store.show_overrides(self.workspace)

    def test_binding_updates_require_new_review_and_old_profile_can_be_reapproved(
        self,
    ) -> None:
        self.attach()
        self.apply()
        self.source("Changed base convention.")
        self.attach(update=True)
        self.assertTrue(self.store.show_overrides(self.workspace)["stale"])
        with self.assertRaises(ValueError):
            self.store.show_overrides(self.workspace, effective=True)
        preview = self.store.change_overrides(self.workspace, self.profile)
        self.assertTrue(preview["previous_profile_stale"])
        self.assertIn(
            "Use the base convention", json.dumps(preview["previous_effective_rules"])
        )
        self.assertIn("Changed base convention", json.dumps(preview["effective_rules"]))
        self.apply()
        self.assertFalse(self.store.show_overrides(self.workspace)["stale"])
        shown = self.store.show_overrides(self.workspace, effective=True)
        self.assertIn("Changed base convention", json.dumps(shown))
        self.assertIn("Use the project convention", json.dumps(shown))

    def test_detach_and_reattach_do_not_reactivate_old_overrides(self) -> None:
        self.attach()
        self.apply()
        preview = self.bindings.change(self.workspace, "detach", "engineering")
        self.bindings.change(
            self.workspace,
            "detach",
            "engineering",
            expected_sha256=cast(str, preview["preview_sha256"]),
        )
        with self.assertRaises(ValueError):
            self.store.show_overrides(self.workspace, effective=True)
        self.attach()
        with self.assertRaises(ValueError):
            self.store.show_overrides(self.workspace, effective=True)
        self.apply(clear=True)
        self.assertFalse(self.store.show_overrides(self.workspace)["stale"])

    def test_source_and_binding_changes_invalidate_confirmation(self) -> None:
        self.attach()
        preview = self.store.change_overrides(self.workspace, self.profile)
        self.write_profile(text="Changed after review.")
        with self.assertRaises(ValueError):
            self.store.change_overrides(
                self.workspace,
                self.profile,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertFalse(self.record_path().exists())
        preview = self.store.change_overrides(self.workspace, self.profile)
        self.source("New binding.")
        self.attach(update=True)
        with self.assertRaises(ValueError):
            self.store.change_overrides(
                self.workspace,
                self.profile,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.apply()
        preview = self.store.change_overrides(self.workspace, None)
        self.apply(clear=True)
        self.apply()
        with self.assertRaises(ValueError):
            self.store.change_overrides(
                self.workspace,
                None,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )

    def test_structural_authority_duplicate_keys_and_input_bounds(self) -> None:
        valid = self.profile.read_bytes()
        profile = json.loads(valid)
        for key in (
            "tools",
            "execution_authorized",
            "history",
            "accepted_requirements",
            "storage",
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                decode_profile(json.dumps({**profile, key: True}).encode())
        for payload in (
            b'{"overrides":[],"overrides":[]}',
            b"\xff",
            b"[" * 2000,
            valid + b" " * OVERRIDE_INPUT_BYTES,
        ):
            with self.assertRaises(ValueError):
                decode_profile(payload)
        changed = valid.replace(b'"ENG001"', b'"ENG002"', 1)
        with self.assertRaises(ValueError):
            decode_profile(changed)
        profile["overrides"] = profile["overrides"] * 65
        with self.assertRaises(ValueError):
            decode_profile(json.dumps(profile).encode())

    def test_private_files_corruption_history_and_unsafe_input_reject(self) -> None:
        self.attach()
        alias = self.base / "alias.json"
        alias.symlink_to(self.profile)
        with self.assertRaises((OSError, ValueError)):
            self.store.change_overrides(self.workspace, alias)
        self.apply()
        path = self.record_path()
        payload = path.read_bytes()
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.store.show_overrides(self.workspace)
        path.chmod(0o600)
        path.write_bytes(payload + b"\n")
        with self.assertRaises(ValueError):
            self.store.show_overrides(self.workspace)
        path.write_bytes(payload)
        saved = SavedOverrides.model_validate_json(payload)
        history = self.storage / history_name(saved.sha256)
        history.write_bytes(payload.replace(b"Project needs", b"Changed needs"))
        with self.assertRaises(ValueError):
            self.store.show_overrides(self.workspace)
        history.unlink()
        with self.assertRaises(ValueError):
            self.store.show_overrides(self.workspace)

    def test_mid_publication_change_and_failure_preserve_current_profile(self) -> None:
        self.attach()
        self.apply()
        original = self.record_path().read_bytes()
        self.write_profile(text="Reviewed next version.")
        preview = self.store.change_overrides(self.workspace, self.profile)

        def mutate(
            root: int,
            name: str,
            payload: bytes,
            verify: Callable[[], None],
            *,
            immutable: bool = False,
        ) -> None:
            self.write_profile(text="Changed during publication.")
            publish_file(root, name, payload, verify, immutable=immutable)

        with (
            patch(
                "mos_eisley.project_guidance_override_store.publish_file",
                side_effect=mutate,
            ),
            self.assertRaises(ValueError),
        ):
            self.store.change_overrides(
                self.workspace,
                self.profile,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertEqual(self.record_path().read_bytes(), original)
        preview = self.store.change_overrides(self.workspace, self.profile)
        with (
            patch("os.replace", side_effect=OSError("injected failure")),
            self.assertRaises(OSError),
        ):
            self.store.change_overrides(
                self.workspace,
                self.profile,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertEqual(self.record_path().read_bytes(), original)
        self.store.change_overrides(
            self.workspace,
            self.profile,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )

    def test_exact_raw_source_and_owner_directory_metadata_are_pinned(self) -> None:
        self.attach()
        self.apply()
        saved = SavedOverrides.model_validate_json(self.record_path().read_bytes())
        self.assertEqual(saved.source_json, self.profile.read_text())
        self.profile.write_bytes(self.profile.read_bytes() + b"\n")
        self.apply()
        current = SavedOverrides.model_validate_json(self.record_path().read_bytes())
        self.assertNotEqual(saved.sha256, current.sha256)
        invalid = current.model_dump(mode="json")
        invalid["context_materialized"] = True
        with self.assertRaises(ValueError):
            SavedOverrides.model_validate_json(json.dumps(invalid))
        self.workspace.rename(self.base / "old")
        self.workspace.mkdir()
        with self.assertRaises(ValueError):
            self.store.show_overrides(self.workspace)
        self.assertEqual(canonical_bytes(current), self.record_path().read_bytes())

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "guidance-overrides",
                *args,
                "-C",
                str(self.workspace),
                "--guidance-storage",
                str(self.storage),
            ],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "HOME": str(self.base)},
        )

    def test_cli_review_apply_effective_clear_and_history(self) -> None:
        self.attach()
        preview = self.cli("set", "--input", str(self.profile), "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        event = json.loads(preview.stdout)
        self.assertEqual(event["type"], "guidance.overrides")
        self.assertFalse(self.record_path().exists())
        result = self.cli(
            "set",
            "--input",
            str(self.profile),
            "--apply",
            "--expected-sha256",
            event["preview_sha256"],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.profile.unlink()
        shown = self.cli("show", "--json")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        history_hash = json.loads(shown.stdout)["override_snapshot_sha256"]
        effective = self.cli("effective")
        self.assertEqual(effective.returncode, 0, effective.stderr)
        self.assertIn("Use the project convention", effective.stdout)
        self.assertFalse(json.loads(effective.stdout)["context_materialized"])
        preview = self.cli("clear", "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        event = json.loads(preview.stdout)
        result = self.cli(
            "clear", "--apply", "--expected-sha256", event["preview_sha256"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        history = self.cli("show", "--snapshot-sha256", history_hash, "--json")
        self.assertEqual(history.returncode, 0, history.stderr)
        self.assertIn("Use the project convention", history.stdout)
        self.assertEqual(list(self.workspace.iterdir()), [])
        self.assertFalse((self.base / ".mos-eisley-conversations").exists())
        self.assertFalse((self.base / ".mos-eisley-memory").exists())

    def test_cli_rejects_stale_effective_view_and_invalid_mutation_options(
        self,
    ) -> None:
        self.attach()
        self.apply()
        self.source("Updated base.")
        self.attach(update=True)
        result = self.cli("effective", "--json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(json.loads(self.cli("show", "--json").stdout)["stale"])
        for args in (
            ("show", "--apply"),
            ("set",),
            ("clear", "--input", str(self.profile)),
            ("set", "--input", str(self.profile), "--apply"),
            ("effective", "--snapshot-sha256", "a" * 64),
        ):
            with self.subTest(args=args):
                self.assertEqual(self.cli(*args).returncode, 2)

    def test_cli_rejected_input_does_not_leak_and_success_escapes_controls(
        self,
    ) -> None:
        self.attach()
        self.profile.write_text('{"tools":["REJECTED_PRIVATE_OVERRIDE_CANARY"]}')
        result = self.cli("set", "--input", str(self.profile))
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(
            "REJECTED_PRIVATE_OVERRIDE_CANARY", result.stdout + result.stderr
        )
        self.write_profile(text="Literal controls: \x1b[31m")
        result = self.cli("set", "--input", str(self.profile))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("\x1b", result.stdout)
        self.assertFalse(self.record_path().exists())


if __name__ == "__main__":
    unittest.main()
