"""Independent, one-use authorization for an exact quarantined skill package."""

from __future__ import annotations

import base64
import binascii
import os
import sqlite3
import stat
from collections.abc import Generator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.skills import SkillIdentity, SkillPackageArchive
from mos_eisley.evaluation.models import EvaluationDataset, SweepPlan
from mos_eisley.evaluation.skill_comparison import (
    SealedSkillComparison,
    SkillComparisonReport,
    SkillHoldoutUseClaim,
)
from mos_eisley.evaluation.skill_promotion import (
    AuthenticatedSkillPromotion,
    SkillEvaluationLineage,
    SkillPromotionAuthorityPolicy,
)
from mos_eisley.run.skill_release import SkillReleaseEvidence
from mos_eisley.run.skill_release_control import (
    AuthenticatedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillReleaseControlAuthorityPolicy,
    authenticate_skill_release_control,
    verify_authenticated_skill_release_control,
)
from mos_eisley.run.skill_staging import SkillStagingManifest, SkillStagingStore

_DOMAIN = b"mos-eisley/skill-installation/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class TrustedSkillInstallationAuthority(Contract):
    authority_id: Identifier
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: EncodedKey

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode(self.public_key_base64, 32, "public key")
        return self

    @property
    def public_key_sha256(self) -> str:
        return digest(_decode(self.public_key_base64, 32, "public key"))


class SkillInstallationAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_installation_authority_policy"] = (
        "skill_installation_authority_policy"
    )
    policy_id: Identifier
    staging_store_policy_sha256: Digest
    control_anchor_policy_sha256: Digest
    claim_store_id: Digest
    installation_target_id: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_decision_lifetime_seconds: Annotated[int, Field(gt=0, le=86_400)]
    authorities: Annotated[
        tuple[TrustedSkillInstallationAuthority, ...],
        Field(min_length=1, max_length=20),
    ]
    may_authorize_installation: Literal[True] = True
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("skill installation authority window must be positive")
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "skill installation authorities need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillInstallationDecision(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_installation_decision"] = "skill_installation_decision"
    authority_policy_sha256: Digest
    staging_store_policy_sha256: Digest
    staging_manifest_sha256: Digest
    control_anchor_policy_sha256: Digest
    control_anchor_entry_sha256: Digest
    signed_control_sha256: Digest
    release_evidence_sha256: Digest
    claim_store_id: Digest
    installation_target_id: Digest
    action: Literal["candidate", "rollback"]
    archive_sha256: Digest
    skill: SkillIdentity
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    one_use_required: Literal[True] = True
    installation_authorized: Literal[True] = True
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("skill installation decision window must be positive")
        if self.skill.kind != "persona":
            raise ValueError("skill installation requires a persona skill")
        return self

    @property
    def decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillInstallationSignature(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    signer_id: Identifier
    public_key_sha256: Digest
    decision_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedSkillInstallationDecision(Contract):
    schema_version: Literal[1] = 1
    decision: SkillInstallationDecision
    signature: SkillInstallationSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.decision_sha256 != self.decision.decision_sha256:
            raise ValueError("signature does not identify this skill installation")
        return self

    @property
    def signed_decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedSkillInstallation(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["authenticated_skill_installation"] = (
        "authenticated_skill_installation"
    )
    authority_policy_sha256: Digest
    staging_manifest_sha256: Digest
    archive_sha256: Digest
    skill: SkillIdentity
    claim_store_id: Digest
    installation_target_id: Digest
    signed_decision: SignedSkillInstallationDecision
    authenticated_at: UtcTimestamp
    valid_until: UtcTimestamp
    one_use_required: Literal[True] = True
    installation_authorized: Literal[True] = True
    installation_performed: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @field_validator("authenticated_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_sources(self) -> Self:
        decision = self.signed_decision.decision
        if (
            self.authority_policy_sha256 != decision.authority_policy_sha256
            or self.staging_manifest_sha256 != decision.staging_manifest_sha256
            or self.archive_sha256 != decision.archive_sha256
            or self.skill != decision.skill
            or self.claim_store_id != decision.claim_store_id
            or self.installation_target_id != decision.installation_target_id
            or self.valid_until != decision.valid_until
            or not decision.issued_at <= self.authenticated_at < self.valid_until
        ):
            raise ValueError("authenticated skill installation source mismatch")
        return self

    @property
    def authorization_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def check_current(self, now: datetime) -> None:
        current = _require_utc(now)
        if not self.authenticated_at <= current < self.valid_until:
            raise ValueError("skill installation authorization is not current")


class SkillInstallationClaimStorePolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_installation_claim_store_policy"] = (
        "skill_installation_claim_store_policy"
    )
    store_id: Digest
    authority_policy_sha256: Digest
    max_claims: Annotated[int, Field(ge=1, le=100_000)] = 10_000
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillInstallationClaim(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_installation_claim"] = "skill_installation_claim"
    claim_store_policy_sha256: Digest
    authorization_sha256: Digest
    decision_sha256: Digest
    archive_sha256: Digest
    installation_target_id: Digest
    claimed_at: UtcTimestamp
    authorization_consumed: Literal[True] = True
    installation_performed: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @field_validator("claimed_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @property
    def claim_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillInstallationClaimStoreSnapshot(Contract):
    schema_version: Literal[1] = 1
    policy: SkillInstallationClaimStorePolicy
    claims: Annotated[tuple[SkillInstallationClaim, ...], Field(max_length=100_000)]

    @model_validator(mode="after")
    def canonical_claims(self) -> Self:
        identities = tuple(item.decision_sha256 for item in self.claims)
        if tuple(sorted(set(identities))) != identities:
            raise ValueError("skill installation claims must be unique and sorted")
        return self

    @property
    def snapshot_sha256(self) -> str:
        return digest(canonical_bytes(self))


def trusted_skill_installation_authority(
    authority_id: str, public_key: bytes
) -> TrustedSkillInstallationAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain exactly 32 bytes")
    return TrustedSkillInstallationAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def sign_skill_installation_decision(
    decision: SkillInstallationDecision,
    signer_id: str,
    private_key: bytes,
) -> SignedSkillInstallationDecision:
    """Sign canonical installation authority; the CLI never accepts private keys."""
    decision = SkillInstallationDecision.model_validate_json(canonical_bytes(decision))
    try:
        signer = Ed25519PrivateKey.from_private_bytes(private_key)
    except (UnsupportedAlgorithm, ValueError):
        raise ValueError("Ed25519 signing unavailable or private key invalid") from None
    public_key = signer.public_key().public_bytes_raw()
    return SignedSkillInstallationDecision(
        decision=decision,
        signature=SkillInstallationSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            decision_sha256=decision.decision_sha256,
            signature_base64=base64.b64encode(
                signer.sign(_DOMAIN + canonical_bytes(decision))
            ).decode("ascii"),
        ),
    )


def verify_signed_skill_installation_decision(
    signed: SignedSkillInstallationDecision,
    policy: SkillInstallationAuthorityPolicy,
) -> TrustedSkillInstallationAuthority:
    signed = SignedSkillInstallationDecision.model_validate_json(
        canonical_bytes(signed)
    )
    policy = SkillInstallationAuthorityPolicy.model_validate_json(
        canonical_bytes(policy)
    )
    decision = signed.decision
    if decision.authority_policy_sha256 != policy.policy_sha256:
        raise ValueError("skill installation authority policy differs")
    if not (
        policy.valid_from
        <= decision.issued_at
        < decision.valid_until
        <= policy.valid_until
    ):
        raise ValueError("skill installation window exceeds its authority policy")
    if (
        decision.valid_until - decision.issued_at
    ).total_seconds() > policy.max_decision_lifetime_seconds:
        raise ValueError("skill installation decision exceeds its maximum lifetime")
    matches = [
        item
        for item in policy.authorities
        if item.authority_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("signer is not trusted by the skill installation policy")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("signature key differs from skill installation policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(decision),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError("skill installation signature verification failed") from None
    return trusted


def _validate_authority_separation(
    installation_policy: SkillInstallationAuthorityPolicy,
    control_policy: SkillReleaseControlAuthorityPolicy,
    promotion_policy: SkillPromotionAuthorityPolicy,
    lineages: tuple[SkillEvaluationLineage, SkillEvaluationLineage],
) -> None:
    excluded_ids = {item.authority_id for item in control_policy.authorities}
    excluded_keys = {item.public_key_sha256 for item in control_policy.authorities}
    excluded_ids |= {item.authority_id for item in promotion_policy.authorities}
    excluded_keys |= {item.public_key_sha256 for item in promotion_policy.authorities}
    excluded_ids |= {
        item.adjudicator_id for lineage in lineages for item in lineage[5].adjudicators
    } | {item.adjudicator_id for lineage in lineages for item in lineage[6].resolvers}
    excluded_keys |= {
        item.public_key_sha256
        for lineage in lineages
        for item in lineage[5].adjudicators
    } | {
        item.public_key_sha256 for lineage in lineages for item in lineage[6].resolvers
    }
    if any(
        item.authority_id in excluded_ids or item.public_key_sha256 in excluded_keys
        for item in installation_policy.authorities
    ):
        raise ValueError(
            "skill installation authority must be independent of release control, "
            "promotion, and evaluation"
        )


def _verified_selection(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    staging_store: SkillStagingStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    action: Literal["candidate", "rollback"],
    now: datetime,
) -> tuple[
    SkillStagingManifest,
    SkillPackageArchive,
    AuthenticatedSkillReleaseControl,
]:
    current = _require_utc(now)
    verify_authenticated_skill_release_control(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
    )
    current_control = authenticate_skill_release_control(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control.signed_control,
        control_policy,
        control.rollback_archive,
        current,
    )
    _validate_authority_separation(
        installation_policy,
        control_policy,
        promotion_policy,
        (calibration, holdout),
    )
    if (
        installation_policy.staging_store_policy_sha256
        != staging_store.policy.policy_sha256
        or installation_policy.control_anchor_policy_sha256
        != anchor.policy.policy_sha256
        or staging_store.policy.control_anchor_policy_sha256
        != anchor.policy.policy_sha256
    ):
        raise ValueError("skill installation policy does not match staging or control")
    selected = archive if action == "candidate" else current_control.rollback_archive
    if action == "candidate" and not current_control.release_allowed:
        raise ValueError("candidate installation requires an allowed release")
    if action == "rollback" and not current_control.release_revoked:
        raise ValueError("rollback installation requires a revoked release")
    if selected is None:
        raise ValueError("skill installation control has no rollback archive")
    manifest, staged_archive = staging_store.load(selected.archive_sha256)
    if (
        staged_archive != selected
        or manifest.intent.action != action
        or manifest.intent.release_evidence_sha256 != evidence.release_evidence_sha256
        or manifest.intent.skill != selected.descriptor.identity
    ):
        raise ValueError("staged skill package does not match installation sources")
    return manifest, staged_archive, current_control


def make_skill_installation_decision(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    staging_store: SkillStagingStore,
    installation_policy: SkillInstallationAuthorityPolicy,
    action: Literal["candidate", "rollback"],
    issued_at: datetime,
    valid_until: datetime,
) -> SkillInstallationDecision:
    """Derive an exact, externally signable installation decision."""
    issued = _require_utc(issued_at)
    expires = _require_utc(valid_until)
    manifest, selected, current_control = _verified_selection(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        staging_store,
        installation_policy,
        action,
        issued,
    )
    if not (
        installation_policy.valid_from
        <= issued
        < expires
        <= installation_policy.valid_until
        and expires <= current_control.valid_until
        and expires <= evidence.valid_until
    ):
        raise ValueError("skill installation window exceeds a source validity window")
    if (
        expires - issued
    ).total_seconds() > installation_policy.max_decision_lifetime_seconds:
        raise ValueError("skill installation decision exceeds its maximum lifetime")
    with anchor.guard_latest(current_control, control_policy, issued) as anchored:
        return SkillInstallationDecision(
            authority_policy_sha256=installation_policy.policy_sha256,
            staging_store_policy_sha256=staging_store.policy.policy_sha256,
            staging_manifest_sha256=manifest.manifest_sha256,
            control_anchor_policy_sha256=anchor.policy.policy_sha256,
            control_anchor_entry_sha256=anchored.anchor_entry_sha256,
            signed_control_sha256=current_control.signed_control.signed_control_sha256,
            release_evidence_sha256=evidence.release_evidence_sha256,
            claim_store_id=installation_policy.claim_store_id,
            installation_target_id=installation_policy.installation_target_id,
            action=action,
            archive_sha256=selected.archive_sha256,
            skill=selected.descriptor.identity,
            issued_at=issued,
            valid_until=expires,
        )


def authenticate_skill_installation(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    staging_store: SkillStagingStore,
    signed: SignedSkillInstallationDecision,
    installation_policy: SkillInstallationAuthorityPolicy,
    action: Literal["candidate", "rollback"],
    now: datetime,
) -> AuthenticatedSkillInstallation:
    """Reverify the full lineage, exact staging bytes, latest state, and signature."""
    current = _require_utc(now)
    verify_signed_skill_installation_decision(signed, installation_policy)
    expected = make_skill_installation_decision(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        staging_store,
        installation_policy,
        action,
        signed.decision.issued_at,
        signed.decision.valid_until,
    )
    if expected != signed.decision:
        raise ValueError("signed skill installation decision differs from sources")
    manifest, selected, current_control = _verified_selection(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        staging_store,
        installation_policy,
        action,
        current,
    )
    with anchor.guard_latest(current_control, control_policy, current) as anchored:
        if (
            anchored.anchor_entry_sha256 != signed.decision.control_anchor_entry_sha256
            or manifest.manifest_sha256 != signed.decision.staging_manifest_sha256
            or selected.archive_sha256 != signed.decision.archive_sha256
        ):
            raise ValueError("skill installation decision is no longer current")
    if not signed.decision.issued_at <= current < signed.decision.valid_until:
        raise ValueError("skill installation decision is not current")
    return AuthenticatedSkillInstallation(
        authority_policy_sha256=installation_policy.policy_sha256,
        staging_manifest_sha256=manifest.manifest_sha256,
        archive_sha256=selected.archive_sha256,
        skill=selected.descriptor.identity,
        claim_store_id=installation_policy.claim_store_id,
        installation_target_id=installation_policy.installation_target_id,
        signed_decision=signed,
        authenticated_at=current,
        valid_until=signed.decision.valid_until,
    )


def verify_authenticated_skill_installation(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    staging_store: SkillStagingStore,
    authenticated: AuthenticatedSkillInstallation,
    installation_policy: SkillInstallationAuthorityPolicy,
    action: Literal["candidate", "rollback"],
    now: datetime,
) -> None:
    rebuilt = authenticate_skill_installation(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        staging_store,
        authenticated.signed_decision,
        installation_policy,
        action,
        authenticated.authenticated_at,
    )
    if rebuilt != authenticated:
        raise ValueError("authenticated skill installation provenance mismatch")
    authenticated.check_current(now)


def _validate_private_database(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ValueError("skill installation claim store must be a regular file")
    if metadata.st_uid != os.getuid() or metadata.st_nlink != 1:
        raise ValueError("skill installation claim store ownership is invalid")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError("skill installation claim store must have mode 0600")


def _validate_private_directory(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ValueError("skill installation claim parent must be a directory")
    if metadata.st_uid != os.getuid():
        raise ValueError("skill installation claim parent ownership is invalid")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("skill installation claim parent must be private")


def _connect_claim_store(path: Path) -> sqlite3.Connection:
    _validate_private_directory(path.absolute().parent)
    _validate_private_database(path)
    connection = sqlite3.connect(
        path.absolute().as_uri() + "?mode=rw",
        uri=True,
        timeout=0.25,
        isolation_level=None,
    )
    try:
        connection.execute("PRAGMA synchronous=EXTRA")
        connection.execute("PRAGMA trusted_schema=OFF")
        if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            raise ValueError(
                "skill installation claim store requires rollback journaling"
            )
        return connection
    except BaseException:
        connection.close()
        raise


def _load_claim_store_policy(
    connection: sqlite3.Connection,
) -> SkillInstallationClaimStorePolicy:
    rows = connection.execute(
        "SELECT value FROM metadata WHERE key = 'policy'"
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("skill installation claim store policy is missing")
    payload = bytes(rows[0][0])
    policy = SkillInstallationClaimStorePolicy.model_validate_json(payload)
    if payload != canonical_bytes(policy):
        raise ValueError("skill installation claim store policy is not canonical")
    return policy


class SkillInstallationClaimStore:
    """Private at-most-once ledger; consumed claims are never refunded automatically."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        _validate_private_directory(self.path.parent)
        with closing(_connect_claim_store(self.path)) as connection:
            self.policy = _load_claim_store_policy(connection)

    @classmethod
    def create(
        cls,
        path: Path,
        policy: SkillInstallationClaimStorePolicy,
        authority_policy: SkillInstallationAuthorityPolicy,
    ) -> SkillInstallationClaimStore:
        policy = SkillInstallationClaimStorePolicy.model_validate_json(
            canonical_bytes(policy)
        )
        authority_policy = SkillInstallationAuthorityPolicy.model_validate_json(
            canonical_bytes(authority_policy)
        )
        if (
            policy.store_id != authority_policy.claim_store_id
            or policy.authority_policy_sha256 != authority_policy.policy_sha256
        ):
            raise ValueError("claim store policy does not match installation authority")
        _validate_private_directory(path.absolute().parent)
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        os.close(descriptor)
        try:
            with closing(_connect_claim_store(path)) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "CREATE TABLE metadata ("
                    "key TEXT PRIMARY KEY, value BLOB NOT NULL) STRICT"
                )
                connection.execute(
                    "CREATE TABLE claims ("
                    "decision_sha256 TEXT PRIMARY KEY, "
                    "authorization_sha256 TEXT NOT NULL, "
                    "claim BLOB NOT NULL, authorization BLOB NOT NULL) STRICT"
                )
                connection.execute(
                    "INSERT INTO metadata(key, value) VALUES ('policy', ?)",
                    (canonical_bytes(policy),),
                )
            directory_fd = os.open(
                path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return cls(path)

    def snapshot(
        self, authority_policy: SkillInstallationAuthorityPolicy
    ) -> SkillInstallationClaimStoreSnapshot:
        _validate_private_database(self.path)
        if (
            self.policy.store_id != authority_policy.claim_store_id
            or self.policy.authority_policy_sha256 != authority_policy.policy_sha256
        ):
            raise ValueError("claim store does not match installation authority policy")
        claims: list[SkillInstallationClaim] = []
        with closing(_connect_claim_store(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_claim_store_policy(connection) != self.policy:
                raise ValueError("skill installation claim store policy changed")
            rows = connection.execute(
                "SELECT decision_sha256, authorization_sha256, claim, authorization "
                "FROM claims ORDER BY decision_sha256"
            ).fetchall()
        for (
            decision_sha256,
            authorization_sha256,
            claim_payload,
            authorization_payload,
        ) in rows:
            claim = SkillInstallationClaim.model_validate_json(bytes(claim_payload))
            authorization = AuthenticatedSkillInstallation.model_validate_json(
                bytes(authorization_payload)
            )
            verify_signed_skill_installation_decision(
                authorization.signed_decision, authority_policy
            )
            if (
                canonical_bytes(claim) != bytes(claim_payload)
                or canonical_bytes(authorization) != bytes(authorization_payload)
                or authorization_sha256 != authorization.authorization_sha256
                or claim.authorization_sha256 != authorization.authorization_sha256
                or decision_sha256 != claim.decision_sha256
                or decision_sha256
                != authorization.signed_decision.decision.decision_sha256
                or claim.archive_sha256 != authorization.archive_sha256
                or claim.installation_target_id != authorization.installation_target_id
                or claim.claim_store_policy_sha256 != self.policy.policy_sha256
            ):
                raise ValueError("skill installation claim store entry is invalid")
            claims.append(claim)
        if len(claims) > self.policy.max_claims:
            raise ValueError("skill installation claim store exceeds policy")
        return SkillInstallationClaimStoreSnapshot(
            policy=self.policy,
            claims=tuple(claims),
        )

    def _claim_under_guard(
        self,
        authorization: AuthenticatedSkillInstallation,
        authority_policy: SkillInstallationAuthorityPolicy,
        now: datetime,
    ) -> SkillInstallationClaim:
        current = _require_utc(now)
        authorization.check_current(current)
        verify_signed_skill_installation_decision(
            authorization.signed_decision, authority_policy
        )
        if (
            authorization.claim_store_id != self.policy.store_id
            or self.policy.authority_policy_sha256 != authority_policy.policy_sha256
        ):
            raise ValueError("authorization does not match its one-use claim store")
        claim = SkillInstallationClaim(
            claim_store_policy_sha256=self.policy.policy_sha256,
            authorization_sha256=authorization.authorization_sha256,
            decision_sha256=authorization.signed_decision.decision.decision_sha256,
            archive_sha256=authorization.archive_sha256,
            installation_target_id=authorization.installation_target_id,
            claimed_at=current,
        )
        with closing(_connect_claim_store(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if _load_claim_store_policy(connection) != self.policy:
                raise ValueError("skill installation claim store policy changed")
            count = connection.execute("SELECT COUNT(*) FROM claims").fetchone()
            if count is None or int(count[0]) >= self.policy.max_claims:
                connection.rollback()
                raise ValueError("skill installation claim store limit reached")
            try:
                connection.execute(
                    "INSERT INTO claims("
                    "decision_sha256, authorization_sha256, claim, authorization) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        authorization.signed_decision.decision.decision_sha256,
                        authorization.authorization_sha256,
                        canonical_bytes(claim),
                        canonical_bytes(authorization),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
                raise ValueError(
                    "skill installation authorization was already consumed"
                ) from None
        return claim


@contextmanager
def guard_and_claim_skill_installation(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control: AuthenticatedSkillReleaseControl,
    control_policy: SkillReleaseControlAuthorityPolicy,
    anchor: SkillReleaseControlAnchor,
    staging_store: SkillStagingStore,
    authorization: AuthenticatedSkillInstallation,
    installation_policy: SkillInstallationAuthorityPolicy,
    claim_store: SkillInstallationClaimStore,
    action: Literal["candidate", "rollback"],
    now: datetime,
) -> Generator[SkillInstallationClaim, None, None]:
    """Burn one authorization and hold latest release control through caller commit."""
    current = _require_utc(now)
    verify_authenticated_skill_installation(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        staging_store,
        authorization,
        installation_policy,
        action,
        current,
    )
    _, _, current_control = _verified_selection(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_policy,
        archive,
        evidence,
        control,
        control_policy,
        anchor,
        staging_store,
        installation_policy,
        action,
        current,
    )
    with anchor.guard_latest(current_control, control_policy, current) as anchored:
        if (
            anchored.anchor_entry_sha256
            != authorization.signed_decision.decision.control_anchor_entry_sha256
        ):
            raise ValueError("skill installation authorization is no longer latest")
        claim = claim_store._claim_under_guard(  # pyright: ignore[reportPrivateUsage]
            authorization, installation_policy, current
        )
        yield claim
