"""Dispatch checks use synthetic keys and provider transports, never live calls."""

import asyncio
import json
from datetime import timedelta
from importlib.metadata import version
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock, patch

import httpx2
from pydantic import JsonValue
from test_openai_spend import FakeTransport
from test_review_approval_flow import ScriptedUser
from test_review_conformance_admission import ReviewConformanceFixture

from mos_eisley.core.models import ReviewPolicy
from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient
from mos_eisley.providers.openai_live import EphemeralOpenAITransport
from mos_eisley.providers.openai_responses import request_payload
from mos_eisley.providers.openai_spend import count_payload
from mos_eisley.run.review_conformance_admission import ReviewConformanceRuntime
from mos_eisley.run.review_conformance_probe import BrokeredReviewConformanceProbe


class ReviewProbeFixture(ReviewConformanceFixture):
    def setUp(self) -> None:
        super().setUp()
        self.key_loader = Mock(return_value="synthetic-test-key")

        def transport(*_: object) -> FakeTransport:
            return (
                self.judge
                if self.controller.phase == "judge_running"
                else self.base.fake
            )

        self.sdk = self.enterContext(
            patch(
                "mos_eisley.run.review_conformance_probe.EphemeralOpenAITransport",
                side_effect=transport,
            )
        )

    def probe(self, user: ScriptedUser | None = None) -> BrokeredReviewConformanceProbe:
        probe = BrokeredReviewConformanceProbe(
            self.review,
            self.base.reviewer,
            ReviewPolicy(min_critics=1, min_providers=1),
            ScriptedUser(("approve", "approve")) if user is None else user,
            critic_containers=(self.base.container,),
            judge_container=self.base.container,
            authority_policy=lambda: self.policy,
            load_authorization=self.load_certificate,
            load_api_key=self.key_loader,
        )
        self.controller = probe.controller
        self.preview = self.controller.preview
        self.runtime = ReviewConformanceRuntime(
            sdk_version=version("openai"), image_id=self.base.container.image_id
        )
        return probe


