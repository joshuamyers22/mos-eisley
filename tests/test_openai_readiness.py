"""OpenAI model-readiness probe security and CLI behavior."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

import httpx2
from openai import AsyncOpenAI
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient
from mos_eisley.providers.openai_readiness import (
    OPENAI_READINESS_MODEL,
    OPENAI_READINESS_MODELS,
    OpenAIReadinessReceipt,
    SDKOpenAIModelMetadataTransport,
    make_openai_readiness_receipt,
)


class OpenAIReadinessTransportTests(IsolatedAsyncioTestCase):
    async def _receipt(
        self,
        reply: httpx2.MockTransport,
        model: str = OPENAI_READINESS_MODEL,
    ) -> OpenAIReadinessReceipt:
        async with BoundedOpenAIHttpClient(transport=reply) as http_client:
            sdk = AsyncOpenAI(
                api_key="synthetic-secret-key",
                base_url="https://api.openai.com/v1",
                max_retries=0,
                http_client=http_client,
            )
            return await make_openai_readiness_receipt(
                SDKOpenAIModelMetadataTransport(sdk),
                checked_at=datetime(2026, 9, 7, tzinfo=UTC),
                sdk_version="2.0.0",
                model=model,
            )

    async def test_visible_model_uses_one_get_and_transfers_no_prompt(self) -> None:
        for model in OPENAI_READINESS_MODELS:
            with self.subTest(model=model):
                requests: list[httpx2.Request] = []

                async def reply(
                    request: httpx2.Request,
                    model: str = model,
                    requests: list[httpx2.Request] = requests,
                ) -> httpx2.Response:
                    requests.append(request)
                    return httpx2.Response(
                        200,
                        json={
                            "id": model,
                            "object": "model",
                            "created": 1,
                            "owned_by": "openai",
                        },
                        request=request,
                    )

                receipt = await self._receipt(httpx2.MockTransport(reply), model)
                self.assertEqual(receipt.model, model)
                self.assertEqual(receipt.outcome, "visible")
                self.assertIsNone(receipt.failure_kind)
                self.assertIsNone(receipt.failure_detail)
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0].method, "GET")
                self.assertEqual(requests[0].url.path, f"/v1/models/{model}")
                self.assertEqual(requests[0].content, b"")
                payload = canonical_bytes(receipt)
                self.assertNotIn(b"synthetic-secret-key", payload)
                for denied in (
                    "prompt_transferred",
                    "generation_requested",
                    "spend_authorized",
                    "billing_verified",
                    "responses_access_verified",
                    "grading_authorized",
                    "scoring_authorized",
                    "routing_activation_authorized",
                    "retry_authorized",
                ):
                    self.assertIs(receipt.model_dump()[denied], False)

    async def test_model_outside_registry_is_rejected_before_transport(self) -> None:
        transport = AsyncMock()
        with self.assertRaises(ValueError):
            await make_openai_readiness_receipt(
                transport,
                checked_at=datetime(2026, 9, 7, tzinfo=UTC),
                sdk_version="2.0.0",
                model="gpt-unregistered",
            )
        transport.retrieve_model.assert_not_awaited()

    async def test_sdk_errors_become_allowlisted_receipts_without_raw_details(
        self,
    ) -> None:
        cases: tuple[tuple[int, str, dict[str, str]], ...] = (
            (401, "authentication_error", {}),
            (403, "permission_error", {}),
            (404, "not_found_error", {}),
            (429, "rate_limit_error", {}),
            (429, "quota_error", {"code": "insufficient_quota"}),
            (400, "invalid_request_error", {}),
            (500, "provider_error", {}),
        )
        for status, expected, detail in cases:
            calls = 0

            async def reply(
                request: httpx2.Request,
                status: int = status,
                detail: dict[str, str] = detail,
            ) -> httpx2.Response:
                nonlocal calls
                calls += 1
                return httpx2.Response(
                    status,
                    json={
                        "error": {
                            "message": "private raw detail synthetic-secret-key",
                            "type": "fixture_error",
                            **detail,
                        }
                    },
                    request=request,
                )

            with self.subTest(status=status, expected=expected):
                receipt = await self._receipt(httpx2.MockTransport(reply))
                self.assertEqual(receipt.outcome, "error")
                self.assertEqual(receipt.failure_kind, expected)
                self.assertIsNone(receipt.failure_detail)
                self.assertEqual(calls, 1)
                payload = canonical_bytes(receipt)
                self.assertNotIn(b"private raw detail", payload)
                self.assertNotIn(b"synthetic-secret-key", payload)

    async def test_transport_and_timeout_errors_are_coarse_and_not_retried(
        self,
    ) -> None:
        cases = (
            (
                httpx2.ConnectError("private network detail"),
                "transport_error",
                "connection_error",
            ),
            (
                httpx2.RemoteProtocolError("private protocol detail"),
                "transport_error",
                "protocol_error",
            ),
            (
                RuntimeError("private unknown detail"),
                "transport_error",
                "unknown_transport_error",
            ),
            (httpx2.ReadTimeout("private timeout detail"), "provider_timeout", None),
        )
        for failure, expected, detail in cases:
            calls = 0

            async def reply(
                request: httpx2.Request,
                failure: Exception = failure,
            ) -> httpx2.Response:
                nonlocal calls
                calls += 1
                raise failure

            with self.subTest(expected=expected):
                receipt = await self._receipt(httpx2.MockTransport(reply))
                self.assertEqual(receipt.failure_kind, expected)
                self.assertEqual(receipt.failure_detail, detail)
                self.assertEqual(calls, 1)
                self.assertNotIn(b"private", canonical_bytes(receipt))

    async def test_ignored_identity_request_reports_safe_decode_detail(self) -> None:
        class InvalidDeflateBody(httpx2.AsyncByteStream):
            async def __aiter__(self):
                yield b"private invalid deflate body"

        async def reply(request: httpx2.Request) -> httpx2.Response:
            self.assertEqual(request.headers["accept-encoding"], "identity")
            return httpx2.Response(
                200,
                headers={"content-encoding": "deflate"},
                stream=InvalidDeflateBody(),
                request=request,
            )

        receipt = await self._receipt(httpx2.MockTransport(reply))
        self.assertEqual(receipt.failure_kind, "transport_error")
        self.assertEqual(receipt.failure_detail, "response_decode_error")
        self.assertNotIn(b"private", canonical_bytes(receipt))

    async def test_response_limit_has_distinct_safe_detail(self) -> None:
        async def reply(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                200,
                headers={"content-length": "1000001"},
                content=b"private",
                request=request,
            )

        receipt = await self._receipt(httpx2.MockTransport(reply))
        self.assertEqual(receipt.failure_kind, "transport_error")
        self.assertEqual(receipt.failure_detail, "response_limit_error")
        self.assertNotIn(b"private", canonical_bytes(receipt))

    async def test_mismatched_model_metadata_fails_closed(self) -> None:
        async def reply(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                200,
                json={
                    "id": "gpt-unexpected",
                    "object": "model",
                    "created": 1,
                    "owned_by": "openai",
                },
                request=request,
            )

        receipt = await self._receipt(httpx2.MockTransport(reply))
        self.assertEqual(receipt.outcome, "error")
        self.assertEqual(receipt.failure_kind, "provider_error")


class OpenAIReadinessReceiptTests(TestCase):
    def test_outcome_and_timezone_are_strict(self) -> None:
        common = {
            "model": OPENAI_READINESS_MODEL,
            "checked_at": datetime(2026, 9, 7, tzinfo=UTC),
            "sdk_version": "2.0.0",
        }
        for update in (
            {"outcome": "visible", "failure_kind": "provider_error"},
            {"outcome": "error", "failure_kind": None},
            {"outcome": "error", "failure_kind": "transport_error"},
            {
                "outcome": "error",
                "failure_kind": "permission_error",
                "failure_detail": "connection_error",
            },
            {"outcome": "visible", "checked_at": datetime(2026, 9, 7)},
            {
                "outcome": "visible",
                "checked_at": datetime.fromisoformat("2026-09-07T00:00:00-04:00"),
            },
            {"outcome": "visible", "routing_activation_authorized": True},
            {"outcome": "visible", "model": "gpt-unregistered"},
        ):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                OpenAIReadinessReceipt.model_validate(common | update)


class OpenAIReadinessCliTests(TestCase):
    @staticmethod
    def _receipt(
        outcome: Literal["visible", "error"] = "visible",
        model: str = OPENAI_READINESS_MODEL,
    ) -> OpenAIReadinessReceipt:
        return OpenAIReadinessReceipt(
            model=model,
            checked_at=datetime(2026, 9, 7, tzinfo=UTC),
            sdk_version="2.0.0",
            outcome=outcome,
            failure_kind=(None if outcome == "visible" else "permission_error"),
        )

    def test_consent_parent_and_key_preflight_precede_probe(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            probe = AsyncMock()
            with (
                patch("mos_eisley.cli.probe_openai_readiness", probe),
                patch("mos_eisley.cli._openai_api_key") as key,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(["openai-readiness", "--output", str(output)]), 2)
                key.assert_not_called()
                self.assertEqual(
                    main(
                        [
                            "openai-readiness",
                            "--output",
                            str(Path(directory) / "missing" / "receipt.json"),
                            "--allow-provider-access",
                        ]
                    ),
                    2,
                )
                key.assert_not_called()
                probe.assert_not_awaited()

            occupied = Path(directory) / "occupied.json"
            occupied.symlink_to(Path(directory) / "absent-target")
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-secret-key"}),
                patch("mos_eisley.cli.probe_openai_readiness", probe),
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(
                    main(
                        [
                            "openai-readiness",
                            "--output",
                            str(occupied),
                            "--allow-provider-access",
                        ]
                    ),
                    2,
                )
                probe.assert_not_awaited()

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("mos_eisley.cli.probe_openai_readiness", probe),
                redirect_stderr(io.StringIO()) as errors,
            ):
                self.assertEqual(
                    main(
                        [
                            "openai-readiness",
                            "--output",
                            str(output),
                            "--allow-provider-access",
                        ]
                    ),
                    2,
                )
                self.assertNotIn("OPENAI_API_KEY", errors.getvalue())
                probe.assert_not_awaited()

    def test_success_writes_exclusive_private_receipt_and_cannot_repeat(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            model = "gpt-5.6-terra"
            probe = AsyncMock(return_value=self._receipt(model=model))
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-secret-key"}),
                patch("mos_eisley.cli.probe_openai_readiness", probe),
                patch("mos_eisley.cli._openai_sdk_version", return_value="2.0.0"),
                redirect_stdout(io.StringIO()) as stdout,
            ):
                self.assertEqual(
                    main(
                        [
                            "openai-readiness",
                            "--model",
                            model,
                            "--output",
                            str(output),
                            "--allow-provider-access",
                        ]
                    ),
                    0,
                )
            event = json.loads(stdout.getvalue())
            self.assertEqual(event["model"], model)
            self.assertEqual(event["outcome"], "visible")
            self.assertIs(event["billing_verified"], False)
            self.assertIs(event["responses_access_verified"], False)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(b"synthetic-secret-key", output.read_bytes())

            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-secret-key"}),
                patch("mos_eisley.cli.probe_openai_readiness", probe),
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(
                    main(
                        [
                            "openai-readiness",
                            "--output",
                            str(output),
                            "--allow-provider-access",
                        ]
                    ),
                    2,
                )
            probe.assert_awaited_once()
            assert probe.await_args is not None
            self.assertEqual(probe.await_args.kwargs["model"], model)

    def test_model_outside_registry_is_rejected_before_key_access(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            with (
                patch("mos_eisley.cli._openai_api_key") as key,
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                main(
                    [
                        "openai-readiness",
                        "--model",
                        "gpt-unregistered",
                        "--output",
                        str(output),
                        "--allow-provider-access",
                    ]
                )
            self.assertEqual(raised.exception.code, 2)
            key.assert_not_called()

    def test_probe_cannot_substitute_a_different_registered_model(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            probe = AsyncMock(return_value=self._receipt(model=OPENAI_READINESS_MODEL))
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-secret-key"}),
                patch("mos_eisley.cli.probe_openai_readiness", probe),
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(
                    main(
                        [
                            "openai-readiness",
                            "--model",
                            "gpt-5.6-terra",
                            "--output",
                            str(output),
                            "--allow-provider-access",
                        ]
                    ),
                    2,
                )
            self.assertFalse(output.exists())

    def test_safe_provider_failure_is_written_and_returns_two(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-secret-key"}),
                patch(
                    "mos_eisley.cli.probe_openai_readiness",
                    AsyncMock(return_value=self._receipt("error")),
                ),
                patch("mos_eisley.cli._openai_sdk_version", return_value="2.0.0"),
                redirect_stdout(io.StringIO()) as stdout,
            ):
                self.assertEqual(
                    main(
                        [
                            "openai-readiness",
                            "--output",
                            str(output),
                            "--allow-provider-access",
                        ]
                    ),
                    2,
                )
            self.assertEqual(
                json.loads(stdout.getvalue())["failure_kind"], "permission_error"
            )
            receipt = OpenAIReadinessReceipt.model_validate_json(output.read_bytes())
            self.assertEqual(receipt.failure_kind, "permission_error")
