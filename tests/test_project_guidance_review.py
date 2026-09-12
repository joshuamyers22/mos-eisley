import asyncio
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_project_guidance_role as role_fixture

from mos_eisley.core.models import (
    Brief,
    CriticRequest,
    CriticSpec,
    Critique,
    JudgeDecision,
    JudgeRequest,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.skills import SkillIdentity, SkillRunAssignment, SkillRunManifest
from mos_eisley.demo import demo_inputs
from mos_eisley.project_guidance_review import (
    PreparedGuidanceReview,
    ReviewGuidanceSelection,
    decode_prepared_review,
    prepare_guidance_review,
    verify_current_review,
)
from mos_eisley.project_guidance_role import RoleContext
from mos_eisley.project_guidance_role_admission import (
    RoleContextAdmissionStore,
    RoleContextSelection,
)
from mos_eisley.providers.recorded import Cassette, CriticRecording, RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.run.store import load_run, save_run


class GuidedReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = role_fixture.RoleContextTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        selections: list[RoleContextSelection] = []
        for role in ("critic", "judge"):
            self.fixture.selection["role"] = role
            self.fixture.write_selection()
            saved = self.fixture.snapshot(self.fixture.freeze())
            selections.append(
                RoleContextSelection(
                    snapshot_sha256=saved.sha256,
                    context_sha256=digest(canonical_bytes(saved.context)),
                    role=saved.context.role,
                    scope=saved.context.scope,
                )
            )
        self.selection = ReviewGuidanceSelection(
            critic=selections[0], judge=selections[1]
        )
        self.source = Brief(
            spec="Review this explicit change.",
            diff="+run_batch()",
            constraints="Keep tests reproducible.",
        )
        self.store = RoleContextAdmissionStore(self.fixture.storage)
        self.policy_sha = digest(self.fixture.policy_path.read_bytes())
        self.prepared = self.prepare()

    def prepare(self, source: Brief | None = None) -> PreparedGuidanceReview:
        return prepare_guidance_review(
            self.store,
            self.fixture.workspace,
            self.selection,
            source or self.source,
            self.fixture.policy_path,
            self.policy_sha,
        )

    def cassette(self, brief: Brief | None = None) -> Cassette:
        selected = brief or self.prepared.brief
        critics = tuple(
            CriticSpec(
                id=f"critic-{i}",
                provider=f"fixture-{i}",
                model="fixture",
                persona="Review the rubric.",
            )
            for i in range(2)
        )
        return Cassette(
            brief_id=selected.brief_id,
            critics=tuple(
                CriticRecording(
                    critic=critic,
                    request_sha256=digest(
                        canonical_bytes(
                            CriticRequest(brief=selected, persona=critic.persona)
                        )
                    ),
                    response=Critique(),
                )
                for critic in critics
            ),
            judge_request_sha256=digest(
                canonical_bytes(JudgeRequest(brief=selected, findings=()))
            ),
            judge_response=JudgeDecision(rationale="Recorded checks passed."),
        )

    def run_recorded(self, policy: ReviewPolicy | None = None):
        cassette = self.cassette()
        return asyncio.run(
            review(
                self.prepared.brief,
                tuple(item.critic for item in cassette.critics),
                RecordedReviewer(cassette),
                policy or ReviewPolicy(),
            )
        )

    def test_projection_preserves_explicit_source_and_shares_exact_rubric(self) -> None:
        self.assertEqual(self.prepared.brief.spec, self.source.spec)
        self.assertEqual(self.prepared.brief.diff, self.source.diff)
        self.assertTrue(
            self.prepared.brief.constraints.startswith(self.source.constraints)
        )
        self.assertIn("Use batch execution.", self.prepared.brief.constraints)
        self.assertIn("Review implementation", self.prepared.brief.constraints)
        for private in ("PRIVATE-POLICY-PROSE-CANARY", "PRIVATE-BRIEF-CANARY"):
            self.assertNotIn(private, canonical_bytes(self.prepared).decode())
        self.assertNotEqual(self.source.brief_id, self.prepared.brief.brief_id)
        self.assertFalse(self.prepared.provider_request_sent)
        self.assertFalse(self.prepared.execution_authorized)
        self.assertEqual(self.run_recorded().verdict.decision, "accept")

    def test_paired_selection_rejects_wrong_role_and_scope(self) -> None:
        for field, value in (("role", "creator"), ("scope", "Unrelated scope")):
            data = self.selection.model_dump(mode="json")
            data["critic"][field] = value
            with self.assertRaises(ValueError):
                ReviewGuidanceSelection.model_validate_json(json.dumps(data))

    def test_different_role_rubrics_reject(self) -> None:
        data = self.prepared.judge_context.model_dump(mode="json")
        data["rules"][0]["checks"] = ["Different rubric"]
        judge = RoleContext.model_validate_json(json.dumps(data))
        selection = self.selection.model_dump(mode="json")
        selection["judge"]["context_sha256"] = digest(canonical_bytes(judge))
        with self.assertRaisesRegex(ValueError, "identical frozen guidance"):
            PreparedGuidanceReview.model_validate_json(
                json.dumps(
                    {
                        **self.prepared.model_dump(mode="json"),
                        "selection": selection,
                        "judge_context": judge.model_dump(mode="json"),
                    }
                )
            )

    def test_constraints_limit_rejects_without_truncating(self) -> None:
        with self.assertRaises(ValueError):
            self.prepare(Brief(spec="s", diff="d", constraints="x" * 32000))
        self.assertEqual(self.source.constraints, "Keep tests reproducible.")

    def test_retained_source_and_projection_share_a_total_byte_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "512 KiB"):
            self.prepare(Brief(spec="s" * 128000, diff="d" * 256000))

    def test_full_critic_request_budget_still_applies(self) -> None:
        result = self.run_recorded(ReviewPolicy(max_request_bytes=1024))
        self.assertEqual(result.verdict.decision, "infrastructure_error")
        self.assertTrue(all(item.error == "budget_exceeded" for item in result.critics))

    def test_changed_brief_and_duplicate_input_reject(self) -> None:
        data = self.prepared.model_dump(mode="json")
        data["brief"]["constraints"] += " Forged guidance"
        with self.assertRaises(ValueError):
            decode_prepared_review(json.dumps(data).encode())
        raw = canonical_bytes(self.prepared)
        with self.assertRaises(ValueError):
            decode_prepared_review(raw[:-1] + b',"owner_uid":0}')
        with self.assertRaises(ValueError):
            decode_prepared_review(raw + b" " * (512 * 1024))

    def test_current_verification_rejects_stale_and_other_project(self) -> None:
        other = self.fixture.workspace / "nested"
        other.mkdir()
        with self.assertRaises(ValueError):
            verify_current_review(
                self.store,
                other,
                self.prepared,
                self.fixture.policy_path,
                self.policy_sha,
            )
        self.fixture.fixture.accept(clear=True)
        with self.assertRaises(ValueError):
            verify_current_review(
                self.store,
                self.fixture.workspace,
                self.prepared,
                self.fixture.policy_path,
                self.policy_sha,
            )

    def save(self) -> Path:
        return save_run(
            self.fixture.base / "runs",
            self.prepared.brief,
            self.cassette(),
            ReviewPolicy(),
            self.run_recorded(),
            guidance_review=self.prepared,
        )

    def test_manifest_pins_guidance_and_historical_replay_needs_no_original_files(
        self,
    ) -> None:
        path = self.save()
        manifest = json.loads((path / "manifest.json").read_text())
        self.assertEqual(manifest["schema_version"], 3)
        self.assertIn(
            "guidance-review.json", {item["name"] for item in manifest["artifacts"]}
        )
        self.fixture.policy_path.unlink()
        self.fixture.input.unlink()
        self.fixture.fixture.brief.unlink()
        for stored in self.fixture.storage.iterdir():
            stored.unlink()
        brief, cassette, policy, expected = load_run(path)
        actual = asyncio.run(
            review(
                brief,
                tuple(item.critic for item in cassette.critics),
                RecordedReviewer(cassette),
                policy,
            )
        )
        self.assertEqual(expected, actual)
        self.assertEqual(
            decode_prepared_review((path / "guidance-review.json").read_bytes()),
            self.prepared,
        )

    def test_manifest_artifact_tampering_and_wrong_run_brief_reject(self) -> None:
        path = self.save()
        (path / "guidance-review.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            load_run(path)
        with self.assertRaisesRegex(ValueError, "run brief"):
            save_run(
                self.fixture.base / "other-runs",
                self.source,
                self.cassette(self.source),
                ReviewPolicy(),
                self.run_recorded(),
                guidance_review=self.prepared,
            )
        self.assertFalse((self.fixture.base / "other-runs").exists())

    def test_combined_skill_guidance_manifest_requires_both_artifacts(self) -> None:
        cassette = self.cassette()
        skills = SkillRunManifest(
            assignments=tuple(
                SkillRunAssignment(
                    critic_id=item.critic.id,
                    skill=SkillIdentity(
                        source="user",
                        name="fixture-persona",
                        kind="persona",
                        package_sha256="a" * 64,
                        instructions_sha256=digest(item.critic.persona.encode()),
                    ),
                    instructions_sha256=digest(item.critic.persona.encode()),
                    instruction_bytes=len(item.critic.persona.encode()),
                )
                for item in cassette.critics
            )
        )
        path = save_run(
            self.fixture.base / "runs",
            self.prepared.brief,
            cassette,
            ReviewPolicy(),
            self.run_recorded(),
            skill_manifest=skills,
            guidance_review=self.prepared,
        )
        load_run(path)
        manifest_path = path / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["schema_version"], 4)
        manifest["artifacts"] = [
            item for item in manifest["artifacts"] if item["name"] != "skills.json"
        ]
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "artifact set"):
            load_run(path)

    def test_rehashed_guidance_different_from_stored_brief_rejects(self) -> None:
        path = self.save()
        changed = self.prepare(Brief(spec="Changed spec", diff=self.source.diff))
        (path / "guidance-review.json").write_bytes(canonical_bytes(changed))
        manifest_path = path / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        for item in manifest["artifacts"]:
            if item["name"] == "guidance-review.json":
                item["sha256"] = changed.sha256
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "run brief"):
            load_run(path)

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "guidance-review",
                *args,
                "-C",
                str(self.fixture.workspace),
                "--guidance-storage",
                str(self.fixture.storage),
                "--policy",
                str(self.fixture.policy_path),
                "--expected-policy-sha256",
                self.policy_sha,
                "--json",
            ],
            cwd=self.fixture.base,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_prepare_run_and_stale_input(self) -> None:
        selection = self.fixture.base / "review-selection.json"
        source = self.fixture.base / "source.json"
        selection.write_bytes(canonical_bytes(self.selection))
        source.write_bytes(canonical_bytes(self.source))
        preview = self.cli(
            "prepare", "--selection", str(selection), "--brief", str(source)
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        receipt = json.loads(preview.stdout)
        prepared = self.fixture.base / "prepared.json"
        prepared.write_text(json.dumps(receipt["prepared"]))
        cassette = self.fixture.base / "cassette.json"
        cassette.write_bytes(canonical_bytes(self.cassette()))
        args = (
            "run",
            "--prepared",
            str(prepared),
            "--expected-prepared-sha256",
            receipt["prepared_sha256"],
            "--cassette",
            str(cassette),
            "--output",
            str(self.fixture.base / "runs"),
        )
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads(result.stdout)
        self.assertEqual(event["decision"], "accept")
        self.assertEqual(load_run(Path(event["path"]))[0], self.prepared.brief)
        self.fixture.fixture.accept(clear=True)
        result = self.cli(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PRIVATE-POLICY-PROSE-CANARY", result.stdout + result.stderr)

    def test_cli_rejects_wrong_cassette_and_bad_options(self) -> None:
        for args in (
            ("prepare",),
            ("run",),
            ("prepare", "--output", str(self.fixture.base)),
        ):
            with self.subTest(args=args):
                self.assertNotEqual(self.cli(*args).returncode, 0)
        prepared = self.fixture.base / "prepared.json"
        prepared.write_bytes(canonical_bytes(self.prepared))
        cassette = self.fixture.base / "cassette.json"
        cassette.write_bytes(canonical_bytes(demo_inputs()[1]))
        result = self.cli(
            "run",
            "--prepared",
            str(prepared),
            "--expected-prepared-sha256",
            self.prepared.sha256,
            "--cassette",
            str(cassette),
            "--output",
            str(self.fixture.base / "runs"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.fixture.base / "runs").exists())

    def test_policy_change_after_offline_review_prevents_run_save(self) -> None:
        import argparse

        from mos_eisley.project_guidance_review_cli import add_command, run_command

        prepared = self.fixture.base / "prepared.json"
        prepared.write_bytes(canonical_bytes(self.prepared))
        cassette = self.fixture.base / "cassette.json"
        cassette.write_bytes(canonical_bytes(self.cassette()))
        parser = argparse.ArgumentParser()
        add_command(parser)
        args = parser.parse_args(
            [
                "run",
                "--prepared",
                str(prepared),
                "--expected-prepared-sha256",
                self.prepared.sha256,
                "--cassette",
                str(cassette),
                "--output",
                str(self.fixture.base / "runs"),
                "-C",
                str(self.fixture.workspace),
                "--guidance-storage",
                str(self.fixture.storage),
                "--policy",
                str(self.fixture.policy_path),
                "--expected-policy-sha256",
                self.policy_sha,
            ]
        )
        result = self.run_recorded()

        async def mutate(*unused: object):
            self.fixture.policy_path.write_text(
                self.fixture.policy_path.read_text() + " "
            )
            return result

        with (
            patch("mos_eisley.project_guidance_review_cli.review", side_effect=mutate),
            self.assertRaises(ValueError),
        ):
            run_command(args)
        self.assertFalse((self.fixture.base / "runs").exists())


if __name__ == "__main__":
    unittest.main()
