"""One-owner G4 review cannot be confused with independent-signer evidence."""

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

import test_reviewer_independent_review as independent_fixture
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_reviewer_provenance import NOW, G4ProvenanceFixture

from mos_eisley.cli import main
from mos_eisley.core.models import (
    CriticResult,
    CriticSpec,
    Critique,
    JudgeDecision,
    JudgeRequest,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.review.citations import citation_bound_request
from mos_eisley.reviewer_single_operator_review import (
    G4SingleOperatorCriticObservation,
    G4SingleOperatorJudgeObservation,
    G4SingleOperatorReviewAuthority,
    G4SingleOperatorReviewDecision,
    G4SingleOperatorReviewRecord,
    assess_single_operator_review,
    sign_single_operator_review_authority,
    sign_single_operator_review_decision,
)


class G4SingleOperatorReviewTests(unittest.TestCase):
    def _case(self, root: Path) -> tuple[dict[str, Any], tuple[Any, ...]]:
        def fixture(path: Path) -> G4ProvenanceFixture:
            return G4ProvenanceFixture(path, single_operator=True)

        with patch(
            "test_reviewer_candidate_execution.G4ProvenanceFixture",
            side_effect=fixture,
        ):
            common, previous = independent_fixture.G4IndependentReviewTests()._case(
                root
            )
        subject = previous["subject"]
        provenance = common["provenance"]
        owner_key = previous["creator_key"]
        common["creator_key"] = owner_key
        specs = (
            CriticSpec(
                id="anthropic-critic",
                provider="anthropic",
                model="claude-sonnet-5",
                persona="Independently inspect the complete G4 subject.",
            ),
            CriticSpec(
                id="openai-critic",
                provider="openai",
                model="gpt-5.6-luna",
                persona="Adversarially inspect the complete G4 subject.",
            ),
        )
        requests = tuple(
            citation_bound_request(subject.brief, s.persona) for s in specs
        )
        signed_authority = sign_single_operator_review_authority(
            G4SingleOperatorReviewAuthority(
                authority_id="g4-one-human-two-model-providers",
                provenance_policy_sha256=provenance.policy.policy_sha256,
                subject_sha256=subject.subject_sha256,
                review_policy=ReviewPolicy(min_critics=2, min_providers=2),
                critics=specs,
                critic_request_sha256s=tuple(
                    digest(canonical_bytes(item)) for item in requests
                ),
                judge_provider="openai",
                judge_model="gpt-5.6-luna",
                issued_at=NOW + timedelta(minutes=9),
                expires_at=NOW + timedelta(minutes=40),
            ),
            "creator",
            owner_key,
        )
        critics = tuple(
            G4SingleOperatorCriticObservation(
                result=CriticResult(
                    critic=spec,
                    status="completed",
                    critique=Critique(findings=()),
                ),
                request_sha256=digest(canonical_bytes(request)),
                response_sha256=digest(f"response-{index}".encode()),
                audit_sha256=digest(f"audit-{index}".encode()),
                observed_at=NOW + timedelta(minutes=10 + index),
                full_subject_review_claimed=True,
            )
            for index, (spec, request) in enumerate(zip(specs, requests, strict=True))
        )
        judge_request = JudgeRequest(brief=subject.brief, findings=())
        judge = G4SingleOperatorJudgeObservation(
            provider="openai",
            model="gpt-5.6-luna",
            request_sha256=digest(canonical_bytes(judge_request)),
            response_sha256=digest(b"judge response"),
            audit_sha256=digest(b"judge audit"),
            decision=JudgeDecision(rationale="No upheld findings."),
            observed_at=NOW + timedelta(minutes=15),
        )
        from mos_eisley.review.pipeline import judge_verdict

        signed_decision = sign_single_operator_review_decision(
            G4SingleOperatorReviewDecision(
                authority_sha256=signed_authority.artifact_sha256,
                subject_sha256=subject.subject_sha256,
                critic_artifact_sha256s=tuple(item.artifact_sha256 for item in critics),
                judge_artifact_sha256=judge.artifact_sha256,
                verdict=judge_verdict(judge_request, judge.decision),
                decided_at=NOW + timedelta(minutes=16),
            ),
            "creator",
            owner_key,
        )
        return common, (
            subject,
            provenance,
            signed_authority,
            critics,
            judge,
            signed_decision,
        )

    def test_accept_is_only_owner_attested(self) -> None:
        with TemporaryDirectory() as directory:
            _, case = self._case(Path(directory))
            record = assess_single_operator_review(*case)
            self.assertEqual(record.decision.decision.verdict.decision, "accept")
            self.assertTrue(record.single_operator_review_evidence_passed)
            self.assertFalse(record.independent_review_evidence_passed)
            self.assertFalse(record.independent_human_review_proven)
            self.assertFalse(record.provider_operation_proven)
            self.assertFalse(record.acceptance_authorized)
            self.assertEqual(
                G4SingleOperatorReviewRecord.model_validate_json(
                    canonical_bytes(record)
                ),
                record,
            )

    def test_changed_critic_observation_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            _, case = self._case(Path(directory))
            subject, provenance, authority, critics, judge, decision = case
            tampered = critics[0].model_copy(
                update={"response_sha256": digest(b"another response")}
            )
            with self.assertRaisesRegex(ValueError, "exact review evidence"):
                assess_single_operator_review(
                    subject,
                    provenance,
                    authority,
                    (tampered, critics[1]),
                    judge,
                    decision,
                )

    def test_other_human_key_cannot_sign_decision(self) -> None:
        with TemporaryDirectory() as directory:
            _, case = self._case(Path(directory))
            subject, provenance, authority, critics, judge, decision = case
            foreign = sign_single_operator_review_decision(
                decision.decision, "creator", Ed25519PrivateKey.generate()
            )
            with self.assertRaisesRegex(ValueError, "creator signer is not enrolled"):
                assess_single_operator_review(
                    subject, provenance, authority, critics, judge, foreign
                )

    def test_one_provider_family_does_not_meet_quorum(self) -> None:
        with TemporaryDirectory() as directory:
            _, case = self._case(Path(directory))
            subject, provenance, authority, critics, judge, decision = case
            errored = G4SingleOperatorCriticObservation(
                result=CriticResult(
                    critic=critics[0].result.critic,
                    status="error",
                    error="provider_error",
                ),
                request_sha256=critics[0].request_sha256,
                observed_at=critics[0].observed_at,
                full_subject_review_claimed=False,
            )
            with self.assertRaisesRegex(ValueError, "quorum"):
                assess_single_operator_review(
                    subject,
                    provenance,
                    authority,
                    (errored, critics[1]),
                    judge,
                    decision,
                )

    def test_cli_assembles_and_replays_single_operator_record(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            common, case = self._case(root)
            _, _, authority, critics, judge, decision = case
            artifacts = {
                "candidate": common["candidate"],
                "provenance": common["provenance"],
                "controls": common["controls"],
                "binding": common["reviewer_binding"],
                "receipt": common["final_receipt"],
                "authority": authority,
                "judge": judge,
                "decision": decision,
            }
            for name, artifact in artifacts.items():
                (root / f"{name}.json").write_bytes(canonical_bytes(artifact))
            for index, artifact in enumerate(critics, 1):
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
            output = root / "single-operator-record.json"
            captured = io.StringIO()
            with redirect_stdout(captured):
                self.assertEqual(
                    main(
                        [
                            "g4-assemble-single-operator-review",
                            *common_args,
                            "--authority",
                            str(root / "authority.json"),
                            "--critic",
                            str(root / "critic-1.json"),
                            "--critic",
                            str(root / "critic-2.json"),
                            "--judge",
                            str(root / "judge.json"),
                            "--decision",
                            str(root / "decision.json"),
                            "--output",
                            str(output),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "g4-verify-single-operator-review",
                            *common_args,
                            "--review-record",
                            str(output),
                        ]
                    ),
                    0,
                )
            self.assertIn(
                '"independent_review_evidence_passed": false', captured.getvalue()
            )
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
