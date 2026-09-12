import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.core.models import digest
from mos_eisley.project_guidance_binding import GuidanceBindingStore
from mos_eisley.project_guidance_override_store import GuidanceOverrideStore
from mos_eisley.project_guidance_policy import (
    POLICY_BYTES,
    GuidancePolicyCheckStore,
    OwnerGuidancePolicy,
    decode_policy,
    policy_decisions,
)
from mos_eisley.project_guidance_precedence_store import ProjectAssessmentStore
from mos_eisley.project_requirement_store import RequirementStore


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "guidance"
        self.policy_root = self.base / "owner-policy"
        self.policy_root.mkdir(mode=0o700)
        self.policy_path = self.policy_root / "policy.json"
        self.policy_data: dict[str, object] = {
            "policy_id": "local-guidance-policy",
            "revision": "v1",
            "owner_uid": os.getuid(),
            "workspace": MappedDirectory.inspect(self.workspace).model_dump(
                mode="json"
            ),
            "prohibitions": [
                {
                    "id": "DENY1",
                    "reference": {"kind": "requirement", "rule_id": "REQ1"},
                    "reason": "Owner policy prohibits selecting this requirement.",
                }
            ],
        }
        self.write_policy()
        self.store = GuidancePolicyCheckStore(self.storage)
        self.requirements = RequirementStore(self.storage)
        self.assessments = ProjectAssessmentStore(self.storage)
        self.selection = self.base / "requirements.json"
        self.brief = self.base / "brief.md"
        self.brief.write_text("Use batch execution.\n")
        self.selection.write_text(
            json.dumps(
                {
                    "review_rationale": "Accepted project brief.",
                    "sources": [
                        {
                            "id": "brief",
                            "kind": "brief",
                            "content_sha256": digest(self.brief.read_bytes()),
                        }
                    ],
                    "requirements": [
                        {
                            "id": "REQ1",
                            "source_id": "brief",
                            "text": "Use batch execution.",
                            "applies_when": "Planning implementation",
                            "rationale": "Project requirement",
                            "checks": ["Review implementation"],
                        }
                    ],
                }
            )
        )
        self.assessment = self.base / "assessment.json"
        self.assessment.write_text(
            json.dumps({"review_rationale": "Reviewed all guidance.", "conflicts": []})
        )

    def write_policy(self) -> None:
        self.policy_path.write_text(json.dumps(self.policy_data))
        self.policy_path.chmod(0o600)

    def check(self) -> dict[str, object]:
        return self.store.check_policy(
            self.workspace, self.policy_path, digest(self.policy_path.read_bytes())
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

    def assess(self) -> None:
        preview = self.assessments.change_assessment(self.workspace, self.assessment)
        self.assessments.change_assessment(
            self.workspace,
            self.assessment,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )

    def test_empty_project_check_is_read_only_and_incomplete(self) -> None:
        receipt = self.check()
        self.assertEqual(receipt["status"], "incomplete")
        self.assertFalse(receipt["guidance_selection_allowed"])
        self.assertTrue(receipt["policy_satisfied"])
        self.assertFalse(self.storage.exists())
        self.assertEqual(
            cast(list[dict[str, object]], receipt["decisions"])[0]["status"],
            "not_present",
        )

    def test_owner_policy_blocks_accepted_requirement_and_preserves_evidence(
        self,
    ) -> None:
        self.accept()
        self.assess()
        receipt = self.check()
        self.assertEqual(receipt["status"], "blocked")
        self.assertFalse(receipt["policy_satisfied"])
        self.assertFalse(receipt["guidance_selection_allowed"])
        self.assertFalse(receipt["runtime_authorization_evaluated"])
        self.assertFalse(receipt["execution_authorized"])
        self.assertFalse(receipt["context_materialized"])
        self.assertEqual(receipt["policy_source_json"], self.policy_path.read_text())
        self.assertEqual(
            receipt["policy_source_sha256"], digest(self.policy_path.read_bytes())
        )
        guidance = cast(dict[str, object], receipt["guidance"])
        self.assertTrue(guidance["project_resolution_complete"])
        self.assertIsNotNone(guidance["requirement_snapshot_sha256"])

    def test_matching_policy_and_current_combined_review_allow_selection_only(
        self,
    ) -> None:
        self.accept()
        self.assess()
        self.policy_data["prohibitions"] = [
            {
                "id": "DENY2",
                "reference": {"kind": "requirement", "rule_id": "REQ2"},
                "reason": "Prohibited if introduced.",
            }
        ]
        self.write_policy()
        receipt = self.check()
        self.assertEqual(receipt["status"], "allowed")
        self.assertTrue(receipt["guidance_selection_allowed"])
        self.assertFalse(receipt["execution_authorized"])
        self.assertEqual(receipt["scope"], "owner_prohibitions_on_guidance_selection")

    def test_stale_or_unassessed_guidance_cannot_be_allowed(self) -> None:
        self.accept()
        self.policy_data["prohibitions"] = [
            {
                "id": "DENY2",
                "reference": {"kind": "requirement", "rule_id": "REQ2"},
                "reason": "Future constraint.",
            }
        ]
        self.write_policy()
        self.assertEqual(self.check()["status"], "incomplete")
        self.assess()
        self.assertEqual(self.check()["status"], "allowed")
        self.accept(clear=True)
        self.assertEqual(self.check()["status"], "incomplete")
        self.accept()
        self.assertEqual(self.check()["status"], "incomplete")

    def test_changed_policy_hash_requires_explicit_reselection(self) -> None:
        sha = digest(self.policy_path.read_bytes())
        self.policy_path.write_text(self.policy_path.read_text() + " ")
        with self.assertRaises(ValueError):
            self.store.check_policy(self.workspace, self.policy_path, sha)
        self.assertFalse(self.storage.exists())
        with self.assertRaises(ValueError):
            self.store.check_policy(self.workspace, self.policy_path, "not-a-digest")

    def test_wrong_owner_project_or_directory_identity_reject(self) -> None:
        self.policy_data["owner_uid"] = os.getuid() + 1
        self.write_policy()
        with self.assertRaises(ValueError):
            self.check()
        self.policy_data["owner_uid"] = os.getuid()
        self.write_policy()
        another = self.base / "another"
        another.mkdir()
        with self.assertRaises(ValueError):
            self.store.check_policy(
                another, self.policy_path, digest(self.policy_path.read_bytes())
            )
        self.workspace.rename(self.base / "old-project")
        self.workspace.mkdir()
        with self.assertRaises(ValueError):
            self.check()

    def test_repository_policy_cannot_self_nominate(self) -> None:
        private = self.workspace / "policy"
        private.mkdir(mode=0o700)
        path = private / "policy.json"
        path.write_bytes(self.policy_path.read_bytes())
        path.chmod(0o600)
        with self.assertRaises(ValueError):
            self.store.check_policy(self.workspace, path, digest(path.read_bytes()))
        self.assertFalse(self.storage.exists())

    def test_private_file_parent_symlink_and_hardlink_boundaries(self) -> None:
        self.policy_root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.check()
        self.policy_root.chmod(0o700)
        self.policy_path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.check()
        self.policy_path.chmod(0o600)
        link = self.policy_root / "link.json"
        link.symlink_to(self.policy_path)
        with self.assertRaises(OSError):
            self.store.check_policy(
                self.workspace, link, digest(self.policy_path.read_bytes())
            )
        link.unlink()
        os.link(self.policy_path, link)
        with self.assertRaises(ValueError):
            self.check()
        link.unlink()
        parent_link = self.base / "policy-link"
        parent_link.symlink_to(self.policy_root, target_is_directory=True)
        with self.assertRaises(OSError):
            self.store.check_policy(
                self.workspace,
                parent_link / "policy.json",
                digest(self.policy_path.read_bytes()),
            )

    def test_policy_changed_during_inspection_rejects(self) -> None:
        def mutate(
            policy: OwnerGuidancePolicy, rules: list[dict[str, object]] | None
        ) -> list[dict[str, object]]:
            self.policy_path.write_text(self.policy_path.read_text() + " ")
            return policy_decisions(policy, rules)

        with (
            patch(
                "mos_eisley.project_guidance_policy.policy_decisions",
                side_effect=mutate,
            ),
            self.assertRaises(ValueError),
        ):
            self.check()

    def test_guidance_changed_during_policy_inspection_rejects(self) -> None:
        self.accept()
        self.assess()
        current = next(self.storage.glob("requirements-project-*.json"))

        def mutate(
            policy: OwnerGuidancePolicy, rules: list[dict[str, object]] | None
        ) -> list[dict[str, object]]:
            current.write_bytes(current.read_bytes() + b" ")
            return policy_decisions(policy, rules)

        with (
            patch(
                "mos_eisley.project_guidance_policy.policy_decisions",
                side_effect=mutate,
            ),
            self.assertRaises(ValueError),
        ):
            self.check()

    def test_policy_schema_rejects_grants_duplicates_and_size_overflow(self) -> None:
        raw = self.policy_path.read_bytes()
        decode_policy(raw + b" " * (POLICY_BYTES - len(raw)))
        for payload in (
            raw + b" " * (POLICY_BYTES + 1 - len(raw)),
            json.dumps({**self.policy_data, "execution_authorized": True}).encode(),
            raw[:-1] + b',"policy_id":"duplicate"}',
            b"\xff",
        ):
            with self.assertRaises(ValueError):
                decode_policy(payload)
        prohibitions = cast(list[dict[str, object]], self.policy_data["prohibitions"])
        prohibitions.append(dict(prohibitions[0]))
        self.write_policy()
        with self.assertRaises(ValueError):
            self.check()

    def test_advisory_omission_must_be_reassessed_before_policy_allows(self) -> None:
        markdown = self.base / "advisory.md"
        markdown.write_text("Prefer services.\n")
        descriptor = self.base / "advisory.json"
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
                            "text": "Prefer services.",
                            "applies_when": "Planning",
                            "rationale": "Preference",
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
        self.assess()
        self.policy_data["prohibitions"] = [
            {
                "id": "DENY-ENG",
                "reference": {
                    "kind": "advisory",
                    "template_id": "engineering",
                    "rule_id": "ENG1",
                },
                "reason": "Owner prohibits this preference.",
            }
        ]
        self.write_policy()
        self.assertEqual(self.check()["status"], "blocked")
        profile = self.base / "overrides.json"
        profile.write_text(
            json.dumps(
                {
                    "overrides": [
                        {
                            "template_id": "engineering",
                            "rule_id": "ENG1",
                            "action": "omit",
                            "reason": "Honor owner policy.",
                        }
                    ]
                }
            )
        )
        overrides = GuidanceOverrideStore(self.storage)
        preview = overrides.change_overrides(self.workspace, profile)
        overrides.change_overrides(
            self.workspace,
            profile,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )
        self.assertEqual(self.check()["status"], "incomplete")
        self.assess()
        self.assertEqual(self.check()["status"], "allowed")
        self.assertEqual(
            cast(list[dict[str, object]], self.check()["decisions"])[0]["status"],
            "not_selected",
        )
        preview = bindings.change(self.workspace, "detach", "engineering")
        bindings.change(
            self.workspace,
            "detach",
            "engineering",
            expected_sha256=cast(str, preview["preview_sha256"]),
        )
        receipt = self.check()
        self.assertEqual(receipt["status"], "incomplete")
        self.assertFalse(receipt["policy_satisfied"])
        self.assertEqual(
            cast(list[dict[str, object]], receipt["decisions"])[0]["status"],
            "unavailable",
        )

    def cli(self, *, sha: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "guidance-policy-check",
                "-C",
                str(self.workspace),
                "--policy",
                str(self.policy_path),
                "--expected-policy-sha256",
                digest(self.policy_path.read_bytes()) if sha is None else sha,
                "--guidance-storage",
                str(self.storage),
                "--json",
            ],
            cwd=self.base,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_blocked_allowed_and_redacted_invalid_policy(self) -> None:
        self.accept()
        self.assess()
        blocked = self.cli()
        self.assertEqual(blocked.returncode, 3, blocked.stderr)
        self.assertEqual(json.loads(blocked.stdout)["status"], "blocked")
        self.policy_data["prohibitions"] = [
            {
                "id": "DENY2",
                "reference": {"kind": "requirement", "rule_id": "REQ2"},
                "reason": "Prohibited if added.",
            }
        ]
        self.write_policy()
        allowed = self.cli()
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertTrue(json.loads(allowed.stdout)["guidance_selection_allowed"])
        self.policy_path.write_text('{"secret":"POLICY-SECRET-CANARY"}')
        invalid = self.cli()
        self.assertEqual(invalid.returncode, 2)
        self.assertNotIn("POLICY-SECRET-CANARY", invalid.stdout + invalid.stderr)

    def test_cli_incomplete_is_nonzero_and_stale_hash_rejects(self) -> None:
        result = self.cli()
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "incomplete")
        self.assertEqual(self.cli(sha="a" * 64).returncode, 2)
        self.assertFalse(self.storage.exists())


if __name__ == "__main__":
    unittest.main()
