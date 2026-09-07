"""Narrow OpenAI model-visibility readiness probe and non-authorizing receipt."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Protocol, Self

from openai import AsyncOpenAI, OpenAIError
from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Identifier
from mos_eisley.core.ports import ProviderError, ProviderFailureKind
from mos_eisley.providers.openai_errors import safe_openai_failure_kind
from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient

OPENAI_READINESS_MODEL = "gpt-5.6-luna"
OPENAI_API_BASE = "https://api.openai.com/v1"


class OpenAIReadinessReceipt(Contract):
    """Durable result that deliberately grants no downstream authority."""

    schema_version: Literal[1] = 1
    mode: Literal["openai_model_readiness"] = "openai_model_readiness"
    provider: Literal["openai"] = "openai"
    model: Identifier
    checked_at: datetime
    sdk_package: Literal["openai"] = "openai"
    sdk_version: str = Field(min_length=1, max_length=64)
    endpoint_origin: Literal["https://api.openai.com"] = "https://api.openai.com"
    api_family: Literal["models"] = "models"
    outcome: Literal["visible", "error"]
    failure_kind: ProviderFailureKind | None = None
    automatic_retries: Literal[0] = 0
    credential_accessed: Literal[True] = True
    provider_request_attempted: Literal[True] = True
    prompt_transferred: Literal[False] = False
    generation_requested: Literal[False] = False
    spend_authorized: Literal[False] = False
    billing_verified: Literal[False] = False
    responses_access_verified: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False
    retry_authorized: Literal[False] = False

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if self.checked_at.utcoffset() != UTC.utcoffset(self.checked_at):
            raise ValueError("readiness timestamp must use UTC")
        if (self.outcome == "visible") != (self.failure_kind is None):
            raise ValueError("readiness outcome and failure kind disagree")
        return self


class OpenAIModelMetadataTransport(Protocol):
    async def retrieve_model(self, model: str) -> str: ...


class SDKOpenAIModelMetadataTransport:
    """Official-SDK boundary for one model retrieval request."""

    def __init__(self, client: AsyncOpenAI) -> None:
        self.client = client

    async def retrieve_model(self, model: str) -> str:
        try:
            result = await self.client.models.retrieve(model)
        except OpenAIError as error:
            failure_kind = safe_openai_failure_kind(error)
        else:
            if result.object != "model" or result.id != model:
                raise ProviderError(
                    "OpenAI model metadata was invalid",
                    failure_kind="provider_error",
                )
            return result.id
        raise ProviderError(
            "OpenAI model metadata request failed",
            failure_kind=failure_kind,
        )


async def make_openai_readiness_receipt(
    transport: OpenAIModelMetadataTransport,
    *,
    checked_at: datetime,
    sdk_version: str,
) -> OpenAIReadinessReceipt:
    """Attempt exactly one fixed model lookup and reduce it to safe evidence."""

    try:
        model = await transport.retrieve_model(OPENAI_READINESS_MODEL)
    except ProviderError as error:
        if error.failure_stage is not None:
            raise ValueError(
                "readiness transport returned an invalid failure stage"
            ) from None
        return OpenAIReadinessReceipt(
            model=OPENAI_READINESS_MODEL,
            checked_at=checked_at,
            sdk_version=sdk_version,
            outcome="error",
            failure_kind=error.failure_kind,
        )
    if model != OPENAI_READINESS_MODEL:
        raise ValueError("readiness transport returned an unexpected model")
    return OpenAIReadinessReceipt(
        model=model,
        checked_at=checked_at,
        sdk_version=sdk_version,
        outcome="visible",
    )


async def probe_openai_readiness(
    api_key: str,
    *,
    timeout_seconds: float,
    checked_at: datetime,
    sdk_version: str,
) -> OpenAIReadinessReceipt:
    """Own and close the credentialed zero-retry SDK client for one lookup."""

    if not api_key:
        raise ValueError("OpenAI API key must not be empty")
    if not 0 < timeout_seconds <= 30:
        raise ValueError("OpenAI readiness timeout must be between zero and 30 seconds")
    async with AsyncOpenAI(
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=0,
        base_url=OPENAI_API_BASE,
        http_client=BoundedOpenAIHttpClient(
            trust_env=False,
            follow_redirects=False,
        ),
    ) as sdk:
        return await make_openai_readiness_receipt(
            SDKOpenAIModelMetadataTransport(sdk),
            checked_at=checked_at,
            sdk_version=sdk_version,
        )
