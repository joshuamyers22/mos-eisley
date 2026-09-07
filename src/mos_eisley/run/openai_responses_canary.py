"""Independently authorized synthetic OpenAI Responses API canary."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, JsonValue, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import ModelResponse, TextBlock, ToolCallBlock
from mos_eisley.providers.openai_responses import response_from_payload
from mos_eisley.providers.openai_spend import (
    BudgetedOpenAITransport,
    CountedTransport,
    SpendPolicy,
    SpendReceipt,
    SpendReservation,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.spend_ledger import LedgerEntryStatus, SpendLedger
from mos_eisley.run.store import ArtifactHash, private_write

OPENAI_RESPONSES_CANARY_MODEL = "gpt-5.6-luna"
OPENAI_RESPONSES_CANARY_MAX_OUTPUT_TOKENS = 32
OPENAI_RESPONSES_CANARY_INSTRUCTIONS = (
    "This is a synthetic API connectivity canary. Do not call tools. "
    "Return one short, non-empty acknowledgement."
)
OPENAI_RESPONSES_CANARY_INPUT = "Synthetic canary. Reply with OK."
OPENAI_RESPONSES_CANARY_ARTIFACTS = (
    "authority-policy.json",
    "signed-authorization.json",
    "spend-policy.json",
    "request.json",
    "spend-reservation.json",
    "spend-receipt.json",
    "result.json",
)
OPENAI_RESPONSES_CANARY_MAX_ARTIFACT_BYTES = 1_000_000

_DOMAIN = b"mos-eisley/openai-responses-canary-authorization/v1\x00"
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


def _json_bytes(value: dict[str, JsonValue]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _directory_sha256(directory: Path) -> str:
    return digest(str(directory.resolve()).encode())


class OpenAIResponsesCanaryRequest(Contract):
    """Human-reviewable contract for the fixed synthetic provider requests."""

    schema_version: Literal[1] = 1
    mode: Literal["openai_responses_canary_request"] = "openai_responses_canary_request"
    provider: Literal["openai"] = "openai"
    api_family: Literal["responses"] = "responses"
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    instructions: Annotated[str, Field(min_length=1, max_length=1000)] = (
        OPENAI_RESPONSES_CANARY_INSTRUCTIONS
    )
    input_text: Annotated[str, Field(min_length=1, max_length=1000)] = (
        OPENAI_RESPONSES_CANARY_INPUT
    )
    reasoning_effort: Literal["none"] = "none"
    max_output_tokens: Literal[32] = 32
    service_tier: Literal["default"] = "default"
    store: Literal[False] = False
    truncation: Literal["disabled"] = "disabled"
    tools_requested: Literal[False] = False
    parallel_tool_calls: Literal[False] = False
    streaming: Literal[False] = False
    background: Literal[False] = False

    @model_validator(mode="after")
    def exact_synthetic_text(self) -> Self:
        if (
            self.instructions != OPENAI_RESPONSES_CANARY_INSTRUCTIONS
            or self.input_text != OPENAI_RESPONSES_CANARY_INPUT
        ):
            raise ValueError("canary request text is not the fixed synthetic text")
        return self

    def response_payload(self) -> dict[str, JsonValue]:
        return {
            "model": self.model,
            "instructions": self.instructions,
            "input": [{"role": "user", "content": self.input_text}],
            "tools": [],
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": self.max_output_tokens,
            "parallel_tool_calls": self.parallel_tool_calls,
            "stream": self.streaming,
            "background": self.background,
            "store": self.store,
            "truncation": self.truncation,
            "service_tier": self.service_tier,
        }

    def count_payload(self) -> dict[str, JsonValue]:
        request = self.response_payload()
        return {
            key: value
            for key, value in request.items()
            if key
            not in (
                "max_output_tokens",
                "stream",
                "background",
                "store",
                "service_tier",
            )
        }


def openai_responses_canary_request_contract() -> OpenAIResponsesCanaryRequest:
    return OpenAIResponsesCanaryRequest()


def openai_responses_canary_request() -> dict[str, JsonValue]:
    """Return the only generation request this canary may send."""

    return openai_responses_canary_request_contract().response_payload()


def openai_responses_canary_count_request() -> dict[str, JsonValue]:
    """Return the exact SDK token-count request made before spending admission."""

    return openai_responses_canary_request_contract().count_payload()


class TrustedOpenAIResponsesCanaryAuthority(Contract):
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


class OpenAIResponsesCanaryAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["openai_responses_canary_authority_policy"] = (
        "openai_responses_canary_authority_policy"
    )
    policy_id: Identifier
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_authorization_lifetime_seconds: Annotated[int, Field(gt=0, le=3600)]
    max_request_timeout_seconds: Annotated[float, Field(gt=0, le=30)]
    authorities: Annotated[
        tuple[TrustedOpenAIResponsesCanaryAuthority, ...],
        Field(min_length=1, max_length=20),
    ]
    provider: Literal["openai"] = "openai"
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    command: Literal["openai-responses-canary"] = "openai-responses-canary"
    independent_signature_required: Literal[True] = True
    exact_request_binding_required: Literal[True] = True
    explicit_local_consent_also_required: Literal[True] = True
    automatic_retry_authorized: Literal[False] = False
    tool_access_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("canary authority policy window must be positive")
        identities = tuple(item.authority_id for item in self.authorities)
        keys = tuple(item.public_key_sha256 for item in self.authorities)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "canary authorities need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class OpenAIResponsesCanaryAuthorization(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["openai_responses_canary_authorization"] = (
        "openai_responses_canary_authorization"
    )
    authority_policy_sha256: Digest
    spend_policy_sha256: Digest
    ledger_id: Digest
    ledger_entry_id: Digest
    output_directory_sha256: Digest
    request: OpenAIResponsesCanaryRequest
    token_count_request_sha256: Digest
    response_request_sha256: Digest
    max_cost_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    timeout_seconds: Annotated[float, Field(gt=0, le=30)]
    issued_at: UtcTimestamp
    valid_until: UtcTimestamp
    provider: Literal["openai"] = "openai"
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    command: Literal["openai-responses-canary"] = "openai-responses-canary"
    credential_mode: Literal["api_key"] = "api_key"
    currency: Literal["USD"] = "USD"
    provider_requests_authorized: Literal[2] = 2
    one_token_count_authorized: Literal[True] = True
    one_generation_authorized: Literal[True] = True
    synthetic_data_transfer_authorized: Literal[True] = True
    user_data_transfer_authorized: Literal[False] = False
    credential_access_authorized: Literal[True] = True
    spend_authorized: Literal[True] = True
    tool_access_authorized: Literal[False] = False
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def positive_window(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("canary authorization window must be positive")
        if (
            self.request != openai_responses_canary_request_contract()
            or self.token_count_request_sha256
            != digest(_json_bytes(self.request.count_payload()))
            or self.response_request_sha256
            != digest(_json_bytes(self.request.response_payload()))
        ):
            raise ValueError("canary authorization request binding is invalid")
        return self

    @property
    def authorization_sha256(self) -> str:
        return digest(canonical_bytes(self))


class OpenAIResponsesCanaryAuthorizationSignature(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    signer_id: Identifier
    public_key_sha256: Digest
    authorization_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedOpenAIResponsesCanaryAuthorization(Contract):
    schema_version: Literal[1] = 1
    authorization: OpenAIResponsesCanaryAuthorization
    signature: OpenAIResponsesCanaryAuthorizationSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if (
            self.signature.authorization_sha256
            != self.authorization.authorization_sha256
        ):
            raise ValueError("signature does not identify this canary authorization")
        return self

    @property
    def signed_authorization_sha256(self) -> str:
        return digest(canonical_bytes(self))


class OpenAIResponsesCanaryResult(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["openai_responses_canary"] = "openai_responses_canary"
    completed_at: UtcTimestamp
    sdk_package: Literal["openai"] = "openai"
    sdk_version: Annotated[str, Field(min_length=1, max_length=64)]
    provider: Literal["openai"] = "openai"
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    authority_policy_sha256: Digest
    signed_authorization_sha256: Digest
    authorization_sha256: Digest
    spend_policy_sha256: Digest
    ledger_id: Digest
    ledger_entry_id: Digest
    token_count_request_sha256: Digest
    response_request_sha256: Digest
    provider_response_sha256: Digest
    spend_reservation_sha256: Digest
    spend_receipt_sha256: Digest
    retained_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    response: ModelResponse
    outcome: Literal["verified"] = "verified"
    provider_requests_attempted: Literal[2] = 2
    prompt_class: Literal["fixed_synthetic"] = "fixed_synthetic"
    prompt_transferred: Literal[True] = True
    user_data_transferred: Literal[False] = False
    generation_requested: Literal[True] = True
    credential_accessed: Literal[True] = True
    automatic_retries: Literal[0] = 0
    tools_requested: Literal[False] = False
    responses_access_verified: Literal[True] = True
    billing_verified: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False
    retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @field_validator("completed_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def successful_text_response(self) -> Self:
        if (
            self.response.stop_reason != "end_turn"
            or self.response.usage.unit != "tokens"
            or not any(
                isinstance(block, TextBlock) and bool(block.text)
                for block in self.response.turn.blocks
            )
            or any(
                isinstance(block, ToolCallBlock) for block in self.response.turn.blocks
            )
            or self.provider_response_sha256 != digest(canonical_bytes(self.response))
        ):
            raise ValueError("canary result is not a completed text response")
        return self


class OpenAIResponsesCanaryManifest(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["openai_responses_canary"] = "openai_responses_canary"
    output_directory_sha256: Digest
    artifacts: tuple[ArtifactHash, ...]


def trusted_openai_responses_canary_authority(
    authority_id: str, public_key: bytes
) -> TrustedOpenAIResponsesCanaryAuthority:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedOpenAIResponsesCanaryAuthority(
        authority_id=authority_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def make_openai_responses_canary_authorization(
    spend_policy: SpendPolicy,
    ledger_id: str,
    authority_policy: OpenAIResponsesCanaryAuthorityPolicy,
    output_directory: Path,
    timeout_seconds: float,
    issued_at: datetime,
    valid_until: datetime,
) -> OpenAIResponsesCanaryAuthorization:
    """Derive exact signable canary authority without credential access or sending."""

    spend_policy = SpendPolicy.model_validate_json(canonical_bytes(spend_policy))
    authority_policy = OpenAIResponsesCanaryAuthorityPolicy.model_validate_json(
        canonical_bytes(authority_policy)
    )
    issued = _require_utc(issued_at)
    expires = _require_utc(valid_until)
    if spend_policy.model != OPENAI_RESPONSES_CANARY_MODEL:
        raise ValueError("canary spending policy model mismatch")
    if spend_policy.max_output_tokens < OPENAI_RESPONSES_CANARY_MAX_OUTPUT_TOKENS:
        raise ValueError("canary output limit exceeds spending policy")
    max_cost = spend_policy.cost(
        spend_policy.max_input_tokens, OPENAI_RESPONSES_CANARY_MAX_OUTPUT_TOKENS
    )
    if max_cost > spend_policy.max_cost_microusd:
        raise ValueError("canary maximum exposure exceeds spending policy")
    if not 0 < timeout_seconds <= authority_policy.max_request_timeout_seconds:
        raise ValueError("canary timeout exceeds authority policy")
    if not (
        authority_policy.valid_from <= issued
        and spend_policy.valid_from <= issued
        and issued < expires
        and expires <= authority_policy.valid_until
        and expires <= spend_policy.valid_until
        and (expires - issued).total_seconds()
        <= authority_policy.max_authorization_lifetime_seconds
        and issued + timedelta(seconds=timeout_seconds) <= expires
    ):
        raise ValueError("canary authorization window exceeds policy")
    output_sha256 = _directory_sha256(output_directory)
    return OpenAIResponsesCanaryAuthorization(
        authority_policy_sha256=authority_policy.policy_sha256,
        spend_policy_sha256=spend_policy.policy_sha256,
        ledger_id=ledger_id,
        ledger_entry_id=output_sha256,
        output_directory_sha256=output_sha256,
        request=openai_responses_canary_request_contract(),
        token_count_request_sha256=digest(
            _json_bytes(openai_responses_canary_count_request())
        ),
        response_request_sha256=digest(_json_bytes(openai_responses_canary_request())),
        max_cost_microusd=max_cost,
        timeout_seconds=timeout_seconds,
        issued_at=issued,
        valid_until=expires,
    )


def sign_openai_responses_canary_authorization(
    authorization: OpenAIResponsesCanaryAuthorization,
    signer_id: str,
    private_key: bytes,
) -> SignedOpenAIResponsesCanaryAuthorization:
    """Sign exact canary authority; command-line paths never accept private keys."""

    if len(private_key) != 32:
        raise ValueError("Ed25519 private key must contain 32 bytes")
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(_DOMAIN + canonical_bytes(authorization))
    except (ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return SignedOpenAIResponsesCanaryAuthorization(
        authorization=authorization,
        signature=OpenAIResponsesCanaryAuthorizationSignature(
            signer_id=signer_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            authorization_sha256=authorization.authorization_sha256,
            signature_base64=base64.b64encode(signature).decode("ascii"),
        ),
    )


def verify_openai_responses_canary_authorization(
    signed: SignedOpenAIResponsesCanaryAuthorization,
    authority_policy: OpenAIResponsesCanaryAuthorityPolicy,
    spend_policy: SpendPolicy,
    ledger_id: str,
    output_directory: Path,
    timeout_seconds: float,
    now: datetime,
) -> OpenAIResponsesCanaryAuthorization:
    """Authenticate current exact request and spend authority before key access."""

    current = _require_utc(now)
    signed = SignedOpenAIResponsesCanaryAuthorization.model_validate_json(
        canonical_bytes(signed)
    )
    authority_policy = OpenAIResponsesCanaryAuthorityPolicy.model_validate_json(
        canonical_bytes(authority_policy)
    )
    matches = [
        item
        for item in authority_policy.authorities
        if item.authority_id == signed.signature.signer_id
    ]
    if (
        len(matches) != 1
        or matches[0].public_key_sha256 != signed.signature.public_key_sha256
        or signed.authorization.authority_policy_sha256
        != authority_policy.policy_sha256
    ):
        raise ValueError("canary authorization signer is not enrolled")
    signer = matches[0]
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(signer.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(signed.authorization),
        )
    except (InvalidSignature, ValueError, UnsupportedAlgorithm):
        raise ValueError("canary authorization signature is invalid") from None
    expected = make_openai_responses_canary_authorization(
        spend_policy,
        ledger_id,
        authority_policy,
        output_directory,
        timeout_seconds,
        signed.authorization.issued_at,
        signed.authorization.valid_until,
    )
    if (
        signed.authorization != expected
        or not authority_policy.valid_from <= current <= authority_policy.valid_until
        or not spend_policy.valid_from <= current <= spend_policy.valid_until
        or not signed.authorization.issued_at
        <= current
        <= signed.authorization.valid_until
        or current + timedelta(seconds=timeout_seconds)
        > signed.authorization.valid_until
    ):
        raise ValueError("canary authorization does not match current policy")
    return signed.authorization


def begin_openai_responses_canary(
    directory: Path,
    authority_policy: OpenAIResponsesCanaryAuthorityPolicy,
    signed_authorization: SignedOpenAIResponsesCanaryAuthorization,
    spend_policy: SpendPolicy,
) -> None:
    """Create a fresh private run and preserve every trusted input before dispatch."""

    if directory.exists() or directory.is_symlink():
        raise ValueError("canary output directory already exists")
    if not directory.parent.is_dir():
        raise ValueError("canary output parent must already exist")
    directory.mkdir(mode=0o700)
    payloads = {
        "authority-policy.json": canonical_bytes(authority_policy),
        "signed-authorization.json": canonical_bytes(signed_authorization),
        "spend-policy.json": canonical_bytes(spend_policy),
        "request.json": _json_bytes(openai_responses_canary_request()),
    }
    for name, payload in payloads.items():
        private_write(directory / name, payload)


async def execute_openai_responses_canary(
    transport: CountedTransport,
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    directory: Path,
    authority_policy: OpenAIResponsesCanaryAuthorityPolicy,
    signed_authorization: SignedOpenAIResponsesCanaryAuthorization,
    *,
    completed_at: datetime | None = None,
    sdk_version: str,
) -> OpenAIResponsesCanaryResult:
    """Execute the fixed request once and commit a manifest only after verification."""

    authorization = verify_openai_responses_canary_authorization(
        signed_authorization,
        authority_policy,
        spend_policy,
        ledger.policy.ledger_id,
        directory,
        signed_authorization.authorization.timeout_seconds,
        datetime.now(UTC),
    )
    snapshot = ledger.snapshot()
    if (
        snapshot.blocked
        or snapshot.available_microusd < authorization.max_cost_microusd
    ):
        raise ValueError("canary ledger cannot cover maximum authorized exposure")
    if ledger.entry_status(authorization.ledger_entry_id) is not None:
        raise ValueError("canary spending identity was already used")
    preserved = {
        "authority-policy.json": canonical_bytes(authority_policy),
        "signed-authorization.json": canonical_bytes(signed_authorization),
        "spend-policy.json": canonical_bytes(spend_policy),
        "request.json": _json_bytes(openai_responses_canary_request()),
    }
    if any(
        read_bounded(directory / name, OPENAI_RESPONSES_CANARY_MAX_ARTIFACT_BYTES)
        != payload
        for name, payload in preserved.items()
    ):
        raise ValueError("canary preserved inputs changed before dispatch")
    budgeted = BudgetedOpenAITransport(transport, spend_policy, directory, ledger)
    async with asyncio.timeout(authorization.timeout_seconds):
        raw_response = await budgeted.create_response(openai_responses_canary_request())
    response = response_from_payload(raw_response)
    reservation_payload = read_bounded(
        directory / "spend-reservation.json",
        OPENAI_RESPONSES_CANARY_MAX_ARTIFACT_BYTES,
    )
    receipt_payload = read_bounded(
        directory / "spend-receipt.json",
        OPENAI_RESPONSES_CANARY_MAX_ARTIFACT_BYTES,
    )
    reservation = SpendReservation.model_validate_json(reservation_payload)
    receipt = SpendReceipt.model_validate_json(receipt_payload)
    if (
        receipt.status != "settled"
        or receipt.ledger_id != authorization.ledger_id
        or receipt.ledger_entry_id != authorization.ledger_entry_id
        or reservation.policy_sha256 != authorization.spend_policy_sha256
        or reservation.request_sha256 != authorization.response_request_sha256
        or reservation.max_output_tokens != OPENAI_RESPONSES_CANARY_MAX_OUTPUT_TOKENS
        or reservation.reserved_microusd > authorization.max_cost_microusd
        or receipt.input_tokens != response.usage.input
        or receipt.output_tokens != response.usage.output
    ):
        raise ValueError("canary spending evidence does not match authorization")
    result = OpenAIResponsesCanaryResult(
        completed_at=_require_utc(
            completed_at if completed_at is not None else datetime.now(UTC)
        ),
        sdk_version=sdk_version,
        authority_policy_sha256=authorization.authority_policy_sha256,
        signed_authorization_sha256=signed_authorization.signed_authorization_sha256,
        authorization_sha256=authorization.authorization_sha256,
        spend_policy_sha256=authorization.spend_policy_sha256,
        ledger_id=authorization.ledger_id,
        ledger_entry_id=authorization.ledger_entry_id,
        token_count_request_sha256=authorization.token_count_request_sha256,
        response_request_sha256=authorization.response_request_sha256,
        provider_response_sha256=digest(canonical_bytes(response)),
        spend_reservation_sha256=digest(reservation_payload),
        spend_receipt_sha256=digest(receipt_payload),
        retained_microusd=receipt.retained_microusd,
        response=response,
    )
    result_payload = canonical_bytes(result)
    private_write(directory / "result.json", result_payload)
    artifacts = tuple(
        ArtifactHash(
            name=name,
            sha256=digest(
                read_bounded(
                    directory / name, OPENAI_RESPONSES_CANARY_MAX_ARTIFACT_BYTES
                )
            ),
        )
        for name in OPENAI_RESPONSES_CANARY_ARTIFACTS
    )
    private_write(
        directory / "manifest.json",
        canonical_bytes(
            OpenAIResponsesCanaryManifest(
                output_directory_sha256=_directory_sha256(directory),
                artifacts=artifacts,
            )
        ),
    )
    return result


def load_openai_responses_canary(
    directory: Path, ledger: SpendLedger | None = None
) -> OpenAIResponsesCanaryResult:
    """Reverify a completed canary from its content-addressed private artifacts."""

    manifest = OpenAIResponsesCanaryManifest.model_validate_json(
        read_bounded(
            directory / "manifest.json", OPENAI_RESPONSES_CANARY_MAX_ARTIFACT_BYTES
        )
    )
    names = tuple(item.name for item in manifest.artifacts)
    actual_names = {path.name for path in directory.iterdir()}
    if (
        manifest.output_directory_sha256 != _directory_sha256(directory)
        or names != OPENAI_RESPONSES_CANARY_ARTIFACTS
        or actual_names != {*OPENAI_RESPONSES_CANARY_ARTIFACTS, "manifest.json"}
        or any(path.is_symlink() or not path.is_file() for path in directory.iterdir())
    ):
        raise ValueError("canary manifest identity or artifact set is invalid")
    payloads: dict[str, bytes] = {}
    for artifact in manifest.artifacts:
        payload = read_bounded(
            directory / artifact.name, OPENAI_RESPONSES_CANARY_MAX_ARTIFACT_BYTES
        )
        if digest(payload) != artifact.sha256:
            raise ValueError(f"canary artifact digest mismatch: {artifact.name}")
        payloads[artifact.name] = payload
    if payloads["request.json"] != _json_bytes(openai_responses_canary_request()):
        raise ValueError("canary request is not the fixed synthetic request")
    authority_policy = OpenAIResponsesCanaryAuthorityPolicy.model_validate_json(
        payloads["authority-policy.json"]
    )
    signed = SignedOpenAIResponsesCanaryAuthorization.model_validate_json(
        payloads["signed-authorization.json"]
    )
    spend_policy = SpendPolicy.model_validate_json(payloads["spend-policy.json"])
    reservation = SpendReservation.model_validate_json(
        payloads["spend-reservation.json"]
    )
    receipt = SpendReceipt.model_validate_json(payloads["spend-receipt.json"])
    result = OpenAIResponsesCanaryResult.model_validate_json(payloads["result.json"])
    authorization = verify_openai_responses_canary_authorization(
        signed,
        authority_policy,
        spend_policy,
        result.ledger_id,
        directory,
        signed.authorization.timeout_seconds,
        result.completed_at,
    )
    if (
        result.authority_policy_sha256 != authority_policy.policy_sha256
        or result.signed_authorization_sha256 != signed.signed_authorization_sha256
        or result.authorization_sha256 != authorization.authorization_sha256
        or result.spend_policy_sha256 != spend_policy.policy_sha256
        or result.ledger_id != authorization.ledger_id
        or result.ledger_entry_id != authorization.ledger_entry_id
        or result.token_count_request_sha256
        != digest(_json_bytes(openai_responses_canary_count_request()))
        or result.response_request_sha256
        != digest(_json_bytes(openai_responses_canary_request()))
        or result.spend_reservation_sha256 != digest(payloads["spend-reservation.json"])
        or result.spend_receipt_sha256 != digest(payloads["spend-receipt.json"])
        or reservation.policy_sha256 != spend_policy.policy_sha256
        or reservation.request_sha256 != authorization.response_request_sha256
        or reservation.max_output_tokens != OPENAI_RESPONSES_CANARY_MAX_OUTPUT_TOKENS
        or receipt.reservation_sha256 != digest(canonical_bytes(reservation))
        or receipt.status != "settled"
        or receipt.ledger_id != authorization.ledger_id
        or receipt.ledger_entry_id != authorization.ledger_entry_id
        or receipt.input_tokens != result.response.usage.input
        or receipt.output_tokens != result.response.usage.output
        or result.retained_microusd != receipt.retained_microusd
        or receipt.retained_microusd
        != spend_policy.cost(result.response.usage.input, result.response.usage.output)
    ):
        raise ValueError("canary artifacts do not match their authorization")
    if ledger is not None:
        status = ledger.entry_status(authorization.ledger_entry_id)
        expected_status = LedgerEntryStatus(
            entry_id=authorization.ledger_entry_id,
            reservation_sha256=digest(canonical_bytes(reservation)),
            reserved_microusd=reservation.reserved_microusd,
            charged_microusd=receipt.retained_microusd,
            status="settled",
        )
        if (
            status != expected_status
            or ledger.policy.ledger_id != authorization.ledger_id
        ):
            raise ValueError("canary ledger evidence does not match artifacts")
    return result
