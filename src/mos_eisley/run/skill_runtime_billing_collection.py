"""Strict private collection of complete OpenAI aggregate billing pages."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, TypeAdapter, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest

UtcTimestamp = Annotated[datetime, Field()]
Cursor = Annotated[str, Field(min_length=1, max_length=2048)]
ExternalIdentifier = Annotated[str, Field(min_length=1, max_length=1000)]
Count = Annotated[int, Field(ge=0)]
Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]
OptionalCount = Annotated[int, Field(ge=0)] | None
_USAGE_DOMAIN = b"mos-eisley/openai-billing-usage-pages/v1\x00"
_COSTS_DOMAIN = b"mos-eisley/openai-billing-cost-pages/v1\x00"
_IDENTIFIER: TypeAdapter[str] = TypeAdapter(Identifier)


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class OpenAICompletionUsageResult(Contract):
    object: Literal["organization.usage.completions.result"]
    input_tokens: Count
    output_tokens: Count
    num_model_requests: Count
    project_id: ExternalIdentifier
    api_key_id: ExternalIdentifier
    model: Identifier
    service_tier: Literal["default"]
    user_id: None = None
    batch: bool | None = None
    input_audio_tokens: OptionalCount = None
    input_cache_write_tokens: OptionalCount = None
    input_cached_audio_tokens: OptionalCount = None
    input_cached_image_tokens: OptionalCount = None
    input_cached_text_tokens: OptionalCount = None
    input_cached_tokens: OptionalCount = None
    input_image_tokens: OptionalCount = None
    input_text_tokens: OptionalCount = None
    input_uncached_tokens: OptionalCount = None
    output_audio_tokens: OptionalCount = None
    output_image_tokens: OptionalCount = None
    output_text_tokens: OptionalCount = None


class OpenAICompletionUsageBucket(Contract):
    object: Literal["bucket"]
    start_time: Annotated[int, Field(ge=0)]
    end_time: Annotated[int, Field(gt=0)]
    results: Annotated[tuple[OpenAICompletionUsageResult, ...], Field(max_length=1000)]


class OpenAICompletionUsagePage(Contract):
    object: Literal["page"]
    data: Annotated[tuple[OpenAICompletionUsageBucket, ...], Field(max_length=10)]
    has_more: bool
    next_page: Cursor | None = None

    @model_validator(mode="after")
    def coherent_cursor(self) -> Self:
        if self.has_more != (self.next_page is not None):
            raise ValueError("OpenAI usage page cursor is inconsistent")
        return self


class OpenAICostAmount(Contract):
    value: Annotated[float, Field(ge=0, le=1_000_000)]
    currency: Literal["usd"]


class OpenAICostResult(Contract):
    object: Literal["organization.costs.result"]
    amount: OpenAICostAmount
    line_item: Annotated[str, Field(min_length=1, max_length=1000)]
    project_id: ExternalIdentifier
    api_key_id: ExternalIdentifier
    quantity: float | None = None
    quantity_unit: Annotated[str, Field(min_length=1, max_length=100)] | None = None


class OpenAICostBucket(Contract):
    object: Literal["bucket"]
    start_time: Annotated[int, Field(ge=0)]
    end_time: Annotated[int, Field(gt=0)]
    results: Annotated[tuple[OpenAICostResult, ...], Field(max_length=1000)]


class OpenAICostPage(Contract):
    object: Literal["page"]
    data: Annotated[tuple[OpenAICostBucket, ...], Field(max_length=10)]
    has_more: bool
    next_page: Cursor | None = None

    @model_validator(mode="after")
    def coherent_cursor(self) -> Self:
        if self.has_more != (self.next_page is not None):
            raise ValueError("OpenAI costs page cursor is inconsistent")
        return self


class OpenAIAdminBillingTransport(Protocol):
    sdk_version: Identifier
    automatic_retries: Literal[0]

    async def completion_usage_page(
        self,
        *,
        start_time: int,
        end_time: int,
        project_id: str,
        api_key_id: str,
        model: str,
        page: str | None,
    ) -> dict[str, JsonValue]: ...

    async def costs_page(
        self,
        *,
        start_time: int,
        end_time: int,
        project_id: str,
        api_key_id: str,
        page: str | None,
    ) -> dict[str, JsonValue]: ...


class CollectedSkillRuntimeBillingEvidence(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["collected_skill_runtime_billing_evidence"] = (
        "collected_skill_runtime_billing_evidence"
    )
    provider: Literal["openai"] = "openai"
    usage_endpoint: Literal["GET /organization/usage/completions"] = (
        "GET /organization/usage/completions"
    )
    costs_endpoint: Literal["GET /organization/costs"] = "GET /organization/costs"
    project_id_sha256: Digest
    api_key_id_sha256: Digest
    model: Identifier
    service_tier: Literal["default"] = "default"
    usage_bucket_start: UtcTimestamp
    usage_bucket_end: UtcTimestamp
    costs_bucket_start: UtcTimestamp
    costs_bucket_end: UtcTimestamp
    usage_pages: Annotated[
        tuple[OpenAICompletionUsagePage, ...], Field(min_length=1, max_length=20)
    ]
    costs_pages: Annotated[
        tuple[OpenAICostPage, ...], Field(min_length=1, max_length=20)
    ]
    external_input_tokens: Count
    external_output_tokens: Count
    external_cost_microusd: Money
    collected_at: UtcTimestamp
    sdk_package: Literal["openai"] = "openai"
    sdk_version: Identifier
    official_sdk_used: Literal[True] = True
    bounded_http_client_used: Literal[True] = True
    automatic_retries: Literal[0] = 0
    trust_environment_disabled: Literal[True] = True
    redirects_disabled: Literal[True] = True
    pagination_complete: Literal[True] = True
    one_completion_request_in_usage_bucket_verified: Literal[True] = True
    complete_daily_api_key_exclusivity_proven: Literal[False] = False
    exact_provider_request_cost_attribution_proven: Literal[False] = False
    provider_request_id_present: Literal[False] = False
    admin_credential_persisted: Literal[False] = False
    billing_admin_read_performed: Literal[True] = True
    model_inference_request_sent: Literal[False] = False
    ledger_mutation_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False

    @model_validator(mode="after")
    def valid_collection(self) -> Self:
        for value in (
            self.usage_bucket_start,
            self.usage_bucket_end,
            self.costs_bucket_start,
            self.costs_bucket_end,
            self.collected_at,
        ):
            _require_utc(value)
        if self.usage_bucket_end - self.usage_bucket_start != timedelta(minutes=1):
            raise ValueError("collected usage bucket must span one minute")
        if (
            self.usage_bucket_start.second != 0
            or self.usage_bucket_start.microsecond != 0
        ):
            raise ValueError("collected usage bucket must align to a UTC minute")
        if self.costs_bucket_end - self.costs_bucket_start != timedelta(days=1):
            raise ValueError("collected costs bucket must span one day")
        if self.costs_bucket_start.time() != datetime.min.time():
            raise ValueError("collected costs bucket must align to a UTC day")
        if self.collected_at < max(self.usage_bucket_end, self.costs_bucket_end):
            raise ValueError("billing collection predates a completed bucket")
        _validate_page_chain(self.usage_pages, "usage")
        _validate_page_chain(self.costs_pages, "costs")
        usage_buckets = tuple(
            bucket for page in self.usage_pages for bucket in page.data
        )
        cost_buckets = tuple(
            bucket for page in self.costs_pages for bucket in page.data
        )
        usage_results = tuple(
            result for bucket in usage_buckets for result in bucket.results
        )
        cost_results = tuple(
            result for bucket in cost_buckets for result in bucket.results
        )
        usage_start = int(self.usage_bucket_start.timestamp())
        usage_end = int(self.usage_bucket_end.timestamp())
        costs_start = int(self.costs_bucket_start.timestamp())
        costs_end = int(self.costs_bucket_end.timestamp())
        if (
            len(usage_buckets) != 1
            or usage_buckets[0].start_time != usage_start
            or usage_buckets[0].end_time != usage_end
            or len(usage_results) != 1
        ):
            raise ValueError(
                "billing collection lacks one exact usage bucket and group"
            )
        usage = usage_results[0]
        if (
            usage.num_model_requests != 1
            or digest(usage.project_id.encode()) != self.project_id_sha256
            or digest(usage.api_key_id.encode()) != self.api_key_id_sha256
            or usage.model != self.model
            or usage.service_tier != self.service_tier
            or usage.input_tokens != self.external_input_tokens
            or usage.output_tokens != self.external_output_tokens
        ):
            raise ValueError("billing collection usage scope or totals are invalid")
        if (
            len(cost_buckets) != 1
            or not cost_results
            or cost_buckets[0].start_time != costs_start
            or cost_buckets[0].end_time != costs_end
        ):
            raise ValueError("billing collection lacks the exact costs bucket")
        if any(
            digest(result.project_id.encode()) != self.project_id_sha256
            or digest(result.api_key_id.encode()) != self.api_key_id_sha256
            for result in cost_results
        ):
            raise ValueError("billing collection costs scope is invalid")
        cost_groups = {
            (result.project_id, result.api_key_id, result.line_item)
            for result in cost_results
        }
        if len(cost_groups) != len(cost_results):
            raise ValueError("billing collection contains duplicate cost groups")
        try:
            microusd = sum(
                (Decimal(str(result.amount.value)) for result in cost_results),
                start=Decimal(0),
            ) * Decimal(1_000_000)
            if microusd != microusd.to_integral_value():
                raise ValueError("billing collection cost exceeds microusd precision")
            calculated_cost = int(microusd)
        except (InvalidOperation, OverflowError):
            raise ValueError("billing collection cost is invalid") from None
        if calculated_cost != self.external_cost_microusd:
            raise ValueError("billing collection cost total is invalid")
        return self

    @property
    def usage_evidence_sha256(self) -> str:
        return _pages_digest(_USAGE_DOMAIN, self.usage_pages)

    @property
    def costs_evidence_sha256(self) -> str:
        return _pages_digest(_COSTS_DOMAIN, self.costs_pages)

    @property
    def collection_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _pages_digest(domain: bytes, pages: tuple[Contract, ...]) -> str:
    state = digest(domain)
    for page in pages:
        state = digest(
            domain + bytes.fromhex(state) + bytes.fromhex(digest(canonical_bytes(page)))
        )
    return state


def _validate_page_chain(
    pages: tuple[OpenAICompletionUsagePage | OpenAICostPage, ...], label: str
) -> None:
    cursors: set[str] = set()
    for index, page in enumerate(pages):
        has_more = page.has_more
        next_page = page.next_page
        final = index == len(pages) - 1
        if final == has_more or final != (next_page is None):
            raise ValueError(f"OpenAI {label} pagination is incomplete")
        if next_page is not None and next_page in cursors:
            raise ValueError(f"OpenAI {label} pagination cursor repeated")
        if next_page is not None:
            cursors.add(next_page)


async def _collect_pages[PageT: (OpenAICompletionUsagePage, OpenAICostPage)](
    fetch: Callable[[str | None], Awaitable[dict[str, JsonValue]]],
    page_type: type[PageT],
    label: str,
) -> tuple[PageT, ...]:
    pages: list[PageT] = []
    cursor: str | None = None
    seen: set[str] = set()
    for _ in range(20):
        raw = await fetch(cursor)
        # Strict Python validation correctly rejects list-to-tuple coercion, while
        # strict JSON validation accepts JSON arrays as immutable tuple fields.
        page = page_type.model_validate_json(
            json.dumps(
                raw,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        pages.append(page)
        if not page.has_more:
            return tuple(pages)
        if page.next_page is None or page.next_page in seen:
            raise ValueError(f"OpenAI {label} pagination cursor is invalid")
        seen.add(page.next_page)
        cursor = page.next_page
    raise ValueError(f"OpenAI {label} pagination exceeds page limit")


async def collect_skill_runtime_billing_evidence(
    transport: OpenAIAdminBillingTransport,
    *,
    project_id: str,
    api_key_id: str,
    model: str,
    published_at: datetime,
    collected_at: datetime,
) -> CollectedSkillRuntimeBillingEvidence:
    """Collect and strictly reduce complete pages without sending a model request."""

    published = _require_utc(published_at)
    current = _require_utc(collected_at)
    if (
        not project_id
        or len(project_id) > 1000
        or not api_key_id
        or len(api_key_id) > 1000
    ):
        raise ValueError("billing collection scope identifiers are invalid")
    if transport.automatic_retries != 0:
        raise ValueError("billing collection transport must disable retries")
    _IDENTIFIER.validate_python(model, strict=True)
    usage_start = published.replace(second=0, microsecond=0)
    usage_end = usage_start + timedelta(minutes=1)
    costs_start = published.replace(hour=0, minute=0, second=0, microsecond=0)
    costs_end = costs_start + timedelta(days=1)
    if current < max(usage_end, costs_end):
        raise ValueError("billing collection requires completed billing buckets")
    usage_pages = await _collect_pages(
        lambda page: transport.completion_usage_page(
            start_time=int(usage_start.timestamp()),
            end_time=int(usage_end.timestamp()),
            project_id=project_id,
            api_key_id=api_key_id,
            model=model,
            page=page,
        ),
        OpenAICompletionUsagePage,
        "usage",
    )
    usage_buckets = tuple(bucket for page in usage_pages for bucket in page.data)
    usage = tuple(result for bucket in usage_buckets for result in bucket.results)
    if (
        len(usage_buckets) != 1
        or usage_buckets[0].start_time != int(usage_start.timestamp())
        or usage_buckets[0].end_time != int(usage_end.timestamp())
        or len(usage) != 1
        or usage[0].num_model_requests != 1
        or usage[0].project_id != project_id
        or usage[0].api_key_id != api_key_id
        or usage[0].model != model
        or usage[0].service_tier != "default"
    ):
        raise ValueError("billing collection did not isolate one usage group")
    costs_pages = await _collect_pages(
        lambda page: transport.costs_page(
            start_time=int(costs_start.timestamp()),
            end_time=int(costs_end.timestamp()),
            project_id=project_id,
            api_key_id=api_key_id,
            page=page,
        ),
        OpenAICostPage,
        "costs",
    )
    costs = tuple(
        result
        for page in costs_pages
        for bucket in page.data
        for result in bucket.results
    )
    microusd = sum(
        (Decimal(str(result.amount.value)) for result in costs), start=Decimal(0)
    ) * Decimal(1_000_000)
    if not costs or microusd != microusd.to_integral_value():
        raise ValueError(
            "billing collection cost is absent or exceeds microusd precision"
        )
    return CollectedSkillRuntimeBillingEvidence(
        project_id_sha256=digest(project_id.encode()),
        api_key_id_sha256=digest(api_key_id.encode()),
        model=model,
        usage_bucket_start=usage_start,
        usage_bucket_end=usage_end,
        costs_bucket_start=costs_start,
        costs_bucket_end=costs_end,
        usage_pages=usage_pages,
        costs_pages=costs_pages,
        external_input_tokens=usage[0].input_tokens,
        external_output_tokens=usage[0].output_tokens,
        external_cost_microusd=int(microusd),
        collected_at=current,
        sdk_version=transport.sdk_version,
    )
