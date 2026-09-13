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
from mos_eisley.core.models import digest
from mos_eisley.project_guidance_binding import GuidanceBindingStore
from mos_eisley.project_guidance_conflict_store import (
    GuidanceConflictStore,
    conflict_history_name,
    conflict_name,
)
from mos_eisley.project_guidance_conflicts import (
    ASSESSMENT_BYTES,
    SavedConflictAssessment,
    decode_assessment,
)
from mos_eisley.project_guidance_override_store import GuidanceOverrideStore
from mos_eisley.project_guidance_storage import publish_file


class ConflictTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "private"
        self.bindings = GuidanceBindingStore(self.storage)
        self.overrides = GuidanceOverrideStore(self.storage)
        self.store = GuidanceConflictStore(self.storage)
        self.descriptor = self.base / "guidance.json"
        self.markdown = self.base / "guidance.md"
        self.assessment = self.base / "conflicts.json"
        self.source()
        self.write_assessment()

    def source(self, *, changed: bool = False) -> None:
        texts = (
            "Prefer batches.",
            "Prefer a service." if not changed else "Prefer scheduled work.",
            "Prefer interactive execution.",
        )
        self.markdown.write_text("\n".join(texts) + "\n")
        self.descriptor.write_text(
            json.dumps(
                {
                    "template_id": "engineering",
                    "version": "1.0.0",
                    "source_revision": "local-v1",
                    "content_sha256": digest(self.markdown.read_bytes()),
                    "rules": [
                        {
                            "id": f"ENG{index}",
                            "text": text,
                            "applies_when": "Choosing architecture",
                            "rationale": "Project context",
                            "checks": ["Review the design"],
                        }
                        for index, text in enumerate(texts, 1)
                    ],
                }
            )
        )

    def reference(self, rule: int) -> dict[str, str]:
        return {"template_id": "engineering", "rule_id": f"ENG{rule}"}

    def conflict(
        self,
        identifier: str = "ARCH1",
        *,
        rules: tuple[int, ...] = (1, 2),
        preferred: int | None = None,
    ) -> dict[str, object]:
        return {
            "id": identifier,
            "rules": [self.reference(rule) for rule in rules],
            "explanation": "These defaults recommend different execution models.",
            "preferred_rule": None if preferred is None else self.reference(preferred),
            "resolution_rationale": None
            if preferred is None
            else "Reviewed workload fits this rule.",
        }

    def write_assessment(
        self,
        *,
        preferred: int | None = None,
        conflicts: list[dict[str, object]] | None = None,
    ) -> None:
        self.assessment.write_text(
            json.dumps(
                {
                    "review_rationale": "Reviewed this project's advisory rules.",
                    "conflicts": [self.conflict(preferred=preferred)]
                    if conflicts is None
                    else conflicts,
                }
            )
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
        path = None if clear else self.assessment
        preview = self.store.change_assessment(workspace, path)
        return self.store.change_assessment(
            workspace, path, expected_sha256=cast(str, preview["preview_sha256"])
        )

    def record_path(self) -> Path:
        return self.storage / conflict_name(MappedDirectory.inspect(self.workspace))

    def set_override(self, *, omit: bool = False) -> None:
        path = self.base / "overrides.json"
        path.write_text(
            json.dumps(
                {
                    "overrides": [
                        {
                            "template_id": "engineering",
                            "rule_id": "ENG2",
                            "action": "omit" if omit else "replace",
                            "reason": "Explicit project choice",
                            "replacement": None
                            if omit
                            else {
                                "id": "ENG2",
                                "text": "Prefer the approved service.",
                                "applies_when": "Designing this project",
                                "rationale": "Measured workload",
                                "checks": ["Verify service needs"],
                            },
                        }
                    ]
                }
            )
        )
        preview = self.overrides.change_overrides(self.workspace, path)
        self.overrides.change_overrides(
            self.workspace, path, expected_sha256=cast(str, preview["preview_sha256"])
        )

    def test_preview_is_read_only_and_unresolved_conflicts_remain_visible(self) -> None:
        shown = self.store.show_conflicts(self.workspace, effective=True)
        self.assertEqual(shown["assessment_status"], "unassessed")
        self.assertFalse(shown["advisory_resolution_complete"])
        self.assertFalse(self.storage.exists())
        with self.assertRaises(ValueError):
            self.store.change_assessment(self.workspace, self.assessment)
        self.assertFalse(self.storage.exists())
        self.attach()
        preview = self.store.change_assessment(self.workspace, self.assessment)
        self.assertFalse(preview["applied"])
        self.assertFalse(self.record_path().exists())
        self.assertIn("ARCH1", cast(str, preview["diff"]))
        self.apply()
        shown = self.store.show_conflicts(self.workspace, effective=True)
        self.assertEqual(shown["assessment_status"], "current")
        self.assertEqual(shown["unresolved_conflict_ids"], ["ARCH1"])
        self.assertFalse(shown["advisory_resolution_complete"])
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_resolution_excludes_loser_with_provenance_and_preserves_inputs(
        self,
    ) -> None:
        self.attach()
        original = self.markdown.read_bytes()
        self.apply()
        self.write_assessment(preferred=1)
        self.apply()
        shown = self.store.show_conflicts(self.workspace, effective=True)
        self.assertTrue(shown["advisory_resolution_complete"])
        self.assertFalse(shown["context_materialized"])
        rules = cast(list[dict[str, object]], shown["rules"])
        self.assertTrue(rules[0]["selected"])
        self.assertIsNone(rules[1]["effective_rule"])
        self.assertIsNotNone(rules[1]["pre_conflict_rule"])
        self.assertEqual(rules[1]["excluded_by_conflicts"], ["ARCH1"])
        self.assertTrue(rules[2]["selected"])
        self.assertEqual(self.markdown.read_bytes(), original)

    def test_changed_binding_invalidates_assessment_and_reapproval_shows_both_versions(
        self,
    ) -> None:
        self.attach()
        self.write_assessment(preferred=1)
        self.apply()
        self.source(changed=True)
        self.attach(update=True)
        shown = self.store.show_conflicts(self.workspace, effective=True)
        self.assertEqual(shown["assessment_status"], "stale")
        self.assertFalse(shown["advisory_resolution_complete"])
        self.assertEqual(shown["stale_conflict_ids"], ["ARCH1"])
        self.assertTrue(
            all(
                item["selected"]
                for item in cast(list[dict[str, object]], shown["rules"])
            )
        )
        preview = self.store.change_assessment(self.workspace, self.assessment)
        self.assertIn("Prefer a service", json.dumps(preview["previous_report"]))
        self.assertIn("Prefer scheduled work", json.dumps(preview["proposed_report"]))
        self.apply()
        self.assertEqual(
            self.store.show_conflicts(self.workspace)["assessment_status"], "current"
        )

    def test_lower_priority_unknown_or_omitted_participants_reject(self) -> None:
        self.attach()
        self.set_override()
        self.write_assessment(preferred=1)
        with self.assertRaises(ValueError):
            self.store.change_assessment(self.workspace, self.assessment)
        self.write_assessment(preferred=2)
        self.apply()
        self.set_override(omit=True)
        with self.assertRaises(ValueError):
            self.store.change_assessment(self.workspace, self.assessment)
        self.write_assessment(conflicts=[self.conflict(rules=(1, 9), preferred=1)])
        with self.assertRaises(ValueError):
            self.store.change_assessment(self.workspace, self.assessment)

    def test_overlapping_incompatible_winners_reject(self) -> None:
        self.attach()
        self.write_assessment(
            conflicts=[
                self.conflict(preferred=1),
                self.conflict("ARCH2", rules=(2, 3), preferred=2),
            ]
        )
        with self.assertRaises(ValueError):
            self.store.change_assessment(self.workspace, self.assessment)
        self.assertFalse(self.record_path().exists())
        self.write_assessment(
            conflicts=[
                self.conflict(preferred=1),
                self.conflict("ARCH2", rules=(1, 3), preferred=1),
            ]
        )
        self.apply()
        self.assertTrue(
            self.store.show_conflicts(self.workspace)["advisory_resolution_complete"]
        )

    def test_clear_is_unassessed_and_history_is_never_current(self) -> None:
        self.attach()
        self.write_assessment(preferred=1)
        self.apply()
        saved = SavedConflictAssessment.model_validate_json(
            self.record_path().read_bytes()
        )
        self.apply(clear=True)
        shown = self.store.show_conflicts(self.workspace)
        self.assertEqual(shown["assessment_status"], "unassessed")
        self.assertFalse(shown["advisory_resolution_complete"])
        history = self.store.show_conflicts(
            self.workspace, snapshot_sha256=saved.sha256
        )
        self.assertEqual(history["assessment_status"], "historical")
        self.assertFalse(history["advisory_resolution_complete"])
        self.assertIsNone(history["rules"])
        self.assertTrue(
            cast(dict[str, object], history["pinned_report"])[
                "advisory_resolution_complete"
            ]
        )
        self.write_assessment(conflicts=[])
        self.apply()
        self.assertTrue(
            self.store.show_conflicts(self.workspace)["advisory_resolution_complete"]
        )

    def test_two_projects_users_and_nested_directories_are_isolated(self) -> None:
        self.attach()
        self.apply()
        original = self.record_path().read_bytes()
        saved = SavedConflictAssessment.model_validate_json(original)
        second = self.base / "second"
        second.mkdir()
        self.attach(second)
        self.write_assessment(preferred=1)
        self.apply(workspace=second)
        self.assertEqual(self.record_path().read_bytes(), original)
        nested = self.workspace / "nested"
        nested.mkdir()
        self.assertEqual(
            self.store.show_conflicts(nested)["assessment_status"], "unassessed"
        )
        with self.assertRaises(ValueError):
            self.store.show_conflicts(second, snapshot_sha256=saved.sha256)
        with (
            patch("os.getuid", return_value=os.getuid() + 1),
            self.assertRaises(ValueError),
        ):
            self.store.show_conflicts(self.workspace)

    def test_input_changes_and_concurrent_clear_reapply_invalidate_review(self) -> None:
        self.attach()
        preview = self.store.change_assessment(self.workspace, self.assessment)
        self.write_assessment(preferred=1)
        with self.assertRaises(ValueError):
            self.store.change_assessment(
                self.workspace,
                self.assessment,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.apply()
        preview = self.store.change_assessment(self.workspace, None)
        self.apply(clear=True)
        self.apply()
        with self.assertRaises(ValueError):
            self.store.change_assessment(
                self.workspace,
                None,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )

    def test_invalid_fields_duplicate_keys_ids_and_bounds_reject(self) -> None:
        valid = self.assessment.read_bytes()
        document = json.loads(valid)
        for key in (
            "tools",
            "history",
            "accepted_requirements",
            "mandatory_policy",
            "storage",
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                decode_assessment(json.dumps({**document, key: True}).encode())
        for payload in (
            b"\xff",
            b"[" * 2000,
            b'{"conflicts":[],"conflicts":[]}',
            valid + b" " * ASSESSMENT_BYTES,
        ):
            with self.assertRaises(ValueError):
                decode_assessment(payload)
        document["conflicts"] *= 2
        with self.assertRaises(ValueError):
            decode_assessment(json.dumps(document).encode())
        self.write_assessment(conflicts=[self.conflict(rules=(1, 1))])
        with self.assertRaises(ValueError):
            decode_assessment(self.assessment.read_bytes())
        self.write_assessment(conflicts=[self.conflict(preferred=9)])
        with self.assertRaises(ValueError):
            decode_assessment(self.assessment.read_bytes())

    def test_corrupt_history_permissions_and_unsafe_input_reject(self) -> None:
        self.attach()
        alias = self.base / "alias"
        alias.symlink_to(self.assessment)
        with self.assertRaises((OSError, ValueError)):
            self.store.change_assessment(self.workspace, alias)
        self.apply()
        path = self.record_path()
        payload = path.read_bytes()
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.store.show_conflicts(self.workspace)
        path.chmod(0o600)
        path.write_bytes(payload + b"\n")
        with self.assertRaises(ValueError):
            self.store.show_conflicts(self.workspace)
        path.write_bytes(payload)
        saved = SavedConflictAssessment.model_validate_json(payload)
        (self.storage / conflict_history_name(saved.sha256)).unlink()
        with self.assertRaises(ValueError):
            self.store.show_conflicts(self.workspace)

    def test_mid_publication_change_and_failure_preserve_prior_assessment(self) -> None:
        self.attach()
        self.apply()
        before = self.record_path().read_bytes()
        self.write_assessment(preferred=1)
        preview = self.store.change_assessment(self.workspace, self.assessment)

        def mutate(
            root: int,
            name: str,
            payload: bytes,
            verify: Callable[[], None],
            *,
            immutable: bool = False,
        ) -> None:
            self.write_assessment(preferred=2)
            publish_file(root, name, payload, verify, immutable=immutable)

        with (
            patch(
                "mos_eisley.project_guidance_conflict_store.publish_file",
                side_effect=mutate,
            ),
            self.assertRaises(ValueError),
        ):
            self.store.change_assessment(
                self.workspace,
                self.assessment,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertEqual(self.record_path().read_bytes(), before)
        preview = self.store.change_assessment(self.workspace, self.assessment)
        with (
            patch("os.replace", side_effect=OSError("injected failure")),
            self.assertRaises(OSError),
        ):
            self.store.change_assessment(
                self.workspace,
                self.assessment,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertEqual(self.record_path().read_bytes(), before)
        self.store.change_assessment(
            self.workspace,
            self.assessment,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )

    def test_override_changes_stale_the_assessment_and_clear_survives_stale_guidance(
        self,
    ) -> None:
        self.attach()
        self.write_assessment(preferred=1)
        self.apply()
        self.set_override()
        shown = self.store.show_conflicts(self.workspace, effective=True)
        self.assertEqual(shown["assessment_status"], "stale")
        self.assertFalse(shown["advisory_resolution_complete"])
        self.write_assessment(preferred=2)
        self.apply()
        self.source(changed=True)
        self.attach(update=True)
        self.assertTrue(self.store.show_conflicts(self.workspace)["guidance_stale"])
        with self.assertRaises(ValueError):
            self.overrides.show_overrides(self.workspace, effective=True)
        self.apply(clear=True)
        self.assertEqual(
            self.store.show_conflicts(self.workspace)["assessment_status"], "unassessed"
        )

    def test_exact_input_budget_and_replaced_directory(self) -> None:
        self.attach()
        payload = self.assessment.read_bytes()
        self.assessment.write_bytes(payload + b" " * (ASSESSMENT_BYTES - len(payload)))
        self.apply()
        saved = SavedConflictAssessment.model_validate_json(
            self.record_path().read_bytes()
        )
        self.assertEqual(len(cast(str, saved.source_json).encode()), ASSESSMENT_BYTES)
        self.workspace.rename(self.base / "old-project")
        self.workspace.mkdir()
        with self.assertRaises(ValueError):
            self.store.show_conflicts(self.workspace)

    def cli(
        self, *args: str, command: str = "guidance-conflicts"
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                command,
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

    def test_cli_review_resolve_effective_clear_history_and_override_view(self) -> None:
        self.attach()
        preview = self.cli("set", "--input", str(self.assessment), "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(self.record_path().exists())
        event = json.loads(preview.stdout)
        self.assertEqual(event["type"], "guidance.conflicts")
        applied = self.cli(
            "set",
            "--input",
            str(self.assessment),
            "--apply",
            "--expected-sha256",
            event["preview_sha256"],
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        unresolved = self.cli("effective", "--json", command="guidance-overrides")
        self.assertEqual(unresolved.returncode, 0, unresolved.stderr)
        self.assertEqual(
            json.loads(unresolved.stdout)["unresolved_conflict_ids"], ["ARCH1"]
        )
        self.write_assessment(preferred=1)
        preview = self.cli("set", "--input", str(self.assessment), "--json")
        event = json.loads(preview.stdout)
        applied = self.cli(
            "set",
            "--input",
            str(self.assessment),
            "--apply",
            "--expected-sha256",
            event["preview_sha256"],
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assessment.unlink()
        effective = self.cli("effective", "--json")
        event = json.loads(effective.stdout)
        self.assertTrue(event["advisory_resolution_complete"])
        self.assertFalse(event["context_materialized"])
        history_hash = event["conflict_snapshot_sha256"]
        preview = self.cli("clear", "--json")
        token = json.loads(preview.stdout)["preview_sha256"]
        applied = self.cli("clear", "--apply", "--expected-sha256", token)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        history = self.cli("show", "--snapshot-sha256", history_hash)
        self.assertEqual(history.returncode, 0, history.stderr)
        self.assertEqual(json.loads(history.stdout)["assessment_status"], "historical")
        self.assertEqual(list(self.workspace.iterdir()), [])
        self.assertFalse((self.base / ".mos-eisley-conversations").exists())
        self.assertFalse((self.base / ".mos-eisley-memory").exists())

    def test_cli_invalid_options_and_rejected_input_do_not_leak(self) -> None:
        self.attach()
        for args in (
            ("show", "--apply"),
            ("set",),
            ("clear", "--input", str(self.assessment)),
            ("set", "--input", str(self.assessment), "--apply"),
            ("effective", "--snapshot-sha256", "a" * 64),
        ):
            with self.subTest(args=args):
                self.assertEqual(self.cli(*args).returncode, 2)
        self.assessment.write_text('{"tools":["PRIVATE_CONFLICT_CANARY"]}')
        result = self.cli("set", "--input", str(self.assessment))
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("PRIVATE_CONFLICT_CANARY", result.stdout + result.stderr)
        self.write_assessment()
        self.assessment.write_text(
            self.assessment.read_text()
            .replace("ARCH1", "ARCH2")
            .replace("execution models", "execution models \\u001b[31m")
        )
        result = self.cli("set", "--input", str(self.assessment))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("\x1b", result.stdout)
        self.assertFalse(self.record_path().exists())


if __name__ == "__main__":
    unittest.main()
