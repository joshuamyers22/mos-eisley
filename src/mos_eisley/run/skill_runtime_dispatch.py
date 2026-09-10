"""Independent, at-most-once authority for a future skill broker grant."""

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
from mos_eisley.core.registry import ModelRegistry
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.activation_control import RoutingControlAnchor
from mos_eisley.run.routing_preflight import (
    RoutingRuntimePreflight,
    guard_routing_runtime_sources,
)
from mos_eisley.run.skill_default import SkillDefaultStore
from mos_eisley.run.skill_release_control import SkillReleaseControlAnchor
from mos_eisley.run.skill_runtime_admission import (
    SkillRuntimeAdmissionStore,
    SkillRuntimeBrokerAdmission,
    verify_skill_runtime_broker_admission,
)
from mos_eisley.run.skill_runtime_preflight import (
    PreparedSkillRuntimeRequest,
    SignedSkillRuntimeDecision,
    SkillRuntimeAuthorityPolicy,
    SkillRuntimeRequest,
    SkillRuntimeSources,
)
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write

_DOMAIN = b"mos-eisley/skill-runtime-dispatch-authority/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


class TrustedSkillRuntimeDispatchAuthority(Contract):
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


class SkillRuntimeDispatchClaimStorePolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_dispatch_claim_store_policy"] = (
        "skill_runtime_dispatch_claim_store_policy"
    )
    store_id: Digest
    admission_store_policy_sha256: Digest
    routing_control_anchor_policy_sha256: Digest
    skill_control_anchor_policy_sha256: Digest
    default_store_policy_sha256: Digest
    spend_ledger_id: Digest
    max_claims: Annotated[int, Field(ge=1, le=100_000)] = 10_000
    may_consume_one_dispatch_authority: Literal[True] = True
    broker_grant_issued: Literal[False] = False
    direct_provider_dispatch_authorized: Literal[False] = False
    provider_request_sent: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeDispatchAuthorityPolicy(Contract):
    schema_version: Literal[2] = 2
    mode: Literal["skill_runtime_dispatch_authority_policy"] = (
        "skill_runtime_dispatch_authority_policy"
    )
    policy_id: Identifier
    runtime_authority_policy_sha256: Digest
    dispatch_claim_store_policy_sha256: Digest
    broker_grant_store_policy_sha256: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_decision_lifetime_seconds: Annotated[int, Field(gt=0, le=60)]
    authorities: Annotated[
        tuple[TrustedSkillRuntimeDispatchAuthority, ...],
        Field(min_length=1, max_length=20),
    ]
    may_authorize_one_request_bound_grant: Literal[True] = True
    direct_provider_dispatch_authorized: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("dispatch authority policy window must be positive")
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "dispatch authorities need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeDispatchDecision(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_dispatch_decision"] = "skill_runtime_dispatch_decision"
    authority_policy_sha256: Digest
    dispatch_claim_store_policy_sha256: Digest
    admission_sha256: Digest
    admission_id: Digest
    prepared_runtime_request_sha256: Digest
    signed_runtime_decision_sha256: Digest
    runtime_request_sha256: Digest
    route_candidate_id: Digest
    provider_request_sha256: Digest
    broker_request_sha256: Digest
    spend_ledger_id: Digest
    ledger_entry_id: Digest
    spend_reservation_sha256: Digest
    routing_control_entry_sha256: Digest
    skill_control_entry_sha256: Digest
    default_pointer_sha256: Digest
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    one_use_required: Literal[True] = True
    may_issue_one_request_bound_grant: Literal[True] = True
    direct_provider_dispatch_authorized: Literal[False] = False
    broker_grant_issued: Literal[False] = False
    provider_request_sent: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("dispatch decision window must be positive")
        return self

    @property
    def decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeDispatchSignature(Contract):
    signer_id: Identifier
    public_key_sha256: Digest
    decision_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedSkillRuntimeDispatchDecision(Contract):
    schema_version: Literal[1] = 1
    decision: SkillRuntimeDispatchDecision
    signature: SkillRuntimeDispatchSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.decision_sha256 != self.decision.decision_sha256:
            raise ValueError("signature does not identify this dispatch decision")
        return self

    @property
    def signed_decision_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ConsumedSkillRuntimeDispatchAuthority(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["consumed_skill_runtime_dispatch_authority"] = (
        "consumed_skill_runtime_dispatch_authority"
    )
    claim_store_policy_sha256: Digest
    signed_dispatch_decision_sha256: Digest
    dispatch_decision_sha256: Digest
    admission_sha256: Digest
    admission_id: Digest
    provider_request_sha256: Digest
    broker_request_sha256: Digest
    spend_ledger_id: Digest
    ledger_entry_id: Digest
    spend_reservation_sha256: Digest
    consumed_at: UtcTimestamp
    valid_until: UtcTimestamp
    dispatch_authority_consumed: Literal[True] = True
    request_bound_grant_eligible: Literal[True] = True
    broker_grant_issued: Literal[False] = False
    direct_provider_dispatch_authorized: Literal[False] = False
    provider_request_sent: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @field_validator("consumed_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_until <= self.consumed_at:
            raise ValueError("consumed dispatch authority window must be positive")
        return self

    @property
    def claim_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeDispatchStatus(Contract):
    schema_version: Literal[1] = 1
    claim_store_policy_sha256: Digest
    dispatch_decision_sha256: Digest
    phase: Literal["absent", "consumed"]
    ledger_status: Literal["absent", "held", "settled", "uncertain", "violation"]
    request_bound_grant_eligible: bool
    broker_grant_issued: Literal[False] = False
    direct_provider_dispatch_authorized: Literal[False] = False
    provider_request_sent: Literal[False] = False
    retry_permitted: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False


def trusted_skill_runtime_dispatch_authority(
    authority_id: str, public_key: bytes
) -> TrustedSkillRuntimeDispatchAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedSkillRuntimeDispatchAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def sign_skill_runtime_dispatch_decision(
    decision: SkillRuntimeDispatchDecision, signer_id: str, private_key: bytes
) -> SignedSkillRuntimeDispatchDecision:
    """Sign grant-issuance authority; command-line paths never accept private keys."""

    if len(private_key) != 32:
        raise ValueError("Ed25519 private key must contain 32 bytes")
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(_DOMAIN + canonical_bytes(decision))
    except (ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return SignedSkillRuntimeDispatchDecision(
        decision=decision,
        signature=SkillRuntimeDispatchSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            decision_sha256=decision.decision_sha256,
            signature_base64=base64.b64encode(signature).decode("ascii"),
        ),
    )


def verify_signed_skill_runtime_dispatch_decision(
    signed: SignedSkillRuntimeDispatchDecision,
    policy: SkillRuntimeDispatchAuthorityPolicy,
) -> TrustedSkillRuntimeDispatchAuthority:
    matches = [
        item
        for item in policy.authorities
        if item.authority_id == signed.signature.signer_id
    ]
    if (
        len(matches) != 1
        or matches[0].public_key_sha256 != signed.signature.public_key_sha256
        or signed.decision.authority_policy_sha256 != policy.policy_sha256
    ):
        raise ValueError("skill runtime dispatch signer is not enrolled")
    signer = matches[0]
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(signer.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(signed.decision),
        )
    except (InvalidSignature, ValueError, UnsupportedAlgorithm):
        raise ValueError("skill runtime dispatch signature is invalid") from None
    return signer


def _validate_authority_separation(
    policy: SkillRuntimeDispatchAuthorityPolicy,
    runtime_policy: SkillRuntimeAuthorityPolicy,
) -> None:
    runtime_ids = {item.authority_id for item in runtime_policy.authorities}
    runtime_keys = {item.public_key_sha256 for item in runtime_policy.authorities}
    if any(
        item.authority_id in runtime_ids or item.public_key_sha256 in runtime_keys
        for item in policy.authorities
    ):
        raise ValueError(
            "dispatch authority must be independent of runtime preparation"
        )


def _verify_policy_provenance(
    sources: SkillRuntimeSources,
    ledger: SpendLedger,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    admission_store: SkillRuntimeAdmissionStore,
    claim_store_policy: SkillRuntimeDispatchClaimStorePolicy,
    policy: SkillRuntimeDispatchAuthorityPolicy,
) -> None:
    if (
        policy.runtime_authority_policy_sha256 != runtime_policy.policy_sha256
        or policy.dispatch_claim_store_policy_sha256 != claim_store_policy.policy_sha256
        or claim_store_policy.admission_store_policy_sha256
        != admission_store.policy.policy_sha256
        or claim_store_policy.routing_control_anchor_policy_sha256
        != sources.routing.control_anchor.policy.policy_sha256
        or claim_store_policy.skill_control_anchor_policy_sha256
        != sources.control_anchor.policy.policy_sha256
        or claim_store_policy.default_store_policy_sha256
        != sources.default_store.policy.policy_sha256
        or claim_store_policy.spend_ledger_id != ledger.policy.ledger_id
    ):
        raise ValueError("skill runtime dispatch policy provenance mismatch")
    _validate_authority_separation(policy, runtime_policy)


def make_skill_runtime_dispatch_decision(
    sources: SkillRuntimeSources,
    routing_preflight: RoutingRuntimePreflight,
    request: SkillRuntimeRequest,
    registry: ModelRegistry,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    signed_runtime: SignedSkillRuntimeDecision,
    prepared: PreparedSkillRuntimeRequest,
    admission: SkillRuntimeBrokerAdmission,
    admission_store: SkillRuntimeAdmissionStore,
    claim_store_policy: SkillRuntimeDispatchClaimStorePolicy,
    policy: SkillRuntimeDispatchAuthorityPolicy,
    issued_at: datetime,
    valid_until: datetime,
) -> SkillRuntimeDispatchDecision:
    """Derive independent authority to issue one future grant; never a bearer."""

    issued = _require_utc(issued_at)
    expires = _require_utc(valid_until)
    verify_skill_runtime_broker_admission(
        sources,
        routing_preflight,
        request,
        registry,
        spend_policy,
        ledger,
        runtime_policy,
        signed_runtime,
        prepared,
        admission,
        admission_store,
        issued,
    )
    _verify_policy_provenance(
        sources,
        ledger,
        runtime_policy,
        admission_store,
        claim_store_policy,
        policy,
    )
    if not (
        policy.valid_from <= issued < expires <= policy.valid_until
        and expires <= admission.valid_until
        and (expires - issued).total_seconds() <= policy.max_decision_lifetime_seconds
    ):
        raise ValueError("skill runtime dispatch decision window exceeds policy")
    return SkillRuntimeDispatchDecision(
        authority_policy_sha256=policy.policy_sha256,
        dispatch_claim_store_policy_sha256=claim_store_policy.policy_sha256,
        admission_sha256=admission.admission_sha256,
        admission_id=admission.admission_id,
        prepared_runtime_request_sha256=prepared.preflight_sha256,
        signed_runtime_decision_sha256=signed_runtime.signed_decision_sha256,
        runtime_request_sha256=request.request_sha256,
        route_candidate_id=request.route.candidate_id,
        provider_request_sha256=admission.provider_request_sha256,
        broker_request_sha256=admission.broker_request_sha256,
        spend_ledger_id=admission.spend_ledger_id,
        ledger_entry_id=admission.ledger_entry_id,
        spend_reservation_sha256=admission.spend_reservation_sha256,
        routing_control_entry_sha256=admission.routing_control_entry_sha256,
        skill_control_entry_sha256=admission.skill_control_entry_sha256,
        default_pointer_sha256=admission.default_pointer_sha256,
        issued_at=issued,
        valid_until=expires,
    )


def _validate_private_database(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("dispatch claim store must be a regular file")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("dispatch claim store must be private and locally owned")


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
            raise ValueError("dispatch claim store requires rollback journaling")
        return connection
    except BaseException:
        connection.close()
        raise


def _load_policy(
    connection: sqlite3.Connection,
) -> SkillRuntimeDispatchClaimStorePolicy:
    rows = connection.execute("SELECT policy_json FROM store_policy").fetchall()
    if len(rows) != 1:
        raise ValueError("dispatch claim store policy is invalid")
    policy = SkillRuntimeDispatchClaimStorePolicy.model_validate_json(rows[0][0])
    if rows[0][0] != canonical_bytes(policy):
        raise ValueError("dispatch claim store policy is not canonical")
    return policy


class SkillRuntimeDispatchClaimStore:
    """Private at-most-once claims; contains no prompt, credential, or bearer."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _load_policy(connection)

    @classmethod
    def create(
        cls,
        path: Path,
        policy: SkillRuntimeDispatchClaimStorePolicy,
        admission_store: SkillRuntimeAdmissionStore,
        routing_control_anchor: RoutingControlAnchor,
        skill_control_anchor: SkillReleaseControlAnchor,
        default_store: SkillDefaultStore,
        ledger: SpendLedger,
    ) -> SkillRuntimeDispatchClaimStore:
        if (
            policy.admission_store_policy_sha256 != admission_store.policy.policy_sha256
            or policy.routing_control_anchor_policy_sha256
            != routing_control_anchor.policy.policy_sha256
            or policy.skill_control_anchor_policy_sha256
            != skill_control_anchor.policy.policy_sha256
            or policy.default_store_policy_sha256 != default_store.policy.policy_sha256
            or policy.spend_ledger_id != ledger.policy.ledger_id
        ):
            raise ValueError(
                "dispatch claim store policy does not match local controls"
            )
        policy = SkillRuntimeDispatchClaimStorePolicy.model_validate_json(
            canonical_bytes(policy)
        )
        private_write(path, b"")
        with closing(_connect(path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE store_policy (singleton INTEGER PRIMARY KEY "
                "CHECK(singleton = 1), policy_json BLOB NOT NULL) STRICT"
            )
            connection.execute(
                "INSERT INTO store_policy VALUES (1, ?)", (canonical_bytes(policy),)
            )
            connection.execute(
                "CREATE TABLE claims (dispatch_decision_sha256 TEXT PRIMARY KEY, "
                "signed_decision_sha256 TEXT NOT NULL UNIQUE, "
                "admission_id TEXT NOT NULL UNIQUE, "
                "ledger_entry_id TEXT NOT NULL UNIQUE, "
                "claim_sha256 TEXT NOT NULL UNIQUE, claim_json BLOB NOT NULL, "
                "signed_json BLOB NOT NULL) STRICT"
            )
        return cls(path)

    def _records(
        self, connection: sqlite3.Connection
    ) -> tuple[ConsumedSkillRuntimeDispatchAuthority, ...]:
        rows = connection.execute(
            "SELECT dispatch_decision_sha256, signed_decision_sha256, admission_id, "
            "ledger_entry_id, claim_sha256, claim_json, signed_json FROM claims "
            "ORDER BY rowid"
        ).fetchall()
        records: list[ConsumedSkillRuntimeDispatchAuthority] = []
        for row in rows:
            claim = ConsumedSkillRuntimeDispatchAuthority.model_validate_json(row[5])
            signed = SignedSkillRuntimeDispatchDecision.model_validate_json(row[6])
            if (
                row[0] != claim.dispatch_decision_sha256
                or row[1] != claim.signed_dispatch_decision_sha256
                or row[2] != claim.admission_id
                or row[3] != claim.ledger_entry_id
                or row[4] != claim.claim_sha256
                or row[5] != canonical_bytes(claim)
                or row[6] != canonical_bytes(signed)
                or signed.signed_decision_sha256
                != claim.signed_dispatch_decision_sha256
                or claim.claim_store_policy_sha256 != self.policy.policy_sha256
                or claim.dispatch_decision_sha256 != signed.decision.decision_sha256
                or claim.admission_sha256 != signed.decision.admission_sha256
                or claim.admission_id != signed.decision.admission_id
                or claim.provider_request_sha256
                != signed.decision.provider_request_sha256
                or claim.broker_request_sha256 != signed.decision.broker_request_sha256
                or claim.spend_ledger_id != signed.decision.spend_ledger_id
                or claim.ledger_entry_id != signed.decision.ledger_entry_id
                or claim.spend_reservation_sha256
                != signed.decision.spend_reservation_sha256
                or claim.valid_until != signed.decision.valid_until
                or not signed.decision.issued_at
                <= claim.consumed_at
                < signed.decision.valid_until
            ):
                raise ValueError("dispatch claim store record is invalid")
            records.append(claim)
        if len(records) > self.policy.max_claims:
            raise ValueError("dispatch claim store exceeds policy")
        return tuple(records)

    def get(self, decision_sha256: str) -> ConsumedSkillRuntimeDispatchAuthority | None:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("dispatch claim store identity changed")
            matches = [
                item
                for item in self._records(connection)
                if item.dispatch_decision_sha256 == decision_sha256
            ]
            if len(matches) > 1:
                raise ValueError("dispatch claim identity is not unique")
            return matches[0] if matches else None

    @contextmanager
    def guard_claim(
        self, expected: ConsumedSkillRuntimeDispatchAuthority
    ) -> Generator[ConsumedSkillRuntimeDispatchAuthority, None, None]:
        """Hold one exact consumed claim across a caller's local commit."""

        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("dispatch claim store identity changed")
            matches = [
                item
                for item in self._records(connection)
                if item.dispatch_decision_sha256 == expected.dispatch_decision_sha256
            ]
            if len(matches) != 1 or matches[0] != expected:
                raise ValueError("dispatch authority is not the exact stored claim")
            yield matches[0]

    def consume(
        self,
        signed: SignedSkillRuntimeDispatchDecision,
        policy: SkillRuntimeDispatchAuthorityPolicy,
        now: datetime,
    ) -> ConsumedSkillRuntimeDispatchAuthority:
        current = _require_utc(now)
        verify_signed_skill_runtime_dispatch_decision(signed, policy)
        decision = signed.decision
        if (
            decision.dispatch_claim_store_policy_sha256 != self.policy.policy_sha256
            or not decision.issued_at <= current < decision.valid_until
        ):
            raise ValueError("dispatch decision is not current for this claim store")
        claim = _consumed_claim(signed, self, current)
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if _load_policy(connection) != self.policy:
                raise ValueError("dispatch claim store identity changed")
            records = self._records(connection)
            if len(records) >= self.policy.max_claims:
                raise ValueError("dispatch claim store limit reached")
            if any(
                item.dispatch_decision_sha256 == decision.decision_sha256
                or item.admission_id == decision.admission_id
                or item.ledger_entry_id == decision.ledger_entry_id
                for item in records
            ):
                raise ValueError("dispatch authority was already consumed") from None
            connection.execute(
                "INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    decision.decision_sha256,
                    signed.signed_decision_sha256,
                    decision.admission_id,
                    decision.ledger_entry_id,
                    claim.claim_sha256,
                    canonical_bytes(claim),
                    canonical_bytes(signed),
                ),
            )
        return claim


def _consumed_claim(
    signed: SignedSkillRuntimeDispatchDecision,
    store: SkillRuntimeDispatchClaimStore,
    consumed_at: datetime,
) -> ConsumedSkillRuntimeDispatchAuthority:
    decision = signed.decision
    return ConsumedSkillRuntimeDispatchAuthority(
        claim_store_policy_sha256=store.policy.policy_sha256,
        signed_dispatch_decision_sha256=signed.signed_decision_sha256,
        dispatch_decision_sha256=decision.decision_sha256,
        admission_sha256=decision.admission_sha256,
        admission_id=decision.admission_id,
        provider_request_sha256=decision.provider_request_sha256,
        broker_request_sha256=decision.broker_request_sha256,
        spend_ledger_id=decision.spend_ledger_id,
        ledger_entry_id=decision.ledger_entry_id,
        spend_reservation_sha256=decision.spend_reservation_sha256,
        consumed_at=consumed_at,
        valid_until=decision.valid_until,
    )


def verify_consumed_skill_runtime_dispatch_authority(
    sources: SkillRuntimeSources,
    routing_preflight: RoutingRuntimePreflight,
    request: SkillRuntimeRequest,
    registry: ModelRegistry,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    signed_runtime: SignedSkillRuntimeDecision,
    prepared: PreparedSkillRuntimeRequest,
    admission: SkillRuntimeBrokerAdmission,
    admission_store: SkillRuntimeAdmissionStore,
    claim_store: SkillRuntimeDispatchClaimStore,
    policy: SkillRuntimeDispatchAuthorityPolicy,
    signed_dispatch: SignedSkillRuntimeDispatchDecision,
    claim: ConsumedSkillRuntimeDispatchAuthority,
    now: datetime,
) -> None:
    """Reverify a current exact consumed claim without issuing a grant or sending."""

    current = _require_utc(now)
    rebuilt = make_skill_runtime_dispatch_decision(
        sources,
        routing_preflight,
        request,
        registry,
        spend_policy,
        ledger,
        runtime_policy,
        signed_runtime,
        prepared,
        admission,
        admission_store,
        claim_store.policy,
        policy,
        signed_dispatch.decision.issued_at,
        signed_dispatch.decision.valid_until,
    )
    verify_signed_skill_runtime_dispatch_decision(signed_dispatch, policy)
    expected = _consumed_claim(signed_dispatch, claim_store, claim.consumed_at)
    if (
        rebuilt != signed_dispatch.decision
        or expected != claim
        or claim_store.get(rebuilt.decision_sha256) != claim
    ):
        raise ValueError("consumed skill runtime dispatch provenance mismatch")
    if not claim.consumed_at <= current < claim.valid_until:
        raise ValueError("consumed skill runtime dispatch authority is not current")


def consume_skill_runtime_dispatch_authority(
    sources: SkillRuntimeSources,
    routing_preflight: RoutingRuntimePreflight,
    request: SkillRuntimeRequest,
    registry: ModelRegistry,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    runtime_policy: SkillRuntimeAuthorityPolicy,
    signed_runtime: SignedSkillRuntimeDecision,
    prepared: PreparedSkillRuntimeRequest,
    admission: SkillRuntimeBrokerAdmission,
    admission_store: SkillRuntimeAdmissionStore,
    claim_store: SkillRuntimeDispatchClaimStore,
    policy: SkillRuntimeDispatchAuthorityPolicy,
    signed_dispatch: SignedSkillRuntimeDispatchDecision,
    now: datetime,
) -> ConsumedSkillRuntimeDispatchAuthority:
    """Consume authority under every local guard, without issuing a grant or sending."""

    current = _require_utc(now)
    rebuilt = make_skill_runtime_dispatch_decision(
        sources,
        routing_preflight,
        request,
        registry,
        spend_policy,
        ledger,
        runtime_policy,
        signed_runtime,
        prepared,
        admission,
        admission_store,
        claim_store.policy,
        policy,
        signed_dispatch.decision.issued_at,
        signed_dispatch.decision.valid_until,
    )
    if rebuilt != signed_dispatch.decision:
        raise ValueError("skill runtime dispatch decision provenance mismatch")
    verify_signed_skill_runtime_dispatch_decision(signed_dispatch, policy)
    if not rebuilt.issued_at <= current < rebuilt.valid_until:
        raise ValueError("skill runtime dispatch decision is not current")
    with (
        guard_routing_runtime_sources(sources.routing, routing_preflight, current),
        sources.control_anchor.guard_latest(
            sources.control, sources.control_policy, current
        ) as skill_control,
    ):
        if skill_control.anchor_entry_sha256 != rebuilt.skill_control_entry_sha256:
            raise ValueError("skill runtime dispatch skill control changed")
        with sources.default_store.guard_current(
            sources.default_policy,
            sources.installed_store,
            sources.installation_policy,
        ) as pointer:
            if pointer.pointer_sha256 != rebuilt.default_pointer_sha256:
                raise ValueError("skill runtime dispatch default changed")
            with (
                ledger.guard_held(prepared.ledger_entry),
                admission_store.guard_admission(admission),
            ):
                return claim_store.consume(signed_dispatch, policy, current)


def inspect_skill_runtime_dispatch(
    signed: SignedSkillRuntimeDispatchDecision,
    policy: SkillRuntimeDispatchAuthorityPolicy,
    store: SkillRuntimeDispatchClaimStore,
    ledger: SpendLedger,
) -> SkillRuntimeDispatchStatus:
    """Inspect consumption without granting, retrying, releasing, or sending."""

    verify_signed_skill_runtime_dispatch_decision(signed, policy)
    decision = signed.decision
    if (
        policy.dispatch_claim_store_policy_sha256 != store.policy.policy_sha256
        or decision.spend_ledger_id != ledger.policy.ledger_id
        or store.policy.spend_ledger_id != ledger.policy.ledger_id
    ):
        raise ValueError("skill runtime dispatch status provenance mismatch")
    claim = store.get(decision.decision_sha256)
    entry = ledger.entry_status(decision.ledger_entry_id)
    if (
        entry is not None
        and entry.reservation_sha256 != decision.spend_reservation_sha256
    ):
        raise ValueError("skill runtime dispatch status reservation mismatch")
    return SkillRuntimeDispatchStatus(
        claim_store_policy_sha256=store.policy.policy_sha256,
        dispatch_decision_sha256=decision.decision_sha256,
        phase="absent" if claim is None else "consumed",
        ledger_status="absent" if entry is None else entry.status,
        request_bound_grant_eligible=claim is not None,
    )
