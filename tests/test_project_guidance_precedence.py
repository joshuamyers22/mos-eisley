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
from mos_eisley.project_guidance_conflict_store import GuidanceConflictStore
from mos_eisley.project_guidance_override_store import GuidanceOverrideStore
from mos_eisley.project_guidance_precedence import decode_project_assessment
from mos_eisley.project_guidance_precedence_store import (
    ProjectAssessmentStore,
    project_assessment_history_name,
    project_assessment_name,
)
from mos_eisley.project_guidance_storage import publish_file
from mos_eisley.project_requirement_store import RequirementStore


class PrecedenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "private"
        self.store = ProjectAssessmentStore(self.storage)
        self.requirements = RequirementStore(self.storage)
        self.bindings = GuidanceBindingStore(self.storage)
        self.overrides = GuidanceOverrideStore(self.storage)
        self.input = self.base / "assessment.json"
        self.selection = self.base / "requirements.json"
        self.brief = self.base / "brief.md"
        self.brief.write_text("Use batch execution.\nRetain data locally.\n")
        self.selection_data: dict[str, object] = {
            "review_rationale": "Accepted the project brief.",
            "sources": [
                {
                    "id": "brief",
                    "kind": "brief",
                    "content_sha256": digest(self.brief.read_bytes()),
                }
            ],
            "requirements": [
                {
                    "id": f"REQ{i}",
                    "source_id": "brief",
                    "text": text,
                    "applies_when": "Planning implementation",
                    "rationale": "Project requirement",
                    "checks": ["Review the implementation"],
                }
                for i, text in enumerate(self.brief.read_text().splitlines(), 1)
            ],
        }
        self.selection.write_text(json.dumps(self.selection_data))
        self.markdown = self.base / "guidance.md"
        self.markdown.write_text("Prefer a service.\nPrefer interactive work.\n")
        self.descriptor = self.base / "guidance.json"
        self.descriptor.write_text(
            json.dumps(
                {
                    "template_id": "engineering",
                    "version": "1.0.0",
                    "source_revision": "v1",
                    "content_sha256": digest(self.markdown.read_bytes()),
                    "rules": [
                        {
                            "id": f"ENG{i}",
                            "text": text,
                            "applies_when": "Planning implementation",
                            "rationale": "Advisory preference",
                            "checks": ["Review the design"],
                        }
                        for i, text in enumerate(
                            self.markdown.read_text().splitlines(), 1
                        )
                    ],
                }
            )
        )
        self.write_assessment([])

    def reference(self, identifier: str) -> dict[str, object]:
        requirement = identifier.startswith("REQ")
        return {
            "kind": "requirement" if requirement else "advisory",
            "rule_id": identifier,
            "template_id": None if requirement else "engineering",
        }

    def conflict(
        self,
        rules: tuple[str, ...],
        preferred: str | None = None,
        identifier: str = "C1",
    ) -> dict[str, object]:
        return {
            "id": identifier,
            "rules": [self.reference(rule) for rule in rules],
            "explanation": "These choices conflict for this project.",
            "preferred_rule": None if preferred is None else self.reference(preferred),
            "resolution_rationale": None
            if preferred is None
            else "Reviewed project precedence.",
        }

    def write_assessment(self, conflicts: list[dict[str, object]]) -> None:
        self.input.write_text(
            json.dumps(
                {
                    "review_rationale": "Reviewed requirements and advisory guidance.",
                    "conflicts": conflicts,
                }
            )
        )

    def accept(self, *, clear: bool = False) -> None:
        path = None if clear else self.selection
        sources = () if clear else (self.brief,)
        preview = self.requirements.change(self.workspace, path, sources)
        self.requirements.change(
            self.workspace,
            path,
            sources,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )

    def attach(self, *, detach: bool = False) -> None:
        action = "detach" if detach else "attach"
        descriptor = None if detach else self.descriptor
        markdown = None if detach else self.markdown
        preview = self.bindings.change(
            self.workspace,
            action,
            "engineering",
            descriptor_path=descriptor,
            markdown_path=markdown,
        )
        self.bindings.change(
            self.workspace,
            action,
            "engineering",
            descriptor_path=descriptor,
            markdown_path=markdown,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )

    def apply(self, *, clear: bool = False) -> dict[str, object]:
        path = None if clear else self.input
        preview = self.store.change_assessment(self.workspace, path)
        return self.store.change_assessment(
            self.workspace, path, expected_sha256=cast(str, preview["preview_sha256"])
        )

    def test_empty_project_read_only_and_requirements_only_assessment(self) -> None:
        shown = self.store.show_assessment(self.workspace, effective=True)
        self.assertEqual(shown["assessment_status"], "unassessed")
        self.assertFalse(shown["project_resolution_complete"])
        self.assertEqual(shown["rules"], [])
        self.assertFalse(self.storage.exists())
        with self.assertRaises(ValueError):
            self.apply()
        self.accept()
        preview = self.store.change_assessment(self.workspace, self.input)
        self.assertFalse(preview["applied"])
        self.assertEqual(
            self.store.show_assessment(self.workspace)["assessment_status"],
            "unassessed",
        )
        self.apply()
        shown = self.store.show_assessment(self.workspace, effective=True)
        self.assertTrue(shown["project_resolution_complete"])
        self.assertFalse(shown["trusted_policy_evaluated"])
        self.assertFalse(shown["context_materialized"])
        self.assertEqual(len(cast(list[object], shown["rules"])), 2)

    def test_requirement_precedence_retains_loser_and_source_provenance(self) -> None:
        self.accept()
        self.attach()
        self.write_assessment([self.conflict(("REQ1", "ENG1"), "REQ1")])
        self.apply()
        shown = self.store.show_assessment(self.workspace, effective=True)
        self.assertTrue(shown["project_resolution_complete"])
        rules = {
            rule["rule_id"]: rule
            for rule in cast(list[dict[str, object]], shown["rules"])
        }
        self.assertFalse(rules["ENG1"]["selected"])
        self.assertIsNotNone(rules["ENG1"]["pre_conflict_rule"])
        self.assertEqual(rules["ENG1"]["excluded_by_conflicts"], ["C1"])
        self.assertTrue(rules["REQ1"]["selected"])
        provenance = cast(dict[str, object], rules["REQ1"]["provenance"])
        self.assertEqual(provenance["character_start"], 0)
        self.assertEqual(provenance["character_end"], len("Use batch execution."))
        self.assertEqual(
            rules["REQ1"]["requirement_snapshot_sha256"],
            shown["requirement_snapshot_sha256"],
        )
        self.assertEqual(shown["scope"], "accepted_requirements_and_advisory")

    def test_cannot_prefer_advisory_over_requirement_or_drop_accepted_contradiction(
        self,
    ) -> None:
        self.accept()
        self.attach()
        for conflict in (
            self.conflict(("REQ1", "ENG1"), "ENG1"),
            self.conflict(("REQ1", "REQ2"), "REQ1"),
        ):
            self.write_assessment([conflict])
            with self.assertRaises(ValueError):
                self.apply()
        self.write_assessment([self.conflict(("REQ1", "REQ2"))])
        self.apply()
        shown = self.store.show_assessment(self.workspace, effective=True)
        self.assertEqual(shown["unresolved_conflict_ids"], ["C1"])
        self.assertFalse(shown["project_resolution_complete"])

    def test_requirement_replace_clear_reaccept_invalidates_assessment_and_review(
        self,
    ) -> None:
        self.accept()
        self.attach()
        self.write_assessment([self.conflict(("REQ1", "ENG1"), "REQ1")])
        preview = self.store.change_assessment(self.workspace, self.input)
        self.apply()
        self.selection_data["review_rationale"] = "Re-reviewed requirements."
        self.selection.write_text(json.dumps(self.selection_data))
        self.accept()
        shown = self.store.show_assessment(self.workspace, effective=True)
        self.assertEqual(shown["assessment_status"], "stale")
        self.assertFalse(shown["project_resolution_complete"])
        self.assertEqual(shown["stale_conflict_ids"], ["C1"])
        self.assertTrue(
            all(
                rule["selected"]
                for rule in cast(list[dict[str, object]], shown["rules"])
            )
        )
        with self.assertRaises(ValueError):
            self.store.change_assessment(
                self.workspace,
                self.input,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.apply()
        self.accept(clear=True)
        self.assertEqual(
            self.store.show_assessment(self.workspace)["assessment_status"], "stale"
        )
        self.accept()
        self.assertEqual(
            self.store.show_assessment(self.workspace)["assessment_status"], "stale"
        )

    def test_advisory_assessment_does_not_establish_combined_completion(self) -> None:
        self.attach()
        legacy = GuidanceConflictStore(self.storage)
        preview = legacy.change_assessment(self.workspace, self.input)
        legacy.change_assessment(
            self.workspace,
            self.input,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )
        self.assertTrue(
            legacy.show_conflicts(self.workspace)["advisory_resolution_complete"]
        )
        self.assertFalse(
            self.store.show_assessment(self.workspace)["project_resolution_complete"]
        )
        self.accept()
        self.apply()
        self.assertTrue(
            self.store.show_assessment(self.workspace)["project_resolution_complete"]
        )

    def test_override_priority_omissions_and_stale_bindings(self) -> None:
        self.accept()
        self.attach()
        profile = self.base / "overrides.json"
        descriptor = json.loads(self.descriptor.read_text())
        profile.write_text(
            json.dumps(
                {
                    "overrides": [
                        {
                            "template_id": "engineering",
                            "rule_id": "ENG1",
                            "action": "replace",
                            "reason": "Project workload",
                            "replacement": descriptor["rules"][0],
                        }
                    ]
                }
            )
        )
        preview = self.overrides.change_overrides(self.workspace, profile)
        self.overrides.change_overrides(
            self.workspace,
            profile,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )
        self.write_assessment([self.conflict(("ENG1", "ENG2"), "ENG2")])
        with self.assertRaises(ValueError):
            self.apply()
        self.write_assessment([self.conflict(("REQ1", "ENG1"), "REQ1")])
        self.apply()
        self.attach(detach=True)
        with self.assertRaises(ValueError):
            self.store.show_assessment(self.workspace, effective=True)
        self.assertTrue(self.store.show_assessment(self.workspace)["guidance_stale"])
        self.apply(clear=True)

    def test_history_pins_prior_requirements_and_clear_stays_unassessed(self) -> None:
        self.accept()
        self.write_assessment([self.conflict(("REQ1", "REQ2"))])
        self.apply()
        sha = cast(
            str, self.store.show_assessment(self.workspace)["conflict_snapshot_sha256"]
        )
        self.accept(clear=True)
        historical = self.store.show_assessment(self.workspace, snapshot_sha256=sha)
        self.assertEqual(historical["assessment_status"], "historical")
        self.assertFalse(historical["project_resolution_complete"])
        self.assertIsNone(historical["rules"])
        self.assertEqual(
            cast(dict[str, object], historical["pinned_report"])[
                "unresolved_conflict_ids"
            ],
            ["C1"],
        )
        self.apply(clear=True)
        self.assertEqual(
            self.store.show_assessment(self.workspace)["assessment_status"],
            "unassessed",
        )

    def test_unknown_omitted_and_inconsistent_participants_reject(self) -> None:
        self.accept()
        self.attach()
        self.write_assessment([self.conflict(("REQ99", "ENG1"), "REQ99")])
        with self.assertRaises(ValueError):
            self.apply()
        self.write_assessment(
            [
                self.conflict(("REQ1", "ENG1"), "REQ1"),
                self.conflict(("ENG1", "ENG2"), "ENG1", "C2"),
            ]
        )
        with self.assertRaises(ValueError):
            self.apply()
        profile = self.base / "omit.json"
        profile.write_text(
            json.dumps(
                {
                    "overrides": [
                        {
                            "template_id": "engineering",
                            "rule_id": "ENG1",
                            "action": "omit",
                            "reason": "Not applicable",
                        }
                    ]
                }
            )
        )
        preview = self.overrides.change_overrides(self.workspace, profile)
        self.overrides.change_overrides(
            self.workspace,
            profile,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )
        self.write_assessment([self.conflict(("REQ1", "ENG1"), "REQ1")])
        with self.assertRaises(ValueError):
            self.apply()

    def test_owner_project_and_nested_history_isolation(self) -> None:
        self.accept()
        self.apply()
        sha = cast(
            str, self.store.show_assessment(self.workspace)["conflict_snapshot_sha256"]
        )
        for path in (self.base / "another", self.workspace / "nested"):
            path.mkdir()
            self.assertEqual(
                self.store.show_assessment(path)["assessment_status"], "unassessed"
            )
            with self.assertRaises(ValueError):
                self.store.show_assessment(path, snapshot_sha256=sha)
        with (
            patch(
                "mos_eisley.project_guidance_precedence_store.os.getuid",
                return_value=os.getuid() + 1,
            ),
            self.assertRaises((ValueError, PermissionError)),
        ):
            self.store.show_assessment(self.workspace)

    def test_stale_input_and_mid_publication_requirement_mutation_reject(self) -> None:
        self.accept()
        preview = self.store.change_assessment(self.workspace, self.input)
        self.input.write_text(self.input.read_text() + " ")
        with self.assertRaises(ValueError):
            self.store.change_assessment(
                self.workspace,
                self.input,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        preview = self.store.change_assessment(self.workspace, self.input)
        requirement_path = next(self.storage.glob("requirements-project-*.json"))
        original = requirement_path.read_bytes()

        def mutate(
            root: int,
            name: str,
            payload: bytes,
            verify: Callable[[], None],
            *,
            immutable: bool = False,
        ) -> None:
            requirement_path.write_bytes(original + b" ")
            publish_file(root, name, payload, verify, immutable=immutable)

        with (
            patch(
                "mos_eisley.project_guidance_precedence_store.publish_file",
                side_effect=mutate,
            ),
            self.assertRaises(ValueError),
        ):
            self.store.change_assessment(
                self.workspace,
                self.input,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertFalse(
            (
                self.storage
                / project_assessment_name(MappedDirectory.inspect(self.workspace))
            ).exists()
        )

    def test_corruption_history_and_unsafe_input_fail_closed(self) -> None:
        self.accept()
        self.apply()
        sha = cast(
            str, self.store.show_assessment(self.workspace)["conflict_snapshot_sha256"]
        )
        history = self.storage / project_assessment_history_name(sha)
        history.write_bytes(history.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.store.show_assessment(self.workspace)
        with self.assertRaises(ValueError):
            self.store.show_assessment(self.workspace, snapshot_sha256="../../escape")
        link = self.base / "link.json"
        link.symlink_to(self.input)
        with self.assertRaises(OSError):
            self.store.change_assessment(self.workspace, link)

    def test_schema_rejects_authority_unqualified_duplicate_and_oversized_input(
        self,
    ) -> None:
        valid: dict[str, object] = {"review_rationale": "Reviewed", "conflicts": []}
        raw = json.dumps(valid).encode()
        self.assertEqual(
            decode_project_assessment(raw + b" " * (65536 - len(raw))).conflicts, ()
        )
        for raw in (
            json.dumps({**valid, "trusted_policy_evaluated": True}).encode(),
            b'{"review_rationale":"one","review_rationale":"two","conflicts":[]}',
            b" " * 65537,
        ):
            with self.assertRaises(ValueError):
                decode_project_assessment(raw)
        conflict = self.conflict(("REQ1", "ENG1"))
        rules = cast(list[dict[str, object]], conflict["rules"])
        rules[1]["template_id"] = None
        self.write_assessment([conflict])
        with self.assertRaises(ValueError):
            decode_project_assessment(self.input.read_bytes())
        self.write_assessment([self.conflict(("REQ1", "REQ1"))])
        with self.assertRaises(ValueError):
            decode_project_assessment(self.input.read_bytes())

    def test_override_change_invalidates_combined_assessment(self) -> None:
        self.accept()
        self.attach()
        self.apply()
        profile = self.base / "override.json"
        profile.write_text(
            json.dumps(
                {
                    "overrides": [
                        {
                            "template_id": "engineering",
                            "rule_id": "ENG1",
                            "action": "omit",
                            "reason": "This preference is irrelevant to the project.",
                        }
                    ]
                }
            )
        )
        preview = self.overrides.change_overrides(self.workspace, profile)
        self.overrides.change_overrides(
            self.workspace,
            profile,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )
        shown = self.store.show_assessment(self.workspace, effective=True)
        self.assertEqual(shown["assessment_status"], "stale")
        self.assertFalse(shown["project_resolution_complete"])
        self.apply()
        self.assertTrue(
            self.store.show_assessment(self.workspace)["project_resolution_complete"]
        )

    def test_failed_current_publication_preserves_previous_assessment(self) -> None:
        self.accept()
        self.apply()
        previous = self.store.show_assessment(self.workspace)[
            "conflict_snapshot_sha256"
        ]
        self.write_assessment([self.conflict(("REQ1", "REQ2"))])
        preview = self.store.change_assessment(self.workspace, self.input)

        def fail_current(
            root: int,
            name: str,
            payload: bytes,
            verify: Callable[[], None],
            *,
            immutable: bool = False,
        ) -> None:
            if not immutable:
                raise OSError("before current publication")
            publish_file(root, name, payload, verify, immutable=True)

        with (
            patch(
                "mos_eisley.project_guidance_precedence_store.publish_file",
                side_effect=fail_current,
            ),
            self.assertRaises(OSError),
        ):
            self.store.change_assessment(
                self.workspace,
                self.input,
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertEqual(
            self.store.show_assessment(self.workspace)["conflict_snapshot_sha256"],
            previous,
        )
        # The archived candidate cannot claim current resolution completion.
        for path in self.storage.glob("assessment-snapshot-*.json"):
            sha = path.name.removeprefix("assessment-snapshot-").removesuffix(".json")
            historical = self.store.show_assessment(self.workspace, snapshot_sha256=sha)
            self.assertFalse(historical["project_resolution_complete"])
            self.assertEqual(historical["assessment_status"], "historical")

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "guidance-assess",
                *args,
                "-C",
                str(self.workspace),
                "--guidance-storage",
                str(self.storage),
                "--json",
            ],
            cwd=self.base,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_review_effective_stale_clear_history(self) -> None:
        self.accept()
        self.attach()
        self.write_assessment([self.conflict(("REQ1", "ENG1"), "REQ1")])
        args = ("set", "--input", str(self.input))
        preview = self.cli(*args)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        applied = self.cli(
            *args,
            "--apply",
            "--expected-sha256",
            json.loads(preview.stdout)["preview_sha256"],
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        shown = json.loads(self.cli("effective").stdout)
        self.assertTrue(shown["project_resolution_complete"])
        self.accept(clear=True)
        self.assertEqual(
            json.loads(self.cli("effective").stdout)["assessment_status"], "stale"
        )
        historical = self.cli(
            "show", "--snapshot-sha256", shown["conflict_snapshot_sha256"]
        )
        self.assertFalse(json.loads(historical.stdout)["project_resolution_complete"])
        preview = self.cli("clear")
        cleared = self.cli(
            "clear",
            "--apply",
            "--expected-sha256",
            json.loads(preview.stdout)["preview_sha256"],
        )
        self.assertEqual(cleared.returncode, 0, cleared.stderr)

    def test_cli_rejects_invalid_options_and_redacts_input(self) -> None:
        for args in (
            ("show", "--apply"),
            ("set", "--input", str(self.input), "--apply"),
            ("clear", "--input", str(self.input)),
            ("effective", "--snapshot-sha256", "a" * 64),
        ):
            with self.subTest(args=args):
                self.assertNotEqual(self.cli(*args).returncode, 0)
        self.input.write_text('{"secret":"PRECEDENCE-SECRET-CANARY"}')
        result = self.cli("set", "--input", str(self.input))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PRECEDENCE-SECRET-CANARY", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
