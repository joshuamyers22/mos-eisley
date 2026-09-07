"""The credentialed conformance CLI is explicit, isolated, and non-scoreable."""

import asyncio
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from importlib.metadata import version as distribution_version
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue

from mos_eisley.cli import main
from mos_eisley.core.models import Critique, canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient
from mos_eisley.providers.openai_live import EphemeralOpenAITransport
from mos_eisley.run.broker_audit import (
    AssignmentAuthorization,
    inspect_broker_recovery,
)
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.brokered_evaluation import BrokeredEvaluationArtifact
from mos_eisley.run.evaluation_conformance import (
    EvaluationConformancePolicy,
    prepare_evaluation_conformance_policy,
    trusted_evaluation_conformance_observer,
)
from mos_eisley.run.openai_conformance import build_openai_conformance_payload
from mos_eisley.run.provider_broker import RequestBoundBroker
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write
from tests.test_openai_conformance import conformance_inputs
from tests.test_openai_provider import response_payload


def conformance_response(model: str) -> dict[str, JsonValue]:
    response = response_payload(
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": Critique(findings=()).model_dump_json(),
                    }
                ],
            }
        ]
    )
    response["model"] = model
    response["service_tier"] = "default"
    return response


class EphemeralOpenAITransportTests(IsolatedAsyncioTestCase):
    async def test_sdk_clients_are_bounded_loop_local_and_closed(self) -> None:
        batch, policy = conformance_inputs()
        payload = build_openai_conformance_payload(
            batch, batch.requests[0].sample_id, policy
        )
        requests: list[httpx.Request] = []
        clients: list[BoundedOpenAIHttpClient] = []

        async def reply(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/input_tokens"):
                return httpx.Response(200, json={"input_tokens": 100}, request=request)
            body = conformance_response(policy.model)
            body["object"] = "response"
            body["created_at"] = 0
            return httpx.Response(200, json=body, request=request)

        def bounded_client(**options: object) -> BoundedOpenAIHttpClient:
            self.assertFalse(options["trust_env"])
            self.assertFalse(options["follow_redirects"])
            client = BoundedOpenAIHttpClient(transport=httpx.MockTransport(reply))
            clients.append(client)
            return client

        with patch(
            "mos_eisley.providers.openai_live.BoundedOpenAIHttpClient",
            side_effect=bounded_client,
        ):
            transport = EphemeralOpenAITransport("synthetic-test-key", 10)
            count_payload = {
                key: value
                for key, value in payload.items()
                if key not in ("max_output_tokens", "store", "include", "service_tier")
            }
            self.assertEqual(await transport.count_input_tokens(count_payload), 100)
            response = await transport.create_response(payload)

        self.assertEqual(response["model"], policy.model)
        self.assertEqual(
            [request.url.path for request in requests],
            ["/v1/responses/input_tokens", "/v1/responses"],
        )
        self.assertEqual(len(clients), 2)
        self.assertTrue(all(client.is_closed for client in clients))


class OpenAIConformanceCLITests(TestCase):
    def _inputs(self, root: Path) -> tuple[list[str], SpendLedger]:
        batch, policy = conformance_inputs()
        batch_path = root / "batch.json"
        policy_path = root / "policy.json"
        private_write(batch_path, canonical_bytes(batch))
        private_write(policy_path, canonical_bytes(policy))
        ledger = SpendLedger.create(root / "ledger.sqlite", 20_000)
        observer = trusted_evaluation_conformance_observer(
            "observer-a",
            Ed25519PrivateKey.generate().public_key().public_bytes_raw(),
        )
        now = datetime.now(UTC)
        conformance_policy = prepare_evaluation_conformance_policy(
            batch,
            batch.requests[0].sample_id,
            policy,
            ledger,
            root / "audit",
            "openai-probe-1",
            now - timedelta(minutes=5),
            now + timedelta(minutes=30),
            120,
            (observer,),
            (distribution_version("openai"),),
        )
        conformance_policy_path = root / "conformance-policy.json"
        private_write(conformance_policy_path, canonical_bytes(conformance_policy))
        return (
            [
                "openai-conformance",
                "--batch",
                str(batch_path),
                "--sample-id",
                batch.requests[0].sample_id,
                "--spend-policy",
                str(policy_path),
                "--spend-ledger",
                str(ledger.path),
                "--conformance-policy",
                str(conformance_policy_path),
                "--docker",
                "/usr/local/bin/docker",
                "--image",
                "sha256:" + "a" * 64,
                "--audit-dir",
                str(root / "audit"),
                "--authorization-output",
                str(root / "trusted-authorization.json"),
                "--artifact-output",
                str(root / "artifact.json"),
                "--lifecycle-root",
                str(root / "lifecycles"),
                "--allow-data-transfer",
            ],
            ledger,
        )

    @staticmethod
    def _redeem_without_docker(
        broker: RequestBoundBroker, object_: object, *, timeout: float
    ) -> BrokerReply:
        del object_, timeout
        return BrokerReply(
            response=asyncio.run(broker.redeem(canonical_bytes(broker.claim())))
        )

    def test_one_assignment_produces_bound_non_scoreable_artifact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            options, ledger = self._inputs(root)
            batch, _ = conformance_inputs()
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret-test-key"}),
                patch(
                    "mos_eisley.cli.EphemeralOpenAITransport.count_input_tokens",
                    new=AsyncMock(return_value=100),
                ) as count,
                patch(
                    "mos_eisley.cli.EphemeralOpenAITransport.create_response",
                    new=AsyncMock(return_value=conformance_response("gpt-6-astra")),
                ) as create,
                patch(
                    "mos_eisley.cli.run_isolated_broker",
                    side_effect=self._redeem_without_docker,
                ),
                redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(main(options), 0)

            event = json.loads(output.getvalue())
            self.assertEqual(event["type"], "openai.conformance.completed")
            self.assertFalse(event["promotion_eligible"])
            self.assertEqual(event["cost_microusd"], 140)
            self.assertIsNone(event["lifecycle_path"])
            count.assert_awaited_once()
            create.assert_awaited_once()

            authorization = AssignmentAuthorization.model_validate_json(
                (root / "trusted-authorization.json").read_bytes()
            )
            artifact = BrokeredEvaluationArtifact.model_validate_json(
                (root / "artifact.json").read_bytes()
            )
            self.assertEqual(artifact.authorization, authorization)
            self.assertEqual(
                artifact.authorization.sample_id, batch.requests[0].sample_id
            )
            self.assertEqual(event["artifact_sha256"], artifact.artifact_sha256)
            state = inspect_broker_recovery(root / "audit", authorization, ledger)
            self.assertEqual(
                (state.phase, state.ledger_status, state.outcome_status),
                ("finished", "settled", "response_received"),
            )
            self.assertNotIn(
                b"secret-test-key",
                b"".join(
                    path.read_bytes() for path in root.rglob("*") if path.is_file()
                ),
            )

    def test_consent_fails_before_files_credentials_or_dispatch(self) -> None:
        options = [
            "openai-conformance",
            "--batch",
            "missing-batch",
            "--sample-id",
            "a" * 64,
            "--spend-policy",
            "missing-policy",
            "--spend-ledger",
            "missing-ledger",
            "--conformance-policy",
            "missing-conformance-policy",
            "--docker",
            "/usr/local/bin/docker",
            "--image",
            "sha256:" + "a" * 64,
            "--audit-dir",
            "audit",
            "--authorization-output",
            "authorization.json",
            "--artifact-output",
            "artifact.json",
        ]
        with (
            patch("mos_eisley.cli._openai_api_key") as credential,
            patch("mos_eisley.cli.read_bounded") as read,
            patch("mos_eisley.cli.run_isolated_broker") as dispatch,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(options), 2)
            credential.assert_not_called()
            read.assert_not_called()
            dispatch.assert_not_called()

    def test_missing_key_and_bad_output_layout_fail_before_dispatch(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            options, _ = self._inputs(root)
            with (
                patch(
                    "mos_eisley.cli._openai_api_key", return_value=None
                ) as credential,
                patch("mos_eisley.cli.EphemeralOpenAITransport") as transport,
                patch("mos_eisley.cli.run_isolated_broker") as dispatch,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(options), 2)
                transport.assert_not_called()
                dispatch.assert_not_called()
                credential.assert_called_once_with()
            self.assertFalse((root / "audit").exists())
            self.assertFalse((root / "trusted-authorization.json").exists())

            nested = options.copy()
            nested[nested.index(str(root / "trusted-authorization.json"))] = str(
                root / "audit" / "trusted.json"
            )
            with (
                patch("mos_eisley.cli._openai_api_key") as credential,
                patch("mos_eisley.cli.EphemeralOpenAITransport") as transport,
                patch("mos_eisley.cli.run_isolated_broker") as dispatch,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(nested), 2)
                credential.assert_not_called()
                transport.assert_not_called()
                dispatch.assert_not_called()

    def test_unknown_assignment_fails_before_credential_or_dispatch(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            options, _ = self._inputs(root)
            options[options.index("b" * 64)] = "0" * 64
            with (
                patch("mos_eisley.cli._openai_api_key") as credential,
                patch("mos_eisley.cli.run_isolated_broker") as dispatch,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(options), 2)
                credential.assert_not_called()
                dispatch.assert_not_called()

    def test_policy_mismatch_fails_before_credential_or_dispatch(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            options, _ = self._inputs(root)
            policy_path = root / "conformance-policy.json"
            policy = EvaluationConformancePolicy.model_validate_json(
                policy_path.read_bytes()
            )
            changed_path = root / "changed-conformance-policy.json"
            private_write(
                changed_path,
                canonical_bytes(
                    policy.model_copy(update={"allowed_sdk_versions": ("0.0.0",)})
                ),
            )
            options[options.index(str(policy_path))] = str(changed_path)
            with (
                patch("mos_eisley.cli._openai_api_key") as credential,
                patch("mos_eisley.cli.run_isolated_broker") as dispatch,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(options), 2)
                credential.assert_not_called()
                dispatch.assert_not_called()

    def test_dispatched_failure_is_not_mislabeled_as_success_artifact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            options, ledger = self._inputs(root)
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret-test-key"}),
                patch(
                    "mos_eisley.cli.EphemeralOpenAITransport.count_input_tokens",
                    new=AsyncMock(return_value=100),
                ),
                patch(
                    "mos_eisley.cli.EphemeralOpenAITransport.create_response",
                    new=AsyncMock(side_effect=ProviderError("synthetic failure")),
                ),
                patch(
                    "mos_eisley.cli.run_isolated_broker",
                    side_effect=self._redeem_without_docker,
                ),
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(options), 2)

            authorization = AssignmentAuthorization.model_validate_json(
                (root / "trusted-authorization.json").read_bytes()
            )
            state = inspect_broker_recovery(root / "audit", authorization, ledger)
            self.assertEqual(
                (state.phase, state.ledger_status, state.outcome_status),
                ("finished", "uncertain", "failed"),
            )
            self.assertFalse((root / "artifact.json").exists())
