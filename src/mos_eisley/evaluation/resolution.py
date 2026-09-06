"""Authenticated two-grader comparison and independent conflict resolution."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    AdjudicatorProvenance,
    FindingJudgment,
    GradingBatch,
    Judgment,
    validate_adjudication,
)
from mos_eisley.evaluation.agreement import AgreementReport, compare_adjudications
from mos_eisley.evaluation.authentication import (
    AuthenticatedAdjudication,
    GradingTrustPolicy,
    TrustedAdjudicator,
    verify_authenticated_adjudication,
)

_DOMAIN = b"mos-eisley/conflict-resolution/v1\x00"
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


class ResolutionTrustPolicy(Contract):
    schema_version: Literal[1] = 1
    policy_id: Identifier
    rubric_sha256: Digest
    resolvers: Annotated[
        tuple[TrustedAdjudicator, ...], Field(min_length=1, max_length=20)
    ]

    @model_validator(mode="after")
    def unique_identities_and_keys(self) -> Self:
        identities = tuple(item.adjudicator_id for item in self.resolvers)
        keys = tuple(item.public_key_sha256 for item in self.resolvers)
        if len(identities) != len(set(identities)) or len(keys) != len(set(keys)):
            raise ValueError(
                "resolution policy identities and public keys must be unique"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ResolvedFinding(Contract):
    sample_id: Digest
    judgment: FindingJudgment


class ResolutionSet(Contract):
    schema_version: Literal[1] = 1
    grading_batch_sha256: Digest
    grading_trust_policy_sha256: Digest
    resolution_trust_policy_sha256: Digest
    left_authenticated_adjudication_sha256: Digest
    right_authenticated_adjudication_sha256: Digest
    agreement_report_sha256: Digest
    resolver_id: Identifier
    rubric_sha256: Digest
    completed_at: Annotated[
        str,
        Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),
    ]
    resolutions: Annotated[
        tuple[ResolvedFinding, ...], Field(min_length=1, max_length=2_500_000)
    ]

    @field_validator("completed_at")
    @classmethod
    def valid_utc_timestamp(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as error:
            raise ValueError("completion time must be a valid UTC timestamp") from error
        return value

    @model_validator(mode="after")
    def unique_resolutions(self) -> Self:
        keys = tuple(
            (item.sample_id, item.judgment.finding_index) for item in self.resolutions
        )
        if len(keys) != len(set(keys)):
            raise ValueError("resolution decisions must be unique")
        return self

    @property
    def resolution_set_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ResolutionSignature(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    signer_id: Identifier
    public_key_sha256: Digest
    resolution_set_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedResolutionSet(Contract):
    schema_version: Literal[1] = 1
    resolution: ResolutionSet
    signature: ResolutionSignature

    @model_validator(mode="after")
    def bound_identity_and_content(self) -> Self:
        if (
            self.signature.signer_id != self.resolution.resolver_id
            or self.signature.resolution_set_sha256
            != self.resolution.resolution_set_sha256
        ):
            raise ValueError("signature does not identify this resolution set")
        return self

    @property
    def signed_resolution_sha256(self) -> str:
        return digest(canonical_bytes(self))


class DualGradingResolution(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["dual_authenticated_resolution"] = "dual_authenticated_resolution"
    grading_batch_sha256: Digest
    grading_trust_policy_sha256: Digest
    resolution_trust_policy_sha256: Digest
    left: AuthenticatedAdjudication
    right: AuthenticatedAdjudication
    agreement: AgreementReport
    signed_resolution: SignedResolutionSet | None
    resolved_judgments: Annotated[tuple[Judgment, ...], Field(max_length=50_000)]
    promotion_eligible: Literal[False] = False

    @model_validator(mode="after")
    def bound_sources(self) -> Self:
        left_adjudication = self.left.signed_adjudication.adjudication
        right_adjudication = self.right.signed_adjudication.adjudication
        resolution = (
            self.signed_resolution.resolution
            if self.signed_resolution is not None
            else None
        )
        if (
            self.left.grading_batch_sha256 != self.grading_batch_sha256
            or self.right.grading_batch_sha256 != self.grading_batch_sha256
            or self.left.trust_policy_sha256 != self.grading_trust_policy_sha256
            or self.right.trust_policy_sha256 != self.grading_trust_policy_sha256
            or self.agreement.grading_batch_sha256 != self.grading_batch_sha256
            or self.agreement.left_adjudication_sha256
            != left_adjudication.adjudication_sha256
            or self.agreement.right_adjudication_sha256
            != right_adjudication.adjudication_sha256
        ):
            raise ValueError("dual-grade artifact source binding mismatch")
        if bool(self.agreement.conflicts) != (resolution is not None):
            raise ValueError("dual-grade artifact resolution presence mismatch")
        if resolution is not None and (
            resolution.grading_batch_sha256 != self.grading_batch_sha256
            or resolution.grading_trust_policy_sha256
            != self.grading_trust_policy_sha256
            or resolution.resolution_trust_policy_sha256
            != self.resolution_trust_policy_sha256
            or resolution.left_authenticated_adjudication_sha256
            != self.left.authenticated_adjudication_sha256
            or resolution.right_authenticated_adjudication_sha256
            != self.right.authenticated_adjudication_sha256
            or resolution.agreement_report_sha256 != self.agreement.report_sha256
        ):
            raise ValueError("dual-grade artifact resolution binding mismatch")
        return self

    @property
    def dual_grading_resolution_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _message(resolution: ResolutionSet) -> bytes:
    return _DOMAIN + canonical_bytes(resolution)


def sign_resolution_set(
    resolution: ResolutionSet, signer_id: str, private_key: bytes
) -> SignedResolutionSet:
    """Sign canonical resolution bytes; callers retain private-key custody."""
    if signer_id != resolution.resolver_id:
        raise ValueError("signer identity differs from resolver")
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
    except (UnsupportedAlgorithm, ValueError):
        raise ValueError("Ed25519 signing unavailable or private key invalid") from None
    public_key = key.public_key().public_bytes_raw()
    return SignedResolutionSet(
        resolution=resolution,
        signature=ResolutionSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            resolution_set_sha256=resolution.resolution_set_sha256,
            signature_base64=base64.b64encode(key.sign(_message(resolution))).decode(
                "ascii"
            ),
        ),
    )


def _verify_resolution_signature(
    signed: SignedResolutionSet, policy: ResolutionTrustPolicy
) -> None:
    resolution = signed.resolution
    if (
        signed.signature.signer_id != resolution.resolver_id
        or signed.signature.resolution_set_sha256 != resolution.resolution_set_sha256
    ):
        raise ValueError("signature does not identify this resolution set")
    matches = [
        item
        for item in policy.resolvers
        if item.adjudicator_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("resolver is not trusted by this policy")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("signature public key differs from resolution policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _message(resolution),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError("resolution signature verification failed") from None


def _validate_separation(
    grading_policy: GradingTrustPolicy, resolution_policy: ResolutionTrustPolicy
) -> None:
    if grading_policy.rubric_sha256 != resolution_policy.rubric_sha256:
        raise ValueError("grading and resolution policies require the same rubric")
    grading_ids = {item.adjudicator_id for item in grading_policy.adjudicators}
    grading_keys = {item.public_key_sha256 for item in grading_policy.adjudicators}
    resolution_ids = {item.adjudicator_id for item in resolution_policy.resolvers}
    resolution_keys = {item.public_key_sha256 for item in resolution_policy.resolvers}
    if grading_ids & resolution_ids or grading_keys & resolution_keys:
        raise ValueError("grader and resolver trust policies must be disjoint")


def _conflict_keys(report: AgreementReport) -> set[tuple[str, int]]:
    return {(item.sample_id, item.finding_index) for item in report.conflicts}


def _resolved_judgments(
    batch: GradingBatch,
    left: AdjudicationSet,
    signed: SignedResolutionSet,
    report: AgreementReport,
) -> tuple[Judgment, ...]:
    resolution = signed.resolution
    expected = _conflict_keys(report)
    supplied = {
        (item.sample_id, item.judgment.finding_index): item.judgment
        for item in resolution.resolutions
    }
    if set(supplied) != expected:
        raise ValueError("resolution set must exactly cover grading conflicts")
    conflicts = {
        (item.sample_id, item.finding_index): item for item in report.conflicts
    }
    for key, decision in supplied.items():
        conflict = conflicts[key]
        if decision.finding_sha256 not in {
            conflict.left.finding_sha256,
            conflict.right.finding_sha256,
        }:
            raise ValueError("resolved finding content hash differs from conflict")
    judgments = tuple(
        judgment.model_copy(
            update={
                "findings": tuple(
                    supplied.get((judgment.sample_id, item.finding_index), item)
                    for item in judgment.findings
                )
            }
        )
        for judgment in left.judgments
    )
    combined = AdjudicationSet(
        grading_batch_sha256=batch.grading_batch_sha256,
        adjudicator=AdjudicatorProvenance(
            adjudicator_id=resolution.resolver_id,
            method="human",
            rubric_sha256=resolution.rubric_sha256,
            completed_at=resolution.completed_at,
        ),
        judgments=judgments,
    )
    validate_adjudication(batch, combined)
    return judgments


def resolve_authenticated_adjudications(
    batch: GradingBatch,
    left: AuthenticatedAdjudication,
    right: AuthenticatedAdjudication,
    grading_policy: GradingTrustPolicy,
    resolution_policy: ResolutionTrustPolicy,
    signed_resolution: SignedResolutionSet | None = None,
) -> DualGradingResolution:
    """Verify two grades and require an independent signature for every conflict."""
    verify_authenticated_adjudication(batch, left, grading_policy)
    verify_authenticated_adjudication(batch, right, grading_policy)
    _validate_separation(grading_policy, resolution_policy)
    left_signed = left.signed_adjudication
    right_signed = right.signed_adjudication
    if (
        left_signed.signature.signer_id == right_signed.signature.signer_id
        or left_signed.signature.public_key_sha256
        == right_signed.signature.public_key_sha256
    ):
        raise ValueError("dual grading requires distinct authenticated graders")
    report = compare_adjudications(
        batch, left_signed.adjudication, right_signed.adjudication
    )
    if report.rubric_sha256 != resolution_policy.rubric_sha256:
        raise ValueError("agreement rubric differs from resolution policy")
    if not report.conflicts:
        if signed_resolution is not None:
            raise ValueError("a resolution is prohibited when no conflicts exist")
        resolved = left_signed.adjudication.judgments
        validate_adjudication(batch, left_signed.adjudication)
    else:
        if signed_resolution is None:
            raise ValueError("authenticated resolution is required for conflicts")
        _verify_resolution_signature(signed_resolution, resolution_policy)
        resolution = signed_resolution.resolution
        if (
            resolution.grading_batch_sha256 != batch.grading_batch_sha256
            or resolution.grading_trust_policy_sha256 != grading_policy.policy_sha256
            or resolution.resolution_trust_policy_sha256
            != resolution_policy.policy_sha256
            or resolution.left_authenticated_adjudication_sha256
            != left.authenticated_adjudication_sha256
            or resolution.right_authenticated_adjudication_sha256
            != right.authenticated_adjudication_sha256
            or resolution.agreement_report_sha256 != report.report_sha256
            or resolution.rubric_sha256 != resolution_policy.rubric_sha256
        ):
            raise ValueError("resolution set source binding mismatch")
        if resolution.completed_at < max(
            left_signed.adjudication.adjudicator.completed_at,
            right_signed.adjudication.adjudicator.completed_at,
        ):
            raise ValueError("resolution cannot predate either adjudication")
        resolved = _resolved_judgments(
            batch, left_signed.adjudication, signed_resolution, report
        )
    return DualGradingResolution(
        grading_batch_sha256=batch.grading_batch_sha256,
        grading_trust_policy_sha256=grading_policy.policy_sha256,
        resolution_trust_policy_sha256=resolution_policy.policy_sha256,
        left=left,
        right=right,
        agreement=report,
        signed_resolution=signed_resolution,
        resolved_judgments=resolved,
    )


def verify_dual_grading_resolution(
    batch: GradingBatch,
    artifact: DualGradingResolution,
    grading_policy: GradingTrustPolicy,
    resolution_policy: ResolutionTrustPolicy,
) -> None:
    """Rebuild a stored result from its signed sources and independent policies."""
    rebuilt = resolve_authenticated_adjudications(
        batch,
        artifact.left,
        artifact.right,
        grading_policy,
        resolution_policy,
        artifact.signed_resolution,
    )
    if rebuilt != artifact:
        raise ValueError("dual-grade resolution provenance mismatch")
