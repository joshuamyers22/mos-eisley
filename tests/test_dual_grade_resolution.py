"""Dual grading preserves signed sources and isolates conflict authority."""

import base64
import io
import json
import stat
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.evaluation.adjudication import AdjudicationSet
from mos_eisley.evaluation.agreement import compare_adjudications
from mos_eisley.evaluation.authentication import (
    AuthenticatedAdjudication,
    GradingTrustPolicy,
    authenticate_adjudication,
    sign_adjudication,
    trusted_adjudicator,
)
from mos_eisley.evaluation.resolution import (
    DualGradingResolution,
    ResolutionSet,
    ResolutionSignature,
    ResolutionTrustPolicy,
    ResolvedFinding,
    SignedResolutionSet,
    resolve_authenticated_adjudications,
    sign_resolution_set,
    verify_dual_grading_resolution,
)
from mos_eisley.run.store import private_write
from tests.test_adjudication_agreement import packet, ratings, replace_decision


class DualGradeResolutionTests(TestCase):
    def setUp(self) -> None:
        self.batch = packet()
        self.left_key = Ed25519PrivateKey.generate()
        self.right_key = Ed25519PrivateKey.generate()
        self.resolver_key = Ed25519PrivateKey.generate()
        self.left_grade = ratings(self.batch, "grader-a")
        self.right_grade = ratings(self.batch, "grader-b")
        self.grading_policy = GradingTrustPolicy(
            policy_id="human-grading-v1",
            rubric_sha256=self.left_grade.adjudicator.rubric_sha256,
            adjudicators=(
                trusted_adjudicator(
                    "grader-a", self.left_key.public_key().public_bytes_raw()
                ),
                trusted_adjudicator(
                    "grader-b", self.right_key.public_key().public_bytes_raw()
                ),
            ),
        )
        self.resolution_policy = ResolutionTrustPolicy(
            policy_id="independent-resolution-v1",
            rubric_sha256=self.grading_policy.rubric_sha256,
            resolvers=(
                trusted_adjudicator(
                    "resolver-a", self.resolver_key.public_key().public_bytes_raw()
                ),
            ),
        )

    def authenticate(
        self,
        grade: AdjudicationSet,
        identity: str,
        signer: Ed25519PrivateKey,
    ) -> AuthenticatedAdjudication:
        return authenticate_adjudication(
            self.batch,
            sign_adjudication(grade, identity, signer.private_bytes_raw()),
            self.grading_policy,
        )

    def authenticated_pair(
        self, *, conflict: bool = False
    ) -> tuple[AuthenticatedAdjudication, AuthenticatedAdjudication]:
        right = self.right_grade
        if conflict:
            first = right.judgments[0].findings[0]
            right = replace_decision(
                right,
                first.model_copy(
                    update={
                        "disposition": "false_positive",
                        "expected_finding_ids": (),
                        "rationale": "This does not match the reference defect.",
                    }
                ),
            )
        return (
            self.authenticate(self.left_grade, "grader-a", self.left_key),
            self.authenticate(right, "grader-b", self.right_key),
        )

    def resolution_set(
        self,
        left: AuthenticatedAdjudication,
        right: AuthenticatedAdjudication,
    ) -> ResolutionSet:
        agreement = compare_adjudications(
            self.batch,
            left.signed_adjudication.adjudication,
            right.signed_adjudication.adjudication,
        )
        return ResolutionSet(
            grading_batch_sha256=self.batch.grading_batch_sha256,
            grading_trust_policy_sha256=self.grading_policy.policy_sha256,
            resolution_trust_policy_sha256=self.resolution_policy.policy_sha256,
            left_authenticated_adjudication_sha256=(
                left.authenticated_adjudication_sha256
            ),
            right_authenticated_adjudication_sha256=(
                right.authenticated_adjudication_sha256
            ),
            agreement_report_sha256=agreement.report_sha256,
            resolver_id="resolver-a",
            rubric_sha256=self.resolution_policy.rubric_sha256,
            completed_at="2026-09-05T13:00:00Z",
            resolutions=tuple(
                ResolvedFinding(
                    sample_id=conflict.sample_id,
                    judgment=conflict.left.model_copy(
                        update={"rationale": "Independent review supports this label."}
                    ),
                )
                for conflict in agreement.conflicts
            ),
        )

    def signed_resolution(
        self,
        left: AuthenticatedAdjudication,
        right: AuthenticatedAdjudication,
    ) -> SignedResolutionSet:
        return sign_resolution_set(
            self.resolution_set(left, right),
            "resolver-a",
            self.resolver_key.private_bytes_raw(),
        )

    def test_exact_agreement_preserves_both_receipts_without_resolution(self) -> None:
        left, right = self.authenticated_pair()
        artifact = resolve_authenticated_adjudications(
            self.batch,
            left,
            right,
            self.grading_policy,
            self.resolution_policy,
        )
        self.assertEqual(artifact.left, left)
        self.assertEqual(artifact.right, right)
        self.assertEqual(artifact.signed_resolution, None)
        self.assertEqual(artifact.resolved_judgments, self.left_grade.judgments)
        self.assertFalse(artifact.promotion_eligible)
        verify_dual_grading_resolution(
            self.batch, artifact, self.grading_policy, self.resolution_policy
        )
        with self.assertRaisesRegex(ValueError, "prohibited"):
            resolve_authenticated_adjudications(
                self.batch,
                left,
                right,
                self.grading_policy,
                self.resolution_policy,
                sign_resolution_set(
                    self.resolution_set(*self.authenticated_pair(conflict=True)),
                    "resolver-a",
                    self.resolver_key.private_bytes_raw(),
                ),
            )

    def test_every_conflict_requires_a_valid_independent_resolution(self) -> None:
        left, right = self.authenticated_pair(conflict=True)
        with self.assertRaisesRegex(ValueError, "required for conflicts"):
            resolve_authenticated_adjudications(
                self.batch,
                left,
                right,
                self.grading_policy,
                self.resolution_policy,
            )
        signed = self.signed_resolution(left, right)
        artifact = resolve_authenticated_adjudications(
            self.batch,
            left,
            right,
            self.grading_policy,
            self.resolution_policy,
            signed,
        )
        self.assertEqual(len(artifact.agreement.conflicts), 1)
        self.assertEqual(
            artifact.resolved_judgments[0].findings[0].rationale,
            "Independent review supports this label.",
        )
        verify_dual_grading_resolution(
            self.batch, artifact, self.grading_policy, self.resolution_policy
        )

    def test_graders_and_resolvers_are_cryptographically_separate(self) -> None:
        left, right = self.authenticated_pair()
        overlapping_id = ResolutionTrustPolicy(
            policy_id="bad-resolution-id",
            rubric_sha256=self.grading_policy.rubric_sha256,
            resolvers=(
                trusted_adjudicator(
                    "grader-a", self.resolver_key.public_key().public_bytes_raw()
                ),
            ),
        )
        overlapping_key = ResolutionTrustPolicy(
            policy_id="bad-resolution-key",
            rubric_sha256=self.grading_policy.rubric_sha256,
            resolvers=(
                trusted_adjudicator(
                    "resolver-a", self.left_key.public_key().public_bytes_raw()
                ),
            ),
        )
        for policy in (overlapping_id, overlapping_key):
            with (
                self.subTest(policy=policy.policy_id),
                self.assertRaisesRegex(ValueError, "disjoint"),
            ):
                resolve_authenticated_adjudications(
                    self.batch, left, right, self.grading_policy, policy
                )
        with self.assertRaisesRegex(ValueError, "distinct authenticated graders"):
            resolve_authenticated_adjudications(
                self.batch,
                left,
                left,
                self.grading_policy,
                self.resolution_policy,
            )

    def test_resolution_rejects_missing_extra_or_invalid_decisions(self) -> None:
        left, right = self.authenticated_pair(conflict=True)
        source = self.resolution_set(left, right)
        decision = source.resolutions[0]
        variants = (
            source.model_copy(update={"resolutions": ()}),
            source.model_copy(
                update={
                    "resolutions": (
                        decision,
                        decision.model_copy(
                            update={
                                "sample_id": "f" * 64,
                            }
                        ),
                    )
                }
            ),
            source.model_copy(
                update={
                    "resolutions": (
                        decision.model_copy(
                            update={
                                "judgment": decision.judgment.model_copy(
                                    update={"finding_sha256": "f" * 64}
                                )
                            }
                        ),
                    )
                }
            ),
            source.model_copy(
                update={
                    "resolutions": (
                        decision.model_copy(
                            update={
                                "judgment": decision.judgment.model_copy(
                                    update={
                                        "disposition": "unresolved",
                                        "expected_finding_ids": (),
                                    }
                                )
                            }
                        ),
                    )
                }
            ),
        )
        for variant in variants:
            signed = sign_resolution_set(
                variant, "resolver-a", self.resolver_key.private_bytes_raw()
            )
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                resolve_authenticated_adjudications(
                    self.batch,
                    left,
                    right,
                    self.grading_policy,
                    self.resolution_policy,
                    signed,
                )

    def test_source_order_policy_and_signature_tampering_fail_closed(self) -> None:
        left, right = self.authenticated_pair(conflict=True)
        signed = self.signed_resolution(left, right)
        changed_policy = self.resolution_policy.model_copy(
            update={"policy_id": "changed-resolution-policy"}
        )
        wrong_signature = signed.model_copy(
            update={
                "signature": signed.signature.model_copy(
                    update={
                        "signature_base64": base64.b64encode(
                            self.resolver_key.sign(canonical_bytes(signed.resolution))
                        ).decode("ascii")
                    }
                )
            }
        )
        cases = (
            (right, left, self.resolution_policy, signed),
            (left, right, changed_policy, signed),
            (left, right, self.resolution_policy, wrong_signature),
        )
        for first, second, policy, candidate in cases:
            with self.subTest(policy=policy.policy_id), self.assertRaises(ValueError):
                resolve_authenticated_adjudications(
                    self.batch,
                    first,
                    second,
                    self.grading_policy,
                    policy,
                    candidate,
                )
        predating = self.resolution_set(left, right).model_copy(
            update={"completed_at": "2026-09-05T11:59:59Z"}
        )
        with self.assertRaisesRegex(ValueError, "predate"):
            resolve_authenticated_adjudications(
                self.batch,
                left,
                right,
                self.grading_policy,
                self.resolution_policy,
                sign_resolution_set(
                    predating, "resolver-a", self.resolver_key.private_bytes_raw()
                ),
            )

    def test_resolution_contract_rejects_bad_timestamp_duplicate_and_encoding(
        self,
    ) -> None:
        left, right = self.authenticated_pair(conflict=True)
        source = self.resolution_set(left, right)
        value = source.model_dump(mode="json")
        value["completed_at"] = "2026-02-30T00:00:00Z"
        with self.assertRaises(ValidationError):
            ResolutionSet.model_validate(value)
        value = source.model_dump(mode="json")
        value["resolutions"].append(value["resolutions"][0])
        with self.assertRaises(ValidationError):
            ResolutionSet.model_validate(value)
        with self.assertRaises(ValidationError):
            ResolutionSignature(
                signer_id="resolver-a",
                public_key_sha256="a" * 64,
                resolution_set_sha256="b" * 64,
                signature_base64="!" * 88,
            )
        with self.assertRaises(ValidationError):
            ResolutionTrustPolicy(
                policy_id="duplicate-resolver-key",
                rubric_sha256=self.grading_policy.rubric_sha256,
                resolvers=(
                    self.resolution_policy.resolvers[0],
                    self.resolution_policy.resolvers[0].model_copy(
                        update={"adjudicator_id": "resolver-b"}
                    ),
                ),
            )

    def test_reverification_rejects_tampered_derived_result(self) -> None:
        left, right = self.authenticated_pair(conflict=True)
        artifact = resolve_authenticated_adjudications(
            self.batch,
            left,
            right,
            self.grading_policy,
            self.resolution_policy,
            self.signed_resolution(left, right),
        )
        first = artifact.resolved_judgments[0].findings[0]
        tampered = artifact.model_copy(
            update={
                "resolved_judgments": (
                    artifact.resolved_judgments[0].model_copy(
                        update={
                            "findings": (
                                first.model_copy(update={"rationale": "Tampered."}),
                                *artifact.resolved_judgments[0].findings[1:],
                            )
                        }
                    ),
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            verify_dual_grading_resolution(
                self.batch, tampered, self.grading_policy, self.resolution_policy
            )

    def test_cli_writes_private_reverifiable_artifact_without_private_keys(
        self,
    ) -> None:
        left, right = self.authenticated_pair(conflict=True)
        signed = self.signed_resolution(left, right)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            values = {
                "batch": self.batch,
                "left": left,
                "right": right,
                "grading_policy": self.grading_policy,
                "resolution_policy": self.resolution_policy,
                "resolution": signed,
            }
            paths = {name: root / f"{name}.json" for name in values}
            output = root / "dual-resolution.json"
            for name, value in values.items():
                private_write(paths[name], canonical_bytes(value))
            arguments = [
                "eval-resolve-adjudications",
                "--grading-batch",
                str(paths["batch"]),
                "--left-authenticated",
                str(paths["left"]),
                "--right-authenticated",
                str(paths["right"]),
                "--grading-trust-policy",
                str(paths["grading_policy"]),
                "--resolution-trust-policy",
                str(paths["resolution_policy"]),
                "--signed-resolution",
                str(paths["resolution"]),
                "--output",
                str(output),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(arguments), 0)
            event = json.loads(stdout.getvalue())
            artifact = DualGradingResolution.model_validate_json(output.read_bytes())
            self.assertEqual(
                event["dual_grading_resolution_sha256"],
                artifact.dual_grading_resolution_sha256,
            )
            self.assertEqual(event["conflicts"], 1)
            self.assertFalse(event["promotion_eligible"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            verify_dual_grading_resolution(
                self.batch, artifact, self.grading_policy, self.resolution_policy
            )
            for key in (self.left_key, self.right_key, self.resolver_key):
                private_key = key.private_bytes_raw()
                self.assertNotIn(private_key, output.read_bytes())
                self.assertNotIn(base64.b64encode(private_key), output.read_bytes())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)


class ResolutionSigningTests(TestCase):
    def test_signing_rejects_wrong_identity_and_private_key(self) -> None:
        tests = DualGradeResolutionTests()
        tests.setUp()
        left, right = tests.authenticated_pair(conflict=True)
        resolution = tests.resolution_set(left, right)
        with self.assertRaisesRegex(ValueError, "identity"):
            sign_resolution_set(
                resolution,
                "different-resolver",
                tests.resolver_key.private_bytes_raw(),
            )
        with self.assertRaisesRegex(ValueError, "private key"):
            sign_resolution_set(resolution, "resolver-a", b"short")

    def test_signed_resolution_binds_identity_and_content(self) -> None:
        tests = DualGradeResolutionTests()
        tests.setUp()
        left, right = tests.authenticated_pair(conflict=True)
        resolution = tests.resolution_set(left, right)
        signed = tests.signed_resolution(left, right)
        value = signed.model_dump(mode="json")
        value["signature"]["resolution_set_sha256"] = "0" * 64
        with self.assertRaises(ValidationError):
            SignedResolutionSet.model_validate(value)
        value = signed.model_dump(mode="json")
        value["signature"]["signer_id"] = "different-resolver"
        with self.assertRaises(ValidationError):
            SignedResolutionSet.model_validate(value)
        self.assertEqual(
            signed.resolution.resolution_set_sha256,
            resolution.resolution_set_sha256,
        )
