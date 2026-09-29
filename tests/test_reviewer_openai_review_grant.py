"""The G4 OpenAI critic grant binds one signer, request and spending hold."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

import test_reviewer_single_operator_review as single_fixture
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue
from test_reviewer_provenance import NOW

from mos_eisley.core.models import digest
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.review.citations import citation_bound_request
from mos_eisley.reviewer_openai_review_grant import (
    OPENAI_LUNA_PRICING,
    prepare_openai_critic_grant,
    run_openai_critic_once,
    sign_openai_critic_grant,
    verify_openai_critic_grant,
)
from mos_eisley.run.spend_ledger import SpendLedger


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return NOW + timedelta(minutes=11)


class _CountedTransport:
    calls = 0

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        del payload
        return 123

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        del payload
        self.calls += 1
        return {
            "id": "resp_fixture",
            "status": "completed",
            "model": "gpt-5.6-luna",
            "service_tier": "default",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"schema_version":1,"findings":[]}',
                        }
                    ],
                }
            ],
            "usage": {
                "input_tokens": 123,
                "output_tokens": 20,
                "input_tokens_details": {"cache_write_tokens": 0},
            },
        }


class G4OpenAIGrantTests(unittest.TestCase):
    def _case(self, root: Path) -> dict[str, Any]:
        common, values = single_fixture.G4SingleOperatorReviewTests()._case(root)
        subject, provenance, authority, _, _, _ = values
        spec = authority.authority.critics[1]
        self.assertEqual(spec.provider, "openai")
        request = citation_bound_request(subject.brief, spec.persona)
        policy = SpendPolicy(
            schema_version=2,
            model="gpt-5.6-luna",
            pricing_source=OPENAI_LUNA_PRICING,
            valid_from=NOW + timedelta(minutes=9),
            valid_until=NOW + timedelta(minutes=30),
            input_microusd_per_million=200_000,
            cache_write_microusd_per_million=250_000,
            output_microusd_per_million=1_200_000,
            max_cost_microusd=50_000,
            max_input_tokens=64_000,
            max_output_tokens=4096,
        )
        ledger = SpendLedger.create(root / "review-ledger.sqlite", 10_000_000)
        with patch("mos_eisley.providers.openai_spend.datetime", _FixedDateTime):
            grant, payload, reservation = prepare_openai_critic_grant(
                grant_id="g4-q1-openai-critic-live-1",
                subject=subject,
                provenance=provenance,
                authority=authority,
                request=request,
                spend_policy=policy,
                ledger=ledger,
                ledger_entry_id=digest(b"one openai critic"),
                issued_at=NOW + timedelta(minutes=10),
                expires_at=NOW + timedelta(minutes=20),
            )
        signed = sign_openai_critic_grant(grant, "creator", common["creator_key"])
        return {
            "subject": subject,
            "provenance": provenance,
            "authority": authority,
            "request": request,
            "policy": policy,
            "ledger": ledger,
            "grant": grant,
            "signed": signed,
            "payload": payload,
            "reservation": reservation,
        }

    def _verify(self, case: dict[str, Any], **kwargs: Any) -> Any:
        with patch("mos_eisley.providers.openai_spend.datetime", _FixedDateTime):
            return verify_openai_critic_grant(
                kwargs.get("signed", case["signed"]),
                subject=case["subject"],
                provenance=case["provenance"],
                authority=case["authority"],
                request=kwargs.get("request", case["request"]),
                spend_policy=kwargs.get("policy", case["policy"]),
                ledger=case["ledger"],
                now=kwargs.get("now", NOW + timedelta(minutes=11)),
            )

    def test_exact_grant_verifies_with_bounded_price_and_payload(self) -> None:
        with TemporaryDirectory() as temp:
            case = self._case(Path(temp))
            body, reservation, entry = self._verify(case)
            self.assertEqual(body, case["payload"])
            self.assertEqual(reservation, case["reservation"])
            self.assertEqual(entry.reserved_microusd, 20_916)
            self.assertEqual(body["reasoning"], {"effort": "low"})
            self.assertEqual(body["tools"], [])
            self.assertEqual(body["service_tier"], "default")
            self.assertFalse(case["grant"].independent_review_evidence_passed)
            self.assertFalse(case["grant"].acceptance_authorized)

    def test_foreign_or_changed_signature_is_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            case = self._case(Path(temp))
            foreign = sign_openai_critic_grant(
                case["grant"], "creator", Ed25519PrivateKey.generate()
            )
            with self.assertRaises(ValueError):
                self._verify(case, signed=foreign)
            changed = case["signed"].model_copy(
                update={
                    "grant": case["grant"].model_copy(
                        update={"provider_request_sha256": digest(b"changed")}
                    )
                }
            )
            with self.assertRaises(ValueError):
                self._verify(case, signed=changed)

    def test_expiry_and_underpriced_policy_are_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            case = self._case(Path(temp))
            with self.assertRaisesRegex(ValueError, "expired"):
                self._verify(case, now=NOW + timedelta(minutes=20))
            underpriced = case["policy"].model_copy(
                update={"output_microusd_per_million": 1}
            )
            with self.assertRaisesRegex(ValueError, "lineage"):
                self._verify(case, policy=underpriced)

    def test_wrong_critic_request_is_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            case = self._case(Path(temp))
            changed = case["request"].model_copy(update={"persona": "changed"})
            with self.assertRaisesRegex(ValueError, "lineage"):
                self._verify(case, request=changed)

    def test_one_use_dispatch_settles_and_writes_observation(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._case(root)
            claims = root / "claims"
            claims.mkdir(mode=0o700)
            fixture = _CountedTransport()

            async def run() -> Any:
                return await run_openai_critic_once(
                    case["signed"],
                    subject=case["subject"],
                    provenance=case["provenance"],
                    authority=case["authority"],
                    request=case["request"],
                    spend_policy=case["policy"],
                    ledger=case["ledger"],
                    claim_store=claims,
                    run_directory=claims / "call-1",
                    transport=fixture,
                )

            with (
                patch("mos_eisley.providers.openai_spend.datetime", _FixedDateTime),
                patch(
                    "mos_eisley.reviewer_openai_review_grant.datetime", _FixedDateTime
                ),
            ):
                observation = asyncio.run(run())
                with self.assertRaises(FileExistsError):
                    asyncio.run(run())
            self.assertEqual(fixture.calls, 1)
            self.assertEqual(observation.result.status, "completed")
            self.assertTrue((claims / "call-1" / "critic-observation.json").exists())
            self.assertEqual(case["ledger"].snapshot().unresolved_entries, 0)
