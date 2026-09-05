"""Credentialed conformance request preparation uses blinded fixture data only."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase

import httpx
from openai import AsyncOpenAI
from pydantic import JsonValue, TypeAdapter

from mos_eisley.core.models import Brief
from mos_eisley.evaluation.execution import EvaluationRequest, ExecutionBatch
from mos_eisley.evaluation.models import RouteCandidate
from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient
from mos_eisley.providers.openai_responses import SDKOpenAITransport
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport, SpendPolicy
from mos_eisley.run.openai_conformance import (
    build_openai_conformance_payload,
    critique_format,
)
from mos_eisley.run.spend_ledger import SpendLedger
from tests.test_openai_provider import response_payload
from tests.test_openai_spend import FakeTransport


def conformance_inputs() -> tuple[ExecutionBatch, SpendPolicy]:
    route = RouteCandidate(
        backend="api",
        provider="openai",
        model="gpt-6-astra",
        effort="high",
        client_version="openai/2",
        registry_sha256="a" * 64,
    )
    request = EvaluationRequest(
        sample_id="b" * 64,
        route=route,
        brief=Brief(
            spec="Return every item.",
            diff="return items[:-1]",
            constraints="Do not make network requests.",
        ),
    )
    now = datetime.now(UTC)
    policy = SpendPolicy(
        model=route.model,
        pricing_source="synthetic conformance rates",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        input_microusd_per_million=1_000_000,
        output_microusd_per_million=2_000_000,
        max_cost_microusd=20_000,
    )
    return ExecutionBatch(plan_sha256="c" * 64, requests=(request,)), policy


class ConformanceRequestTests(TestCase):
    def test_payload_is_assignment_bound_text_only_and_structured(self) -> None:
        batch, policy = conformance_inputs()
        payload = build_openai_conformance_payload(
            batch, batch.requests[0].sample_id, policy
        )
        self.assertEqual(payload["model"], "gpt-6-astra")
        self.assertEqual(payload["reasoning"], {"effort": "high"})
        self.assertEqual(payload["tools"], [])
        self.assertFalse(payload["store"])
        self.assertEqual(payload["truncation"], "disabled")
        self.assertNotIn("expected_findings", str(payload))
        content = payload["input"]
        self.assertIsInstance(content, list)
        self.assertIn("items[:-1]", str(content))

    def test_schema_is_strict_at_every_object_and_requires_defaults(self) -> None:
        schema = critique_format()["format"]
        assert isinstance(schema, dict)
        self.assertEqual(schema["type"], "json_schema")
        self.assertTrue(schema["strict"])

        def inspect(value: JsonValue) -> None:
            if isinstance(value, list):
                for item in value:
                    inspect(item)
            elif isinstance(value, dict):
                self.assertNotIn("default", value)
                self.assertNotIn("title", value)
                properties = value.get("properties")
                if value.get("type") == "object" and isinstance(properties, dict):
                    required = value.get("required")
                    self.assertIsInstance(required, list)
                    assert isinstance(required, list)
                    self.assertTrue(all(isinstance(item, str) for item in required))
                    self.assertEqual(set(required), set(properties))
                    self.assertFalse(value["additionalProperties"])
                for item in value.values():
                    inspect(item)

        inspect(schema["schema"])

    def test_unknown_sample_provider_or_policy_model_rejected(self) -> None:
        batch, policy = conformance_inputs()
        with self.assertRaises(ValueError):
            build_openai_conformance_payload(batch, "0" * 64, policy)
        wrong_route = batch.requests[0].route.model_copy(update={"provider": "other"})
        wrong = batch.model_copy(
            update={
                "requests": (
                    batch.requests[0].model_copy(update={"route": wrong_route}),
                )
            }
        )
        with self.assertRaises(ValueError):
            build_openai_conformance_payload(wrong, wrong.requests[0].sample_id, policy)
        with self.assertRaises(ValueError):
            build_openai_conformance_payload(
                batch,
                batch.requests[0].sample_id,
                policy.model_copy(update={"model": "other"}),
            )


class ConformanceSpendTests(IsolatedAsyncioTestCase):
    async def test_installed_sdk_serializes_structured_conformance_payload(
        self,
    ) -> None:
        batch, policy = conformance_inputs()
        payload = build_openai_conformance_payload(
            batch, batch.requests[0].sample_id, policy
        )
        captured: list[dict[str, JsonValue]] = []

        async def reply(request: httpx.Request) -> httpx.Response:
            value = TypeAdapter(dict[str, JsonValue]).validate_python(
                json.loads(request.content)
            )
            captured.append(value)
            body = response_payload(
                [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": '{"findings":[]}'}],
                    }
                ]
            )
            body.update(
                {
                    "object": "response",
                    "created_at": 0,
                    "model": policy.model,
                    "service_tier": "default",
                }
            )
            return httpx.Response(200, json=body, request=request)

        async with BoundedOpenAIHttpClient(
            transport=httpx.MockTransport(reply)
        ) as http_client:
            sdk = AsyncOpenAI(
                api_key="synthetic-test-key",
                base_url="https://api.openai.com/v1",
                max_retries=0,
                http_client=http_client,
            )
            response = await SDKOpenAITransport(sdk).create_response(payload)
        self.assertEqual(response["model"], policy.model)
        self.assertEqual(captured[0]["text"], critique_format())

    async def test_spending_controller_accepts_only_host_built_structured_request(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            batch, policy = conformance_inputs()
            payload = build_openai_conformance_payload(
                batch, batch.requests[0].sample_id, policy
            )
            fake = FakeTransport(root)
            fake.response["model"] = policy.model
            ledger = SpendLedger.create(root / "ledger.sqlite", 20_000)
            response = await BudgetedOpenAITransport(
                fake, policy, root, ledger
            ).create_response(payload)
            self.assertEqual(response, fake.response)
            self.assertEqual(len(fake.calls), 1)
            self.assertIn("text", fake.calls[0])