class ReviewProbeTests(ReviewProbeFixture, IsolatedAsyncioTestCase):
    async def test_probe_checks_both_phases_and_keeps_credentials_in_host(self):
        probe = self.probe()
        self.key_loader.assert_not_called()
        self.sdk.assert_not_called()
        result = await probe.run()
        assert result is not None
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(self.key_loader.call_count, 4)
        self.assertEqual(self.sdk.call_count, 4)
        self.assertEqual(len(probe.approval_ui.authorizations), 2)
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 40)
        for path in self.directory.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"synthetic-test-key", path.read_bytes())
        with self.assertRaises(ValueError):
            await probe.run()
        self.assertEqual(self.key_loader.call_count, 4)

    async def test_decline_never_loads_credentials(self):
        self.assertIsNone(await self.probe(ScriptedUser(("decline",))).run())
        self.key_loader.assert_not_called()
        self.sdk.assert_not_called()
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def test_missing_signature_never_loads_credentials(self):
        with patch.object(self, "load_certificate", return_value=None):
            self.assertIsNone(await self.probe(ScriptedUser(())).run())
        self.key_loader.assert_not_called()

    async def test_judge_decline_keeps_allowance_without_judge_credentials(self):
        probe = self.probe(ScriptedUser(("approve", "decline")))
        self.assertIsNone(await probe.run())
        self.assertEqual(self.key_loader.call_count, 2)
        self.assertEqual(self.judge.calls, [])
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 345)

    async def test_policy_revocation_after_count_blocks_generation(self):
        async def revoke(_payload: dict[str, JsonValue]) -> int:
            self.policy = self.policy.model_copy(update={"policy_id": "revoked"})
            return 10

        with (
            patch.object(self.base.fake, "count_input_tokens", side_effect=revoke),
            self.assertRaises(ValueError),
        ):
            await self.probe().run()
        self.assertEqual(self.key_loader.call_count, 1)
        self.assertEqual(self.base.fake.calls, [])
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 650)

    async def test_image_change_after_count_blocks_generation(self):
        async def changed(_payload: dict[str, JsonValue]) -> int:
            self.base.container.image_id = "sha256:" + "f" * 64
            return 10

        with (
            patch.object(self.base.fake, "count_input_tokens", side_effect=changed),
            self.assertRaises(ValueError),
        ):
            await self.probe().run()
        self.assertEqual(self.key_loader.call_count, 1)
        self.assertEqual(self.base.fake.calls, [])

    async def test_guidance_change_after_count_blocks_generation(self):
        async def changed(_payload: dict[str, JsonValue]) -> int:
            self.invalidate()
            return 10

        with (
            patch.object(self.base.fake, "count_input_tokens", side_effect=changed),
            self.assertRaises(ValueError),
        ):
            await self.probe().run()
        self.assertEqual(self.key_loader.call_count, 1)
        self.assertEqual(self.base.fake.calls, [])

    async def test_expiry_after_count_blocks_generation(self):
        async def expired(_payload: dict[str, JsonValue]) -> int:
            # The dispatch adapter uses the real clock, independently of signed data.
            self.clock.return_value = self.timestamp + timedelta(seconds=21)
            return 10

        with (
            patch("mos_eisley.run.review_conformance_probe.datetime") as clock,
            patch.object(self.base.fake, "count_input_tokens", side_effect=expired),
            self.assertRaises(ValueError),
        ):
            self.clock = clock.now
            self.clock.return_value = self.timestamp
            await self.probe().run()
        self.assertEqual(self.key_loader.call_count, 1)
        self.assertEqual(self.base.fake.calls, [])

    async def test_revocation_inside_key_loader_prevents_sdk_construction(self):
        def revoke() -> str:
            self.policy = self.policy.model_copy(update={"policy_id": "revoked"})
            return "synthetic-test-key"

        self.key_loader.side_effect = revoke
        with self.assertRaises(ValueError):
            await self.probe().run()
        self.sdk.assert_not_called()
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 650)

    async def test_provider_failure_consumes_attempt_and_preserves_spending(self):
        probe = self.probe()
        with (
            patch.object(self.base.fake, "create_response", side_effect=OSError),
            self.assertRaises(ValueError),
        ):
            await probe.run()
        self.assertEqual(self.key_loader.call_count, 2)
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 650)
        with self.assertRaises(ValueError):
            await probe.run()
        self.assertEqual(self.key_loader.call_count, 2)

    async def test_transport_cannot_read_key_before_local_approval(self):
        probe = self.probe()
        transport = probe._critics[0]  # pyright: ignore[reportPrivateUsage]
        with self.assertRaisesRegex(ValueError, "local approval"):
            await transport.count_input_tokens({})
        self.key_loader.assert_not_called()
        with self.assertRaisesRegex(ValueError, "consumed"):
            await transport.count_input_tokens({})

    async def test_payload_type_substitution_is_rejected_before_credentials(self):
        probe = self.probe()
        await probe.approval_ui.approve(probe.controller.preview)
        transport = probe._critics[0]  # pyright: ignore[reportPrivateUsage]
        payload = count_payload(request_payload(self.preview.requests[0]))
        # Python dictionary equality considers True == 1. Canonical payload
        # comparison must still reject the changed wire type.
        payload["parallel_tool_calls"] = 1
        with (
            patch.object(type(probe.controller), "phase", "critics_running"),
            patch.object(type(probe.controller), "start", Mock()),
            self.assertRaisesRegex(ValueError, "payload differs"),
        ):
            await transport.count_input_tokens(payload)
        self.key_loader.assert_not_called()

    async def test_real_sdk_uses_bounded_clients_exact_endpoint_and_no_retries(self):
        requests: list[httpx2.Request] = []
        clients: list[BoundedOpenAIHttpClient] = []

        async def reply(request: httpx2.Request) -> httpx2.Response:
            requests.append(request)
            if request.url.path.endswith("/input_tokens"):
                body: dict[str, JsonValue] = {"input_tokens": 10}
            else:
                body = dict(
                    self.judge.response
                    if self.controller.phase == "judge_running"
                    else self.base.fake.response
                )
                body.update({"object": "response", "created_at": 0})
                body["usage"] = {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "input_tokens_details": {
                        "cached_tokens": 0,
                        "cache_write_tokens": 0,
                    },
                    "output_tokens_details": {"reasoning_tokens": 0},
                }
            return httpx2.Response(200, json=body, request=request)

        def bounded_client(**options: object) -> BoundedOpenAIHttpClient:
            self.assertFalse(options["trust_env"])
            self.assertFalse(options["follow_redirects"])
            client = BoundedOpenAIHttpClient(transport=httpx2.MockTransport(reply))
            clients.append(client)
            return client

        with (
            patch(
                "mos_eisley.run.review_conformance_probe.EphemeralOpenAITransport",
                EphemeralOpenAITransport,
            ),
            patch(
                "mos_eisley.providers.openai_live.BoundedOpenAIHttpClient",
                side_effect=bounded_client,
            ),
        ):
            result = await self.probe().run()
        assert result is not None
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(len(requests), 4)
        self.assertEqual(len(clients), 4)
        self.assertTrue(all(client.is_closed for client in clients))
        for request in requests:
            self.assertEqual(request.url.host, "api.openai.com")
            self.assertEqual(request.url.scheme, "https")
            self.assertEqual(
                request.headers["authorization"], "Bearer synthetic-test-key"
            )
            self.assertEqual(request.headers["x-stainless-retry-count"], "0")
            payload = json.loads(request.content)
            if request.url.path == "/v1/responses":
                self.assertIs(payload["store"], False)
                self.assertEqual(payload["truncation"], "disabled")
                self.assertEqual(payload["service_tier"], "default")
            else:
                self.assertEqual(request.url.path, "/v1/responses/input_tokens")

    async def test_repeated_cancellation_awaits_provider_and_worker_cleanup(self):
        entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def pending(_payload: dict[str, JsonValue]) -> int:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
            return 10

        with patch.object(self.base.fake, "count_input_tokens", side_effect=pending):
            probe = self.probe()
            task = asyncio.create_task(probe.run())
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            await asyncio.wait_for(cleaning.wait(), 5)
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(probe.controller.phase, "cancelled")
        self.assertEqual(self.key_loader.call_count, 1)
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 650)
