"""Judge authority requires both complete audits and preserves one-use spending."""

from __future__ import annotations

import asyncio
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import test_reviewer_plan_test_live as fixture
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import digest
from mos_eisley.providers.anthropic_review import AnthropicReviewHTTPTransport
from mos_eisley.reviewer_plan_test_judge import (
    PlanTestCriticAuditInput,
    SignedG4PlanTestJudgeLiveGrant,
    prepare_plan_test_judge_grant,
    run_plan_test_judge_once,
    sign_plan_test_judge_grant,
    verify_plan_test_judge_audit,
    verify_plan_test_judge_grant,
)
from mos_eisley.reviewer_plan_test_live import (
    prepare_plan_test_critic_grant,
    run_plan_test_critic_once,
    sign_plan_test_critic_grant,
)
from mos_eisley.run.spend_ledger import SpendLedger


class PlanTestJudgeTests(unittest.TestCase):
    def test_verified_pair_one_use_and_tamper_denial(self) -> None:
        f = fixture.PlanTestLiveTests()
        f.setUp()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = SpendLedger.create(root / "ledger.sqlite", 250_000)
            inputs: list[PlanTestCriticAuditInput] = []
            for provider in ("anthropic", "openai"):
                spend = f.spend(provider)
                grant, _, _ = prepare_plan_test_critic_grant(
                    grant_id=provider + "-critic",
                    provider=provider,
                    packet=f.fixture.packet,
                    policy=f.policy,
                    authority=f.authority,
                    spend=spend,
                    ledger=ledger,
                    entry_id=digest(provider.encode()),
                    issued=f.now,
                    expires=f.now + timedelta(minutes=30),
                )
                signed = sign_plan_test_critic_grant(grant, f.fixture.key)
                claims = root / provider
                claims.mkdir(mode=0o700)
                run = claims / grant.grant_id
                transport = fixture.CountedFixture(provider)
                wire = (
                    cast(AnthropicReviewHTTPTransport, transport)
                    if provider == "anthropic"
                    else transport
                )
                asyncio.run(
                    run_plan_test_critic_once(
                        signed,
                        packet=f.fixture.packet,
                        policy=f.policy,
                        authority=f.authority,
                        spend=spend,
                        ledger=ledger,
                        claims=claims,
                        run=run,
                        transport=wire,
                    )
                )
                inputs.append(PlanTestCriticAuditInput(signed, spend, claims, run))
            critics = (inputs[0], inputs[1])
            spend = f.spend("openai")
            grant, _, _ = prepare_plan_test_judge_grant(
                grant_id="judge-1",
                packet=f.fixture.packet,
                policy=f.policy,
                authority=f.authority,
                critics=critics,
                spend=spend,
                ledger=ledger,
                entry_id=digest(b"judge"),
                issued=f.now,
                expires=f.now + timedelta(minutes=30),
            )
            signed = sign_plan_test_judge_grant(grant, f.fixture.key)

            def verify(
                candidate: SignedG4PlanTestJudgeLiveGrant = signed,
                pair: tuple[
                    PlanTestCriticAuditInput, PlanTestCriticAuditInput
                ] = critics,
            ) -> None:
                verify_plan_test_judge_grant(
                    candidate,
                    packet=f.fixture.packet,
                    policy=f.policy,
                    authority=f.authority,
                    critics=pair,
                    spend=spend,
                    ledger=ledger,
                    now=f.now,
                )

            verify()
            with self.assertRaises(ValueError):
                verify(sign_plan_test_judge_grant(grant, Ed25519PrivateKey.generate()))
            with self.assertRaises(ValueError):
                verify(pair=(critics[1], critics[0]))
            response = critics[0].run / "provider-response.json"
            saved = response.read_bytes()
            response.write_bytes(b"{}")
            with self.assertRaises(ValueError):
                verify()
            response.write_bytes(saved)
            claims = root / "judge"
            claims.mkdir(mode=0o700)
            transport = fixture.CountedFixture(
                "openai",
                '{"schema_version":1,"upheld":[],'
                '"rationale":"Plan and tests cover the stated contract."}',
            )

            def call():
                return asyncio.run(
                    run_plan_test_judge_once(
                        signed,
                        packet=f.fixture.packet,
                        policy=f.policy,
                        authority=f.authority,
                        critics=critics,
                        spend=spend,
                        ledger=ledger,
                        claims=claims,
                        run=claims / "judge-1",
                        transport=transport,
                    )
                )

            observation = call()
            replay = verify_plan_test_judge_audit(
                signed,
                packet=f.fixture.packet,
                policy=f.policy,
                authority=f.authority,
                critics=critics,
                spend=spend,
                ledger=ledger,
                claims=claims,
                run=claims / "judge-1",
            )
            self.assertEqual(replay, observation)
            self.assertEqual(observation.decision.upheld, ())
            self.assertEqual((transport.counts, transport.calls), (1, 1))
            with self.assertRaises((ValueError, FileExistsError)):
                call()
            self.assertEqual((transport.counts, transport.calls), (1, 1))
            self.assertFalse(ledger.snapshot().unresolved_entries)
