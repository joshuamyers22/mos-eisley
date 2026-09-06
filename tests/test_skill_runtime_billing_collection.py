"""OpenAI billing collection is bounded, complete, exact, and credential-safe."""

import io
import json
import os
import stat
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, cast
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import httpx
from pydantic import JsonValue, ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.providers.openai_billing import (
    EphemeralOpenAIAdminBillingTransport,
)
from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient
from mos_eisley.run.skill_runtime_billing import (
    SkillRuntimeBillingObservation,
)
from mos_eisley.run.skill_runtime_billing_collection import (
    CollectedSkillRuntimeBillingEvidence,
    collect_skill_runtime_billing_evidence,
)
from mos_eisley.run.store import private_write
from tests import test_skill_runtime_billing as billing_module


def usage_page(
    start: datetime,
    end: datetime,
    project_id: str,
    api_key_id: str,
    model: str,
    *,
    input_tokens: int = 12,
    output_tokens: int = 7,
    requests: int = 1,
    has_more: bool = False,
    next_page: str | None = None,
) -> dict[str, JsonValue]:
    return {
        "object": "page",
        "data": [
            {
                "object": "bucket",
                "start_time": int(start.timestamp()),
                "end_time": int(end.timestamp()),
                "results": [
                    {
                        "object": "organization.usage.completions.result",
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "num_model_requests": requests,
                        "project_id": project_id,
                        "api_key_id": api_key_id,
                        "model": model,
                        "service_tier": "default",
                    }
                ],
            }
        ],
        "has_more": has_more,
        "next_page": next_page,
    }


def costs_page(
    start: datetime,
    end: datetime,
    project_id: str,
    api_key_id: str,
    cost_microusd: int,
    *,
    has_more: bool = False,
    next_page: str | None = None,
) -> dict[str, JsonValue]:
    return {
        "object": "page",
        "data": [
            {
                "object": "bucket",
                "start_time": int(start.timestamp()),
                "end_time": int(end.timestamp()),
                "results": [
                    {
                        "object": "organization.costs.result",
                        "amount": {
                            "value": cost_microusd / 1_000_000,
                            "currency": "usd",
                        },
                        "line_item": "model, input_tokens",
                        "project_id": project_id,
                        "api_key_id": api_key_id,
                    }
                ],
            }
        ],
        "has_more": has_more,
        "next_page": next_page,
    }


class FakeBillingTransport:
    sdk_version = "2.54.0"
    automatic_retries: Literal[0] = 0

    def __init__(
        self,
        usage: list[dict[str, JsonValue]],
        costs: list[dict[str, JsonValue]],
    ) -> None:
        self.usage = usage
        self.costs = costs
        self.usage_calls: list[str | None] = []
        self.costs_calls: list[str | None] = []

    async def completion_usage_page(self, **options: object) -> dict[str, JsonValue]:
        page = cast(str | None, options["page"])
        self.usage_calls.append(page)
        return self.usage[len(self.usage_calls) - 1]

    async def costs_page(self, **options: object) -> dict[str, JsonValue]:
        page = cast(str | None, options["page"])
        self.costs_calls.append(page)
        return self.costs[len(self.costs_calls) - 1]


class SkillRuntimeBillingCollectionTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.billing = billing_module.SkillRuntimeBillingTests()
        self.billing.setUp()
        self.addCleanup(self.billing.doCleanups)
        self.project_id = "proj_test_runtime"
        self.api_key_id = "key_test_runtime"

    def fake(
        self,
        *,
        usage: dict[str, JsonValue] | None = None,
        costs: dict[str, JsonValue] | None = None,
    ) -> FakeBillingTransport:
        return FakeBillingTransport(
            [
                usage
                or usage_page(
                    self.billing.usage_start,
                    self.billing.usage_end,
                    self.project_id,
                    self.api_key_id,
                    self.billing.result.model,
                    input_tokens=self.billing.result.usage.input,
                    output_tokens=self.billing.result.usage.output,
                )
            ],
            [
                costs
                or costs_page(
                    self.billing.costs_start,
                    self.billing.costs_end,
                    self.project_id,
                    self.api_key_id,
                    self.billing.result.charged_microusd,
                )
            ],
        )

    async def collect(
        self, transport: FakeBillingTransport | None = None
    ) -> CollectedSkillRuntimeBillingEvidence:
        return await collect_skill_runtime_billing_evidence(
            transport or self.fake(),
            project_id=self.project_id,
            api_key_id=self.api_key_id,
            model=self.billing.result.model,
            published_at=self.billing.publication.committed_at,
            collected_at=self.billing.retrieved_at,
        )

    async def test_collects_exact_private_pages_and_safe_summary(self) -> None:
        transport = self.fake()
        collection = await self.collect(transport)

        self.assertEqual(transport.usage_calls, [None])
        self.assertEqual(transport.costs_calls, [None])
        self.assertEqual(
            collection.external_input_tokens, self.billing.result.usage.input
        )
        self.assertEqual(
            collection.external_output_tokens, self.billing.result.usage.output
        )
        self.assertEqual(
            collection.external_cost_microusd,
            self.billing.result.charged_microusd,
        )
        self.assertTrue(collection.pagination_complete)
        self.assertTrue(collection.one_completion_request_in_usage_bucket_verified)
        self.assertFalse(collection.complete_daily_api_key_exclusivity_proven)
        self.assertFalse(collection.exact_provider_request_cost_attribution_proven)
        self.assertTrue(collection.billing_admin_read_performed)
        self.assertFalse(collection.model_inference_request_sent)
        self.assertFalse(collection.admin_credential_persisted)
        self.assertFalse(collection.ledger_mutation_authorized)
        self.assertEqual(len(collection.usage_evidence_sha256), 64)
        self.assertEqual(len(collection.costs_evidence_sha256), 64)

    async def test_multiple_requests_or_foreign_scope_fail_closed(self) -> None:
        multiple = usage_page(
            self.billing.usage_start,
            self.billing.usage_end,
            self.project_id,
            self.api_key_id,
            self.billing.result.model,
            requests=2,
        )
        multiple_transport = self.fake(usage=multiple)
        with self.assertRaisesRegex(ValueError, "did not isolate one usage group"):
            await self.collect(multiple_transport)
        self.assertEqual(multiple_transport.costs_calls, [])
        foreign = costs_page(
            self.billing.costs_start,
            self.billing.costs_end,
            "foreign-project",
            self.api_key_id,
            self.billing.result.charged_microusd,
        )
        with self.assertRaisesRegex(ValidationError, "costs scope"):
            await self.collect(self.fake(costs=foreign))

    async def test_shifted_bucket_and_sub_microusd_cost_fail_closed(self) -> None:
        shifted = usage_page(
            self.billing.usage_start + timedelta(seconds=1),
            self.billing.usage_end + timedelta(seconds=1),
            self.project_id,
            self.api_key_id,
            self.billing.result.model,
        )
        with self.assertRaisesRegex(ValueError, "did not isolate one usage group"):
            await self.collect(self.fake(usage=shifted))
        imprecise = costs_page(
            self.billing.costs_start,
            self.billing.costs_end,
            self.project_id,
            self.api_key_id,
            self.billing.result.charged_microusd,
        )
        amount = cast(
            dict[str, JsonValue],
            cast(
                list[JsonValue],
                cast(dict[str, JsonValue], cast(list[JsonValue], imprecise["data"])[0])[
                    "results"
                ],
            )[0],
        )["amount"]
        cast(dict[str, JsonValue], amount)["value"] = 0.0000001
        with self.assertRaisesRegex(ValueError, "exceeds microusd precision"):
            await self.collect(self.fake(costs=imprecise))

    async def test_cursor_repetition_and_page_limit_are_rejected(self) -> None:
        first = usage_page(
            self.billing.usage_start,
            self.billing.usage_end,
            self.project_id,
            self.api_key_id,
            self.billing.result.model,
            has_more=True,
            next_page="repeat",
        )
        transport = FakeBillingTransport([first, first], self.fake().costs)
        with self.assertRaisesRegex(ValueError, "cursor is invalid"):
            await self.collect(transport)

        pages = [
            usage_page(
                self.billing.usage_start,
                self.billing.usage_end,
                self.project_id,
                self.api_key_id,
                self.billing.result.model,
                has_more=True,
                next_page=f"cursor-{index}",
            )
            for index in range(20)
        ]
        over_limit = FakeBillingTransport(pages, self.fake().costs)
        with self.assertRaisesRegex(ValueError, "exceeds page limit"):
            await self.collect(over_limit)
        self.assertEqual(over_limit.costs_calls, [])

    async def test_duplicate_cost_groups_are_rejected(self) -> None:
        duplicate = costs_page(
            self.billing.costs_start,
            self.billing.costs_end,
            self.project_id,
            self.api_key_id,
            self.billing.result.charged_microusd,
        )
        data = cast(list[JsonValue], duplicate["data"])
        bucket = cast(dict[str, JsonValue], data[0])
        results = cast(list[JsonValue], bucket["results"])
        results.append(results[0])
        with self.assertRaisesRegex(ValidationError, "duplicate cost groups"):
            await self.collect(self.fake(costs=duplicate))

    async def test_invalid_or_open_bucket_fails_before_admin_read(self) -> None:
        invalid_model = self.fake()
        with self.assertRaises(ValidationError):
            await collect_skill_runtime_billing_evidence(
                invalid_model,
                project_id=self.project_id,
                api_key_id=self.api_key_id,
                model="invalid model",
                published_at=self.billing.publication.committed_at,
                collected_at=self.billing.retrieved_at,
            )
        self.assertEqual(invalid_model.usage_calls, [])
        self.assertEqual(invalid_model.costs_calls, [])

        open_bucket = self.fake()
        with self.assertRaisesRegex(ValueError, "completed billing buckets"):
            await collect_skill_runtime_billing_evidence(
                open_bucket,
                project_id=self.project_id,
                api_key_id=self.api_key_id,
                model=self.billing.result.model,
                published_at=self.billing.publication.committed_at,
                collected_at=self.billing.costs_end - timedelta(seconds=1),
            )
        self.assertEqual(open_bucket.usage_calls, [])
        self.assertEqual(open_bucket.costs_calls, [])

    async def test_collection_tampering_is_rejected(self) -> None:
        payload = (await self.collect()).model_dump(mode="json")
        payload["admin_credential_persisted"] = True
        with self.assertRaises(ValidationError):
            CollectedSkillRuntimeBillingEvidence.model_validate_json(
                json.dumps(payload, separators=(",", ":"), sort_keys=True)
            )


