"""CLI ordering and durable-output tests for the synthetic Responses canary."""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.openai_responses_canary import (
    OPENAI_RESPONSES_CANARY_MODEL,
    OpenAIResponsesCanaryAuthorityPolicy,
    SignedOpenAIResponsesCanaryAuthorization,
    execute_openai_responses_canary,
    load_openai_responses_canary,
    make_openai_responses_canary_authorization,
    sign_openai_responses_canary_authorization,
    trusted_openai_responses_canary_authority,
)
from mos_eisley.run.spend_ledger import SpendLedger


class _Transport:
    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        return 8

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return {
            "id": "resp_cli_canary",
            "status": "completed",
            "model": OPENAI_RESPONSES_CANARY_MODEL,
            "service_tier": "default",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "OK"}],
                }
            ],
            "usage": {
                "input_tokens": 8,
                "output_tokens": 2,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
            "incomplete_details": None,
        }


def _inputs(root: Path) -> tuple[Path, Path, Path, Ed25519PrivateKey]:
    now = datetime.now(UTC)
    key = Ed25519PrivateKey.generate()
    spend_policy = SpendPolicy(
        model=OPENAI_RESPONSES_CANARY_MODEL,
        pricing_source="official fixture",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        input_microusd_per_million=1_000_000,
        output_microusd_per_million=1_000_000,
        max_cost_microusd=1_000,
        max_input_tokens=100,
        max_output_tokens=64,
    )
    authority_policy = OpenAIResponsesCanaryAuthorityPolicy(
        policy_id="canary-cli-policy",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        max_authorization_lifetime_seconds=600,
        max_request_timeout_seconds=20,
        authorities=(
            trusted_openai_responses_canary_authority(
                "canary-cli-signer", key.public_key().public_bytes_raw()
            ),
        ),
    )
    spend_path = root / "spend-policy.json"
    spend_path.write_bytes(canonical_bytes(spend_policy))
    authority_path = root / "authority-policy.json"
    authority_path.write_bytes(canonical_bytes(authority_policy))
    ledger_path = root / "spending.sqlite"
    SpendLedger.create(ledger_path, 10_000)
    return spend_path, ledger_path, authority_path, key


