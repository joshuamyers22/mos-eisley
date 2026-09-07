"""Broker outcomes retain exact coverage without becoming scoreable evidence."""

import asyncio
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Critique, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.evaluation.execution import (
    ExecutionBatch,
    RawResultSet,
    make_execution_batch,
)
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.brokered_evaluation import (
    BrokeredEvaluationArtifact,
    BrokeredEvaluationResultSet,
    compile_brokered_evaluation,
    compile_brokered_evaluation_failure,
    compile_brokered_evaluation_result_set,
)
from mos_eisley.run.evaluation_broker import (
    authorize_assignment,
    make_assignment_broker,
)
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write
from tests.test_evaluation_execution import inputs, make_plan
from tests.test_openai_provider import response_payload
from tests.test_openai_spend import FakeTransport, policy, request


class BrokeredEvaluationTests(IsolatedAsyncioTestCase):
    def _context(
        self,
        root: Path,
        text: str,
        *,
        status: str = "completed",
        transport_error: BaseException | None = None,
        input_tokens: int = 100,
        lifetime_seconds: float = 30,
    ):
        data, grid, gate = inputs()
        plan = make_plan(data, grid, 1, 0, gate)
        batch, _ = make_execution_batch(plan, data, "calibration", b"a" * 32)
        evaluation_request = batch.requests[0]
        payload = request()
        payload["model"] = evaluation_request.route.model
        payload["reasoning"] = {"effort": evaluation_request.route.effort}
        fake = FakeTransport(root)
        fake.tokens = input_tokens
        fake.error = transport_error
        fake.response = response_payload(
            [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            status=status,
            incomplete_reason=("max_output_tokens" if status == "incomplete" else None),
        )
        fake.response["model"] = evaluation_request.route.model
        fake.response["service_tier"] = "default"
        ledger = SpendLedger.create(root / "ledger.sqlite", 500)
        transport = BudgetedOpenAITransport(
            fake,
            policy().model_copy(update={"model": evaluation_request.route.model}),
            root,
            ledger,
        )
        expected = authorize_assignment(
            batch, evaluation_request.sample_id, payload, transport
        )
        broker = make_assignment_broker(
            batch,
            evaluation_request.sample_id,
            payload,
            transport,
            root / "audit",
            lifetime_seconds=lifetime_seconds,
        )
        return broker, expected, ledger

    async def test_complete_text_becomes_non_scoreable_bound_artifact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            critique = Critique(findings=())
            broker, expected, ledger = self._context(root, critique.model_dump_json())
            reply = BrokerReply(
                response=await broker.redeem(canonical_bytes(broker.claim()))
            )
            artifact = compile_brokered_evaluation(
                reply, expected, root / "audit", ledger
            )
            self.assertEqual(artifact.critique, critique)
            self.assertEqual(artifact.authorization, expected)
            assert artifact.usage is not None
            self.assertEqual(artifact.usage.unit, "tokens")
            self.assertEqual(artifact.cost_microusd, 140)
            self.assertFalse(artifact.promotion_eligible)
            self.assertFalse(artifact.live_result_eligible)
            self.assertFalse(artifact.retry_permitted)
            self.assertFalse(artifact.automatic_budget_release_authorized)
            self.assertEqual(artifact.status, "completed")
            self.assertEqual(len(artifact.artifact_sha256), 64)

    async def test_changed_reply_and_wrong_ledger_fail_before_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            broker, expected, ledger = self._context(
                root, Critique(findings=()).model_dump_json()
            )
            reply = BrokerReply(
                response=await broker.redeem(canonical_bytes(broker.claim()))
            )
            changed = reply.model_copy(update={"response": {"changed": True}})
            with self.assertRaises(ValueError):
                compile_brokered_evaluation(changed, expected, root / "audit", ledger)
            other_root = root / "other"
            other_root.mkdir()
            other = SpendLedger.create(other_root / "ledger.sqlite", 500)
            with self.assertRaises(ValueError):
                compile_brokered_evaluation(reply, expected, root / "audit", other)

    async def test_invalid_critique_or_incomplete_response_is_not_evidence(
        self,
    ) -> None:
        for index, (text, status) in enumerate(
            (("not json", "completed"), (Critique().model_dump_json(), "incomplete"))
        ):
            with TemporaryDirectory() as directory:
                root = Path(directory)
                broker, expected, ledger = self._context(root, text, status=status)
                reply = BrokerReply(
                    response=await broker.redeem(canonical_bytes(broker.claim()))
                )
                with (
                    self.subTest(index=index),
                    self.assertRaisesRegex(
                        ValueError, "brokered critique validation failed"
                    ),
                ):
                    compile_brokered_evaluation(reply, expected, root / "audit", ledger)

    def test_unredeemed_grant_cannot_mint_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, expected, ledger = self._context(
                root, Critique(findings=()).model_dump_json()
            )
            with self.assertRaisesRegex(ValueError, "provenance is incomplete"):
                compile_brokered_evaluation(
                    BrokerReply(response={}), expected, root / "audit", ledger
                )

    async def test_provider_failure_and_cancellation_are_preserved(self) -> None:
        for index, (error, expected_status, expected_error) in enumerate(
            (
                (RuntimeError("private detail"), "failed", "provider_error"),
                (TimeoutError(), "failed", "timeout"),
                (asyncio.CancelledError(), "cancelled", "cancelled"),
            )
        ):
            with self.subTest(index=index), TemporaryDirectory() as directory:
                root = Path(directory)
                broker, expected, ledger = self._context(
                    root,
                    Critique().model_dump_json(),
                    transport_error=error,
                )
                with self.assertRaises((ProviderError, asyncio.CancelledError)):
                    await broker.redeem(canonical_bytes(broker.claim()))
                artifact = compile_brokered_evaluation_failure(
                    expected, root / "audit", ledger
                )
                self.assertEqual(artifact.status, "error")
                self.assertEqual(artifact.outcome_status, expected_status)
                self.assertEqual(artifact.error, expected_error)
                self.assertEqual(artifact.ledger_status, "uncertain")
                self.assertEqual(artifact.cost_microusd, 300)
                self.assertIsNotNone(artifact.latency_ms)
                self.assertIsNone(artifact.provider_request_id)
                self.assertFalse(artifact.live_result_eligible)
                self.assertFalse(artifact.retry_permitted)
                self.assertFalse(artifact.automatic_budget_release_authorized)

    async def test_pre_reservation_failure_preserves_absent_cost(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            broker, expected, ledger = self._context(
                root,
                Critique().model_dump_json(),
                input_tokens=65_000,
            )
            with self.assertRaises(ProviderError):
                await broker.redeem(canonical_bytes(broker.claim()))
            artifact = compile_brokered_evaluation_failure(
                expected, root / "audit", ledger
            )
            self.assertEqual(artifact.ledger_status, "absent")
            self.assertIsNone(artifact.cost_microusd)

    async def test_actual_broker_deadline_is_distinct_from_cancellation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            broker, expected, ledger = self._context(
                root,
                Critique().model_dump_json(),
                lifetime_seconds=0.01,
            )

            async def slow(_: object) -> None:
                await asyncio.sleep(1)

            with (
                patch.object(
                    BudgetedOpenAITransport,
                    "create_response",
                    side_effect=slow,
                ),
                self.assertRaises(ProviderError),
            ):
                await broker.redeem(canonical_bytes(broker.claim()))
            artifact = compile_brokered_evaluation_failure(
                expected, root / "audit", ledger
            )
            self.assertEqual(artifact.outcome_status, "failed")
            self.assertEqual(artifact.error, "timeout")
            self.assertEqual(artifact.ledger_status, "absent")

    async def test_failure_compilation_cli_requires_independent_authorization(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            broker, expected, ledger = self._context(
                root,
                Critique().model_dump_json(),
                transport_error=RuntimeError("private detail"),
            )
            with self.assertRaises(ProviderError):
                await broker.redeem(canonical_bytes(broker.claim()))
            expected_path = root / "trusted-authorization.json"
            output_path = root / "failure-artifact.json"
            private_write(expected_path, canonical_bytes(expected))
            options = [
                "eval-compile-brokered-failure",
                "--expected-authorization",
                str(expected_path),
                "--audit-dir",
                str(root / "audit"),
                "--spend-ledger",
                str(ledger.path),
                "--output",
                str(output_path),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(options), 0)
            event = json.loads(stdout.getvalue())
            self.assertEqual(event["type"], "evaluation.brokered_failure.compiled")
            self.assertEqual(event["status"], "error")
            self.assertEqual(event["error"], "provider_error")
            self.assertFalse(event["live_result_eligible"])
            self.assertFalse(event["retry_permitted"])
            self.assertFalse(event["automatic_budget_release_authorized"])
            artifact = BrokeredEvaluationArtifact.model_validate_json(
                output_path.read_bytes()
            )
            self.assertEqual(event["artifact_sha256"], artifact.artifact_sha256)

            own_anchor = options.copy()
            own_anchor[2] = str(root / "audit" / "authorization.json")
            own_anchor[-1] = str(root / "rejected.json")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(own_anchor), 2)
            self.assertFalse((root / "rejected.json").exists())

            audit_copy = root / "audit" / "authorization-copy.json"
            private_write(audit_copy, canonical_bytes(expected))
            copied_anchor = options.copy()
            copied_anchor[2] = str(audit_copy)
            copied_anchor[-1] = str(root / "copy-rejected.json")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(copied_anchor), 2)
            self.assertFalse((root / "copy-rejected.json").exists())

            hard_link = root / "authorization-hard-link.json"
            hard_link.hardlink_to(root / "audit" / "authorization.json")
            linked_anchor = options.copy()
            linked_anchor[2] = str(hard_link)
            linked_anchor[-1] = str(root / "link-rejected.json")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(linked_anchor), 2)
            self.assertFalse((root / "link-rejected.json").exists())

            audit_output = options.copy()
            audit_output[-1] = str(root / "audit" / "derived.json")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(audit_output), 2)
            self.assertFalse((root / "audit" / "derived.json").exists())

    async def test_result_set_cli_remains_incompatible_with_raw_results(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            critique = Critique(findings=())
            broker, expected, ledger = self._context(root, critique.model_dump_json())
            reply = BrokerReply(
                response=await broker.redeem(canonical_bytes(broker.claim()))
            )
            artifact = compile_brokered_evaluation(
                reply, expected, root / "audit", ledger
            )
            data, grid, gate = inputs()
            plan = make_plan(data, grid, 1, 0, gate)
            full_batch, _ = make_execution_batch(plan, data, "calibration", b"a" * 32)
            batch = ExecutionBatch(
                plan_sha256=full_batch.plan_sha256,
                requests=(full_batch.requests[0],),
            )
            authorization = artifact.authorization.model_copy(
                update={"batch_sha256": batch.batch_sha256}
            )
            artifact = artifact.model_copy(
                update={
                    "authorization": authorization,
                    "authorization_sha256": digest(canonical_bytes(authorization)),
                }
            )
            batch_path = root / "batch.json"
            artifact_path = root / "artifact.json"
            output_path = root / "brokered-results.json"
            private_write(batch_path, canonical_bytes(batch))
            private_write(artifact_path, canonical_bytes(artifact))
            options = [
                "eval-assemble-brokered-results",
                "--batch",
                str(batch_path),
                "--artifact",
                str(artifact_path),
                "--output",
                str(output_path),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(options), 0)
            event = json.loads(stdout.getvalue())
            self.assertEqual(event["type"], "evaluation.brokered_results.assembled")
            self.assertEqual(event["assignments"], 1)
            self.assertEqual(event["completed"], 1)
            self.assertEqual(event["errors"], 0)
            self.assertFalse(event["credentialed_conformance_proven"])
            self.assertFalse(event["live_raw_result_set_issued"])
            self.assertFalse(event["grading_authorized"])
            self.assertFalse(event["scoring_authorized"])
            self.assertFalse(event["retry_permitted"])
            self.assertFalse(event["automatic_budget_release_authorized"])
            result = BrokeredEvaluationResultSet.model_validate_json(
                output_path.read_bytes()
            )
            with self.assertRaises(ValidationError):
                RawResultSet.model_validate_json(canonical_bytes(result))

    async def test_exact_batch_result_set_preserves_failures_and_order(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            critique = Critique(findings=())
            broker, expected, ledger = self._context(root, critique.model_dump_json())
            reply = BrokerReply(
                response=await broker.redeem(canonical_bytes(broker.claim()))
            )
            base = compile_brokered_evaluation(reply, expected, root / "audit", ledger)
            data, grid, gate = inputs()
            plan = make_plan(data, grid, 1, 0, gate)
            batch, _ = make_execution_batch(plan, data, "calibration", b"a" * 32)
            artifacts: list[BrokeredEvaluationArtifact] = []
            for index, request_ in enumerate(batch.requests):
                authorization = base.authorization.model_copy(
                    update={
                        "sample_id": request_.sample_id,
                        "candidate_id": request_.route.candidate_id,
                        "evaluation_request_sha256": request_.request_sha256,
                        "provider_request_sha256": digest(
                            f"provider-request-{index}".encode()
                        ),
                        "ledger_entry_id": digest(f"ledger-entry-{index}".encode()),
                    }
                )
                changes: dict[str, object] = {
                    "authorization": authorization,
                    "authorization_sha256": digest(canonical_bytes(authorization)),
                    "outcome_sha256": digest(f"outcome-{index}".encode()),
                    "provider_response_sha256": digest(f"response-{index}".encode()),
                    "provider_request_id": f"response-{index}",
                }
                if index == len(batch.requests) - 1:
                    changes.update(
                        {
                            "status": "error",
                            "outcome_status": "failed",
                            "ledger_status": "uncertain",
                            "provider_response_sha256": None,
                            "provider_request_id": None,
                            "usage": None,
                            "critique": None,
                            "error": "provider_error",
                        }
                    )
                artifacts.append(base.model_copy(update=changes))

            result = compile_brokered_evaluation_result_set(
                batch, tuple(reversed(artifacts))
            )
            self.assertIsInstance(result, BrokeredEvaluationResultSet)
            self.assertEqual(
                tuple(item.authorization.sample_id for item in result.artifacts),
                tuple(item.sample_id for item in batch.requests),
            )
            self.assertEqual(result.artifacts[-1].status, "error")
            self.assertTrue(result.exact_batch_coverage_verified)
            self.assertTrue(result.failures_preserved)
            self.assertFalse(result.credentialed_conformance_proven)
            self.assertFalse(result.live_raw_result_set_issued)
            self.assertFalse(result.grading_authorized)
            self.assertFalse(result.scoring_authorized)
            self.assertFalse(result.retry_permitted)
            self.assertFalse(result.automatic_budget_release_authorized)
            self.assertFalse(result.promotion_eligible)

            with self.assertRaisesRegex(ValueError, "exactly cover"):
                compile_brokered_evaluation_result_set(batch, tuple(artifacts[:-1]))

            changed = artifacts[0].model_copy(
                update={
                    "authorization": artifacts[0].authorization.model_copy(
                        update={"candidate_id": "f" * 64}
                    )
                }
            )
            with self.assertRaises(ValueError):
                compile_brokered_evaluation_result_set(batch, (changed, *artifacts[1:]))
