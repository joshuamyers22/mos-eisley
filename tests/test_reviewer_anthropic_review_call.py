"""G4 Anthropic critic grant binds one owner, request and shared spending hold."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import patch

import test_reviewer_single_operator_review as single_fixture
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue
from test_reviewer_provenance import NOW

from mos_eisley.core.models import digest
from mos_eisley.providers.anthropic_review import AnthropicReviewHTTPTransport
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.review.citations import citation_bound_request
from mos_eisley.reviewer_anthropic_review_call import (
    prepare_anthropic_critic_grant,
    run_anthropic_critic_once,
    sign_anthropic_critic_grant,
    verify_anthropic_critic_grant,
)
from mos_eisley.run.spend_ledger import SpendLedger


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return NOW + timedelta(minutes=11)


class _CountedTransport:
    calls = 0

    async def count_input_tokens(self, _payload: dict[str, JsonValue]) -> int:
        return 123

    async def create_response(
        self, _payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls += 1
        return {
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"findings":[]}'}],
            "usage": {
                "input_tokens": 123,
                "output_tokens": 20,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "service_tier": "standard",
                "inference_geo": "global",
                "server_tool_use": {},
            },
        }


class G4AnthropicGrantTests(unittest.TestCase):
    def _case(self, root: Path) -> dict[str, Any]:
        common, values = single_fixture.G4SingleOperatorReviewTests()._case(root)
        subject, provenance, authority, _, _, _ = values
        spec = authority.authority.critics[0]
        self.assertEqual(spec.provider, "anthropic")
        request = citation_bound_request(subject.brief, spec.persona)
        policy = SpendPolicy(
            schema_version=2,
            model="claude-sonnet-5",
            pricing_source="https://platform.claude.com/docs/en/about-claude/pricing",
            valid_from=NOW + timedelta(minutes=9),
            valid_until=NOW + timedelta(minutes=30),
            input_microusd_per_million=2_000_000,
            cache_write_microusd_per_million=4_000_000,
            output_microusd_per_million=10_000_000,
            max_cost_microusd=200_000,
            max_input_tokens=16_000,
            max_output_tokens=4096,
        )
        ledger = SpendLedger.create(root / "review-ledger.sqlite", 10_000_000)
        grant, payload, reservation = prepare_anthropic_critic_grant(
            grant_id="g4-q1-anthropic-critic-1",
            subject=subject,
            provenance=provenance,
            authority=authority,
            critic_id=spec.id,
            request=request,
            spend_policy=policy,
            ledger=ledger,
            ledger_entry_id=digest(b"one anthropic critic"),
            issued_at=NOW + timedelta(minutes=10),
            expires_at=NOW + timedelta(minutes=20),
        )
        signed = sign_anthropic_critic_grant(grant, "creator", common["creator_key"])
        return {
            "subject": subject,
            "provenance": provenance,
            "authority": authority,
            "request": request,
            "spend_policy": policy,
            "ledger": ledger,
            "grant": grant,
            "signed": signed,
            "payload": payload,
            "reservation": reservation,
        }

    def test_exact_signed_one_call_grant_verifies(self) -> None:
        with TemporaryDirectory() as temp:
            case = self._case(Path(temp))
            payload, reservation, entry = verify_anthropic_critic_grant(
                case["signed"],
                subject=case["subject"],
                provenance=case["provenance"],
                authority=case["authority"],
                request=case["request"],
                spend_policy=case["spend_policy"],
                ledger=case["ledger"],
                now=NOW + timedelta(minutes=11),
            )
            self.assertEqual(payload, case["payload"])
            self.assertEqual(reservation, case["reservation"])
            self.assertEqual(entry.reserved_microusd, 104_960)
            self.assertTrue(case["grant"].provider_dispatch_authorized)
            self.assertTrue(case["grant"].network_authorized)
            self.assertTrue(case["grant"].credential_access_authorized)
            self.assertFalse(case["grant"].independent_review_evidence_passed)
            self.assertFalse(case["grant"].acceptance_authorized)

    def test_larger_review_packet_has_a_fully_held_bounded_grant(self) -> None:
        with TemporaryDirectory() as temp:
            case = self._case(Path(temp))
            policy = case["spend_policy"].model_copy(
                update={"max_input_tokens": 32_000}
            )
            grant, _body, reservation = prepare_anthropic_critic_grant(
                grant_id="g4-q1-anthropic-expanded-packet-1",
                subject=case["subject"],
                provenance=case["provenance"],
                authority=case["authority"],
                critic_id="anthropic-critic",
                request=case["request"],
                spend_policy=policy,
                ledger=case["ledger"],
                ledger_entry_id=digest(b"expanded anthropic packet"),
                issued_at=NOW + timedelta(minutes=10),
                expires_at=NOW + timedelta(minutes=20),
            )
            self.assertEqual(reservation.input_tokens, 32_000)
            self.assertEqual(reservation.reserved_microusd, 168_960)
            self.assertEqual(grant.reserved_microusd, 168_960)
            oversized = policy.model_copy(update={"max_input_tokens": 32_001})
            with self.assertRaisesRegex(ValueError, "signed G4 review lineage"):
                prepare_anthropic_critic_grant(
                    grant_id="g4-q1-anthropic-oversized-packet-1",
                    subject=case["subject"],
                    provenance=case["provenance"],
                    authority=case["authority"],
                    critic_id="anthropic-critic",
                    request=case["request"],
                    spend_policy=oversized,
                    ledger=case["ledger"],
                    ledger_entry_id=digest(b"oversized anthropic packet"),
                    issued_at=NOW + timedelta(minutes=10),
                    expires_at=NOW + timedelta(minutes=20),
                )

    def test_changed_or_foreign_signature_is_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            case = self._case(Path(temp))
            foreign = sign_anthropic_critic_grant(
                case["grant"], "creator", Ed25519PrivateKey.generate()
            )
            with self.assertRaisesRegex(ValueError, "not enrolled"):
                verify_anthropic_critic_grant(
                    foreign,
                    subject=case["subject"],
                    provenance=case["provenance"],
                    authority=case["authority"],
                    request=case["request"],
                    spend_policy=case["spend_policy"],
                    ledger=case["ledger"],
                    now=NOW + timedelta(minutes=11),
                )
            changed = case["signed"].model_copy(
                update={
                    "grant": case["grant"].model_copy(
                        update={"provider_request_sha256": digest(b"wrong")}
                    )
                }
            )
            with self.assertRaisesRegex(ValueError, "signature"):
                verify_anthropic_critic_grant(
                    changed,
                    subject=case["subject"],
                    provenance=case["provenance"],
                    authority=case["authority"],
                    request=case["request"],
                    spend_policy=case["spend_policy"],
                    ledger=case["ledger"],
                    now=NOW + timedelta(minutes=11),
                )

    def test_expiry_and_changed_request_are_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            case = self._case(Path(temp))
            with self.assertRaisesRegex(ValueError, "expired"):
                verify_anthropic_critic_grant(
                    case["signed"],
                    subject=case["subject"],
                    provenance=case["provenance"],
                    authority=case["authority"],
                    request=case["request"],
                    spend_policy=case["spend_policy"],
                    ledger=case["ledger"],
                    now=NOW + timedelta(minutes=20),
                )
            request = case["request"].model_copy(update={"persona": "changed"})
            with self.assertRaisesRegex(ValueError, "lineage"):
                verify_anthropic_critic_grant(
                    case["signed"],
                    subject=case["subject"],
                    provenance=case["provenance"],
                    authority=case["authority"],
                    request=request,
                    spend_policy=case["spend_policy"],
                    ledger=case["ledger"],
                    now=NOW + timedelta(minutes=11),
                )
            underpriced = case["spend_policy"].model_copy(
                update={"output_microusd_per_million": 1}
            )
            with self.assertRaisesRegex(ValueError, "lineage"):
                verify_anthropic_critic_grant(
                    case["signed"],
                    subject=case["subject"],
                    provenance=case["provenance"],
                    authority=case["authority"],
                    request=case["request"],
                    spend_policy=underpriced,
                    ledger=case["ledger"],
                    now=NOW + timedelta(minutes=11),
                )

    def test_one_use_dispatch_writes_private_observation_and_settles(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._case(root)
            claims = root / "claims"
            claims.mkdir(mode=0o700)
            fixture = _CountedTransport()

            async def dispatch() -> Any:
                return await run_anthropic_critic_once(
                    case["signed"],
                    subject=case["subject"],
                    provenance=case["provenance"],
                    authority=case["authority"],
                    request=case["request"],
                    spend_policy=case["spend_policy"],
                    ledger=case["ledger"],
                    claim_store=claims,
                    run_directory=claims / "attempt-1",
                    transport=cast(AnthropicReviewHTTPTransport, fixture),
                )

            with (
                patch(
                    "mos_eisley.reviewer_anthropic_review_call.datetime",
                    _FixedDateTime,
                ),
                patch("mos_eisley.providers.openai_spend.datetime", _FixedDateTime),
                patch(
                    "mos_eisley.providers.anthropic_review_spend.datetime",
                    _FixedDateTime,
                ),
            ):
                observation = asyncio.run(dispatch())
                with self.assertRaises(FileExistsError):
                    asyncio.run(dispatch())
            self.assertEqual(fixture.calls, 1)
            self.assertEqual(observation.result.status, "completed")
            self.assertEqual(case["ledger"].snapshot().charged_microusd, 446)
            self.assertTrue((claims / "attempt-1/critic-observation.json").is_file())
