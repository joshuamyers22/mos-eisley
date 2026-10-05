"""No-network G4 initial-child provider and one-use spend regressions."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import base64
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from protected_anchor_fixture import fixture_anchor
from test_reviewer_coding_broker import _FakeTransport

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.reviewer_coding_broker import parse_initial_child_source_text_proposal
from mos_eisley.reviewer_correction_dispatch import (
    G4CorrectionChildSourceFile,
    creator_test_bundle_sha256,
)
from mos_eisley.reviewer_initial_child import (
    G4InitialChildDispatchApproval,
    G4InitialChildDispatchReceipt,
    G4InitialChildOffer,
    sign_initial_child_dispatch_approval,
    validate_initial_child_proposal,
)
from mos_eisley.reviewer_initial_coding_broker import (
    G4ProductionInitialChildApproval,
    ProductionInitialChildBroker,
    initial_child_request,
    initial_child_source_text_request,
    sign_production_initial_child_approval,
    verify_production_initial_child_receipt,
)
from mos_eisley.reviewer_provenance import (
    G4ChildAssignment,
    G4ProvenanceTrustPolicy,
    provenance_signer,
    sign_child_assignment,
)
from mos_eisley.run.broker_wire import BrokerAck
from mos_eisley.run.duplex import ExchangeHandler
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.provider_broker import ApprovedRequest
from mos_eisley.run.spend_ledger import SpendLedger

IMAGE = "sha256:" + "a" * 64
MODEL = "gpt-5.6-luna"


def _file(path: str, content: bytes) -> G4CorrectionChildSourceFile:
    return G4CorrectionChildSourceFile(
        path=path,
        content_base64=base64.b64encode(content).decode("ascii"),
        content_sha256=digest(content),
    )


class InitialChildBrokerTests(unittest.TestCase):
    def _setup(self, root: Path, *, invalid: bool = False, source_text: bool = False):
        now = datetime.now(UTC)
        creator = Ed25519PrivateKey.generate()
        child = Ed25519PrivateKey.generate()
        human = provenance_signer("creator", creator.public_key())
        child_signer = provenance_signer("child", child.public_key())
        policy = G4ProvenanceTrustPolicy(
            schema_version=2,
            policy_id="initial-child-broker-test",
            creators=(human,),
            reviewers=(human,),
            vcs_brokers=(human,),
            children=(child_signer,),
            valid_from=now - timedelta(hours=1),
            valid_until=now + timedelta(hours=1),
            operator_mode="single_operator",
        )
        task = sign_child_assignment(
            G4ChildAssignment(
                assignment_id="initial-assignment",
                policy_sha256=policy.policy_sha256,
                issued_at=now - timedelta(minutes=3),
                creator_approval_artifact_sha256=digest(b"creator-approval"),
                reviewer_custody_artifact_sha256=digest(b"reviewer-custody"),
                frozen_reviewer_test_package_sha256=digest(b"reviewer-package"),
                base_revision="a" * 40,
                child_signer_id="child",
                child_public_key_sha256=child_signer.public_key_sha256,
                child_brief_sha256=digest(b"implement demo"),
                acceptance_criteria_sha256=digest(b"tests pass"),
                creator_test_paths=("tests/test_demo.py",),
                owned_paths=("src/demo.py",),
                max_input_tokens=1000,
                max_output_tokens=128,
                max_tool_calls=1,
                max_seconds=300,
                max_microusd=1000,
            ),
            "creator",
            creator,
        )
        test_file = _file("tests/test_demo.py", b"assert demo(1) == 2\n")
        order = sign_initial_child_dispatch_approval(
            G4InitialChildDispatchApproval(
                dispatch_id="initial-dispatch",
                policy_sha256=policy.policy_sha256,
                creator_approval_sha256=task.assignment.creator_approval_artifact_sha256,
                reviewer_custody_sha256=task.assignment.reviewer_custody_artifact_sha256,
                assignment_sha256=task.artifact_sha256,
                source_revision=task.assignment.base_revision,
                container_image_id=IMAGE,
                child_signer_id="child",
                brief_sha256=task.assignment.child_brief_sha256,
                acceptance_criteria_sha256=task.assignment.acceptance_criteria_sha256,
                creator_test_bundle_sha256=creator_test_bundle_sha256((test_file,)),
                owned_paths=task.assignment.owned_paths,
                issued_at=now - timedelta(minutes=2),
                expires_at=now + timedelta(minutes=15),
            ),
            "creator",
            creator,
        )
        offer = G4InitialChildOffer(
            dispatch_approval_sha256=order.artifact_sha256,
            assignment_sha256=task.artifact_sha256,
            source_revision=task.assignment.base_revision,
            child_signer_id="child",
            approved_plan="plan",
            brief="implement demo",
            acceptance_criteria="tests pass",
            source_files=(_file("src/demo.py", b"def demo(x): return x\n"),),
            creator_test_files=(test_file,),
            max_input_tokens=1000,
            max_output_tokens=128,
            max_tool_calls=1,
            max_seconds=300,
            max_microusd=1000,
        )
        spend = SpendPolicy(
            schema_version=2,
            model=MODEL,
            pricing_source="fixture",
            valid_from=now - timedelta(minutes=10),
            valid_until=now + timedelta(minutes=30),
            input_microusd_per_million=1_000_000,
            cache_write_microusd_per_million=1_000_000,
            output_microusd_per_million=1_000_000,
            max_cost_microusd=1000,
            max_input_tokens=500,
            max_output_tokens=128,
        )
        ledger = SpendLedger.create(root / "ledger.sqlite", 5000)
        request = (
            initial_child_source_text_request(offer, MODEL, "low", 128)
            if source_text
            else initial_child_request(offer, MODEL, "low", 128)
        )
        live = sign_production_initial_child_approval(
            G4ProductionInitialChildApproval(
                approval_id="initial-live",
                provenance_policy_sha256=policy.policy_sha256,
                assignment_sha256=task.artifact_sha256,
                dispatch_approval_sha256=order.artifact_sha256,
                offer_sha256=offer.offer_sha256,
                provider_request_sha256=digest(
                    canonical_bytes(ApprovedRequest(payload=request))
                ),
                spend_policy_sha256=spend.policy_sha256,
                ledger_id=ledger.policy.ledger_id,
                container_image_id=IMAGE,
                child_signer_id="child",
                model=MODEL,
                effort="low",
                issued_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(minutes=10),
                max_seconds=120,
            ),
            "creator",
            creator,
        )
        transport = _FakeTransport(
            b"def demo(x): return x + 1\n",
            invalid=invalid,
            source_text=source_text,
        )
        container = OfflineContainer(Path("/usr/bin/docker"), IMAGE, root / "life")
        broker = ProductionInitialChildBroker(
            assignment=task,
            dispatch_approval=order,
            offer=offer,
            approval=live,
            provenance_policy=policy,
            spend_policy=spend,
            ledger=ledger,
            child_key=child,
            transport=transport,
            container=container,
            directory=root / "run",
            repository_root=root / "repository",
            protected_anchor=fixture_anchor(creator, ledger, live.artifact_sha256),
        )
        return broker, offer, order, policy, ledger, transport, container

    def test_measured_initial_proposal_and_duplicate_rejection(self) -> None:
        with TemporaryDirectory() as temporary:
            broker, offer, order, policy, ledger, transport, container = self._setup(
                Path(temporary)
            )

            async def exchange(
                arguments: tuple[str, ...],
                payload: bytes,
                handler: ExchangeHandler,
                timeout: float,
            ) -> bytes:
                self.assertEqual(arguments, ("-m", "mos_eisley.run.broker_worker"))
                self.assertGreater(timeout, 0)
                response = await handler(payload)
                return canonical_bytes(BrokerAck(response_sha256=digest(response)))

            with patch.object(container, "exchange_async", side_effect=exchange):
                signed = asyncio.run(broker.generate(offer))
            self.assertEqual(signed.proposal.usage.microusd, 150)
            self.assertEqual(transport.counts, 1)
            self.assertEqual(transport.calls, 1)
            self.assertEqual(ledger.snapshot().unresolved_entries, 0)
            self.assertEqual(ledger.snapshot().charged_microusd, 150)
            receipt = broker.receipt
            assert receipt is not None
            dispatch = G4InitialChildDispatchReceipt(
                approval=order,
                offer=offer,
                signed_proposal=signed,
                execution=validate_initial_child_proposal(offer, signed, policy),
                dispatched_at=datetime.now(UTC),
            )
            verify_production_initial_child_receipt(
                receipt, dispatch, policy, ledger, Path(temporary) / "run"
            )
            with self.assertRaisesRegex(ValueError, "private records differ"):
                verify_production_initial_child_receipt(
                    receipt.model_copy(
                        update={"provider_response_sha256": digest(b"tampered")}
                    ),
                    dispatch,
                    policy,
                    ledger,
                    Path(temporary) / "run",
                )
            with self.assertRaisesRegex(ValueError, "spent"):
                asyncio.run(broker.generate(offer))

    def test_invalid_paid_response_cannot_be_signed(self) -> None:
        with TemporaryDirectory() as temporary:
            broker, offer, _order, _policy, ledger, transport, container = self._setup(
                Path(temporary), invalid=True
            )

            async def exchange(
                _arguments: tuple[str, ...],
                payload: bytes,
                handler: ExchangeHandler,
                _timeout: float,
            ) -> bytes:
                response = await handler(payload)
                return canonical_bytes(BrokerAck(response_sha256=digest(response)))

            with (
                patch.object(container, "exchange_async", side_effect=exchange),
                self.assertRaises(ValueError),
            ):
                asyncio.run(broker.generate(offer))
            self.assertEqual(transport.calls, 1)
            self.assertEqual(ledger.snapshot().unresolved_entries, 0)
            self.assertIsNone(broker.receipt)

    def test_source_text_request_signs_exact_utf8_bytes_and_replays(self) -> None:
        with TemporaryDirectory() as temporary:
            broker, offer, order, policy, ledger, transport, container = self._setup(
                Path(temporary), source_text=True
            )
            request = initial_child_source_text_request(offer, MODEL, "low", 128)
            self.assertIn("content_utf8", str(request["text"]))
            self.assertNotIn("content_base64", str(request["text"]))

            async def exchange(
                _arguments: tuple[str, ...],
                payload: bytes,
                handler: ExchangeHandler,
                _timeout: float,
            ) -> bytes:
                response = await handler(payload)
                return canonical_bytes(BrokerAck(response_sha256=digest(response)))

            with patch.object(container, "exchange_async", side_effect=exchange):
                signed = asyncio.run(broker.generate(offer))
            self.assertEqual(
                signed.proposal.replacements[0].content,
                b"def demo(x): return x + 1\n",
            )
            self.assertEqual(transport.calls, 1)
            receipt = broker.receipt
            assert receipt is not None
            dispatch = G4InitialChildDispatchReceipt(
                approval=order,
                offer=offer,
                signed_proposal=signed,
                execution=validate_initial_child_proposal(offer, signed, policy),
                dispatched_at=datetime.now(UTC),
            )
            verify_production_initial_child_receipt(
                receipt, dispatch, policy, ledger, Path(temporary) / "run"
            )

    def test_source_text_parser_rejects_mixed_or_duplicate_fields(self) -> None:
        valid = json.dumps(
            {
                "replacements": [{"path": "src/demo.py", "content_utf8": "x = 1\n"}],
                "unresolved_issue_count": 0,
            }
        )
        parsed = parse_initial_child_source_text_proposal(valid)
        self.assertEqual(parsed.replacements[0].content, b"x = 1\n")
        with self.assertRaises(ValueError):
            parse_initial_child_source_text_proposal(
                valid.replace('"content_utf8"', '"content_base64"')
            )
        with self.assertRaisesRegex(ValueError, "duplicate JSON keys"):
            parse_initial_child_source_text_proposal(
                valid.replace(
                    '"content_utf8":', '"content_utf8":"bad", "content_utf8":'
                )
            )


if __name__ == "__main__":
    unittest.main()