class EphemeralOpenAIAdminBillingTransportTests(IsolatedAsyncioTestCase):
    async def test_official_sdk_uses_exact_bounded_zero_retry_queries(self) -> None:
        published = datetime(2026, 9, 6, 22, 29, 10, tzinfo=UTC)
        usage_start = published.replace(second=0)
        usage_end = usage_start + timedelta(minutes=1)
        costs_start = published.replace(hour=0, minute=0, second=0)
        costs_end = costs_start + timedelta(days=1)
        requests: list[httpx.Request] = []
        clients: list[BoundedOpenAIHttpClient] = []

        async def reply(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/usage/completions"):
                body = usage_page(
                    usage_start,
                    usage_end,
                    "proj_test",
                    "key_test",
                    "gpt-6-astra",
                )
            else:
                body = costs_page(
                    costs_start,
                    costs_end,
                    "proj_test",
                    "key_test",
                    42,
                )
            return httpx.Response(200, json=body, request=request)

        def bounded_client(**options: object) -> BoundedOpenAIHttpClient:
            self.assertFalse(options["trust_env"])
            self.assertFalse(options["follow_redirects"])
            client = BoundedOpenAIHttpClient(transport=httpx.MockTransport(reply))
            clients.append(client)
            return client

        with patch(
            "mos_eisley.providers.openai_billing.BoundedOpenAIHttpClient",
            side_effect=bounded_client,
        ):
            transport = EphemeralOpenAIAdminBillingTransport("secret-admin-key", 10)
            usage = await transport.completion_usage_page(
                start_time=int(usage_start.timestamp()),
                end_time=int(usage_end.timestamp()),
                project_id="proj_test",
                api_key_id="key_test",
                model="gpt-6-astra",
                page=None,
            )
            costs = await transport.costs_page(
                start_time=int(costs_start.timestamp()),
                end_time=int(costs_end.timestamp()),
                project_id="proj_test",
                api_key_id="key_test",
                page=None,
            )

        self.assertEqual(usage["object"], "page")
        self.assertEqual(costs["object"], "page")
        self.assertEqual(
            [request.url.path for request in requests],
            ["/v1/organization/usage/completions", "/v1/organization/costs"],
        )
        usage_query = requests[0].url.params
        self.assertEqual(usage_query["bucket_width"], "1m")
        self.assertEqual(usage_query["limit"], "1")
        self.assertEqual(usage_query["batch"], "false")
        self.assertEqual(usage_query.get_list("project_ids[]"), ["proj_test"])
        self.assertEqual(usage_query.get_list("api_key_ids[]"), ["key_test"])
        self.assertEqual(usage_query.get_list("models[]"), ["gpt-6-astra"])
        self.assertEqual(
            usage_query.get_list("group_by[]"),
            ["project_id", "api_key_id", "model", "service_tier"],
        )
        self.assertEqual(requests[1].url.params["bucket_width"], "1d")
        self.assertEqual(
            requests[1].url.params.get_list("group_by[]"),
            ["project_id", "api_key_id", "line_item"],
        )
        self.assertTrue(
            all(
                request.headers["authorization"] == "Bearer secret-admin-key"
                for request in requests
            )
        )
        self.assertTrue(all(client.is_closed for client in clients))


class OpenAIBillingCollectionCLITests(TestCase):
    def setUp(self) -> None:
        self.billing = billing_module.SkillRuntimeBillingTests()
        self.billing.setUp()
        self.addCleanup(self.billing.doCleanups)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def inputs(self) -> tuple[list[str], dict[str, Path], FakeBillingTransport]:
        paths = self.billing.paths()
        now = self.billing.retrieved_at
        policy = self.billing.policy.model_copy(
            update={
                "valid_from": now - timedelta(hours=1),
                "valid_until": now + timedelta(hours=1),
            }
        )
        billing_policy = self.root / "billing-policy.json"
        private_write(billing_policy, canonical_bytes(policy))
        paths["billing_policy"] = billing_policy
        output = self.root / "collected-billing.json"
        paths["collection"] = output
        transport = FakeBillingTransport(
            [
                usage_page(
                    self.billing.usage_start,
                    self.billing.usage_end,
                    "proj_cli",
                    "key_cli",
                    self.billing.result.model,
                    input_tokens=self.billing.result.usage.input,
                    output_tokens=self.billing.result.usage.output,
                )
            ],
            [
                costs_page(
                    self.billing.costs_start,
                    self.billing.costs_end,
                    "proj_cli",
                    "key_cli",
                    self.billing.result.charged_microusd,
                )
            ],
        )
        return (
            [
                "openai-billing-collect",
                "--authenticated-conformance",
                str(paths["conformance"]),
                "--conformance-policy",
                str(paths["conformance_policy"]),
                "--response-store",
                str(self.billing.response_store.path),
                "--billing-policy",
                str(paths["billing_policy"]),
                "--project-id",
                "proj_cli",
                "--api-key-id",
                "key_cli",
                "--output",
                str(output),
                "--allow-account-billing-read",
            ],
            paths,
            transport,
        )

    def test_cli_collects_then_derives_without_leaking_admin_key(self) -> None:
        options, paths, transport = self.inputs()
        with (
            patch.dict(os.environ, {"OPENAI_ADMIN_KEY": "secret-admin-key"}),
            patch("mos_eisley.cli.datetime") as clock,
            patch(
                "mos_eisley.cli.EphemeralOpenAIAdminBillingTransport",
                return_value=transport,
            ),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            clock.now.return_value = self.billing.retrieved_at
            self.assertEqual(main(options), 0)
        output = stdout.getvalue()
        event = json.loads(output)
        self.assertEqual(event["type"], "openai.billing_evidence.collected")
        self.assertTrue(event["usage_matches_local"])
        self.assertTrue(event["cost_matches_local"])
        self.assertTrue(event["billing_admin_read_performed"])
        self.assertFalse(event["model_inference_request_sent"])
        self.assertFalse(event["complete_daily_api_key_exclusivity_proven"])
        self.assertFalse(event["exact_provider_request_cost_attribution_proven"])
        self.assertNotIn("secret-admin-key", output)
        collection_bytes = paths["collection"].read_bytes()
        self.assertNotIn(b"secret-admin-key", collection_bytes)
        self.assertEqual(stat.S_IMODE(paths["collection"].stat().st_mode), 0o600)
        collection = CollectedSkillRuntimeBillingEvidence.model_validate_json(
            collection_bytes
        )

        derived_path = self.root / "derived-from-collection.json"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(
                main(
                    [
                        "eval-derive-skill-runtime-billing-evidence",
                        "--authenticated-conformance",
                        str(paths["conformance"]),
                        "--conformance-policy",
                        str(paths["conformance_policy"]),
                        "--response-store",
                        str(self.billing.response_store.path),
                        "--billing-policy",
                        str(paths["billing_policy"]),
                        "--collected-evidence",
                        str(paths["collection"]),
                        "--attest-complete-exclusive-billing-evidence",
                        "--output",
                        str(derived_path),
                    ]
                ),
                0,
            )
        observation = SkillRuntimeBillingObservation.model_validate_json(
            derived_path.read_bytes()
        )
        self.assertEqual(
            observation.usage_evidence_sha256, collection.usage_evidence_sha256
        )
        self.assertEqual(
            observation.costs_evidence_sha256, collection.costs_evidence_sha256
        )

    def test_consent_fails_before_files_credentials_or_transport(self) -> None:
        options = [
            "openai-billing-collect",
            "--authenticated-conformance",
            "missing-conformance",
            "--conformance-policy",
            "missing-policy",
            "--response-store",
            "missing-store",
            "--billing-policy",
            "missing-billing-policy",
            "--project-id",
            "proj_test",
            "--api-key-id",
            "key_test",
            "--output",
            "output.json",
        ]
        with (
            patch("mos_eisley.cli.read_bounded") as read,
            patch("mos_eisley.cli._openai_admin_api_key") as credential,
            patch("mos_eisley.cli.EphemeralOpenAIAdminBillingTransport") as transport,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(options), 2)
            read.assert_not_called()
            credential.assert_not_called()
            transport.assert_not_called()

    def test_missing_admin_key_fails_before_transport_or_output(self) -> None:
        options, paths, _ = self.inputs()
        with (
            patch("mos_eisley.cli.datetime") as clock,
            patch("mos_eisley.cli._openai_admin_api_key", return_value=None),
            patch("mos_eisley.cli.EphemeralOpenAIAdminBillingTransport") as transport,
            redirect_stderr(io.StringIO()),
        ):
            clock.now.return_value = self.billing.retrieved_at
            self.assertEqual(main(options), 2)
        transport.assert_not_called()
        self.assertFalse(paths["collection"].exists())

    def test_existing_output_fails_before_credential_or_transport(self) -> None:
        options, paths, _ = self.inputs()
        private_write(paths["collection"], b"occupied")
        with (
            patch("mos_eisley.cli._openai_admin_api_key") as credential,
            patch("mos_eisley.cli.EphemeralOpenAIAdminBillingTransport") as transport,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(options), 2)
        credential.assert_not_called()
        transport.assert_not_called()
