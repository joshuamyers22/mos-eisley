"""Atomic private response retention and reasoning-redacted runtime publication."""

from __future__ import annotations

import os
import sqlite3
import stat
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self, cast

from pydantic import Field, JsonValue, TypeAdapter, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import Effort, ReasoningBlock, TextBlock, Turn, Usage
from mos_eisley.core.skills import SkillIdentity
from mos_eisley.providers.openai_responses import response_from_payload
from mos_eisley.run.skill_runtime_grant import (
    IssuedSkillRuntimeBrokerGrant,
    SkillRuntimeBrokerGrantStore,
)
from mos_eisley.run.skill_runtime_preflight import PreparedSkillRuntimeRequest
from mos_eisley.run.skill_runtime_provider import (
    SkillRuntimeProviderOutcome,
    SkillRuntimeProviderReply,
    SkillRuntimeProviderSendIntent,
    SkillRuntimeProviderTransactionStore,
    inspect_skill_runtime_provider_transaction,
    skill_runtime_provider_response_bytes,
    skill_runtime_provider_response_sha256,
)
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write

_PUBLICATION_DOMAIN = b"mos-eisley/skill-runtime-response-publication/v1\x00"
_HISTORY_DOMAIN = b"mos-eisley/skill-runtime-response-history/v1\x00"
_STORE_WRITER = object()
_RESPONSE = TypeAdapter(dict[str, JsonValue])
UtcTimestamp = Annotated[datetime, Field()]
Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class SkillRuntimeResponseStorePolicy(Contract):
    schema_version: Literal[2] = 2
    mode: Literal["skill_runtime_response_store_policy"] = (
        "skill_runtime_response_store_policy"
    )
    store_id: Digest
    provider_transaction_store_id: Digest
    max_publications: Annotated[int, Field(ge=1, le=100_000)] = 10_000
    max_raw_response_bytes: Annotated[int, Field(ge=1024, le=1_000_000)] = 1_000_000
    max_total_raw_response_bytes: Annotated[int, Field(ge=1024, le=1_000_000_000)] = (
        64_000_000
    )
    max_published_result_bytes: Annotated[int, Field(ge=1024, le=1_000_000)] = 1_000_000
    private_raw_response_retention_required: Literal[True] = True
    publish_reasoning_authorized: Literal[False] = False
    publish_provider_credentials_authorized: Literal[False] = False
    automatic_provider_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bounded_retention(self) -> Self:
        if self.max_raw_response_bytes > self.max_total_raw_response_bytes:
            raise ValueError("per-response limit exceeds total retention limit")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class PublishedSkillRuntimeResult(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["published_skill_runtime_result"] = "published_skill_runtime_result"
    response_store_policy_sha256: Digest
    publication_id: Digest
    transaction_id: Digest
    intent_sha256: Digest
    outcome_sha256: Digest
    issuance_sha256: Digest
    prepared_runtime_request_sha256: Digest
    runtime_request_sha256: Digest
    route_candidate_id: Digest
    provider_request_sha256: Digest
    provider_response_sha256: Digest
    spend_ledger_id: Digest
    ledger_entry_id: Digest
    skill: SkillIdentity
    model: Identifier
    effort: Effort
    provider_request_id: Annotated[str, Field(min_length=1, max_length=1000)]
    stop_reason: Literal["end_turn", "max_output", "filtered"]
    usage: Usage
    charged_microusd: Money
    assistant: Turn
    published_at: UtcTimestamp
    raw_response_retained_privately: Literal[True] = True
    reasoning_omitted_from_publication: Literal[True] = True
    provider_credential_added_to_publication: Literal[False] = False
    provider_retry_permitted: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @model_validator(mode="after")
    def safe_result(self) -> Self:
        _require_utc(self.published_at)
        if self.assistant.role != "assistant" or any(
            not isinstance(block, TextBlock) for block in self.assistant.blocks
        ):
            raise ValueError("published runtime result must contain text only")
        if self.usage.unit != "tokens":
            raise ValueError("published runtime usage must use provider tokens")
        return self

    @property
    def result_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeResponsePublication(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_response_publication"] = (
        "skill_runtime_response_publication"
    )
    response_store_policy_sha256: Digest
    publication_id: Digest
    transaction_id: Digest
    intent_sha256: Digest
    outcome_sha256: Digest
    issuance_sha256: Digest
    raw_response_sha256: Digest
    result_sha256: Digest
    committed_at: UtcTimestamp
    content_verified: Literal[True] = True
    raw_response_private: Literal[True] = True
    published_result_reasoning_free: Literal[True] = True
    provider_retry_permitted: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @model_validator(mode="after")
    def utc_timestamp(self) -> Self:
        _require_utc(self.committed_at)
        return self

    @property
    def publication_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimeResponseStoreStatus(Contract):
    schema_version: Literal[1] = 1
    response_store_policy_sha256: Digest
    publications: Annotated[int, Field(ge=0)]
    provider_retry_permitted: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    raw_response_export_authorized: Literal[False] = False


class SkillRuntimeResponseHistory(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_response_history"] = "skill_runtime_response_history"
    response_store_policy_sha256: Digest
    publications: Annotated[int, Field(ge=0)]
    history_sha256: Digest
    latest_publication_id: Digest | None
    latest_publication_sha256: Digest | None
    raw_responses_included: Literal[False] = False
    published_results_included: Literal[False] = False

    @model_validator(mode="after")
    def consistent_latest(self) -> Self:
        empty = self.publications == 0
        if empty != (self.latest_publication_id is None) or empty != (
            self.latest_publication_sha256 is None
        ):
            raise ValueError("runtime response history latest entry is inconsistent")
        return self


def _validate_private_database(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("runtime response store must be a regular file")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("runtime response store must be private and locally owned")


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
            raise ValueError("runtime response store requires rollback journaling")
        return connection
    except BaseException:
        connection.close()
        raise


def _load_policy(connection: sqlite3.Connection) -> SkillRuntimeResponseStorePolicy:
    rows = connection.execute("SELECT policy_json FROM store_policy").fetchall()
    if len(rows) != 1:
        raise ValueError("runtime response store policy is invalid")
    policy = SkillRuntimeResponseStorePolicy.model_validate_json(rows[0][0])
    if rows[0][0] != canonical_bytes(policy):
        raise ValueError("runtime response store policy is not canonical")
    return policy


def _publication_id(outcome: SkillRuntimeProviderOutcome) -> str:
    return digest(_PUBLICATION_DOMAIN + bytes.fromhex(outcome.outcome_sha256))


def _publication_matches(
    policy: SkillRuntimeResponseStorePolicy,
    publication: SkillRuntimeResponsePublication,
    result: PublishedSkillRuntimeResult,
    intent: SkillRuntimeProviderSendIntent,
    outcome: SkillRuntimeProviderOutcome,
    raw_response: bytes,
) -> bool:
    return (
        publication.response_store_policy_sha256 == policy.policy_sha256
        and publication.publication_id == _publication_id(outcome)
        and publication.publication_id == result.publication_id
        and publication.transaction_id == result.transaction_id == intent.transaction_id
        and publication.intent_sha256 == result.intent_sha256 == intent.intent_sha256
        and publication.outcome_sha256
        == result.outcome_sha256
        == outcome.outcome_sha256
        and publication.issuance_sha256
        == result.issuance_sha256
        == intent.issuance_sha256
        and publication.raw_response_sha256
        == result.provider_response_sha256
        == outcome.provider_response_sha256
        == digest(raw_response)
        and publication.result_sha256 == result.result_sha256
        and publication.committed_at == result.published_at
        and publication.committed_at >= outcome.completed_at
        and result.response_store_policy_sha256 == policy.policy_sha256
        and result.prepared_runtime_request_sha256
        == intent.prepared_runtime_request_sha256
        and result.runtime_request_sha256 == intent.runtime_request_sha256
        and result.route_candidate_id == intent.route_candidate_id
        and result.provider_request_sha256 == intent.provider_request_sha256
        and result.spend_ledger_id == intent.spend_ledger_id
        and result.ledger_entry_id == intent.ledger_entry_id
        and result.charged_microusd == outcome.charged_microusd
        and outcome.status == "response_received"
        and len(raw_response) <= policy.max_raw_response_bytes
        and len(canonical_bytes(result)) <= policy.max_published_result_bytes
    )


def _result_matches_response(
    result: PublishedSkillRuntimeResult,
    outcome: SkillRuntimeProviderOutcome,
    response: dict[str, JsonValue],
) -> bool:
    try:
        model_response = response_from_payload(response)
    except ProviderError:
        return False
    text = tuple(
        block for block in model_response.turn.blocks if isinstance(block, TextBlock)
    )
    return (
        bool(text)
        and all(
            isinstance(block, (TextBlock, ReasoningBlock))
            for block in model_response.turn.blocks
        )
        and model_response.stop_reason in {"end_turn", "max_output", "filtered"}
        and model_response.provider_request_id == result.provider_request_id
        and model_response.stop_reason == result.stop_reason
        and model_response.usage == result.usage
        and result.assistant == Turn(role="assistant", blocks=text)
        and result.usage.input == outcome.input_tokens
        and result.usage.output == outcome.output_tokens
        and response.get("model") == result.model
    )


class SkillRuntimeResponseStore:
    """Atomic private raw response plus safe reasoning-free result publication."""

    def __init__(self, path: Path):
        self.path = path.absolute()
        with closing(_connect(self.path)) as connection:
            self.policy = _load_policy(connection)

    @classmethod
    def create(
        cls,
        path: Path,
        policy: SkillRuntimeResponseStorePolicy,
        transaction_store: SkillRuntimeProviderTransactionStore,
    ) -> SkillRuntimeResponseStore:
        if (
            transaction_store.policy.response_store_policy_sha256
            != policy.policy_sha256
            or policy.provider_transaction_store_id != transaction_store.policy.store_id
        ):
            raise ValueError("runtime response store policy does not match transaction")
        policy = SkillRuntimeResponseStorePolicy.model_validate_json(
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
                "CREATE TABLE publications (sequence INTEGER NOT NULL UNIQUE "
                "CHECK(sequence >= 1), publication_id TEXT PRIMARY KEY, "
                "transaction_id TEXT NOT NULL UNIQUE, outcome_sha256 TEXT NOT NULL "
                "UNIQUE, provider_request_id TEXT NOT NULL UNIQUE, "
                "raw_response_sha256 TEXT NOT NULL, result_sha256 TEXT NOT NULL "
                "UNIQUE, publication_sha256 TEXT NOT NULL UNIQUE, "
                "raw_response_json BLOB NOT NULL, result_json BLOB NOT NULL, "
                "publication_json BLOB NOT NULL, intent_json BLOB NOT NULL, "
                "outcome_json BLOB NOT NULL) STRICT"
            )
        return cls(path)

    def _records(
        self, connection: sqlite3.Connection
    ) -> tuple[
        tuple[
            SkillRuntimeResponsePublication,
            PublishedSkillRuntimeResult,
            SkillRuntimeProviderSendIntent,
            SkillRuntimeProviderOutcome,
            bytes,
        ],
        ...,
    ]:
        inventory = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(length(raw_response_json)), 0) "
            "FROM publications"
        ).fetchone()
        if (
            inventory is None
            or inventory[0] > self.policy.max_publications
            or inventory[1] > self.policy.max_total_raw_response_bytes
        ):
            raise ValueError("runtime response store exceeds policy")
        rows = connection.execute(
            "SELECT sequence, publication_id, transaction_id, outcome_sha256, "
            "provider_request_id, raw_response_sha256, result_sha256, "
            "publication_sha256, raw_response_json, result_json, publication_json, "
            "intent_json, outcome_json FROM publications ORDER BY sequence"
        ).fetchall()
        records: list[
            tuple[
                SkillRuntimeResponsePublication,
                PublishedSkillRuntimeResult,
                SkillRuntimeProviderSendIntent,
                SkillRuntimeProviderOutcome,
                bytes,
            ]
        ] = []
        for row in rows:
            raw_response = bytes(row[8])
            result = PublishedSkillRuntimeResult.model_validate_json(row[9])
            publication = SkillRuntimeResponsePublication.model_validate_json(row[10])
            intent = SkillRuntimeProviderSendIntent.model_validate_json(row[11])
            outcome = SkillRuntimeProviderOutcome.model_validate_json(row[12])
            try:
                response = _RESPONSE.validate_json(raw_response, strict=True)
            except ValueError:
                raise ValueError("runtime response store payload is invalid") from None
            if (
                row[0] != len(records) + 1
                or row[1] != publication.publication_id
                or row[2] != publication.transaction_id
                or row[3] != publication.outcome_sha256
                or row[4] != result.provider_request_id
                or row[5] != publication.raw_response_sha256
                or row[6] != publication.result_sha256
                or row[7] != publication.publication_sha256
                or row[8] != skill_runtime_provider_response_bytes(response)
                or row[9] != canonical_bytes(result)
                or row[10] != canonical_bytes(publication)
                or row[11] != canonical_bytes(intent)
                or row[12] != canonical_bytes(outcome)
                or not _publication_matches(
                    self.policy,
                    publication,
                    result,
                    intent,
                    outcome,
                    raw_response,
                )
                or not _result_matches_response(result, outcome, response)
            ):
                raise ValueError("runtime response store record is invalid")
            records.append((publication, result, intent, outcome, raw_response))
        if len(records) > self.policy.max_publications:
            raise ValueError("runtime response store exceeds policy")
        return tuple(records)

    def publish(
        self,
        publication: SkillRuntimeResponsePublication,
        result: PublishedSkillRuntimeResult,
        intent: SkillRuntimeProviderSendIntent,
        outcome: SkillRuntimeProviderOutcome,
        raw_response: bytes,
        *,
        writer: object,
    ) -> None:
        if writer is not _STORE_WRITER:
            raise ValueError("runtime response must be published by its compiler")
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if _load_policy(connection) != self.policy:
                raise ValueError("runtime response store identity changed")
            records = self._records(connection)
            if len(records) >= self.policy.max_publications:
                raise ValueError("runtime response store limit reached")
            if (
                sum(len(stored_raw) for _, _, _, _, stored_raw in records)
                + len(raw_response)
                > self.policy.max_total_raw_response_bytes
            ):
                raise ValueError("runtime response store retention limit reached")
            if not _publication_matches(
                self.policy, publication, result, intent, outcome, raw_response
            ):
                raise ValueError("runtime response publication provenance mismatch")
            try:
                response = _RESPONSE.validate_json(raw_response, strict=True)
            except ValueError:
                raise ValueError(
                    "runtime response publication payload is invalid"
                ) from None
            if skill_runtime_provider_response_bytes(
                response
            ) != raw_response or not _result_matches_response(
                result, outcome, response
            ):
                raise ValueError("runtime response publication result is invalid")
            if any(
                stored.publication_id == publication.publication_id
                or stored.transaction_id == publication.transaction_id
                or stored.outcome_sha256 == publication.outcome_sha256
                for stored, _, _, _, _ in records
            ):
                raise ValueError("runtime response was already published")
            connection.execute(
                "INSERT INTO publications VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    len(records) + 1,
                    publication.publication_id,
                    publication.transaction_id,
                    publication.outcome_sha256,
                    result.provider_request_id,
                    publication.raw_response_sha256,
                    publication.result_sha256,
                    publication.publication_sha256,
                    raw_response,
                    canonical_bytes(result),
                    canonical_bytes(publication),
                    canonical_bytes(intent),
                    canonical_bytes(outcome),
                ),
            )

    def load(
        self, publication_id: str
    ) -> tuple[SkillRuntimeResponsePublication, PublishedSkillRuntimeResult]:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("runtime response store identity changed")
            matches = [
                item
                for item in self._records(connection)
                if item[0].publication_id == publication_id
            ]
            if len(matches) != 1:
                raise ValueError("runtime response publication is absent")
            return matches[0][0], matches[0][1]

    def _history(
        self,
        records: tuple[
            tuple[
                SkillRuntimeResponsePublication,
                PublishedSkillRuntimeResult,
                SkillRuntimeProviderSendIntent,
                SkillRuntimeProviderOutcome,
                bytes,
            ],
            ...,
        ],
        publications: int | None = None,
    ) -> SkillRuntimeResponseHistory:
        count = len(records) if publications is None else publications
        if not 0 <= count <= len(records):
            raise ValueError("runtime response history prefix is unavailable")
        state = digest(_HISTORY_DOMAIN)
        selected = records[:count]
        for publication, _, _, _, _ in selected:
            state = digest(
                _HISTORY_DOMAIN
                + bytes.fromhex(state)
                + bytes.fromhex(publication.publication_sha256)
            )
        latest = selected[-1][0] if selected else None
        return SkillRuntimeResponseHistory(
            response_store_policy_sha256=self.policy.policy_sha256,
            publications=count,
            history_sha256=state,
            latest_publication_id=(
                latest.publication_id if latest is not None else None
            ),
            latest_publication_sha256=(
                latest.publication_sha256 if latest is not None else None
            ),
        )

    def history(self) -> SkillRuntimeResponseHistory:
        """Return a hash-only commitment to the fully revalidated ordered history."""

        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("runtime response store identity changed")
            return self._history(self._records(connection))

    def verify_history_prefix(
        self, expected: SkillRuntimeResponseHistory
    ) -> SkillRuntimeResponseHistory:
        """Require an exact committed prefix and return the verified current head."""

        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("runtime response store identity changed")
            records = self._records(connection)
            if (
                expected.response_store_policy_sha256 != self.policy.policy_sha256
                or self._history(records, expected.publications) != expected
            ):
                raise ValueError("runtime response history checkpoint does not match")
            return self._history(records)

    def status(self) -> SkillRuntimeResponseStoreStatus:
        with closing(_connect(self.path)) as connection, connection:
            connection.execute("BEGIN")
            if _load_policy(connection) != self.policy:
                raise ValueError("runtime response store identity changed")
            return SkillRuntimeResponseStoreStatus(
                response_store_policy_sha256=self.policy.policy_sha256,
                publications=len(self._records(connection)),
            )


