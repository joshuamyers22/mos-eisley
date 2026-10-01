"""Plan-stage live grants preserve scope, settlement and one-use protection."""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import test_reviewer_plan_test_review as review_fixture
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue

from mos_eisley.core.models import digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.anthropic_review import AnthropicReviewHTTPTransport
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.reviewer_plan_test_live import (
    Provider,
    prepare_plan_test_critic_grant,
    run_plan_test_critic_once,
    sign_plan_test_critic_grant,
    verify_plan_test_critic_audit,
    verify_plan_test_critic_grant,
)
from mos_eisley.reviewer_plan_test_review import sign_plan_test_authority
from mos_eisley.run.spend_ledger import SpendLedger


class CountedFixture:
    def __init__(
        self, provider: Provider, text: str = '{"schema_version":1,"findings":[]}'
    ) -> None:
        self.provider = provider
        self.text = text
        self.counts = 0
        self.calls = 0

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        del payload
        self.counts += 1
        return 123

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        del payload
        self.calls += 1
        if self.provider == "anthropic":
            return {
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": self.text}],
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
                        {"type": "output_text", "text": self.text},
                    ],
                }
            ],
            "usage": {
                "input_tokens": 123,
                "output_tokens": 20,
                "input_tokens_details": {"cache_write_tokens": 0},
            },
        }


class PlanTestLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = review_fixture.PlanTestReviewTests()
        self.fixture.setUp()
        self.now = datetime.now(UTC)
        self.policy = self.fixture.policy.model_copy(
            update={
                "valid_from": self.now - timedelta(hours=1),
                "valid_until": self.now + timedelta(days=1),
            }
        )
        authority = self.fixture.authority.model_copy(
            update={
                "provenance_policy_sha256": self.policy.policy_sha256,
                "issued_at": self.now - timedelta(minutes=1),
                "expires_at": self.now + timedelta(hours=2),
            }
        )
        self.authority = sign_plan_test_authority(authority, self.fixture.key)

    def spend(self, provider: Provider) -> SpendPolicy:
        if provider == "anthropic":
            return SpendPolicy(
                schema_version=2,
                valid_from=self.now - timedelta(minutes=1),
                valid_until=self.now + timedelta(hours=2),
                model="claude-sonnet-5",
                pricing_source="https://platform.claude.com/docs/en/about-claude/pricing",
                input_microusd_per_million=2_000_000,
                cache_write_microusd_per_million=4_000_000,
                output_microusd_per_million=10_000_000,
                max_input_tokens=17_500,
                max_output_tokens=3900,
                max_cost_microusd=200_000,
            )
        return SpendPolicy(
            schema_version=2,
            valid_from=self.now - timedelta(minutes=1),
            valid_until=self.now + timedelta(hours=2),
            model="gpt-5.6-luna",
            pricing_source="https://developers.openai.com/api/docs/models/gpt-5.6-luna",
            input_microusd_per_million=200_000,
            cache_write_microusd_per_million=250_000,
            output_microusd_per_million=1_200_000,
            max_input_tokens=64_000,
            max_output_tokens=4096,
            max_cost_microusd=50_000,
        )

    def test_both_provider_calls_settle_and_duplicate_never_reaches_transport(
        self,
    ) -> None:
        for provider in ("anthropic", "openai"):
            with self.subTest(provider=provider), TemporaryDirectory() as directory:
                root = Path(directory)
                ledger = SpendLedger.create(root / "ledger.sqlite", 250_000)
                spend = self.spend(provider)
                grant, _, _ = prepare_plan_test_critic_grant(
                    grant_id="critic-1",
                    provider=provider,
                    packet=self.fixture.packet,
                    policy=self.policy,
                    authority=self.authority,
                    spend=spend,
                    ledger=ledger,
                    entry_id=digest(provider.encode()),
                    issued=self.now,
                    expires=self.now + timedelta(minutes=30),
                )
                signed = sign_plan_test_critic_grant(grant, self.fixture.key)
                claims = root / "claims"
                claims.mkdir(mode=0o700)
                run = claims / "critic-1"
                transport = CountedFixture(provider)
                wire = (
                    cast(AnthropicReviewHTTPTransport, transport)
                    if provider == "anthropic"
                    else transport
                )
                observation = asyncio.run(
                    run_plan_test_critic_once(
                        signed,
                        packet=self.fixture.packet,
                        policy=self.policy,
                        authority=self.authority,
                        spend=spend,
                        ledger=ledger,
                        claims=claims,
                        run=run,
                        transport=wire,
                    )
                )
                self.assertEqual(observation.result.status, "completed")
                self.assertEqual((transport.counts, transport.calls), (1, 1))
                status = ledger.entry_status(grant.ledger_entry_id)
                assert status is not None
                self.assertEqual(status.status, "settled")
                self.assertEqual(status.charged_microusd, spend.cost(123, 20, 0))
                replay = verify_plan_test_critic_audit(
                    signed,
                    packet=self.fixture.packet,
                    policy=self.policy,
                    authority=self.authority,
                    spend=spend,
                    ledger=ledger,
                    claims=claims,
                    run=run,
                )
                self.assertEqual(replay, observation)
                response_path = run / "provider-response.json"
                original_response = response_path.read_bytes()
                response_path.write_bytes(b"{}")
                with self.assertRaises((ValueError, ProviderError)):
                    verify_plan_test_critic_audit(
                        signed,
                        packet=self.fixture.packet,
                        policy=self.policy,
                        authority=self.authority,
                        spend=spend,
                        ledger=ledger,
                        claims=claims,
                        run=run,
                    )
                response_path.write_bytes(original_response)
                with self.assertRaises(FileExistsError):
                    asyncio.run(
                        run_plan_test_critic_once(
                            signed,
                            packet=self.fixture.packet,
                            policy=self.policy,
                            authority=self.authority,
                            spend=spend,
                            ledger=ledger,
                            claims=claims,
                            run=run,
                            transport=wire,
                        )
                    )
                self.assertEqual((transport.counts, transport.calls), (1, 1))
                foreign = sign_plan_test_critic_grant(
                    grant, Ed25519PrivateKey.generate()
                )
                with self.assertRaises(ValueError):
                    verify_plan_test_critic_grant(
                        foreign,
                        packet=self.fixture.packet,
                        policy=self.policy,
                        authority=self.authority,
                        spend=spend,
                        ledger=ledger,
                        now=self.now,
                    )
                with self.assertRaises(ValueError):
                    verify_plan_test_critic_grant(
                        signed,
                        packet=self.fixture.packet.model_copy(
                            update={"plan": "Changed"}
                        ),
                        policy=self.policy,
                        authority=self.authority,
                        spend=spend,
                        ledger=ledger,
                        now=self.now,
                    )
                with self.assertRaises(ValueError):
                    verify_plan_test_critic_grant(
                        signed,
                        packet=self.fixture.packet,
                        policy=self.policy,
                        authority=self.authority,
                        spend=spend.model_copy(
                            update={"max_cost_microusd": spend.max_cost_microusd + 1}
                        ),
                        ledger=ledger,
                        now=self.now,
                    )
                wider = SpendLedger.create(root / "wider-ledger.sqlite", 500_000)
                with self.assertRaises(ValueError):
                    verify_plan_test_critic_grant(
                        signed,
                        packet=self.fixture.packet,
                        policy=self.policy,
                        authority=self.authority,
                        spend=spend,
                        ledger=wider,
                        now=self.now,
                    )

    def test_invalid_citation_keeps_settlement_and_raw_audit_without_observation(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = SpendLedger.create(root / "ledger.sqlite", 250_000)
            spend = self.spend("openai")
            grant, _, _ = prepare_plan_test_critic_grant(
                grant_id="bad-critic",
                provider="openai",
                packet=self.fixture.packet,
                policy=self.policy,
                authority=self.authority,
                spend=spend,
                ledger=ledger,
                entry_id=digest(b"bad"),
                issued=self.now,
                expires=self.now + timedelta(minutes=30),
            )
            signed = sign_plan_test_critic_grant(grant, self.fixture.key)
            claims = root / "claims"
            claims.mkdir(mode=0o700)
            run = claims / "bad-critic"
            text = json.dumps(
                {
                    "schema_version": 1,
                    "findings": [
                        {
                            "location": "plan",
                            "category": "spec_violation",
                            "impact": "high",
                            "claim": "Unsupported assertion",
                            "evidence": {
                                "source": "spec",
                                "quote": "Absent quote",
                                "explanation": "Invalid evidence",
                            },
                        }
                    ],
                }
            )
            transport = CountedFixture("openai", text)
            with self.assertRaises(ProviderError):
                asyncio.run(
                    run_plan_test_critic_once(
                        signed,
                        packet=self.fixture.packet,
                        policy=self.policy,
                        authority=self.authority,
                        spend=spend,
                        ledger=ledger,
                        claims=claims,
                        run=run,
                        transport=transport,
                    )
                )
            status = ledger.entry_status(grant.ledger_entry_id)
            assert status is not None
            self.assertEqual(status.status, "settled")
            self.assertTrue((run / "provider-response.json").is_file())
            self.assertTrue((run / "outcome.json").is_file())
            self.assertFalse((run / "critic-observation.json").exists())