class OpenAIResponsesCanaryCliTests(TestCase):
    def test_derivation_reads_no_credential_and_sends_nothing(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spend_path, ledger_path, authority_path, _ = _inputs(root)
            authorization_path = root / "authorization.json"
            run_directory = root / "canary"
            now = datetime.now(UTC)
            with (
                patch("mos_eisley.cli._openai_api_key") as key_access,
                patch("mos_eisley.cli._openai_responses_canary_run") as run,
                redirect_stdout(io.StringIO()) as stdout,
            ):
                exit_code = main(
                    [
                        "openai-derive-responses-canary-authorization",
                        "--spend-policy",
                        str(spend_path),
                        "--spend-ledger",
                        str(ledger_path),
                        "--authority-policy",
                        str(authority_path),
                        "--run-dir",
                        str(run_directory),
                        "--issued-at",
                        now.isoformat(),
                        "--valid-until",
                        (now + timedelta(minutes=5)).isoformat(),
                        "--output",
                        str(authorization_path),
                    ]
                )
            self.assertEqual(exit_code, 0)
            self.assertTrue(authorization_path.is_file())
            self.assertFalse(run_directory.exists())
            key_access.assert_not_called()
            run.assert_not_called()
            event = json.loads(stdout.getvalue())
            self.assertFalse(event["credential_accessed"])
            self.assertFalse(event["provider_request_sent"])

    def test_live_command_verifies_before_key_access_and_completes(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spend_path, ledger_path, authority_path, key = _inputs(root)
            spend_policy = SpendPolicy.model_validate_json(spend_path.read_bytes())
            authority_policy = OpenAIResponsesCanaryAuthorityPolicy.model_validate_json(
                authority_path.read_bytes()
            )
            ledger = SpendLedger(ledger_path)
            run_directory = root / "canary"
            now = datetime.now(UTC)
            authorization = make_openai_responses_canary_authorization(
                spend_policy,
                ledger.policy.ledger_id,
                authority_policy,
                run_directory,
                10,
                now,
                now + timedelta(minutes=5),
            )
            signed = sign_openai_responses_canary_authorization(
                authorization, "canary-cli-signer", key.private_bytes_raw()
            )
            signed_path = root / "signed.json"
            signed_path.write_bytes(canonical_bytes(signed))

            async def fake_run(
                api_key: str,
                timeout: float,
                supplied_policy: SpendPolicy,
                supplied_ledger: SpendLedger,
                supplied_directory: Path,
                supplied_authority_policy: OpenAIResponsesCanaryAuthorityPolicy,
                supplied_signed: SignedOpenAIResponsesCanaryAuthorization,
            ):
                self.assertEqual(api_key, "secret-test-key")
                self.assertEqual(timeout, 10)
                return await execute_openai_responses_canary(
                    _Transport(),
                    supplied_policy,
                    supplied_ledger,
                    supplied_directory,
                    supplied_authority_policy,
                    supplied_signed,
                    sdk_version="2.test",
                )

            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret-test-key"}),
                patch(
                    "mos_eisley.cli._openai_responses_canary_run",
                    side_effect=fake_run,
                ),
                redirect_stdout(io.StringIO()) as stdout,
            ):
                exit_code = main(
                    [
                        "openai-responses-canary",
                        "--spend-policy",
                        str(spend_path),
                        "--spend-ledger",
                        str(ledger_path),
                        "--authority-policy",
                        str(authority_path),
                        "--signed-authorization",
                        str(signed_path),
                        "--run-dir",
                        str(run_directory),
                        "--allow-data-transfer",
                    ]
                )
            self.assertEqual(exit_code, 0)
            result = load_openai_responses_canary(
                run_directory, SpendLedger(ledger_path)
            )
            self.assertTrue(result.responses_access_verified)
            self.assertFalse(result.billing_verified)
            self.assertNotIn(
                b"secret-test-key",
                b"".join(path.read_bytes() for path in run_directory.iterdir()),
            )
            event = json.loads(stdout.getvalue())
            self.assertEqual(event["outcome"], "verified")
            with redirect_stdout(io.StringIO()) as verify_stdout:
                verify_exit = main(
                    [
                        "openai-verify-responses-canary",
                        "--run-dir",
                        str(run_directory),
                        "--spend-ledger",
                        str(ledger_path),
                    ]
                )
            self.assertEqual(verify_exit, 0)
            self.assertEqual(
                json.loads(verify_stdout.getvalue())["type"],
                "openai.responses_canary.verified",
            )

    def test_invalid_authorization_prevents_key_access_and_output(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spend_path, ledger_path, authority_path, key = _inputs(root)
            spend_policy = SpendPolicy.model_validate_json(spend_path.read_bytes())
            authority_policy = OpenAIResponsesCanaryAuthorityPolicy.model_validate_json(
                authority_path.read_bytes()
            )
            ledger = SpendLedger(ledger_path)
            authorized_directory = root / "authorized"
            actual_directory = root / "different"
            now = datetime.now(UTC)
            authorization = make_openai_responses_canary_authorization(
                spend_policy,
                ledger.policy.ledger_id,
                authority_policy,
                authorized_directory,
                10,
                now,
                now + timedelta(minutes=5),
            )
            signed_path = root / "signed.json"
            signed_path.write_bytes(
                canonical_bytes(
                    sign_openai_responses_canary_authorization(
                        authorization, "canary-cli-signer", key.private_bytes_raw()
                    )
                )
            )
            with (
                patch("mos_eisley.cli._openai_api_key") as key_access,
                patch("mos_eisley.cli._openai_responses_canary_run") as run,
                redirect_stderr(io.StringIO()),
            ):
                exit_code = main(
                    [
                        "openai-responses-canary",
                        "--spend-policy",
                        str(spend_path),
                        "--spend-ledger",
                        str(ledger_path),
                        "--authority-policy",
                        str(authority_path),
                        "--signed-authorization",
                        str(signed_path),
                        "--run-dir",
                        str(actual_directory),
                        "--allow-data-transfer",
                    ]
                )
            self.assertEqual(exit_code, 2)
            self.assertFalse(actual_directory.exists())
            key_access.assert_not_called()
            run.assert_not_called()