def publish_skill_runtime_response(
    prepared: PreparedSkillRuntimeRequest,
    issuance: IssuedSkillRuntimeBrokerGrant,
    reply: SkillRuntimeProviderReply,
    grant_store: SkillRuntimeBrokerGrantStore,
    transaction_store: SkillRuntimeProviderTransactionStore,
    ledger: SpendLedger,
    response_store: SkillRuntimeResponseStore,
    now: datetime,
) -> tuple[SkillRuntimeResponsePublication, PublishedSkillRuntimeResult]:
    """Atomically retain exact private response and publish reasoning-free result."""

    current = _require_utc(now)
    if (
        transaction_store.policy.response_store_policy_sha256
        != response_store.policy.policy_sha256
        or response_store.policy.provider_transaction_store_id
        != transaction_store.policy.store_id
    ):
        raise ValueError("skill runtime response store provenance mismatch")
    status = inspect_skill_runtime_provider_transaction(
        issuance, grant_store, transaction_store, ledger
    )
    stored = transaction_store.get(issuance.issuance_sha256)
    if (
        status.phase != "finished"
        or status.outcome != "response_received"
        or status.ledger_status != "settled"
        or stored is None
        or stored != (reply.intent, reply.outcome)
        or prepared.preflight_sha256 != reply.intent.prepared_runtime_request_sha256
        or prepared.runtime_request_sha256 != reply.intent.runtime_request_sha256
        or prepared.route.candidate_id != reply.intent.route_candidate_id
        or issuance.issuance_sha256 != reply.intent.issuance_sha256
        or reply.outcome.provider_response_sha256 is None
        or skill_runtime_provider_response_sha256(reply.response)
        != reply.outcome.provider_response_sha256
    ):
        raise ValueError("skill runtime response transaction provenance is incomplete")
    model_response = response_from_payload(reply.response)
    if (
        model_response.provider_request_id is None
        or model_response.stop_reason not in {"end_turn", "max_output", "filtered"}
        or reply.outcome.input_tokens != model_response.usage.input
        or reply.outcome.output_tokens != model_response.usage.output
    ):
        raise ValueError("skill runtime provider response is not publishable")
    text = tuple(
        block for block in model_response.turn.blocks if isinstance(block, TextBlock)
    )
    if not text:
        raise ValueError("skill runtime provider response has no publishable text")
    if any(
        not isinstance(block, (TextBlock, ReasoningBlock))
        for block in model_response.turn.blocks
    ):
        raise ValueError("skill runtime provider response contains unauthorized tools")
    published_stop_reason = cast(
        Literal["end_turn", "max_output", "filtered"], model_response.stop_reason
    )
    published_at = max(current, reply.outcome.completed_at)
    publication_id = _publication_id(reply.outcome)
    result = PublishedSkillRuntimeResult(
        response_store_policy_sha256=response_store.policy.policy_sha256,
        publication_id=publication_id,
        transaction_id=reply.intent.transaction_id,
        intent_sha256=reply.intent.intent_sha256,
        outcome_sha256=reply.outcome.outcome_sha256,
        issuance_sha256=issuance.issuance_sha256,
        prepared_runtime_request_sha256=prepared.preflight_sha256,
        runtime_request_sha256=prepared.runtime_request_sha256,
        route_candidate_id=prepared.route.candidate_id,
        provider_request_sha256=reply.intent.provider_request_sha256,
        provider_response_sha256=reply.outcome.provider_response_sha256,
        spend_ledger_id=reply.intent.spend_ledger_id,
        ledger_entry_id=reply.intent.ledger_entry_id,
        skill=prepared.skill,
        model=prepared.route.model,
        effort=prepared.route.effort,
        provider_request_id=model_response.provider_request_id,
        stop_reason=published_stop_reason,
        usage=model_response.usage,
        charged_microusd=reply.outcome.charged_microusd,
        assistant=Turn(role="assistant", blocks=text),
        published_at=published_at,
    )
    raw_response = skill_runtime_provider_response_bytes(reply.response)
    publication = SkillRuntimeResponsePublication(
        response_store_policy_sha256=response_store.policy.policy_sha256,
        publication_id=publication_id,
        transaction_id=reply.intent.transaction_id,
        intent_sha256=reply.intent.intent_sha256,
        outcome_sha256=reply.outcome.outcome_sha256,
        issuance_sha256=issuance.issuance_sha256,
        raw_response_sha256=reply.outcome.provider_response_sha256,
        result_sha256=result.result_sha256,
        committed_at=published_at,
    )
    response_store.publish(
        publication,
        result,
        reply.intent,
        reply.outcome,
        raw_response,
        writer=_STORE_WRITER,
    )
    return publication, result
