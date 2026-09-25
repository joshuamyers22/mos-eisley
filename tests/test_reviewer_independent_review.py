"""Offline G4 final implementation-review authority and evidence regressions."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from test_reviewer_final_suites import FinalWholeSuiteTests
from test_reviewer_provenance import NOW

from mos_eisley.cli import main
from mos_eisley.core.models import (
    CriticResult,
    CriticSpec,
    Critique,
    Evidence,
    Finding,
    JudgeDecision,
    ReviewPolicy,
    canonical_bytes,
)
from mos_eisley.review.citations import citation_bound_request
from mos_eisley.reviewer_final_suites import run_final_whole_suites
from mos_eisley.reviewer_independent_review import (
    G4CriticAssessment,
    G4IndependentReviewAuthority,
    G4IndependentReviewRecord,
    G4JudgeAssessment,
    G4ReviewCriticAuthority,
    assess_independent_review,
    build_review_subject,
    decode_review_artifact,
    sign_critic_assessment,
    sign_judge_assessment,
    sign_review_authority,
    verify_independent_review_record,
)
from mos_eisley.reviewer_provenance import provenance_signer


class G4IndependentReviewTests(unittest.TestCase):
    def _case(self, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        helper = FinalWholeSuiteTests()
        inputs, container = helper._case(root)
        with patch.object(container, "execute", side_effect=helper._execute_worker):
            final_receipt = run_final_whole_suites(**inputs, container=container)
        plan_path = root / "approved-plan.txt"
        plan_path.write_bytes(b"approved plan")
        common = {
            key: value
            for key, value in inputs.items()
            if key not in {"approval", "creator_request", "reviewer_request", "now"}
        }
        common["final_receipt"] = final_receipt
        common["approved_plan_path"] = plan_path
        subject = build_review_subject(**common)
        keys = (Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate())
        judge_key = Ed25519PrivateKey.generate()
        critics = tuple(
            G4ReviewCriticAuthority(
                critic=CriticSpec(
                    id=f"critic-{index}",
                    provider=f"provider-{index}",
                    model=f"model-{index}",
                    persona="Review the exact G4 implementation and test result.",
                ),
                signer=provenance_signer(f"critic-{index}", key.public_key()),
            )
            for index, key in enumerate(keys, 1)
        )
        authority = sign_review_authority(
            G4IndependentReviewAuthority(
                authority_id="final-implementation-review",
                provenance_policy_sha256=common["provenance"].policy.policy_sha256,
                subject_sha256=subject.subject_sha256,
                review_policy=ReviewPolicy(min_critics=2, min_providers=2),
                critics=critics,
                judge=provenance_signer("judge", judge_key.public_key()),
                issued_at=NOW + timedelta(minutes=9),
                expires_at=NOW + timedelta(minutes=40),
            ),
            "creator",
            helper.fixture.creator_key,
        )
        assessments = tuple(
            sign_critic_assessment(
                G4CriticAssessment(
                    authority_sha256=authority.artifact_sha256,
                    subject_sha256=subject.subject_sha256,
                    result=CriticResult(
                        critic=enrolled.critic,
                        status="completed",
                        critique=Critique(findings=()),
                    ),
                    assessed_at=NOW + timedelta(minutes=10 + index),
                    full_subject_review_claimed=True,
                ),
                enrolled.signer.signer_id,
                key,
            )
            for index, (enrolled, key) in enumerate(zip(critics, keys, strict=True))
        )
        judge = sign_judge_assessment(
            G4JudgeAssessment(
                authority_sha256=authority.artifact_sha256,
                subject_sha256=subject.subject_sha256,
                critic_artifact_sha256s=tuple(
                    item.artifact_sha256 for item in assessments
                ),
                decision=JudgeDecision(rationale="No upheld findings."),
                assessed_at=NOW + timedelta(minutes=15),
            ),
            "judge",
            judge_key,
        )
        return common, {
            "subject": subject,
            "authority": authority,
            "critics": assessments,
            "judge": judge,
            "critic_keys": keys,
            "judge_key": judge_key,
            "creator_key": helper.fixture.creator_key,
        }

    def test_accepting_evidence_replays_but_never_authorizes_release(self) -> None:
        with TemporaryDirectory() as directory:
            common, signed = self._case(Path(directory))
            record = assess_independent_review(
                signed["subject"],
                common["provenance"],
                signed["authority"],
                signed["critics"],
                signed["judge"],
            )
            self.assertEqual(record.verdict.decision, "accept")
            self.assertTrue(record.independent_review_evidence_passed)
            self.assertFalse(record.independent_human_review_proven)
            self.assertFalse(record.acceptance_authorized)
            self.assertEqual(
                decode_review_artifact(
                    canonical_bytes(record), G4IndependentReviewRecord
                ),
                record,
            )
            verify_independent_review_record(record, **common)

    def test_plan_tamper_and_stale_suite_cannot_replay(self) -> None:
        with TemporaryDirectory() as directory:
            common, signed = self._case(Path(directory))
            record = assess_independent_review(
                signed["subject"],
                common["provenance"],
                signed["authority"],
                signed["critics"],
                signed["judge"],
            )
            common["approved_plan_path"].write_bytes(b"altered plan")
            with self.assertRaisesRegex(ValueError, "creator-approved bytes"):
                verify_independent_review_record(record, **common)
            common["approved_plan_path"].write_bytes(b"approved plan")
            common["final_receipt"] = common["final_receipt"].model_copy(
                update={"final_suites_passed": False}
            )
            with self.assertRaises(ValueError):
                verify_independent_review_record(record, **common)

    def test_wrong_critic_signature_and_missed_quorum_fail(self) -> None:
        with TemporaryDirectory() as directory:
            common, signed = self._case(Path(directory))
            critics = signed["critics"]
            wrong = sign_critic_assessment(
                critics[0].assessment, "critic-1", Ed25519PrivateKey.generate()
            )
            with self.assertRaisesRegex(ValueError, "not enrolled"):
                assess_independent_review(
                    signed["subject"],
                    common["provenance"],
                    signed["authority"],
                    (wrong, critics[1]),
                    signed["judge"],
                )
            failed = sign_critic_assessment(
                critics[0].assessment.model_copy(
                    update={
                        "result": CriticResult(
                            critic=critics[0].assessment.result.critic,
                            status="error",
                            error="provider_error",
                        ),
                        "full_subject_review_claimed": False,
                    }
                ),
                "critic-1",
                signed["critic_keys"][0],
            )
            with self.assertRaisesRegex(ValueError, "quorum"):
                assess_independent_review(
                    signed["subject"],
                    common["provenance"],
                    signed["authority"],
                    (failed, critics[1]),
                    signed["judge"],
                )

    def test_citation_and_judge_lineage_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            common, signed = self._case(Path(directory))
            critics = signed["critics"]
            bad_finding = Finding(
                location="src/demo/__init__.py",
                category="correctness",
                impact="blocker",
                claim="Unsupported claim",
                evidence=Evidence(
                    source="diff",
                    quote="this is not in the exact Git diff",
                    explanation="No supporting source unit.",
                ),
            )
            changed = sign_critic_assessment(
                critics[0].assessment.model_copy(
                    update={
                        "result": CriticResult(
                            critic=critics[0].assessment.result.critic,
                            status="completed",
                            critique=Critique(findings=(bad_finding,)),
                        )
                    }
                ),
                "critic-1",
                signed["critic_keys"][0],
            )
            with self.assertRaises(ValueError):
                assess_independent_review(
                    signed["subject"],
                    common["provenance"],
                    signed["authority"],
                    (changed, critics[1]),
                    signed["judge"],
                )
            forged_judge = sign_judge_assessment(
                signed["judge"].assessment, "judge", Ed25519PrivateKey.generate()
            )
            with self.assertRaisesRegex(ValueError, "not enrolled"):
                assess_independent_review(
                    signed["subject"],
                    common["provenance"],
                    signed["authority"],
                    critics,
                    forged_judge,
                )

    def test_upheld_blocker_is_nonpassing_and_tied_to_exact_diff(self) -> None:
        with TemporaryDirectory() as directory:
            common, signed = self._case(Path(directory))
            critics = signed["critics"]
            raw_unit = (
                citation_bound_request(
                    signed["subject"].brief, critics[0].assessment.result.critic.persona
                )
                .citation_units[0]
                .id
            )
            finding = Finding(
                location="src/demo/__init__.py",
                category="correctness",
                impact="blocker",
                claim="Fixture blocker for verdict policy.",
                evidence=Evidence(
                    source="diff",
                    source_unit=raw_unit,
                    quote="return left + right",
                    explanation="The exact changed line is cited.",
                ),
            )
            first = sign_critic_assessment(
                critics[0].assessment.model_copy(
                    update={
                        "result": CriticResult(
                            critic=critics[0].assessment.result.critic,
                            status="completed",
                            critique=Critique(findings=(finding,)),
                        )
                    }
                ),
                "critic-1",
                signed["critic_keys"][0],
            )
            changed_critics = (first, critics[1])
            judge = sign_judge_assessment(
                signed["judge"].assessment.model_copy(
                    update={
                        "critic_artifact_sha256s": tuple(
                            item.artifact_sha256 for item in changed_critics
                        ),
                        "decision": JudgeDecision(
                            upheld=(finding.finding_id,),
                            rationale="Exact diff evidence sustains the blocker.",
                        ),
                    }
                ),
                "judge",
                signed["judge_key"],
            )
            record = assess_independent_review(
                signed["subject"],
                common["provenance"],
                signed["authority"],
                changed_critics,
                judge,
            )
            self.assertEqual(record.verdict.decision, "reject")
            self.assertFalse(record.independent_review_evidence_passed)
            verify_independent_review_record(record, **common)

    def test_external_review_roles_cannot_reuse_creator_key(self) -> None:
        with TemporaryDirectory() as directory:
            common, signed = self._case(Path(directory))
            grant = signed["authority"].authority
            first = grant.critics[0]
            reused = grant.model_copy(
                update={
                    "critics": (
                        first.model_copy(
                            update={
                                "signer": provenance_signer(
                                    "creator", signed["creator_key"].public_key()
                                )
                            }
                        ),
                        grant.critics[1],
                    )
                }
            )
            signed_authority = sign_review_authority(
                reused, "creator", signed["creator_key"]
            )
            with self.assertRaisesRegex(ValueError, "must differ"):
                assess_independent_review(
                    signed["subject"],
                    common["provenance"],
                    signed_authority,
                    signed["critics"],
                    signed["judge"],
                )

    def test_record_cannot_claim_acceptance(self) -> None:
        with TemporaryDirectory() as directory:
            common, signed = self._case(Path(directory))
            record = assess_independent_review(
                signed["subject"],
                common["provenance"],
                signed["authority"],
                signed["critics"],
                signed["judge"],
            )
            with self.assertRaises(ValidationError):
                G4IndependentReviewRecord.model_validate(
                    {**record.model_dump(), "acceptance_authorized": True}
                )

    def test_cli_assembles_and_verifies_record(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            common, signed = self._case(root)
            artifacts = {
                "candidate": common["candidate"],
                "provenance": common["provenance"],
                "controls": common["controls"],
                "binding": common["reviewer_binding"],
                "receipt": common["final_receipt"],
                "authority": signed["authority"],
                "judge": signed["judge"],
            }
            for name, artifact in artifacts.items():
                (root / f"{name}.json").write_bytes(canonical_bytes(artifact))
            for index, artifact in enumerate(signed["critics"], 1):
                (root / f"critic-{index}.json").write_bytes(canonical_bytes(artifact))
            common_args = [
                "--receipt",
                str(root / "receipt.json"),
                "--candidate",
                str(root / "candidate.json"),
                "--provenance",
                str(root / "provenance.json"),
                "--controls",
                str(root / "controls.json"),
                "--binding",
                str(root / "binding.json"),
                "--creator-package",
                str(common["creator_package_path"]),
                "--reviewer-package",
                str(common["reviewer_package_path"]),
                "--approved-plan",
                str(common["approved_plan_path"]),
                "--repository-root",
                str(common["repository_root"]),
                "--implementation-root",
                str(common["implementation_root"]),
                "--git",
                str(common["git_executable"]),
                "--candidate-dispatch-store",
                str(common["candidate_dispatch_store"]),
                "--final-dispatch-store",
                str(common["final_dispatch_store"]),
            ]
            output = root / "review-record.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "g4-assemble-independent-review",
                            *common_args,
                            "--authority",
                            str(root / "authority.json"),
                            "--critic",
                            str(root / "critic-1.json"),
                            "--critic",
                            str(root / "critic-2.json"),
                            "--judge",
                            str(root / "judge.json"),
                            "--output",
                            str(output),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "g4-verify-independent-review",
                            *common_args,
                            "--review-record",
                            str(output),
                        ]
                    ),
                    0,
                )
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
