"""Independent authorization, execution, and replay tests for the Responses canary."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue

from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import SpendPolicy, SpendReceipt
from mos_eisley.run.openai_responses_canary import (
    OPENAI_RESPONSES_CANARY_INPUT,
    OPENAI_RESPONSES_CANARY_MODEL,
    OpenAIResponsesCanaryAuthorityPolicy,
    SignedOpenAIResponsesCanaryAuthorization,
    begin_openai_responses_canary,
    execute_openai_responses_canary,
    load_openai_responses_canary,
    make_openai_responses_canary_authorization,
    openai_responses_canary_count_request,
    openai_responses_canary_request,
    sign_openai_responses_canary_authorization,
    trusted_openai_responses_canary_authority,
    verify_openai_responses_canary_authorization,
)
from mos_eisley.run.spend_ledger import SpendLedger

NOW = datetime.now(UTC)


def _spend_policy() -> SpendPolicy:
    return SpendPolicy(
        model=OPENAI_RESPONSES_CANARY_MODEL,
        pricing_source="official fixture",
        valid_from=NOW - timedelta(hours=1),
        valid_until=NOW + timedelta(hours=1),
        input_microusd_per_million=1_000_000,
        output_microusd_per_million=1_000_000,
        max_cost_microusd=1_000,
        max_input_tokens=100,
        max_output_tokens=64,
    )


def _cache_write_spend_policy() -> SpendPolicy:
    return SpendPolicy(
        schema_version=2,
        model=OPENAI_RESPONSES_CANARY_MODEL,
        pricing_source="official synthetic cache-write fixture",
        valid_from=NOW - timedelta(hours=1),
        valid_until=NOW + timedelta(hours=1),
        input_microusd_per_million=1_000_000,
        cache_write_microusd_per_million=1_250_000,
        output_microusd_per_million=1_000_000,
        max_cost_microusd=1_000,
        max_input_tokens=100,
        max_output_tokens=64,
    )


def _authority_policy(
    key: Ed25519PrivateKey,
) -> OpenAIResponsesCanaryAuthorityPolicy:
    return OpenAIResponsesCanaryAuthorityPolicy(
        policy_id="canary-authority",
        valid_from=NOW - timedelta(hours=1),
        valid_until=NOW + timedelta(hours=1),
        max_authorization_lifetime_seconds=600,
        max_request_timeout_seconds=20,
        authorities=(
            trusted_openai_responses_canary_authority(
                "canary-signer", key.public_key().public_bytes_raw()
            ),
        ),
    )


def _authorization(
    key: Ed25519PrivateKey,
    policy: SpendPolicy,
    ledger: SpendLedger,
    directory: Path,
    timeout: float = 10,
) -> tuple[
    OpenAIResponsesCanaryAuthorityPolicy,
    SignedOpenAIResponsesCanaryAuthorization,
]:
    authority_policy = _authority_policy(key)
    authorization = make_openai_responses_canary_authorization(
        policy,
        ledger.policy.ledger_id,
        authority_policy,
        directory,
        timeout,
        NOW,
        NOW + timedelta(minutes=5),
    )
    return authority_policy, sign_openai_responses_canary_authorization(
        authorization, "canary-signer", key.private_bytes_raw()
    )


class CanaryTransport:
    def __init__(
        self,
        *,
        fail_response: bool = False,
        cache_write_tokens: int | None = None,
    ) -> None:
        self.counts: list[dict[str, JsonValue]] = []
        self.responses: list[dict[str, JsonValue]] = []
        self.fail_response = fail_response
        self.cache_write_tokens = cache_write_tokens

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        self.counts.append(payload)
        return 12

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.responses.append(payload)
        if self.fail_response:
            raise ProviderError(
                "synthetic failure",
                failure_kind="transport_error",
                failure_stage="response",
            )
        input_details: dict[str, JsonValue] = {"cached_tokens": 0}
        if self.cache_write_tokens is not None:
            input_details["cache_write_tokens"] = self.cache_write_tokens
        return {
            "id": "resp_canary",
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
                "input_tokens": 12,
                "output_tokens": 2,
                "input_tokens_details": input_details,
                "output_tokens_details": {"reasoning_tokens": 0},
            },
            "incomplete_details": None,
        }


class SlowCanaryTransport(CanaryTransport):
    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.responses.append(payload)
        await asyncio.sleep(1)
        raise AssertionError("canary timeout was not enforced")


class OpenAIResponsesCanaryAuthorizationTests(TestCase):
    def test_authorization_binds_exact_requests_spend_path_and_timeout(self) -> None:
        key = Ed25519PrivateKey.generate()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = SpendLedger.create(root / "spending.sqlite", 10_000)
            policy = _spend_policy()
            directory = root / "canary"
            authority_policy, signed = _authorization(key, policy, ledger, directory)

            verified = verify_openai_responses_canary_authorization(
                signed,
                authority_policy,
                policy,
                ledger.policy.ledger_id,
                directory,
                10,
                NOW + timedelta(minutes=1),
            )

            self.assertEqual(verified, signed.authorization)
            self.assertEqual(verified.max_cost_microusd, 132)
            self.assertEqual(verified.provider_requests_authorized, 2)
            self.assertFalse(verified.user_data_transfer_authorized)
            self.assertIn(
                OPENAI_RESPONSES_CANARY_INPUT,
                canonical_bytes(verified).decode(),
            )
            for changed_ledger, changed_directory, changed_timeout in (
                (ledger.policy.ledger_id, root / "other", 10.0),
                (ledger.policy.ledger_id, directory, 9.0),
                ("f" * 64, directory, 10.0),
            ):
                with self.assertRaises(ValueError):
                    verify_openai_responses_canary_authorization(
                        signed,
                        authority_policy,
                        policy,
                        changed_ledger,
                        changed_directory,
                        changed_timeout,
                        NOW + timedelta(minutes=1),
                    )

    def test_invalid_signature_and_expired_window_fail_closed(self) -> None:
        key = Ed25519PrivateKey.generate()
        other = Ed25519PrivateKey.generate()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = SpendLedger.create(root / "spending.sqlite", 10_000)
            policy = _spend_policy()
            authority_policy, signed = _authorization(
                key, policy, ledger, root / "canary"
            )
            other_signed = sign_openai_responses_canary_authorization(
                signed.authorization,
                "canary-signer",
                other.private_bytes_raw(),
            )
            forged = signed.model_copy(
                update={
                    "signature": signed.signature.model_copy(
                        update={
                            "signature_base64": other_signed.signature.signature_base64
                        }
                    )
                }
            )
            for candidate, current in (
                (forged, NOW + timedelta(minutes=1)),
                (signed, NOW + timedelta(minutes=6)),
            ):
                with self.assertRaises(ValueError):
                    verify_openai_responses_canary_authorization(
                        candidate,
                        authority_policy,
                        policy,
                        ledger.policy.ledger_id,
                        root / "canary",
                        10,
                        current,
                    )


class OpenAIResponsesCanaryExecutionTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Discovery can precede this class by more than the five-minute fixture
        # window on CI. Keep execution fixtures fresh without widening authority.
        self.enterContext(patch(f"{__name__}.NOW", datetime.now(UTC)))

    async def test_insufficient_worst_case_ledger_blocks_token_count(self) -> None:
        key = Ed25519PrivateKey.generate()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = SpendLedger.create(root / "spending.sqlite", 100)
            policy = _spend_policy()
            directory = root / "canary"
            authority_policy, signed = _authorization(key, policy, ledger, directory)
            begin_openai_responses_canary(directory, authority_policy, signed, policy)
            transport = CanaryTransport()

            with self.assertRaisesRegex(ValueError, "maximum authorized exposure"):
                await execute_openai_responses_canary(
                    transport,
                    policy,
                    ledger,
                    directory,
                    authority_policy,
                    signed,
                    sdk_version="2.test",
                )

            self.assertEqual(transport.counts, [])
            self.assertEqual(transport.responses, [])
            self.assertEqual(ledger.snapshot().entries, 0)

    async def test_one_deadline_covers_count_and_generation(self) -> None:
        key = Ed25519PrivateKey.generate()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = SpendLedger.create(root / "spending.sqlite", 10_000)
            policy = _spend_policy()
            directory = root / "canary"
            authority_policy, signed = _authorization(
                key, policy, ledger, directory, timeout=0.01
            )
            begin_openai_responses_canary(directory, authority_policy, signed, policy)
            transport = SlowCanaryTransport()

            with self.assertRaises(TimeoutError):
                await execute_openai_responses_canary(
                    transport,
                    policy,
                    ledger,
                    directory,
                    authority_policy,
                    signed,
                    sdk_version="2.test",
                )

            receipt = SpendReceipt.model_validate_json(
                (directory / "spend-receipt.json").read_bytes()
            )
            self.assertEqual(receipt.status, "uncertain")
            self.assertFalse((directory / "manifest.json").exists())

    async def test_changed_preserved_input_prevents_any_provider_request(self) -> None:
        key = Ed25519PrivateKey.generate()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = SpendLedger.create(root / "spending.sqlite", 10_000)
            policy = _spend_policy()
            directory = root / "canary"
            authority_policy, signed = _authorization(key, policy, ledger, directory)
            begin_openai_responses_canary(directory, authority_policy, signed, policy)
            (directory / "request.json").write_text("{}")
            transport = CanaryTransport()

            with self.assertRaisesRegex(ValueError, "changed before dispatch"):
                await execute_openai_responses_canary(
                    transport,
                    policy,
                    ledger,
                    directory,
                    authority_policy,
                    signed,
                    sdk_version="2.test",
                )

            self.assertEqual(transport.counts, [])
            self.assertEqual(transport.responses, [])
            self.assertEqual(ledger.snapshot().entries, 0)

    async def test_success_is_bounded_settled_and_content_verified(self) -> None:
        key = Ed25519PrivateKey.generate()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = SpendLedger.create(root / "spending.sqlite", 10_000)
            policy = _spend_policy()
            directory = root / "canary"
            authority_policy, signed = _authorization(key, policy, ledger, directory)
            begin_openai_responses_canary(directory, authority_policy, signed, policy)
            transport = CanaryTransport()

            result = await execute_openai_responses_canary(
                transport,
                policy,
                ledger,
                directory,
                authority_policy,
                signed,
                completed_at=NOW + timedelta(minutes=1),
                sdk_version="2.test",
            )

            self.assertEqual(
                transport.counts, [openai_responses_canary_count_request()]
            )
            self.assertEqual(transport.responses, [openai_responses_canary_request()])
            self.assertEqual(result.outcome, "verified")
            self.assertTrue(result.responses_access_verified)
            self.assertFalse(result.billing_verified)
            self.assertEqual(result.retained_microusd, 14)
            self.assertEqual(load_openai_responses_canary(directory, ledger), result)
            self.assertEqual(ledger.snapshot().charged_microusd, 14)
            self.assertEqual(ledger.snapshot().unresolved_entries, 0)

            extra = directory / "untracked"
            extra.write_text("confusing evidence")
            with self.assertRaisesRegex(ValueError, "artifact set"):
                load_openai_responses_canary(directory, ledger)
            extra.unlink()
            result_path = directory / "result.json"
            changed = json.loads(result_path.read_bytes())
            changed["responses_access_verified"] = False
            result_path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "artifact digest"):
                load_openai_responses_canary(directory, ledger)

    async def test_schema_two_binds_and_verifies_cache_write_settlement(self) -> None:
        key = Ed25519PrivateKey.generate()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = SpendLedger.create(root / "spending.sqlite", 10_000)
            policy = _cache_write_spend_policy()
            directory = root / "canary"
            authority_policy, signed = _authorization(key, policy, ledger, directory)
            # Independent authorization is derived before provider token counting,
            # so it covers the policy's 100-token input cap and the fixed 32-token
            # canary output cap at the schema-2 worst-case rates.
            self.assertEqual(signed.authorization.max_cost_microusd, 157)
            begin_openai_responses_canary(directory, authority_policy, signed, policy)

            result = await execute_openai_responses_canary(
                CanaryTransport(cache_write_tokens=3),
                policy,
                ledger,
                directory,
                authority_policy,
                signed,
                completed_at=NOW + timedelta(minutes=1),
                sdk_version="2.test",
            )

            receipt = SpendReceipt.model_validate_json(
                (directory / "spend-receipt.json").read_bytes()
            )
            self.assertEqual(result.retained_microusd, 15)
            self.assertEqual(receipt.cache_write_tokens, 3)
            self.assertEqual(ledger.snapshot().charged_microusd, 15)
            self.assertEqual(load_openai_responses_canary(directory, ledger), result)

    async def test_failed_generation_retains_reservation_without_manifest(self) -> None:
        key = Ed25519PrivateKey.generate()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = SpendLedger.create(root / "spending.sqlite", 10_000)
            policy = _spend_policy()
            directory = root / "canary"
            authority_policy, signed = _authorization(key, policy, ledger, directory)
            begin_openai_responses_canary(directory, authority_policy, signed, policy)
            transport = CanaryTransport(fail_response=True)

            with self.assertRaises(ProviderError):
                await execute_openai_responses_canary(
                    transport,
                    policy,
                    ledger,
                    directory,
                    authority_policy,
                    signed,
                    completed_at=NOW + timedelta(minutes=1),
                    sdk_version="2.test",
                )

            self.assertFalse((directory / "manifest.json").exists())
            receipt = SpendReceipt.model_validate_json(
                (directory / "spend-receipt.json").read_bytes()
            )
            self.assertEqual(receipt.status, "uncertain")
            self.assertEqual(ledger.snapshot().unresolved_entries, 1)
