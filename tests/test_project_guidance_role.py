import json
import os
import subprocess
import sys
import unittest
from collections.abc import Callable
from typing import cast
from unittest.mock import patch

import test_project_guidance_policy as policy_fixture

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance_binding import GuidanceBindingStore
from mos_eisley.project_guidance_override_store import GuidanceOverrideStore
from mos_eisley.project_guidance_precedence_store import project_assessment_history_name
from mos_eisley.project_guidance_role import (
    SELECTION_BYTES,
    FrozenRoleContext,
    RoleSelection,
    decode_role_selection,
    project_role_context,
)
from mos_eisley.project_guidance_role_store import RoleGuidanceStore, role_snapshot_name
from mos_eisley.project_guidance_storage import publish_file


class RoleContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = policy_fixture.PolicyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.workspace = self.fixture.workspace
        self.storage = self.fixture.storage
        self.policy_path = self.fixture.policy_path
        self.fixture.policy_data["prohibitions"] = [
            {
                "id": "DENY-OTHER",
                "reference": {"kind": "requirement", "rule_id": "OTHER"},
                "reason": "PRIVATE-POLICY-PROSE-CANARY",
            }
        ]
        self.fixture.write_policy()
        self.fixture.accept()
        self.fixture.assess()
        self.store = RoleGuidanceStore(self.storage)
        self.input = self.base / "role-selection.json"
        self.selection: dict[str, object] = {
            "role": "creator",
            "scope": "Implement batch execution",
            "review_rationale": "Selected requirements relevant to this role.",
            "rules": [{"kind": "requirement", "rule_id": "REQ1"}],
            "omitted_requirements": [],
        }
        self.write_selection()

    def write_selection(self) -> None:
        self.input.write_text(json.dumps(self.selection))

    def preview(self) -> dict[str, object]:
        return self.store.freeze_context(
            self.workspace,
            self.input,
            self.policy_path,
            digest(self.policy_path.read_bytes()),
        )

    def freeze(self) -> dict[str, object]:
        preview = self.preview()
        return self.store.freeze_context(
            self.workspace,
            self.input,
            self.policy_path,
            digest(self.policy_path.read_bytes()),
            expected_sha256=cast(str, preview["preview_sha256"]),
        )

    def snapshot(self, receipt: dict[str, object]) -> FrozenRoleContext:
        return FrozenRoleContext.model_validate_json(json.dumps(receipt["snapshot"]))

    def add_requirement(self) -> None:
        self.fixture.brief.write_text(
            "Use batch execution.\nRetain data locally.\nPRIVATE-BRIEF-CANARY\n"
        )
        selection = json.loads(self.fixture.selection.read_text())
        selection["sources"][0]["content_sha256"] = digest(
            self.fixture.brief.read_bytes()
        )
        selection["requirements"].append(
            {
                **selection["requirements"][0],
                "id": "REQ2",
                "text": "Retain data locally.",
            }
        )
        self.fixture.selection.write_text(json.dumps(selection))
        self.fixture.accept()
        self.fixture.assess()

    def attach_advisory(self) -> None:
        markdown = self.base / "guidance.md"
        markdown.write_text("PRIVATE-OLD-ADVISORY-CANARY\n")
        descriptor = self.base / "guidance.json"
        descriptor.write_text(
            json.dumps(
                {
                    "template_id": "engineering",
                    "version": "1.0.0",
                    "source_revision": "v1",
                    "content_sha256": digest(markdown.read_bytes()),
                    "rules": [
                        {
                            "id": "ENG1",
                            "text": markdown.read_text().strip(),
                            "applies_when": "Planning",
                            "rationale": "Advisory",
                            "checks": ["Review design"],
                        }
                    ],
                }
            )
        )
        bindings = GuidanceBindingStore(self.storage)
        preview = bindings.change(
            self.workspace,
            "attach",
            "engineering",
            descriptor_path=descriptor,
            markdown_path=markdown,
        )
        bindings.change(
            self.workspace,
            "attach",
            "engineering",
            descriptor_path=descriptor,
            markdown_path=markdown,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )

    def test_review_is_read_only_and_all_roles_get_frozen_selected_rules(self) -> None:
        before = {path.name: path.read_bytes() for path in self.storage.iterdir()}
        preview = self.preview()
        self.assertFalse(preview["applied"])
        self.assertEqual(
            before, {path.name: path.read_bytes() for path in self.storage.iterdir()}
        )
        for role in ("creator", "coder", "critic", "judge"):
            self.selection["role"] = role
            self.write_selection()
            receipt = self.freeze()
            snapshot = self.snapshot(receipt)
            self.assertEqual(snapshot.context.role, role)
            self.assertEqual(snapshot.context.rules[0].text, "Use batch execution.")
            self.assertEqual(
                snapshot.context.rules[0].checks, ("Review implementation",)
            )
            self.assertEqual(snapshot.context.rules[0].reference.rule_id, "REQ1")
            self.assertIsNotNone(snapshot.context.rules[0].requirement_snapshot_sha256)
            self.assertEqual(
                snapshot.context.rules[0].source_content_sha256,
                digest(self.fixture.brief.read_bytes()),
            )
            self.assertEqual(
                receipt["context_bytes"], len(canonical_bytes(snapshot.context))
            )
            self.assertEqual(
                receipt["context_sha256"], digest(canonical_bytes(snapshot.context))
            )
            self.assertFalse(snapshot.provider_context_loaded)
            self.assertFalse(snapshot.context.history_loaded)
            self.assertFalse(snapshot.context.execution_authorized)

    def test_every_omitted_requirement_needs_an_explicit_scope_reason(self) -> None:
        self.add_requirement()
        with self.assertRaisesRegex(ValueError, "omitted accepted requirement"):
            self.preview()
        self.selection["omitted_requirements"] = [
            {
                "rule_id": "REQ2",
                "reason": "Storage implementation is outside this role's scope.",
            }
        ]
        self.write_selection()
        snapshot = self.snapshot(self.freeze())
        context = canonical_bytes(snapshot.context).decode()
        self.assertNotIn("Retain data locally.", context)
        self.assertNotIn("PRIVATE-BRIEF-CANARY", context)
        self.assertNotIn("PRIVATE-POLICY-PROSE-CANARY", context)
        self.assertEqual(snapshot.context.omitted_requirements[0].rule_id, "REQ2")
        self.selection["omitted_requirements"] = [
            {"rule_id": "REQ1", "reason": "Already included"},
            {"rule_id": "REQ2", "reason": "Not relevant"},
        ]
        self.write_selection()
        with self.assertRaises(ValueError):
            self.preview()

    def test_only_effective_override_text_and_departure_reason_enter_context(
        self,
    ) -> None:
        self.attach_advisory()
        profile = self.base / "override.json"
        profile.write_text(
            json.dumps(
                {
                    "overrides": [
                        {
                            "template_id": "engineering",
                            "rule_id": "ENG1",
                            "action": "replace",
                            "reason": "Approved departure for this workload.",
                            "replacement": {
                                "id": "ENG1",
                                "text": "Prefer scheduled work.",
                                "applies_when": "Scheduling",
                                "rationale": "Workload fit",
                                "checks": ["Check throughput"],
                            },
                        }
                    ]
                }
            )
        )
        store = GuidanceOverrideStore(self.storage)
        preview = store.change_overrides(self.workspace, profile)
        store.change_overrides(
            self.workspace,
            profile,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )
        self.fixture.assess()
        self.selection["rules"] = [
            {"kind": "requirement", "rule_id": "REQ1"},
            {"kind": "advisory", "template_id": "engineering", "rule_id": "ENG1"},
        ]
        self.write_selection()
        snapshot = self.snapshot(self.freeze())
        rule = snapshot.context.rules[1]
        self.assertEqual(rule.override_reason, "Approved departure for this workload.")
        self.assertIsNotNone(rule.template_snapshot_sha256)
        self.assertIsNotNone(rule.override_snapshot_sha256)
        self.assertNotIn(
            "PRIVATE-OLD-ADVISORY-CANARY", canonical_bytes(snapshot.context).decode()
        )

    def test_unknown_and_conflict_excluded_references_reject(self) -> None:
        self.selection["rules"] = [{"kind": "requirement", "rule_id": "UNKNOWN"}]
        self.write_selection()
        with self.assertRaises(ValueError):
            self.preview()
        self.attach_advisory()
        self.fixture.assessment.write_text(
            json.dumps(
                {
                    "review_rationale": "Reviewed precedence.",
                    "conflicts": [
                        {
                            "id": "C1",
                            "rules": [
                                {"kind": "requirement", "rule_id": "REQ1"},
                                {
                                    "kind": "advisory",
                                    "template_id": "engineering",
                                    "rule_id": "ENG1",
                                },
                            ],
                            "explanation": "Competing designs",
                            "preferred_rule": {
                                "kind": "requirement",
                                "rule_id": "REQ1",
                            },
                            "resolution_rationale": "Accepted requirement wins.",
                        }
                    ],
                }
            )
        )
        self.fixture.assess()
        self.selection["rules"] = [
            {"kind": "requirement", "rule_id": "REQ1"},
            {"kind": "advisory", "template_id": "engineering", "rule_id": "ENG1"},
        ]
        self.write_selection()
        with self.assertRaises(ValueError):
            self.preview()

    def test_policy_blocked_and_stale_guidance_cannot_freeze(self) -> None:
        self.fixture.policy_data["prohibitions"] = [
            {
                "id": "DENY1",
                "reference": {"kind": "requirement", "rule_id": "REQ1"},
                "reason": "Owner prohibition.",
            }
        ]
        self.fixture.write_policy()
        with self.assertRaises(ValueError):
            self.freeze()
        self.fixture.policy_data["prohibitions"] = [
            {
                "id": "DENY2",
                "reference": {"kind": "requirement", "rule_id": "OTHER"},
                "reason": "Owner prohibition.",
            }
        ]
        self.fixture.write_policy()
        self.fixture.accept(clear=True)
        with self.assertRaises(ValueError):
            self.freeze()
        self.assertEqual(list(self.storage.glob("role-snapshot-*.json")), [])

    def test_selection_policy_and_guidance_changes_invalidate_preview(self) -> None:
        preview = self.preview()
        self.input.write_text(self.input.read_text() + " ")
        with self.assertRaises(ValueError):
            self.store.freeze_context(
                self.workspace,
                self.input,
                self.policy_path,
                digest(self.policy_path.read_bytes()),
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.write_selection()
        self.policy_path.write_text(self.policy_path.read_text() + " ")
        with self.assertRaises(ValueError):
            self.store.freeze_context(
                self.workspace,
                self.input,
                self.policy_path,
                digest(self.policy_path.read_bytes()),
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        preview = self.preview()
        self.add_requirement()
        self.selection["omitted_requirements"] = [
            {"rule_id": "REQ2", "reason": "Out of scope"}
        ]
        self.write_selection()
        with self.assertRaises(ValueError):
            self.store.freeze_context(
                self.workspace,
                self.input,
                self.policy_path,
                digest(self.policy_path.read_bytes()),
                expected_sha256=cast(str, preview["preview_sha256"]),
            )

    def test_snapshot_survives_original_file_deletion_and_current_updates(self) -> None:
        receipt = self.freeze()
        original = self.snapshot(receipt)
        self.fixture.accept(clear=True)
        for path in (
            self.policy_path,
            self.input,
            self.fixture.brief,
            self.fixture.selection,
        ):
            path.unlink()
        shown = self.store.show_context(self.workspace, original.sha256)
        self.assertEqual(shown["snapshot"], receipt["snapshot"])
        self.assertTrue(shown["historical_snapshot"])
        self.assertFalse(shown["current_authority"])
        self.assertFalse(shown["provider_context_loaded"])

    def test_new_hash_cannot_launder_a_forged_projection(self) -> None:
        original = self.snapshot(self.freeze())
        data = json.loads(canonical_bytes(original))
        data["context"]["rules"][0]["text"] = "Forged requirement"
        forged = FrozenRoleContext.model_validate_json(json.dumps(data))
        path = self.storage / role_snapshot_name(forged.sha256)
        path.write_bytes(canonical_bytes(forged))
        path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "pinned projection"):
            self.store.show_context(self.workspace, forged.sha256)

    def test_missing_pinned_assessment_and_private_file_corruption_reject(self) -> None:
        snapshot = self.snapshot(self.freeze())
        path = self.storage / role_snapshot_name(snapshot.sha256)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.store.show_context(self.workspace, snapshot.sha256)
        path.chmod(0o600)
        (
            self.storage
            / project_assessment_history_name(
                snapshot.context.assessment_snapshot_sha256
            )
        ).unlink()
        with self.assertRaises(ValueError):
            self.store.show_context(self.workspace, snapshot.sha256)

    def test_owner_project_nested_and_digest_path_isolation(self) -> None:
        snapshot = self.snapshot(self.freeze())
        for path in (self.base / "another", self.workspace / "nested"):
            path.mkdir()
            with self.assertRaises(ValueError):
                self.store.show_context(path, snapshot.sha256)
        with (
            patch(
                "mos_eisley.project_guidance_role_store.os.getuid",
                return_value=os.getuid() + 1,
            ),
            self.assertRaises((ValueError, PermissionError)),
        ):
            self.store.show_context(self.workspace, snapshot.sha256)
        with self.assertRaises(ValueError):
            self.store.show_context(self.workspace, "../../escape")

    def test_mid_publication_policy_change_and_failure_leave_no_role_snapshot(
        self,
    ) -> None:
        preview = self.preview()

        def mutate(
            root: int,
            name: str,
            payload: bytes,
            verify: Callable[[], None],
            *,
            immutable: bool = False,
        ) -> None:
            self.policy_path.write_text(self.policy_path.read_text() + " ")
            publish_file(root, name, payload, verify, immutable=immutable)

        with (
            patch(
                "mos_eisley.project_guidance_role_store.publish_file",
                side_effect=mutate,
            ),
            self.assertRaises(ValueError),
        ):
            self.store.freeze_context(
                self.workspace,
                self.input,
                self.policy_path,
                digest(self.policy_path.read_bytes()),
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertEqual(list(self.storage.glob("role-snapshot-*.json")), [])
        preview = self.preview()
        with (
            patch(
                "mos_eisley.project_guidance_role_store.publish_file",
                side_effect=OSError("injected failure"),
            ),
            self.assertRaises(OSError),
        ):
            self.store.freeze_context(
                self.workspace,
                self.input,
                self.policy_path,
                digest(self.policy_path.read_bytes()),
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertEqual(list(self.storage.glob("role-snapshot-*.json")), [])

    def test_selection_bounds_duplicate_keys_and_authority_fields_reject(self) -> None:
        raw = self.input.read_bytes()
        decode_role_selection(raw + b" " * (SELECTION_BYTES - len(raw)))
        for payload in (
            raw + b" " * (SELECTION_BYTES + 1 - len(raw)),
            raw[:-1] + b',"role":"judge"}',
            json.dumps({**self.selection, "history_path": "/private/notes"}).encode(),
            json.dumps({**self.selection, "execution_authorized": True}).encode(),
        ):
            with self.assertRaises(ValueError):
                decode_role_selection(payload)

    def test_context_byte_limit_rejects_oversized_selected_rules(self) -> None:
        refs = [{"kind": "requirement", "rule_id": f"REQ{i}"} for i in range(64)]
        selection = RoleSelection.model_validate_json(
            json.dumps({**self.selection, "rules": refs})
        )
        rules: list[dict[str, object]] = [
            {
                "reference": ref,
                "selected": True,
                "source": "accepted_project_requirement",
                "effective_rule": {
                    "text": "é" * 2000,
                    "applies_when": "Always",
                    "rationale": "Relevant",
                    "checks": ["Check"],
                },
                "requirement_snapshot_sha256": "a" * 64,
            }
            for ref in refs
        ]
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            project_role_context(selection, rules, "b" * 64, "c" * 64)

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "guidance-context",
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

    def test_cli_preview_freeze_and_historical_show(self) -> None:
        args = (
            "freeze",
            "--input",
            str(self.input),
            "--policy",
            str(self.policy_path),
            "--expected-policy-sha256",
            digest(self.policy_path.read_bytes()),
        )
        preview = self.cli(*args)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(json.loads(preview.stdout)["applied"])
        applied = self.cli(
            *args,
            "--apply",
            "--expected-sha256",
            json.loads(preview.stdout)["preview_sha256"],
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        receipt = json.loads(applied.stdout)
        shown = self.cli("show", "--snapshot-sha256", receipt["snapshot_sha256"])
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(json.loads(shown.stdout)["snapshot"], receipt["snapshot"])
        self.assertFalse(json.loads(shown.stdout)["provider_context_loaded"])

    def test_cli_invalid_options_and_rejected_selection_are_redacted(self) -> None:
        for args in (
            ("show",),
            ("freeze", "--apply"),
            ("show", "--snapshot-sha256", "a" * 64, "--input", str(self.input)),
        ):
            with self.subTest(args=args):
                self.assertNotEqual(self.cli(*args).returncode, 0)
        self.input.write_text('{"secret":"ROLE-CONTEXT-SECRET-CANARY"}')
        result = self.cli(
            "freeze",
            "--input",
            str(self.input),
            "--policy",
            str(self.policy_path),
            "--expected-policy-sha256",
            digest(self.policy_path.read_bytes()),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("ROLE-CONTEXT-SECRET-CANARY", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
