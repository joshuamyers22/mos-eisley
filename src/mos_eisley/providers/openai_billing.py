"""Ephemeral zero-retry OpenAI Admin API billing-page transport."""

from importlib.metadata import version
from typing import Literal

from openai import AsyncOpenAI, omit
from pydantic import JsonValue, TypeAdapter

from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient

_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


class EphemeralOpenAIAdminBillingTransport:
    """Keep the admin key inside one short-lived bounded SDK transport."""

    sdk_version = version("openai")
    automatic_retries: Literal[0] = 0

    def __init__(self, admin_api_key: str, timeout_seconds: float) -> None:
        if not admin_api_key:
            raise ValueError("OpenAI Admin API key must not be empty")
        if not 0 < timeout_seconds <= 60:
            raise ValueError(
                "OpenAI Admin API timeout must be between zero and 60 seconds"
            )
        self._admin_api_key = admin_api_key
        self._timeout_seconds = timeout_seconds

    def _client(self) -> AsyncOpenAI:
        return AsyncOpenAI(
            admin_api_key=self._admin_api_key,
            timeout=self._timeout_seconds,
            max_retries=0,
            base_url="https://api.openai.com/v1",
            http_client=BoundedOpenAIHttpClient(
                trust_env=False,
                follow_redirects=False,
            ),
        )

    async def completion_usage_page(
        self,
        *,
        start_time: int,
        end_time: int,
        project_id: str,
        api_key_id: str,
        model: str,
        page: str | None,
    ) -> dict[str, JsonValue]:
        async with self._client() as sdk:
            response = await sdk.admin.organization.usage.completions(
                start_time=start_time,
                end_time=end_time,
                project_ids=(project_id,),
                api_key_ids=(api_key_id,),
                models=(model,),
                batch=False,
                bucket_width="1m",
                group_by=[
                    "project_id",
                    "api_key_id",
                    "model",
                    "service_tier",
                ],
                limit=1,
                page=page if page is not None else omit,
            )
        return _JSON_OBJECT.validate_python(
            response.model_dump(mode="json"), strict=True
        )

    async def costs_page(
        self,
        *,
        start_time: int,
        end_time: int,
        project_id: str,
        api_key_id: str,
        page: str | None,
    ) -> dict[str, JsonValue]:
        async with self._client() as sdk:
            response = await sdk.admin.organization.usage.costs(
                start_time=start_time,
                end_time=end_time,
                project_ids=(project_id,),
                api_key_ids=(api_key_id,),
                bucket_width="1d",
                group_by=["project_id", "api_key_id", "line_item"],
                limit=1,
                page=page if page is not None else omit,
            )
        return _JSON_OBJECT.validate_python(
            response.model_dump(mode="json"), strict=True
        )
