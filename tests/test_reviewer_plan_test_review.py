"""Pre-delegation review cannot substitute tests, stage, identity or time."""

from __future__ import annotations

import base64
import unittest
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.core.models import CriticSpec, canonical_bytes, digest
from mos_eisley.reviewer_plan_test_review import (
    CreatorTestSource,
    G4PlanTestReviewAuthority,
    G4PlanTestReviewPacket,
    plan_test_brief,
    plan_test_requests,
    sign_plan_test_authority,
    verify_plan_test_authority,
)
from mos_eisley.reviewer_provenance import G4ProvenanceTrustPolicy, provenance_signer


class PlanTestReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 30, tzinfo=UTC)
        self.key = Ed25519PrivateKey.generate()
        owner = provenance_signer("joshua-myers", self.key.public_key())
        child = provenance_signer("child", Ed25519PrivateKey.generate().public_key())
        self.policy = G4ProvenanceTrustPolicy(
            schema_version=2,
            policy_id="test-plan-review",
            creators=(owner,),
            reviewers=(owner,),
            vcs_brokers=(owner,),
            children=(child,),
            operator_mode="single_operator",
            valid_from=self.now,
            valid_until=self.now + timedelta(days=1),
        )
        self.packet = G4PlanTestReviewPacket(
            task_id="duration",
            base_revision="a" * 40,
            plan="Return duration milliseconds; reject malformed literals.",
            creator_tests=(
                CreatorTestSource(
                    path="tests/test_duration.py",
                    content="def test_duration():\n    assert parse('1s') == 1000\n",
                ),
            ),
        )
        self.critics = (
            CriticSpec(
                id="anthropic-critic",
                provider="anthropic",
                model="claude-sonnet-5",
                persona="Review creator tests against the plan.",
            ),
            CriticSpec(
                id="openai-critic",
                provider="openai",
                model="gpt-5.6-luna",
                persona="Find contradictory or missing test expectations.",
            ),
        )
        requests = plan_test_requests(self.packet, self.critics)
        self.authority = G4PlanTestReviewAuthority(
            authority_id="test-pre-delegation",
            provenance_policy_sha256=self.policy.policy_sha256,
            packet_sha256=self.packet.packet_sha256,
            critics=self.critics,
            critic_request_sha256s=(
                digest(canonical_bytes(requests[0])),
                digest(canonical_bytes(requests[1])),
            ),
            issued_at=self.now,
            expires_at=self.now + timedelta(hours=1),
        )

    def test_exact_signed_packet_has_no_delegation_or_approval(self) -> None:
        signed = sign_plan_test_authority(self.authority, self.key)
        verify_plan_test_authority(signed, self.packet, self.policy, now=self.now)
        brief = plan_test_brief(self.packet)
        self.assertIn("+    assert parse('1s') == 1000\n", brief.diff)
        self.assertIn("BEFORE coding delegation", brief.constraints)
        self.assertFalse(signed.authority.coding_delegation_authorized)
        self.assertFalse(signed.authority.plan_and_tests_approved)
        self.assertFalse(signed.authority.provider_dispatch_authorized)

    def test_changed_plan_tests_base_task_roster_key_or_time_rejected(self) -> None:
        signed = sign_plan_test_authority(self.authority, self.key)
        for update in (
            {"plan": "Allow malformed input."},
            {"base_revision": "b" * 40},
            {"task_id": "different-task"},
            {
                "creator_tests": (
                    self.packet.creator_tests[0].model_copy(
                        update={"content": "def test_duration():\n    assert True\n"}
                    ),
                )
            },
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                verify_plan_test_authority(
                    signed,
                    self.packet.model_copy(update=update),
                    self.policy,
                    now=self.now,
                )
        altered = sign_plan_test_authority(
            self.authority.model_copy(
                update={
                    "critics": (
                        self.critics[0],
                        self.critics[1].model_copy(update={"persona": "Changed scope"}),
                    )
                }
            ),
            self.key,
        )
        with self.assertRaises(ValueError):
            verify_plan_test_authority(altered, self.packet, self.policy, now=self.now)
        foreign = sign_plan_test_authority(self.authority, Ed25519PrivateKey.generate())
        with self.assertRaises(ValueError):
            verify_plan_test_authority(foreign, self.packet, self.policy, now=self.now)
        for at in (self.now - timedelta(seconds=1), self.authority.expires_at):
            with self.assertRaises(ValueError):
                verify_plan_test_authority(signed, self.packet, self.policy, now=at)

    def test_duplicate_test_paths_and_stage_escalation_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            G4PlanTestReviewPacket.model_validate(
                {
                    **self.packet.model_dump(),
                    "creator_tests": self.packet.creator_tests * 2,
                }
            )
        for field in (
            "plan_and_tests_approved",
            "coding_delegation_authorized",
            "provider_dispatch_authorized",
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                G4PlanTestReviewAuthority.model_validate(
                    {**self.authority.model_dump(), field: True}
                )

    def test_another_review_stage_signature_cannot_be_replayed(self) -> None:
        signed = sign_plan_test_authority(self.authority, self.key)
        signature = signed.signature.model_copy(
            update={
                "signature_base64": base64.b64encode(
                    self.key.sign(
                        b"mos-eisley/g4-single-operator-review-authority/v1\x00"
                        + canonical_bytes(self.authority)
                    )
                ).decode("ascii")
            }
        )
        with self.assertRaises(ValueError):
            verify_plan_test_authority(
                signed.model_copy(update={"signature": signature}),
                self.packet,
                self.policy,
                now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
