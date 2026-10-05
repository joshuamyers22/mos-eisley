"""Synthetic G6-04 witnessed admission, rollback, cap and stop-race tests."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import (
    ModelRequest,
    TextBlock,
    ToolDefinition,
    ToolSchema,
    Turn,
)
from mos_eisley.evaluation.routing_activation import RoutingActivationAuthorityPolicy
from mos_eisley.run.activation_control import (
    AnchoredRoutingControl,
    RoutingControlAnchorPolicy,
)
from mos_eisley.run.exact_route import (
    ExactRouteRequirements,
    ExactRouteSelection,
)
from mos_eisley.run.routing_preflight import (
    RoutingRuntimePreflight,
    RoutingRuntimeSources,
)
from mos_eisley.run.routing_transaction import (
    InertRoutingResponse,
    InertRoutingTransport,
    OfflineExecutionProfile,
    OfflineOutcome,
    OfflineRoutingEnvelope,
    OfflineTransactionStore,
    SyntheticRoutingMonitor,
    execute_offline_witnessed_routing_transaction,
    inspect_offline_witnessed_transaction,
    offline_provider_options_sha256,
    offline_toolset_sha256,
)
from mos_eisley.run.witnessed_admission import (
    CohortBudgetPolicy,
    SignedCohortBudgetPolicy,
    SignedWitnessEnrollment,
    SyntheticAdmissionTrust,
    SyntheticCheckpointStore,
    SyntheticWitnessedAdmission,
    TaskSessionBinding,
    WitnessedAdmissionReceipt,
    WitnessedAttempt,
    WitnessEnrollment,
    sign_cohort_budget_policy,
    sign_witness_enrollment,
    verify_admission_receipt,
)
from tests import test_routing_runtime_preflight as runtime_module


def run_witnessed_bundle(bundle_path: str, cut_name: str) -> None:
    """Subprocess fault target that opens the same durable synthetic service."""
    root = Path(bundle_path).parent
    bundle = json.loads(Path(bundle_path).read_text())
    checkpoint = SyntheticCheckpointStore(root / "witness.checkpoint.sqlite")
    admission = SyntheticWitnessedAdmission(
        root / "witness.sqlite",
        checkpoint,
        SyntheticAdmissionTrust.model_validate_json(json.dumps(bundle["trust"])),
        RoutingControlAnchorPolicy.model_validate_json(
            json.dumps(bundle["anchor_policy"])
        ),
        RoutingActivationAuthorityPolicy.model_validate_json(
            json.dumps(bundle["activation_authorities"])
        ),
        bytes.fromhex(bundle["witness_private_key"]),
    )
    attempt = WitnessedAttempt.model_validate_json(json.dumps(bundle["attempt"]))
    control = AnchoredRoutingControl.model_validate_json(json.dumps(bundle["control"]))
    preflight = RoutingRuntimePreflight.model_validate_json(
        json.dumps(bundle["preflight"])
    )

    def kill_at(phase: str) -> None:
        if phase == cut_name:
            os._exit(77)

    admission.claim_with_budget(
        attempt=attempt,
        expected_control=control,
        current_preflight=preflight,
        now=preflight.checked_at,
        fault=kill_at,
    )


class WitnessedAdmissionTests(TestCase):
    def setUp(self) -> None:
        self.runtime = runtime_module.RoutingRuntimePreflightTests()
        self.runtime.setUp()
        self.addCleanup(self.runtime.doCleanups)
        self.activation = self.runtime.source
        self.root_sources = self.activation.source.source
        self.now = self.activation.now
        self.preflight = self.runtime.preflight()
        anchored = self.runtime.anchor.snapshot(self.activation.authority_policy).latest
        assert anchored is not None
        self.genesis = anchored
        frozen = self.root_sources.policy.decisions[0]
        self.features = next(
            assignment.features
            for assignment in self.root_sources.manifest.assignments
            if self.root_sources.sealed.protocol.feature_partition.profile(
                assignment.features
            ).profile_id
            == frozen.profile_id
        )
        assert frozen.selected_route is not None
        route = frozen.selected_route
        self.requirements = ExactRouteRequirements(
            role=frozen.role,
            output_contract=frozen.profile.output_contract,
            tool_requirements=frozen.profile.tool_requirements,
            requires_structured_output=True,
        )
        self.selection = ExactRouteSelection(
            candidate_id=route.candidate_id,
            route=route,
            profile_id=frozen.profile_id,
            role=frozen.role,
            source="calibrated_route",
            candidate_policy_sha256=self.root_sources.policy.candidate_policy_sha256,
            preflight_sha256=self.preflight.preflight_sha256,
            requirements_sha256=self.requirements.requirements_sha256,
            registry_sha256=route.registry_sha256,
            registry_verification="fixture",
        )
        tool = ToolDefinition(
            name="read-file",
            description="Read synthetic input",
            input_schema=ToolSchema(type="object"),
        )
        self.request = ModelRequest(
            provider=route.provider,
            model=route.model,
            effort=route.effort,
            system=route.prompt.instructions,
            tools=(tool,),
            turns=(Turn(role="user", blocks=(TextBlock(text="Synthetic task"),)),),
            max_output=1000,
            max_output_tokens=50,
        )
        self.profile = OfflineExecutionProfile(
            role=self.requirements.role,
            output_contract=self.requirements.output_contract,
            requires_structured_output=True,
            tool_names=self.requirements.tool_requirements,
            tools_sha256=offline_toolset_sha256(self.request.tools),
            provider_options_sha256=offline_provider_options_sha256(),
            max_context_bytes=10_000,
            max_output_bytes=1000,
            max_output_tokens=50,
            max_input_tokens=50,
            input_microusd_per_token=1,
            output_microusd_per_token=1,
        )
        promotion_root = self.activation.source
        self.sources = RoutingRuntimeSources(
            dataset=self.root_sources.dataset,
            plan=self.root_sources.plan,
            calibration=self.root_sources.calibration,
            holdout=self.root_sources.holdout,
            manifest=self.root_sources.manifest,
            sealed_study=self.root_sources.sealed,
            calibration_report=self.root_sources.calibration_report,
            candidate_policy=self.root_sources.policy,
            promotion_policy=self.root_sources.promotion_policy,
            claim=self.root_sources.claim(self.root_sources.holdout),
            holdout_report=promotion_root.report,
            promotion=self.activation.promotion,
            promotion_authorities=promotion_root.authority_policy,
            signed_activation_policy=self.activation.sign_policy(),
            signed_snapshot=self.activation.sign_snapshot(),
            signed_control=self.runtime.signed_control,
            activation_authorities=self.activation.authority_policy,
            eligibility=self.runtime.eligibility,
            control_anchor=self.runtime.anchor,
        )
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.operator_key = Ed25519PrivateKey.generate()
        self.budget_key = Ed25519PrivateKey.generate()
        self.witness_key = Ed25519PrivateKey.generate()
        self.trust = SyntheticAdmissionTrust(
            operator_id="operator-a",
            operator_public_key_hex=self.operator_key.public_key()
            .public_bytes_raw()
            .hex(),
            budget_id="budget-a",
            budget_public_key_hex=self.budget_key.public_key().public_bytes_raw().hex(),
        )
        self.budget_policy = CohortBudgetPolicy(
            owner_id="owner-a",
            cohort_id="cohort-a",
            tasks=(
                TaskSessionBinding(task_id="task-a", session_id="session-a"),
                TaskSessionBinding(task_id="task-b", session_id="session-a"),
                TaskSessionBinding(task_id="task-c", session_id="session-b"),
            ),
            valid_from=self.now - timedelta(minutes=1),
            valid_until=self.now + timedelta(minutes=10),
            task_ceiling_microusd=100,
            session_ceiling_microusd=150,
            cohort_ceiling_microusd=200,
            request_maximum_microusd=100,
            max_tasks=3,
            max_sessions=2,
            max_attempts=10,
            max_unresolved=10,
            execution_profile_sha256=self.profile.profile_sha256,
        )
        self.signed_budget = sign_cohort_budget_policy(
            self.budget_policy, "budget-a", self.budget_key.private_bytes_raw()
        )
        self.enrollment = WitnessEnrollment(
            epoch_id="1" * 64,
            witness_id="2" * 64,
            witness_public_key_hex=self.witness_key.public_key()
            .public_bytes_raw()
            .hex(),
            checkpoint_id="3" * 64,
            anchor_policy_sha256=self.activation.control_anchor_policy.policy_sha256,
            activation_authority_policy_sha256=self.activation.authority_policy.policy_sha256,
            genesis_entry_sha256=self.genesis.anchor_entry_sha256,
            genesis_sequence=self.genesis.signed_control.control.sequence,
            budget_policy_sha256=self.budget_policy.policy_sha256,
            owner_id="owner-a",
            cohort_id="cohort-a",
            valid_from=self.now - timedelta(minutes=1),
            valid_until=self.now + timedelta(minutes=10),
        )
        self.signed_enrollment = sign_witness_enrollment(
            self.enrollment, "operator-a", self.operator_key.private_bytes_raw()
        )
        self.admission = self.bootstrap()
        self.store = OfflineTransactionStore.create_witnessed(
            self.root / "transaction.sqlite", admission=self.admission
        )
        self.envelope = self.make_envelope()
        self.transport = self.make_transport()
        self.monitor = SyntheticRoutingMonitor()

    def bootstrap(
        self,
        *,
        path: Path | None = None,
        signed_enrollment: SignedWitnessEnrollment | None = None,
        signed_budget: SignedCohortBudgetPolicy | None = None,
        genesis: AnchoredRoutingControl | None = None,
    ) -> SyntheticWitnessedAdmission:
        target = path or self.root / "witness.sqlite"
        return SyntheticWitnessedAdmission.bootstrap(
            path=target,
            checkpoint_path=target.with_suffix(".checkpoint.sqlite"),
            signed_enrollment=signed_enrollment or self.signed_enrollment,
            signed_budget=signed_budget or self.signed_budget,
            trust=self.trust,
            genesis=genesis or self.genesis,
            anchor_policy=self.activation.control_anchor_policy,
            activation_authorities=self.activation.authority_policy,
            witness_private_key=self.witness_key.private_bytes_raw(),
            now=self.now,
        )

    def make_envelope(
        self,
        *,
        task_id: str = "task-a",
        session_id: str = "session-a",
        attempt_id: str = "attempt-a",
    ) -> OfflineRoutingEnvelope:
        return OfflineRoutingEnvelope(
            owner_id="owner-a",
            cohort_id="cohort-a",
            task_id=task_id,
            session_id=session_id,
            stage_id="stage-a",
            attempt_id=attempt_id,
            selection_sha256=digest(canonical_bytes(self.selection)),
            profile_sha256=self.profile.profile_sha256,
            request_sha256=digest(canonical_bytes(self.request)),
            control_sequence=self.genesis.signed_control.control.sequence,
            control_digest=self.genesis.anchor_entry_sha256,
            maximum_microusd=100,
        )

    def make_attempt(
        self, envelope: OfflineRoutingEnvelope | None = None
    ) -> WitnessedAttempt:
        item = envelope or self.envelope
        return WitnessedAttempt(
            attempt_key=item.attempt_key,
            owner_id=item.owner_id,
            cohort_id=item.cohort_id,
            task_id=item.task_id,
            session_id=item.session_id,
            stage_id=item.stage_id,
            attempt_id=item.attempt_id,
            envelope_sha256=item.envelope_sha256,
            request_sha256=item.request_sha256,
            selection_sha256=item.selection_sha256,
            profile_sha256=item.profile_sha256,
            candidate_id=self.selection.candidate_id,
            candidate_policy_sha256=self.selection.candidate_policy_sha256,
            promotion_receipt_sha256=self.preflight.promotion_receipt_sha256,
            preflight_sha256=self.preflight.preflight_sha256,
            control_sequence=item.control_sequence,
            control_anchor_entry_sha256=item.control_digest,
            maximum_microusd=item.maximum_microusd,
            budget_policy_sha256=self.budget_policy.policy_sha256,
        )

    def make_transport(
        self,
        *,
        response: InertRoutingResponse | None = None,
        error: BaseException | None = None,
    ) -> InertRoutingTransport:
        return InertRoutingTransport(
            provider=self.request.provider,
            backend=self.selection.route.backend,
            client_version=self.selection.route.client_version,
            response=response
            or InertRoutingResponse(
                provider=self.request.provider,
                model=self.request.model,
                service_tier="default",
                input_tokens=10,
                output_tokens=5,
                charged_microusd=15,
            ),
            error=error,
        )

    def claim(
        self,
        envelope: OfflineRoutingEnvelope | None = None,
        **changes: object,
    ) -> WitnessedAdmissionReceipt:
        values: dict[str, object] = {
            "attempt": self.make_attempt(envelope),
            "expected_control": self.genesis,
            "current_preflight": self.preflight,
            "now": self.now,
        }
        values.update(changes)
        return self.admission.claim_with_budget(**values)  # type: ignore[arg-type]

    def execute(self, **changes: object) -> OfflineOutcome:
        values: dict[str, object] = {
            "envelope": self.envelope,
            "selection": self.selection,
            "preflight": self.preflight,
            "requirements": self.requirements,
            "profile": self.profile,
            "request": self.request,
            "features": self.features,
            "sources": self.sources,
            "admission": self.admission,
            "store": self.store,
            "transport": self.transport,
            "monitor": self.monitor,
            "now": self.now,
        }
        values.update(changes)
        return asyncio.run(execute_offline_witnessed_routing_transaction(**values))  # type: ignore[arg-type]

    def stop_entry(self) -> AnchoredRoutingControl:
        stopped = self.activation.control.model_copy(
            update={
                "sequence": self.activation.control.sequence + 1,
                "issued_at": self.now + timedelta(seconds=1),
                "emergency_stop": True,
            }
        )
        signed = self.activation.sign_control(stopped)
        return AnchoredRoutingControl(
            anchor_id=self.genesis.anchor_id,
            previous_entry_sha256=self.genesis.anchor_entry_sha256,
            anchored_at=self.now + timedelta(seconds=1),
            signed_control=signed,
        )

    def bundle(
        self, envelope: OfflineRoutingEnvelope | None = None
    ) -> dict[str, object]:
        return {
            "trust": self.trust.model_dump(mode="json"),
            "anchor_policy": self.activation.control_anchor_policy.model_dump(
                mode="json"
            ),
            "activation_authorities": self.activation.authority_policy.model_dump(
                mode="json"
            ),
            "witness_private_key": self.witness_key.private_bytes_raw().hex(),
            "attempt": self.make_attempt(envelope).model_dump(mode="json"),
            "control": self.genesis.model_dump(mode="json"),
            "preflight": self.preflight.model_dump(mode="json"),
        }

    def run_processes(
        self, *bundles: dict[str, object], cut_name: str = "no_cut"
    ) -> list[int]:
        paths: list[Path] = []
        for index, bundle in enumerate(bundles):
            path = self.root / f"bundle-{index}.json"
            path.write_text(json.dumps(bundle))
            paths.append(path)
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import sys; from tests.test_witnessed_admission import "
                    "run_witnessed_bundle; "
                    "run_witnessed_bundle(sys.argv[1], sys.argv[2])",
                    str(path),
                    cut_name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for path in paths
        ]
        for process in processes:
            process.communicate(timeout=10)
        return [process.returncode for process in processes]

    def bootstrap_with_policy(
        self, policy: CohortBudgetPolicy, suffix: str
    ) -> SyntheticWitnessedAdmission:
        signed_budget = sign_cohort_budget_policy(
            policy, "budget-a", self.budget_key.private_bytes_raw()
        )
        enrollment = self.enrollment.model_copy(
            update={"budget_policy_sha256": policy.policy_sha256}
        )
        signed_enrollment = sign_witness_enrollment(
            enrollment, "operator-a", self.operator_key.private_bytes_raw()
        )
        return self.bootstrap(
            path=self.root / f"witness-{suffix}.sqlite",
            signed_enrollment=signed_enrollment,
            signed_budget=signed_budget,
        )

    def test_bootstrap_is_signed_and_nonresettable(self) -> None:
        state = self.admission.read_current()
        self.assertEqual((state.generation, len(state.attempts)), (0, 0))
        with self.assertRaises(FileExistsError):
            self.bootstrap()
        bad_genesis = self.genesis.model_copy(
            update={"previous_entry_sha256": "a" * 64}
        )
        with self.assertRaises(ValueError):
            self.bootstrap(path=self.root / "bad-genesis.sqlite", genesis=bad_genesis)
        bad_signed = self.signed_enrollment.model_copy(
            update={"signature_base64": self.signed_budget.signature_base64}
        )
        with self.assertRaises(ValueError):
            self.bootstrap(
                path=self.root / "bad-signer.sqlite", signed_enrollment=bad_signed
            )
        malformed_signed = self.signed_enrollment.model_copy(
            update={"signature_base64": "invalid*base64"}
        )
        with self.assertRaises(ValueError):
            self.bootstrap(
                path=self.root / "malformed-signer.sqlite",
                signed_enrollment=malformed_signed,
            )

    def test_happy_path_binds_full_preflight_claim_intent_and_budget(self) -> None:
        outcome = self.execute()
        self.assertEqual(outcome.status, "settled")  # type: ignore[attr-defined]
        status = inspect_offline_witnessed_transaction(
            self.envelope, self.admission, self.store
        )
        self.assertEqual((status.phase, status.budget_status), ("finished", "settled"))
        totals = self.admission.inspect_scopes(
            owner_id="owner-a",
            cohort_id="cohort-a",
            task_id="task-a",
            session_id="session-a",
        )
        self.assertEqual(
            (
                totals.task_charged_microusd,
                totals.session_charged_microusd,
                totals.cohort_charged_microusd,
            ),
            (15, 15, 15),
        )
        self.assertEqual(len(self.transport.entries), 1)
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(len(self.transport.entries), 1)

    def test_stop_before_and_after_admission(self) -> None:
        stopped = self.stop_entry()
        self.admission.advance_control(stopped, self.now + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            self.claim()
        self.assertEqual(self.admission.read_current().attempts, ())

    def test_stop_after_admission_abandons_unsent_intent(self) -> None:
        stopped = self.stop_entry()

        def cut(phase: str) -> None:
            if phase == "after_admission":
                self.admission.advance_control(stopped, self.now + timedelta(seconds=1))

        outcome = self.execute(fault=cut)
        self.assertEqual(outcome.status, "abandoned")  # type: ignore[attr-defined]
        self.assertEqual(self.transport.entries, [])
        status = inspect_offline_witnessed_transaction(
            self.envelope, self.admission, self.store
        )
        self.assertEqual((status.phase, status.budget_status), ("finished", "held"))
        with self.assertRaises(ValueError):
            self.claim(self.make_envelope(task_id="task-b", attempt_id="attempt-b"))

    def test_stop_after_final_check_allows_one_claimed_entry(self) -> None:
        stopped = self.stop_entry()

        def cut(phase: str) -> None:
            if phase == "after_final_check":
                self.admission.advance_control(stopped, self.now + timedelta(seconds=1))

        outcome = self.execute(fault=cut)
        self.assertEqual(outcome.status, "settled")  # type: ignore[attr-defined]
        self.assertEqual(len(self.transport.entries), 1)

    def test_budget_caps_and_settlement_savings(self) -> None:
        first = self.claim()
        second = self.make_envelope(task_id="task-b", attempt_id="attempt-b")
        with self.assertRaises(ValueError):
            self.claim(second)
        self.admission.settle_exact(
            receipt=first, charged_microusd=10, status="settled", now=self.now
        )  # type: ignore[arg-type]
        admitted = self.claim(second)
        self.assertEqual(admitted.reserved_microusd, 100)  # type: ignore[attr-defined]
        totals = self.admission.inspect_scopes(
            owner_id="owner-a",
            cohort_id="cohort-a",
            task_id="task-b",
            session_id="session-a",
        )
        self.assertEqual(
            (
                totals.task_charged_microusd,
                totals.session_charged_microusd,
                totals.cohort_charged_microusd,
            ),
            (100, 110, 110),
        )

    def test_rollback_of_witness_database_is_detected_by_checkpoint(self) -> None:
        old_copy = self.root / "old-witness.sqlite"
        shutil.copyfile(self.admission.path, old_copy)
        self.claim()
        shutil.copyfile(old_copy, self.admission.path)
        with self.assertRaisesRegex(ValueError, "checkpoint mismatch"):
            self.admission.read_current()
        with self.assertRaises(ValueError):
            self.claim(self.make_envelope(task_id="task-b", attempt_id="attempt-b"))

    def test_checkpoint_outage_after_journal_commit_halts_admission(self) -> None:
        with (
            patch.object(
                self.admission.checkpoint,
                "compare_and_swap",
                side_effect=TimeoutError("synthetic checkpoint outage"),
            ),
            self.assertRaises(TimeoutError),
        ):
            self.claim()
        with self.assertRaisesRegex(ValueError, "checkpoint mismatch"):
            self.admission.read_current()
        self.assertEqual(self.transport.entries, [])

    def test_cross_owner_and_unenrolled_session_deny(self) -> None:
        with self.assertRaises(ValueError):
            self.admission.inspect_attempt(
                owner_id="owner-b",
                cohort_id="cohort-a",
                attempt_key=self.envelope.attempt_key,
            )
        wrong = self.make_envelope(task_id="task-b", session_id="session-b")
        with self.assertRaises(ValueError):
            self.claim(wrong)
        self.assertEqual(self.admission.read_current().attempts, ())

    def test_each_cap_denies_atomically_and_equality_admits(self) -> None:
        for scope in ("task", "session", "cohort"):
            with self.subTest(scope=scope):
                policy = self.budget_policy.model_copy(
                    update={f"{scope}_ceiling_microusd": 99}
                )
                admission = self.bootstrap_with_policy(policy, scope)
                attempt = self.make_attempt().model_copy(
                    update={"budget_policy_sha256": policy.policy_sha256}
                )
                with self.assertRaisesRegex(ValueError, "scope exhausted"):
                    admission.claim_with_budget(
                        attempt=attempt,
                        expected_control=self.genesis,
                        current_preflight=self.preflight,
                        now=self.now,
                    )
                self.assertEqual(
                    (
                        admission.read_current().generation,
                        len(admission.read_current().attempts),
                    ),
                    (0, 0),
                )
        receipt = self.claim()
        self.assertEqual(receipt.reserved_microusd, 100)

    def test_uncertain_exposure_and_violation_block_fresh_claims(self) -> None:
        receipt = self.claim()
        self.admission.settle_exact(
            receipt=receipt,
            charged_microusd=100,
            status="uncertain",
            now=self.now,
        )
        with self.assertRaises(ValueError):
            self.claim(self.make_envelope(task_id="task-b", attempt_id="attempt-b"))
        totals = self.admission.inspect_scopes(
            owner_id="owner-a",
            cohort_id="cohort-a",
            task_id="task-a",
            session_id="session-a",
        )
        self.assertEqual(totals.session_charged_microusd, 100)
        self.assertEqual(totals.unresolved_entries, 1)

        alternate = self.bootstrap_with_policy(self.budget_policy, "violation")
        attempt = self.make_attempt()
        receipt_two = alternate.claim_with_budget(
            attempt=attempt,
            expected_control=self.genesis,
            current_preflight=self.preflight,
            now=self.now,
        )
        alternate.settle_exact(
            receipt=receipt_two,
            charged_microusd=100,
            status="violation",
            now=self.now,
        )
        other = self.make_attempt(
            self.make_envelope(
                task_id="task-c", session_id="session-b", attempt_id="attempt-c"
            )
        )
        with self.assertRaisesRegex(ValueError, "ineligible"):
            alternate.claim_with_budget(
                attempt=other,
                expected_control=self.genesis,
                current_preflight=self.preflight,
                now=self.now,
            )

    def test_witness_control_ahead_of_local_anchor_denies_before_claim(self) -> None:
        self.admission.advance_control(
            self.stop_entry(), self.now + timedelta(seconds=1)
        )
        with self.assertRaisesRegex(ValueError, "latest control mismatch"):
            self.execute()
        self.assertEqual(len(self.admission.read_current().attempts), 0)
        self.assertEqual(self.transport.entries, [])

    def test_checkpoint_rollback_and_witness_outage_deny(self) -> None:
        checkpoint_path = self.admission.checkpoint.path
        old_copy = self.root / "old-checkpoint.sqlite"
        shutil.copyfile(checkpoint_path, old_copy)
        self.claim()
        shutil.copyfile(old_copy, checkpoint_path)
        with self.assertRaisesRegex(ValueError, "checkpoint mismatch"):
            self.admission.read_current()
        with self.assertRaises(ValueError):
            self.claim(self.make_envelope(task_id="task-b", attempt_id="attempt-b"))

    def test_cloned_witness_writer_cannot_advance_same_checkpoint(self) -> None:
        clone_path = self.root / "clone.sqlite"
        clone_lock = self.root / "clone.lock"
        shutil.copyfile(self.admission.path, clone_path)
        shutil.copyfile(self.admission.lock_path, clone_lock)
        clone_path.chmod(0o600)
        clone_lock.chmod(0o600)
        clone = SyntheticWitnessedAdmission(
            clone_path,
            self.admission.checkpoint,
            self.trust,
            self.activation.control_anchor_policy,
            self.activation.authority_policy,
            self.witness_key.private_bytes_raw(),
        )
        self.claim()
        other = self.make_attempt(
            self.make_envelope(task_id="task-b", attempt_id="attempt-b")
        )
        with self.assertRaisesRegex(ValueError, "checkpoint mismatch"):
            clone.claim_with_budget(
                attempt=other,
                expected_control=self.genesis,
                current_preflight=self.preflight,
                now=self.now,
            )
        self.assertEqual(len(self.admission.read_current().attempts), 1)

    def test_copied_local_intent_store_cannot_reclaim_witnessed_attempt(self) -> None:
        old_copy = self.root / "old-transaction.sqlite"
        shutil.copyfile(self.store.path, old_copy)
        self.execute()
        shutil.copyfile(old_copy, self.store.path)
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(len(self.transport.entries), 1)

    def test_process_kills_preserve_exact_checkpoint_boundary(self) -> None:
        for cut, generation, count, readable in (
            ("before_db_commit", 0, 0, True),
            ("after_db_commit", 1, 1, False),
            ("after_checkpoint", 1, 1, True),
            ("before_receipt", 1, 1, True),
        ):
            with self.subTest(cut=cut):
                admission = self.bootstrap_with_policy(
                    self.budget_policy, f"kill-{cut}"
                )
                bundle = self.bundle()
                bundle_path = admission.path.with_name("bundle-" + cut + ".json")
                bundle_path.write_text(json.dumps(bundle))
                # The process helper uses fixed names; create a private case directory.
                case_dir = self.root / f"case-{cut}"
                case_dir.mkdir()
                shutil.copyfile(admission.path, case_dir / "witness.sqlite")
                shutil.copyfile(admission.lock_path, case_dir / "witness.lock")
                shutil.copyfile(
                    admission.checkpoint.path, case_dir / "witness.checkpoint.sqlite"
                )
                for filename in (
                    "witness.sqlite",
                    "witness.lock",
                    "witness.checkpoint.sqlite",
                ):
                    (case_dir / filename).chmod(0o600)
                case_bundle = case_dir / "bundle.json"
                case_bundle.write_text(json.dumps(bundle))
                command = [
                    sys.executable,
                    "-c",
                    "import sys; from tests.test_witnessed_admission import "
                    "run_witnessed_bundle; "
                    "run_witnessed_bundle(sys.argv[1], sys.argv[2])",
                    str(case_bundle),
                    cut,
                ]
                result = subprocess.run(command, capture_output=True, check=False)
                self.assertEqual(result.returncode, 77, result.stderr.decode())
                copied = (
                    SyntheticWitnessedAdmission(
                        case_dir / "witness.sqlite",
                        SyntheticCheckpointStore(
                            case_dir / "witness.checkpoint.sqlite"
                        ),
                        self.trust,
                        self.activation.control_anchor_policy,
                        self.activation.authority_policy,
                        self.witness_key.private_bytes_raw(),
                    )
                    if readable
                    else None
                )
                if readable:
                    assert copied is not None
                    state = copied.read_current()
                    self.assertEqual(
                        (state.generation, len(state.attempts)), (generation, count)
                    )
                else:
                    with self.assertRaisesRegex(ValueError, "checkpoint mismatch"):
                        SyntheticWitnessedAdmission(
                            case_dir / "witness.sqlite",
                            SyntheticCheckpointStore(
                                case_dir / "witness.checkpoint.sqlite"
                            ),
                            self.trust,
                            self.activation.control_anchor_policy,
                            self.activation.authority_policy,
                            self.witness_key.private_bytes_raw(),
                        )

    def test_two_processes_claim_one_attempt_and_compete_for_scope(self) -> None:
        codes = self.run_processes(self.bundle(), self.bundle())
        self.assertEqual(sorted(codes), [0, 1])
        self.assertEqual(len(self.admission.read_current().attempts), 1)

        alternate = self.bootstrap_with_policy(self.budget_policy, "compete")
        # The helper uses the default filename, so run competing tasks in a case dir.
        case_dir = self.root / "compete-case"
        case_dir.mkdir()
        shutil.copyfile(alternate.path, case_dir / "witness.sqlite")
        shutil.copyfile(alternate.lock_path, case_dir / "witness.lock")
        shutil.copyfile(
            alternate.checkpoint.path, case_dir / "witness.checkpoint.sqlite"
        )
        for filename in ("witness.sqlite", "witness.lock", "witness.checkpoint.sqlite"):
            (case_dir / filename).chmod(0o600)
        first = self.bundle(
            self.make_envelope(task_id="task-a", attempt_id="attempt-a")
        )
        second = self.bundle(
            self.make_envelope(task_id="task-b", attempt_id="attempt-b")
        )
        commands: list[list[str]] = []
        for index, bundle in enumerate((first, second)):
            path = case_dir / f"bundle-{index}.json"
            path.write_text(json.dumps(bundle))
            commands.append(
                [
                    sys.executable,
                    "-c",
                    "import sys; from tests.test_witnessed_admission import "
                    "run_witnessed_bundle; "
                    "run_witnessed_bundle(sys.argv[1], sys.argv[2])",
                    str(path),
                    "no_cut",
                ]
            )
        processes = [
            subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for cmd in commands
        ]
        for process in processes:
            process.communicate(timeout=10)
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1])
        copied = SyntheticWitnessedAdmission(
            case_dir / "witness.sqlite",
            SyntheticCheckpointStore(case_dir / "witness.checkpoint.sqlite"),
            self.trust,
            self.activation.control_anchor_policy,
            self.activation.authority_policy,
            self.witness_key.private_bytes_raw(),
        )
        self.assertEqual(len(copied.read_current().attempts), 1)

    def test_broker_cuts_after_admission_and_intent_never_retry(self) -> None:
        for cut, phase in (
            ("after_admission", "claimed"),
            ("after_intent", "intent"),
        ):
            with self.subTest(cut=cut):
                fixture = WitnessedAdmissionTests()
                fixture.setUp()
                try:

                    def stop_at(current: str, target: str = cut) -> None:
                        if current == target:
                            raise OSError("synthetic broker crash")

                    with self.assertRaises(OSError):
                        fixture.execute(fault=stop_at)
                    status = inspect_offline_witnessed_transaction(
                        fixture.envelope, fixture.admission, fixture.store
                    )
                    self.assertEqual(
                        (status.phase, status.budget_status), (phase, "held")
                    )
                    with self.assertRaises(ValueError):
                        fixture.execute()
                    self.assertEqual(fixture.transport.entries, [])
                finally:
                    fixture.doCleanups()

    def test_receipt_tamper_and_attempt_mutation_deny(self) -> None:
        receipt = self.claim()
        verify_admission_receipt(
            receipt, self.enrollment, self.make_attempt(), self.now
        )
        changed = receipt.model_copy(update={"reserved_microusd": 1})
        with self.assertRaises(ValueError):
            verify_admission_receipt(
                changed, self.enrollment, self.make_attempt(), self.now
            )
        with self.assertRaises(ValueError):
            self.claim(self.envelope.model_copy(update={"request_sha256": "f" * 64}))

    def test_timeout_violation_and_outcome_write_failure(self) -> None:
        self.transport = self.make_transport(error=TimeoutError("synthetic"))
        outcome = self.execute()
        self.assertEqual(outcome.status, "uncertain")
        row = self.admission.inspect_attempt(
            owner_id="owner-a",
            cohort_id="cohort-a",
            attempt_key=self.envelope.attempt_key,
        )
        assert row is not None
        self.assertEqual((row.status, row.charged_microusd), ("uncertain", 100))

    def test_invalid_price_blocks_cohort_and_retains_full_exposure(self) -> None:
        self.transport = self.make_transport(
            response=InertRoutingResponse(
                provider=self.request.provider,
                model=self.request.model,
                service_tier="default",
                input_tokens=10,
                output_tokens=5,
                charged_microusd=1,
            )
        )
        outcome = self.execute()
        self.assertEqual(outcome.status, "violation")
        totals = self.admission.inspect_scopes(
            owner_id="owner-a",
            cohort_id="cohort-a",
            task_id="task-a",
            session_id="session-a",
        )
        self.assertEqual(totals.cohort_charged_microusd, 100)
        self.assertTrue(totals.blocked)
        with self.assertRaises(ValueError):
            self.claim(
                self.make_envelope(
                    task_id="task-c", session_id="session-b", attempt_id="attempt-c"
                )
            )

    def test_checkpointed_settlement_survives_local_outcome_write_failure(self) -> None:
        with (
            patch.object(self.store, "finish", side_effect=OSError("synthetic fsync")),
            self.assertRaises(OSError),
        ):
            self.execute()
        status = inspect_offline_witnessed_transaction(
            self.envelope, self.admission, self.store
        )
        self.assertEqual((status.phase, status.budget_status), ("intent", "settled"))
        self.assertEqual(len(self.transport.entries), 1)

    def test_settlement_checkpoint_failure_halts_without_retry(self) -> None:
        original = self.admission.checkpoint.compare_and_swap
        calls = 0

        def fail_second(previous: object, successor: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise TimeoutError("synthetic settlement checkpoint outage")
            original(previous, successor)  # type: ignore[arg-type]

        with (
            patch.object(self.admission.checkpoint, "compare_and_swap", fail_second),
            self.assertRaises(TimeoutError),
        ):
            self.execute()
        self.assertEqual(len(self.transport.entries), 1)
        stored = self.store.get(self.envelope.attempt_key)
        assert stored is not None
        self.assertIsNone(stored[1])
        with self.assertRaisesRegex(ValueError, "checkpoint mismatch"):
            self.admission.read_current()

    def test_stale_preflight_and_fabricated_selection_deny_before_claim(self) -> None:
        with self.assertRaises(ValueError):
            self.execute(now=self.preflight.valid_until)
        changed_selection = self.selection.model_copy(update={"profile_id": "f" * 64})
        changed_envelope = self.envelope.model_copy(
            update={"selection_sha256": digest(canonical_bytes(changed_selection))}
        )
        with self.assertRaisesRegex(ValueError, "source-bound"):
            self.execute(selection=changed_selection, envelope=changed_envelope)
        self.assertEqual(self.admission.read_current().attempts, ())

    def test_monitor_and_checkpoint_outage_at_final_read_abandon(self) -> None:
        def lose_monitor(phase: str) -> None:
            if phase == "after_intent":
                self.monitor.healthy = False

        outcome = self.execute(fault=lose_monitor)
        self.assertEqual(outcome.status, "abandoned")
        self.assertEqual(self.transport.entries, [])

    def test_checkpoint_outage_at_final_read_abandons_unsent_attempt(self) -> None:
        patcher = patch.object(
            self.admission.checkpoint,
            "read_current",
            side_effect=TimeoutError("synthetic final read outage"),
        )

        def lose_checkpoint(phase: str) -> None:
            if phase == "after_intent":
                patcher.start()

        try:
            outcome = self.execute(fault=lose_checkpoint)
        finally:
            patcher.stop()
        self.assertEqual(outcome.status, "abandoned")
        self.assertEqual(self.transport.entries, [])
        status = inspect_offline_witnessed_transaction(
            self.envelope, self.admission, self.store
        )
        self.assertEqual((status.phase, status.budget_status), ("finished", "held"))
