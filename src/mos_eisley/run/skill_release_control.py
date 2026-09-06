"""Authenticated revocation and rollback nomination for retained skill releases."""

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
from mos_eisley.run.skill_release import (
    SkillReleaseEvidence,
    verify_skill_release_evidence,
)
from mos_eisley.run.skills import verify_skill_archive
from mos_eisley.run.store import private_write

_DOMAIN = b"mos-eisley/skill-release-control/v1\x00"
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


class TrustedSkillReleaseControlAuthority(Contract):
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


class SkillReleaseControlAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_release_control_authority_policy"] = (
        "skill_release_control_authority_policy"
    )
    policy_id: Identifier
    installation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_decision_lifetime_seconds: Annotated[int, Field(gt=0, le=604_800)]
    authorities: Annotated[
        tuple[TrustedSkillReleaseControlAuthority, ...],
        Field(min_length=1, max_length=20),
    ]

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("skill release control authority window must be positive")
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "skill release control authorities need sorted unique "
                "identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRollbackNomination(Contract):
    release_evidence_sha256: Digest
    archive_sha256: Digest
    rollback_skill: SkillIdentity


class SkillReleaseControlDecision(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_release_control_decision"] = "skill_release_control_decision"
    installation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    authority_policy_sha256: Digest
    release_evidence_sha256: Digest
    archive_sha256: Digest
    candidate_skill: SkillIdentity
    sequence: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
    disposition: Literal["allowed", "revoked"]
    rollback: SkillRollbackNomination | None = None
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("skill release control window must be positive")
        if self.candidate_skill.kind != "persona":
            raise ValueError("skill release control requires a persona skill")
        if self.disposition == "allowed" and self.rollback is not None:
            raise ValueError("an allowed release cannot nominate rollback bytes")
        if self.rollback is not None:
            target = self.rollback
            if (
                target.release_evidence_sha256 != self.release_evidence_sha256
                or target.archive_sha256 == self.archive_sha256
                or target.rollback_skill == self.candidate_skill
                or target.rollback_skill.source != self.candidate_skill.source
                or target.rollback_skill.name != self.candidate_skill.name
                or target.rollback_skill.kind != self.candidate_skill.kind
            ):
                raise ValueError(
                    "rollback nomination does not match this skill release"
                )
        return self

    @property
    def decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillReleaseControlSignature(Contract):
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


class SignedSkillReleaseControl(Contract):
    schema_version: Literal[1] = 1
    decision: SkillReleaseControlDecision
    signature: SkillReleaseControlSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.decision_sha256 != self.decision.decision_sha256:
            raise ValueError("signature does not identify this skill release control")
        return self

    @property
    def signed_control_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedSkillReleaseControl(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["authenticated_skill_release_control"] = (
        "authenticated_skill_release_control"
    )
    installation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False
    authority_policy_sha256: Digest
    release_evidence_sha256: Digest
    archive_sha256: Digest
    candidate_skill: SkillIdentity
    signed_control: SignedSkillReleaseControl
    rollback_archive: SkillPackageArchive | None = None
    authenticated_at: UtcTimestamp
    valid_until: UtcTimestamp
    release_allowed: bool
    release_revoked: bool

    @field_validator("authenticated_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_sources(self) -> Self:
        decision = self.signed_control.decision
        rollback = decision.rollback
        if (
            self.authority_policy_sha256 != decision.authority_policy_sha256
            or self.release_evidence_sha256 != decision.release_evidence_sha256
            or self.archive_sha256 != decision.archive_sha256
            or self.candidate_skill != decision.candidate_skill
            or self.valid_until != decision.valid_until
            or self.release_allowed != (decision.disposition == "allowed")
            or self.release_revoked != (decision.disposition == "revoked")
            or self.release_allowed == self.release_revoked
            or not decision.issued_at <= self.authenticated_at < self.valid_until
            or (rollback is None) != (self.rollback_archive is None)
            or (
                rollback is not None
                and self.rollback_archive is not None
                and (
                    rollback.archive_sha256 != self.rollback_archive.archive_sha256
                    or rollback.rollback_skill
                    != self.rollback_archive.descriptor.identity
                )
            )
        ):
            raise ValueError("authenticated skill release control source mismatch")
        return self

    @property
    def control_receipt_sha256(self) -> str:
        return digest(canonical_bytes(self))


def trusted_skill_release_control_authority(
    authority_id: str, public_key: bytes
) -> TrustedSkillReleaseControlAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain exactly 32 bytes")
    return TrustedSkillReleaseControlAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def sign_skill_release_control(
    decision: SkillReleaseControlDecision,
    signer_id: str,
    private_key: bytes,
) -> SignedSkillReleaseControl:
    """Sign a derived decision; the CLI never accepts private key material."""

    decision = SkillReleaseControlDecision.model_validate_json(
        canonical_bytes(decision)
    )
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
    except (UnsupportedAlgorithm, ValueError):
        raise ValueError("Ed25519 signing unavailable or private key invalid") from None
    public_key = key.public_key().public_bytes_raw()
    return SignedSkillReleaseControl(
        decision=decision,
        signature=SkillReleaseControlSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            decision_sha256=decision.decision_sha256,
            signature_base64=base64.b64encode(
                key.sign(_DOMAIN + canonical_bytes(decision))
            ).decode("ascii"),
        ),
    )


def verify_signed_skill_release_control(
    signed: SignedSkillReleaseControl,
    authority_policy: SkillReleaseControlAuthorityPolicy,
) -> TrustedSkillReleaseControlAuthority:
    signed = SignedSkillReleaseControl.model_validate_json(canonical_bytes(signed))
    authority_policy = SkillReleaseControlAuthorityPolicy.model_validate_json(
        canonical_bytes(authority_policy)
    )
    decision = signed.decision
    if decision.authority_policy_sha256 != authority_policy.policy_sha256:
        raise ValueError("skill release control authority policy differs")
    if not (
        authority_policy.valid_from
        <= decision.issued_at
        < decision.valid_until
        <= authority_policy.valid_until
    ):
        raise ValueError("skill release control window exceeds its authority policy")
    if (
        decision.valid_until - decision.issued_at
    ).total_seconds() > authority_policy.max_decision_lifetime_seconds:
        raise ValueError("skill release control exceeds its maximum lifetime")
    matches = [
        item
        for item in authority_policy.authorities
        if item.authority_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("signer is not trusted by the skill release control policy")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("signature key differs from skill release control policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(decision),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError(
            "skill release control signature verification failed"
        ) from None
    return trusted


def _rollback_nomination(
    evidence: SkillReleaseEvidence,
    rollback_archive: SkillPackageArchive | None,
) -> SkillRollbackNomination | None:
    if rollback_archive is None:
        return None
    verify_skill_archive(rollback_archive)
    return SkillRollbackNomination(
        release_evidence_sha256=evidence.release_evidence_sha256,
        archive_sha256=rollback_archive.archive_sha256,
        rollback_skill=rollback_archive.descriptor.identity,
    )


def _validate_authority_separation(
    control_policy: SkillReleaseControlAuthorityPolicy,
    promotion_policy: SkillPromotionAuthorityPolicy,
    lineages: tuple[SkillEvaluationLineage, SkillEvaluationLineage],
) -> None:
    excluded_ids = {item.authority_id for item in promotion_policy.authorities}
    excluded_keys = {item.public_key_sha256 for item in promotion_policy.authorities}
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
        for item in control_policy.authorities
    ):
        raise ValueError(
            "skill release control authority must be independent of "
            "promotion and evaluation"
        )


def make_skill_release_control_decision(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_authority_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    control_authority_policy: SkillReleaseControlAuthorityPolicy,
    sequence: int,
    disposition: Literal["allowed", "revoked"],
    rollback_archive: SkillPackageArchive | None,
    issued_at: datetime,
    valid_until: datetime,
) -> SkillReleaseControlDecision:
    """Reverify exact release evidence before deriving external signable control."""

    issued = _require_utc(issued_at)
    expires = _require_utc(valid_until)
    verify_skill_release_evidence(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authority_policy,
        archive,
        evidence,
        issued,
    )
    _validate_authority_separation(
        control_authority_policy,
        promotion_authority_policy,
        (calibration, holdout),
    )
    if not (
        control_authority_policy.valid_from
        <= issued
        < expires
        <= control_authority_policy.valid_until
        and expires <= evidence.valid_until
    ):
        raise ValueError("skill release control window exceeds its source or policy")
    if (
        expires - issued
    ).total_seconds() > control_authority_policy.max_decision_lifetime_seconds:
        raise ValueError("skill release control exceeds its maximum lifetime")
    if disposition == "allowed" and rollback_archive is not None:
        raise ValueError("an allowed release cannot nominate rollback bytes")
    return SkillReleaseControlDecision(
        authority_policy_sha256=control_authority_policy.policy_sha256,
        release_evidence_sha256=evidence.release_evidence_sha256,
        archive_sha256=archive.archive_sha256,
        candidate_skill=evidence.candidate_skill,
        sequence=sequence,
        disposition=disposition,
        rollback=_rollback_nomination(evidence, rollback_archive),
        issued_at=issued,
        valid_until=expires,
    )


def authenticate_skill_release_control(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    promotion_authority_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    evidence: SkillReleaseEvidence,
    signed: SignedSkillReleaseControl,
    control_authority_policy: SkillReleaseControlAuthorityPolicy,
    rollback_archive: SkillPackageArchive | None,
    at: datetime,
) -> AuthenticatedSkillReleaseControl:
    """Recompute release provenance, enforce separation/expiry, and verify control."""

    current = _require_utc(at)
    decision = signed.decision
    if not decision.issued_at <= current < decision.valid_until:
        raise ValueError("skill release control is not current")
    expected = make_skill_release_control_decision(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authority_policy,
        archive,
        evidence,
        control_authority_policy,
        decision.sequence,
        decision.disposition,
        rollback_archive,
        decision.issued_at,
        decision.valid_until,
    )
    if decision != expected:
        raise ValueError("signed skill release control differs from recomputation")
    verify_signed_skill_release_control(signed, control_authority_policy)
    verify_skill_release_evidence(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authority_policy,
        archive,
        evidence,
        current,
    )
    return AuthenticatedSkillReleaseControl(
        authority_policy_sha256=control_authority_policy.policy_sha256,
        release_evidence_sha256=evidence.release_evidence_sha256,
        archive_sha256=archive.archive_sha256,
        candidate_skill=evidence.candidate_skill,
        signed_control=signed,
        rollback_archive=rollback_archive,
        authenticated_at=current,
        valid_until=decision.valid_until,
        release_allowed=decision.disposition == "allowed",
        release_revoked=decision.disposition == "revoked",
    )


class SkillReleaseControlAnchorPolicy(Contract):
    schema_version: Literal[1] = 1
    anchor_id: Digest
    release_evidence_sha256: Digest
    control_authority_policy_sha256: Digest
    minimum_sequence: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
    control_authority_ids: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=20)
    ]

    @model_validator(mode="after")
    def canonical_authorities(self) -> Self:
        if tuple(sorted(set(self.control_authority_ids))) != self.control_authority_ids:
            raise ValueError("control authority identities must be unique and sorted")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AnchoredSkillReleaseControl(Contract):
    schema_version: Literal[1] = 1
    anchor_id: Digest
    previous_entry_sha256: Digest | None
    anchored_at: UtcTimestamp
    signed_control: SignedSkillReleaseControl

    @field_validator("anchored_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @property
    def anchor_entry_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillReleaseControlAnchorSnapshot(Contract):
    schema_version: Literal[1] = 1
    policy: SkillReleaseControlAnchorPolicy
    entries: Annotated[int, Field(ge=0)]
    latest: AnchoredSkillReleaseControl | None

    @model_validator(mode="after")
    def consistent_count(self) -> Self:
        if (self.entries == 0) != (self.latest is None):
            raise ValueError("anchor count and latest entry are inconsistent")
        return self

    @property
    def snapshot_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _validate_private_database(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("skill release control anchor must be a regular file")
    if metadata.st_uid != os.getuid():
        raise ValueError("skill release control anchor must be owned by current user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("skill release control anchor must be private")


def _connect(path: Path) -> sqlite3.Connection:
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
                "skill release control anchor requires rollback journaling"
            )
        return connection
    except BaseException:
        connection.close()
        raise


def _load_anchor_policy(
    connection: sqlite3.Connection,
) -> SkillReleaseControlAnchorPolicy:
    rows = connection.execute(
        "SELECT version, anchor_id, release_evidence_sha256, "
        "authority_policy_sha256, minimum_sequence, control_authority_ids "
        "FROM anchor_policy"
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("skill release control anchor policy is invalid")
    version, anchor_id, evidence_hash, authority_hash, minimum, identities = rows[0]
    return SkillReleaseControlAnchorPolicy.model_validate(
        {
            "schema_version": version,
            "anchor_id": anchor_id,
            "release_evidence_sha256": evidence_hash,
            "control_authority_policy_sha256": authority_hash,
            "minimum_sequence": minimum,
            "control_authority_ids": tuple(
                item for item in identities.split("\n") if item
            ),
        }
    )


class SkillReleaseControlAnchor:
    """Private local monotonic state; contains no signing or deployment credential."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _load_anchor_policy(connection)

    @classmethod
    def create(
        cls,
        path: Path,
        policy: SkillReleaseControlAnchorPolicy,
        control_authorities: SkillReleaseControlAuthorityPolicy,
    ) -> SkillReleaseControlAnchor:
        policy = SkillReleaseControlAnchorPolicy.model_validate_json(
            canonical_bytes(policy)
        )
        control_authorities = SkillReleaseControlAuthorityPolicy.model_validate_json(
            canonical_bytes(control_authorities)
        )
        known = {item.authority_id for item in control_authorities.authorities}
        if policy.control_authority_policy_sha256 != control_authorities.policy_sha256:
            raise ValueError(
                "anchor policy does not match release control trust policy"
            )
        if not set(policy.control_authority_ids) <= known:
            raise ValueError("control authority is absent from release trust policy")
        private_write(path, b"")
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE anchor_policy ("
                "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
                "version INTEGER NOT NULL CHECK(version = 1), "
                "anchor_id TEXT NOT NULL, release_evidence_sha256 TEXT NOT NULL, "
                "authority_policy_sha256 TEXT NOT NULL, minimum_sequence INTEGER "
                "NOT NULL CHECK(minimum_sequence >= 0), "
                "control_authority_ids TEXT NOT NULL) STRICT"
            )
            connection.execute(
                "INSERT INTO anchor_policy VALUES (1, 1, ?, ?, ?, ?, ?)",
                (
                    policy.anchor_id,
                    policy.release_evidence_sha256,
                    policy.control_authority_policy_sha256,
                    policy.minimum_sequence,
                    "\n".join(policy.control_authority_ids),
                ),
            )
            connection.execute(
                "CREATE TABLE control_entries ("
                "sequence INTEGER PRIMARY KEY CHECK(sequence >= 0), "
                "entry_sha256 TEXT NOT NULL UNIQUE, "
                "entry_json BLOB NOT NULL) STRICT"
            )
        return cls(path)

    @contextmanager
    def _transaction(self, *, write: bool) -> Generator[sqlite3.Connection, None, None]:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if _load_anchor_policy(connection) != self.policy:
                raise ValueError(
                    "skill release control anchor identity or policy changed"
                )
            yield connection

    def _entries(
        self,
        connection: sqlite3.Connection,
        control_authorities: SkillReleaseControlAuthorityPolicy,
    ) -> tuple[AnchoredSkillReleaseControl, ...]:
        if (
            control_authorities.policy_sha256
            != self.policy.control_authority_policy_sha256
        ):
            raise ValueError("release control authority policy does not match anchor")
        rows = connection.execute(
            "SELECT sequence, entry_sha256, entry_json "
            "FROM control_entries ORDER BY sequence"
        ).fetchall()
        entries: list[AnchoredSkillReleaseControl] = []
        previous: AnchoredSkillReleaseControl | None = None
        for stored_sequence, stored_digest, payload in rows:
            entry = AnchoredSkillReleaseControl.model_validate_json(payload)
            decision = entry.signed_control.decision
            if (
                entry.anchor_id != self.policy.anchor_id
                or decision.release_evidence_sha256
                != self.policy.release_evidence_sha256
                or stored_sequence != decision.sequence
                or stored_digest != entry.anchor_entry_sha256
                or payload != canonical_bytes(entry)
                or entry.previous_entry_sha256
                != (previous.anchor_entry_sha256 if previous is not None else None)
            ):
                raise ValueError("skill release control anchor chain is invalid")
            signer = verify_signed_skill_release_control(
                entry.signed_control, control_authorities
            )
            if signer.authority_id not in self.policy.control_authority_ids:
                raise ValueError("control signer is not authorized by anchor policy")
            if previous is None:
                if decision.sequence < self.policy.minimum_sequence:
                    raise ValueError(
                        "skill release control is below anchor sequence floor"
                    )
            else:
                prior = previous.signed_control.decision
                if (
                    decision.sequence <= prior.sequence
                    or decision.issued_at <= prior.issued_at
                    or entry.anchored_at < previous.anchored_at
                    or (
                        prior.disposition == "revoked"
                        and decision.disposition != "revoked"
                    )
                ):
                    raise ValueError("skill release control anchor is not monotonic")
            entries.append(entry)
            previous = entry
        return tuple(entries)

    def snapshot(
        self, control_authorities: SkillReleaseControlAuthorityPolicy
    ) -> SkillReleaseControlAnchorSnapshot:
        with self._transaction(write=False) as connection:
            entries = self._entries(connection, control_authorities)
            return SkillReleaseControlAnchorSnapshot(
                policy=self.policy,
                entries=len(entries),
                latest=entries[-1] if entries else None,
            )

    def advance(
        self,
        signed_control: SignedSkillReleaseControl,
        control_authorities: SkillReleaseControlAuthorityPolicy,
        now: datetime,
    ) -> SkillReleaseControlAnchorSnapshot:
        current = _require_utc(now)
        decision = signed_control.decision
        if not decision.issued_at <= current < decision.valid_until:
            raise ValueError("only a current skill release control can be anchored")
        if decision.release_evidence_sha256 != self.policy.release_evidence_sha256:
            raise ValueError("skill release control does not match anchor evidence")
        with self._transaction(write=True) as connection:
            entries = self._entries(connection, control_authorities)
            previous = entries[-1] if entries else None
            if previous is None:
                if decision.sequence < self.policy.minimum_sequence:
                    raise ValueError(
                        "skill release control is below anchor sequence floor"
                    )
            else:
                prior = previous.signed_control.decision
                if decision.sequence <= prior.sequence:
                    raise ValueError("skill release control sequence did not advance")
                if (
                    decision.issued_at <= prior.issued_at
                    or current < previous.anchored_at
                ):
                    raise ValueError("skill release control time did not advance")
                if prior.disposition == "revoked" and decision.disposition != "revoked":
                    raise ValueError("skill release revocation cannot be removed")
            signer = verify_signed_skill_release_control(
                signed_control, control_authorities
            )
            if signer.authority_id not in self.policy.control_authority_ids:
                raise ValueError("control signer is not authorized by anchor policy")
            entry = AnchoredSkillReleaseControl(
                anchor_id=self.policy.anchor_id,
                previous_entry_sha256=(
                    previous.anchor_entry_sha256 if previous is not None else None
                ),
                anchored_at=current,
                signed_control=signed_control,
            )
            connection.execute(
                "INSERT INTO control_entries VALUES (?, ?, ?)",
                (
                    decision.sequence,
                    entry.anchor_entry_sha256,
                    canonical_bytes(entry),
                ),
            )
            return SkillReleaseControlAnchorSnapshot(
                policy=self.policy,
                entries=len(entries) + 1,
                latest=entry,
            )

    def require_latest(
        self,
        control: AuthenticatedSkillReleaseControl,
        control_authorities: SkillReleaseControlAuthorityPolicy,
        now: datetime,
    ) -> AnchoredSkillReleaseControl:
        current = _require_utc(now)
        control = AuthenticatedSkillReleaseControl.model_validate_json(
            canonical_bytes(control)
        )
        latest = self.snapshot(control_authorities).latest
        if latest is None:
            raise ValueError("skill release control anchor has no state")
        if latest.signed_control != control.signed_control:
            raise ValueError("skill release control is not the latest anchored state")
        decision = control.signed_control.decision
        if (
            control.release_evidence_sha256 != self.policy.release_evidence_sha256
            or not latest.anchored_at <= current
            or not decision.issued_at <= current < decision.valid_until
            or not control.authenticated_at <= current < control.valid_until
        ):
            raise ValueError("latest anchored skill release control is not current")
        return latest
