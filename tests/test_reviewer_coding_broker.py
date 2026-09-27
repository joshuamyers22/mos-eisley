"""No-network regressions for the separately authorized G4 provider child."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.reviewer_coding_broker import (
    G4ProductionCodingChildApproval,
    ProductionCodingChildBroker,
    _parse_model_proposal,
    coding_child_request,
    sign_production_coding_child_approval,
    verify_production_coding_child_receipt,
)
from mos_eisley.reviewer_correction import (
    G4CorrectionCycleAdmission,
    G4CorrectionCycleApproval,
    G4CorrectionFinding,
    G4CorrectionReservations,
    G4CorrectionTaskBudget,
    G4CorrectionTriage,
    sign_correction_cycle_approval,
    sign_correction_triage,
)
from mos_eisley.reviewer_correction_dispatch import (
    G4CorrectionChildDispatchApproval,
    G4CorrectionChildDispatchReceipt,
    G4CorrectionChildJob,
    G4CorrectionChildOffer,
    G4CorrectionChildSourceFile,
    creator_test_bundle_sha256,
    sign_correction_child_dispatch_approval,
    validate_correction_child_job,
)
from mos_eisley.reviewer_provenance import (
    G4ProvenanceTrustPolicy,
    provenance_signer,
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


class _FakeTransport:
    def __init__(
        self, proposed: bytes, *, invalid: bool = False, fail_send: bool = False
    ) -> None:
        self.proposed = proposed
        self.invalid = invalid
        self.fail_send = fail_send
        self.counts = 0
        self.calls = 0

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        self.counts += 1
        return 100

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls += 1
        if self.fail_send:
            raise RuntimeError("fixture provider send failed")
        replacement = _file("src/demo.py", self.proposed)
        text = json.dumps(
            {
                "replacements": [replacement.model_dump(mode="json")],
                "unresolved_issue_count": 0,
            }
        )
        if self.invalid:
            text = "not json"
        return {
            "id": "resp_fixture",
            "status": "completed",
            "model": MODEL,
            "service_tier": "default",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "input_tokens_details": {"cache_write_tokens": 0},
            },
        }


class ProductionCodingChildBrokerTests(unittest.TestCase):
    def test_unpadded_file_with_placeholder_digest_is_revalidated(self) -> None:
        content = b"def quote_cents():\n    return 1\n"
        output = json.dumps(
            {
                "replacements": [
                    {
                        "path": "src/demo.py",
                        "content_base64": base64.b64encode(content)
                        .decode()
                        .rstrip("="),
                        "content_sha256": "0" * 64,
                    }
                ],
                "unresolved_issue_count": 0,
            }
        )
        parsed = _parse_model_proposal(output)
        self.assertEqual(parsed.replacements[0].content, content)
        self.assertEqual(parsed.replacements[0].content_sha256, digest(content))

    def test_model_file_rejects_invalid_base64_before_signing(self) -> None:
        output = json.dumps(
            {
                "replacements": [{"path": "src/demo.py", "content_base64": "YWJj$"}],
                "unresolved_issue_count": 0,
            }
        )
        with self.assertRaisesRegex(ValueError, "base64"):
            _parse_model_proposal(output)

    def test_duplicate_model_keys_are_not_interpreted_last_wins(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate JSON keys"):
            _parse_model_proposal(
                '{"replacements":[],"unresolved_issue_count":0,'
                '"unresolved_issue_count":1}'
            )

    def _setup(self, root: Path, *, invalid: bool = False, fail_send: bool = False):
        now = datetime.now(UTC)
        keys = [Ed25519PrivateKey.generate() for _ in range(4)]
        creator, reviewer, vcs, child = keys
        policy = G4ProvenanceTrustPolicy(
            policy_id="test-policy",
            creators=(provenance_signer("creator", creator.public_key()),),
            reviewers=(provenance_signer("reviewer", reviewer.public_key()),),
            vcs_brokers=(provenance_signer("vcs", vcs.public_key()),),
            children=(provenance_signer("child", child.public_key()),),
            valid_from=now - timedelta(hours=1),
            valid_until=now + timedelta(hours=1),
        )
        triage = sign_correction_triage(
            G4CorrectionTriage(
                task_id="task-one",
                cycle=1,
                review_policy_sha256=digest(b"review"),
                candidate_receipt_sha256=digest(b"candidate"),
                reproduction_receipt_sha256=digest(b"reproduction"),
                critic_review_sha256=digest(b"critics"),
                issued_at=now - timedelta(minutes=5),
                findings=(
                    G4CorrectionFinding(
                        failed_test_id="test_bug",
                        disposition="implementation_defect",
                        applicable_clause_sha256=digest(b"clause"),
                        citation_evidence_sha256=digest(b"citation"),
                        violation_evidence_sha256=digest(b"violation"),
                    ),
                ),
            ),
            "reviewer",
            reviewer,
        )
        limits = G4CorrectionReservations(
            input_tokens=2000,
            output_tokens=500,
            tool_calls=1,
            seconds=600,
            microusd=5000,
        )
        cycle = sign_correction_cycle_approval(
            G4CorrectionCycleApproval(
                approval_id="cycle-one",
                task_id="task-one",
                cycle=1,
                provenance_policy_sha256=policy.policy_sha256,
                triage_artifact_sha256=triage.artifact_sha256,
                source_revision="a" * 40,
                approved_plan_sha256=digest(b"plan"),
                creator_test_suite_sha256=digest(b"creator-tests"),
                frozen_reviewer_test_package_sha256=digest(b"reviewer-tests"),
                task_budget=G4CorrectionTaskBudget(
                    initial_assignment_sha256=digest(b"assignment"),
                    deadline=now + timedelta(minutes=25),
                    ceiling=limits,
                ),
                reserved_before=G4CorrectionReservations(
                    input_tokens=0,
                    output_tokens=0,
                    tool_calls=0,
                    seconds=0,
                    microusd=0,
                ),
                child_signer_id="child",
                owned_paths=("src/demo.py",),
                max_input_tokens=1000,
                max_output_tokens=128,
                max_tool_calls=1,
                max_seconds=300,
                max_microusd=1000,
                issued_at=now - timedelta(minutes=4),
                expires_at=now + timedelta(minutes=20),
            ),
            "creator",
            creator,
        )
        admission = G4CorrectionCycleAdmission(
            triage=triage,
            approval=cycle,
            candidate_receipt_sha256=triage.triage.candidate_receipt_sha256,
            reproduction_receipt_sha256=triage.triage.reproduction_receipt_sha256,
            provenance_record_sha256=digest(b"provenance"),
            binding_record_sha256=digest(b"binding"),
            adapter_sha256=digest(b"adapter"),
            frozen_reviewer_test_package_sha256=digest(b"reviewer-tests"),
            admitted_at=now - timedelta(minutes=3),
        )
        test_file = _file("tests/test_creator.py", b"assert demo(1) == 2\n")
        order = sign_correction_child_dispatch_approval(
            G4CorrectionChildDispatchApproval(
                dispatch_id="dispatch-one",
                admission_sha256=admission.admission_sha256,
                source_revision="a" * 40,
                container_image_id=IMAGE,
                child_signer_id="child",
                brief_sha256=digest(b"fix demo"),
                acceptance_criteria_sha256=digest(b"tests pass"),
                creator_test_suite_sha256=digest(b"creator-tests"),
                creator_test_bundle_sha256=creator_test_bundle_sha256((test_file,)),
                owned_paths=("src/demo.py",),
                issued_at=now - timedelta(minutes=2),
                expires_at=now + timedelta(minutes=15),
            ),
            "creator",
            creator,
        )
        offer = G4CorrectionChildOffer(
            dispatch_approval_sha256=order.artifact_sha256,
            correction_admission_sha256=admission.admission_sha256,
            source_revision="a" * 40,
            approved_plan="plan",
            brief="fix demo",
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
        request = coding_child_request(offer, MODEL, "low", 128)
        approval = sign_production_coding_child_approval(
            G4ProductionCodingChildApproval(
                approval_id="production-one",
                provenance_policy_sha256=policy.policy_sha256,
                admission_sha256=admission.admission_sha256,
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
            fail_send=fail_send,
        )
        container = OfflineContainer(Path("/usr/bin/docker"), IMAGE, root / "life")
        broker = ProductionCodingChildBroker(
            admission=admission,
            dispatch_approval=order,
            offer=offer,
            approval=approval,
            provenance_policy=policy,
            spend_policy=spend,
            ledger=ledger,
            child_key=child,
            transport=transport,
            container=container,
            directory=root / "run",
            repository_root=root / "repository",
        )
        return (
            broker,
            offer,
            order,
            admission,
            policy,
            ledger,
            transport,
            container,
            approval,
        )

    def test_measured_success_and_one_use(self) -> None:
        with TemporaryDirectory() as temporary:
            broker, offer, order, admission, policy, ledger, transport, container, _ = (
                self._setup(Path(temporary))
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
            self.assertEqual(transport.counts, 1)
            self.assertEqual(transport.calls, 1)
            self.assertEqual(signed.proposal.usage.input_tokens, 100)
            self.assertEqual(signed.proposal.usage.output_tokens, 50)
            self.assertEqual(signed.proposal.usage.microusd, 150)
            self.assertEqual(ledger.snapshot().charged_microusd, 150)
            self.assertEqual(ledger.snapshot().unresolved_entries, 0)
            assert broker.receipt is not None
            dispatch = G4CorrectionChildDispatchReceipt(
                approval=order,
                correction_admission_sha256=admission.admission_sha256,
                offer=offer,
                signed_proposal=signed,
                execution=validate_correction_child_job(
                    G4CorrectionChildJob(offer=offer, signed_proposal=signed)
                ),
                dispatched_at=datetime.now(UTC),
            )
            verify_production_coding_child_receipt(
                broker.receipt, dispatch, policy, ledger, Path(temporary) / "run"
            )
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_production_coding_child_receipt(
                    broker.receipt.model_copy(
                        update={"provider_response_sha256": digest(b"tampered")}
                    ),
                    dispatch,
                    policy,
                    ledger,
                    Path(temporary) / "run",
                )
            with self.assertRaisesRegex(ValueError, "already spent"):
                asyncio.run(broker.generate(offer))

    def test_wrong_binding_denies_before_reservation(self) -> None:
        with TemporaryDirectory() as temporary:
            (
                broker,
                offer,
                order,
                admission,
                policy,
                ledger,
                transport,
                container,
                approval,
            ) = self._setup(Path(temporary))
            with self.assertRaises(ValueError):
                ProductionCodingChildBroker(
                    admission=admission,
                    dispatch_approval=order,
                    offer=offer,
                    approval=approval.model_copy(update={"signature": order.signature}),
                    provenance_policy=policy,
                    spend_policy=broker._spend_policy,
                    ledger=ledger,
                    child_key=broker._child_key,
                    transport=transport,
                    container=container,
                    directory=Path(temporary) / "other",
                    repository_root=Path(temporary) / "repository",
                )
            self.assertEqual(ledger.snapshot().entries, 0)
            self.assertEqual(transport.calls, 0)

    def test_wrong_offer_consumes_attempt_without_provider_or_ledger(self) -> None:
        with TemporaryDirectory() as temporary:
            broker, offer, _, _, _, ledger, transport, _, _ = self._setup(
                Path(temporary)
            )
            changed = offer.model_copy(update={"brief": "different"})
            with self.assertRaisesRegex(ValueError, "offer differs"):
                asyncio.run(broker.generate(changed))
            self.assertEqual(ledger.snapshot().entries, 0)
            self.assertEqual(transport.counts, 0)
            with self.assertRaisesRegex(ValueError, "already spent"):
                asyncio.run(broker.generate(offer))

    def test_second_process_cannot_redeem_same_signed_grant(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (
                broker,
                offer,
                order,
                admission,
                policy,
                ledger,
                transport,
                container,
                approval,
            ) = self._setup(root)

            async def exchange(
                arguments: tuple[str, ...],
                payload: bytes,
                handler: ExchangeHandler,
                timeout: float,
            ) -> bytes:
                response = await handler(payload)
                return canonical_bytes(BrokerAck(response_sha256=digest(response)))

            with patch.object(container, "exchange_async", side_effect=exchange):
                asyncio.run(broker.generate(offer))
            second = ProductionCodingChildBroker(
                admission=admission,
                dispatch_approval=order,
                offer=offer,
                approval=approval,
                provenance_policy=policy,
                spend_policy=broker._spend_policy,
                ledger=ledger,
                child_key=broker._child_key,
                transport=transport,
                container=container,
                directory=root / "second-run",
                repository_root=root / "repository",
            )
            with self.assertRaises(sqlite3.IntegrityError):
                asyncio.run(second.generate(offer))
            self.assertEqual(transport.calls, 1)
            self.assertEqual(ledger.snapshot().entries, 1)

    def test_invalid_model_output_still_settles_and_cannot_retry(self) -> None:
        with TemporaryDirectory() as temporary:
            broker, offer, _, _, _, ledger, transport, container, _ = self._setup(
                Path(temporary), invalid=True
            )

            async def exchange(
                arguments: tuple[str, ...],
                payload: bytes,
                handler: ExchangeHandler,
                timeout: float,
            ) -> bytes:
                response = await handler(payload)
                return canonical_bytes(BrokerAck(response_sha256=digest(response)))

            with (
                patch.object(container, "exchange_async", side_effect=exchange),
                self.assertRaises(ValueError),
            ):
                asyncio.run(broker.generate(offer))
            self.assertEqual(transport.calls, 1)
            self.assertEqual(ledger.snapshot().charged_microusd, 150)
            with self.assertRaisesRegex(ValueError, "already spent"):
                asyncio.run(broker.generate(offer))

    def test_failed_send_keeps_uncertain_full_hold(self) -> None:
        with TemporaryDirectory() as temporary:
            broker, offer, _, _, _, ledger, transport, container, _ = self._setup(
                Path(temporary), fail_send=True
            )

            async def exchange(
                arguments: tuple[str, ...],
                payload: bytes,
                handler: ExchangeHandler,
                timeout: float,
            ) -> bytes:
                response = await handler(payload)
                return canonical_bytes(BrokerAck(response_sha256=digest(response)))

            with (
                patch.object(container, "exchange_async", side_effect=exchange),
                self.assertRaises(ProviderError),
            ):
                asyncio.run(broker.generate(offer))
            self.assertEqual(transport.calls, 1)
            self.assertEqual(ledger.snapshot().charged_microusd, 628)
            self.assertEqual(ledger.snapshot().unresolved_entries, 1)
            with self.assertRaisesRegex(ValueError, "already spent"):
                asyncio.run(broker.generate(offer))


if __name__ == "__main__":
    unittest.main()
