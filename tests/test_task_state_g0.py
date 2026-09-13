"""G0 contract, diagnostic, private replay, and compatibility acceptance tests."""

import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

from mos_eisley.core.models import ReviewPolicy, canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.recorded import RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.run import task_state_store
from mos_eisley.run.store import Manifest, load_run, save_run
from mos_eisley.run.task_state_store import (
    ProfileAssessment,
    TaskStateBundle,
    TaskStateManifest,
    load_task_state,
    save_task_state,
)
from mos_eisley.task_profile import (
    InstructionProfileEntry,
    ProfileSizes,
    TaskProfileManifest,
    ToolProfileEntry,
    diagnose_task_profile,
)
from mos_eisley.task_state import (
    ArtifactReference,
    BoundedEvidenceView,
    CheckpointOmission,
    CheckpointView,
    ClauseRecord,
    ContextInputBreakdown,
    ContinuationSelection,
    DecisionRecord,
    EvidenceReference,
    EvidenceRequirement,
    InputReference,
    MilestoneCheckpoint,
    OmittedRange,
    OutcomeRecord,
    OwnerProjectScope,
    PartialTotal,
    RequestContextMetric,
    ResourceCeiling,
    ResourceLedger,
    VerificationRecord,
    WorkspaceState,
    WorkUnitRecord,
    accumulate_context_metrics,
    validate_continuation,
    verify_bounded_evidence,
)


def hashed(value: str) -> str:
    return digest(value.encode("utf-8"))


class G0Fixture(NamedTuple):
    scope: OwnerProjectScope
    artifact_payload: bytes
    artifact: ArtifactReference
    evidence_view: BoundedEvidenceView
    clause: ClauseRecord
    decision: DecisionRecord
    completed_work: WorkUnitRecord
    queued_work: WorkUnitRecord
    checkpoint: MilestoneCheckpoint
    profile: TaskProfileManifest
    bundle: TaskStateBundle


def g0_fixture() -> G0Fixture:
    scope = OwnerProjectScope(
        owner_uid=os.getuid(),
        project_id="mos-eisley",
        workspace_sha256=hashed("workspace identity"),
    )
    artifact_payload = b"8 tests passed\n"
    artifact = ArtifactReference(
        artifact_id="g0-tests",
        sha256=digest(artifact_payload),
        bytes=len(artifact_payload),
        media_type="text/plain",
        availability="available",
        freshness="current",
    )
    evidence_view = BoundedEvidenceView(
        scope=scope,
        operation_id="g0-test-run",
        workspace_revision="fixture-tree-1",
        source_stream="stdout",
        exit_status=0,
        stdout_sha256=digest(artifact_payload),
        original_bytes=len(artifact_payload),
        visible_bytes=len(artifact_payload),
        original_lines=1,
        visible_lines=1,
        encoding="utf-8",
        content=artifact_payload.decode("utf-8"),
        full_artifact=artifact,
        reduction_policy="identity",
        reduction_version=1,
        complete=True,
    )
    clause_text = "G0 records and deterministic negative fixtures must replay."
    clause = ClauseRecord(
        scope=scope,
        clause_id="g0-exit",
        revision=1,
        plan_sha256=hashed("plan revision"),
        source_location="docs/mos-eisley-plan.md#26.4",
        text=clause_text,
        text_sha256=hashed(clause_text),
    )
    decision = DecisionRecord(
        scope=scope,
        decision_id="g0-scope",
        revision=1,
        statement="Implement contracts and offline checks only.",
        rationale="G1 runtime behavior is outside the selected milestone.",
        source_sha256=hashed("user direction"),
        authority="user",
        authorized_by="josh",
    )
    required_input = InputReference(
        input_id="project-plan",
        sha256=hashed("plan revision"),
        availability="available",
        freshness="current",
    )
    evidence = EvidenceReference(
        evidence_id="focused-tests",
        artifact=artifact,
        kind="verification",
        verification_status="passed",
        satisfies=("tests-pass",),
        view=evidence_view,
    )
    ledger = ResourceLedger(
        input_bytes=1200,
        output_bytes=800,
        attempts=1,
        review_rounds=1,
    )
    ceiling = ResourceCeiling(
        input_bytes=20_000,
        output_bytes=20_000,
        cost_microusd=0,
        attempts=8,
        correction_cycles=3,
        review_rounds=3,
    )
    outcome = OutcomeRecord(
        scope=scope,
        outcome_id="g0-contract-outcome",
        revision=1,
        work_unit_id="g0-contracts",
        work_unit_revision=1,
        status="completed",
        summary="G0 contracts pass their focused acceptance tests.",
        reason="Required offline verification passed.",
        evidence_ids=(evidence.evidence_id,),
    )
    completed_work = WorkUnitRecord(
        scope=scope,
        work_unit_id="g0-contracts",
        revision=1,
        objective="Freeze and verify the G0 contracts.",
        component_scope=("task contracts", "offline replay"),
        interfaces=("task-state", "task-profile"),
        applicable_clauses=(clause.reference,),
        origin_direction_sha256=hashed("user direction"),
        policy_sha256=hashed("trusted policy"),
        required_inputs=(required_input,),
        evidence_requirements=(
            EvidenceRequirement(
                requirement_id="tests-pass",
                description="Focused G0 acceptance tests pass.",
            ),
        ),
        evidence=(evidence,),
        stopping_condition="Stop after the G0 gate passes; do not begin G1.",
        resource_ceiling=ceiling,
        ledger=ledger,
        status="completed",
        terminal_reason=outcome.reason,
        outcome=outcome,
    )
    queued_work = WorkUnitRecord(
        scope=scope,
        work_unit_id="g1-runtime",
        revision=1,
        dependencies=(completed_work.reference,),
        objective="Connect bounded task state to runtime continuation.",
        component_scope=("conversation controller",),
        interfaces=("conversation",),
        applicable_clauses=(clause.reference,),
        origin_direction_sha256=hashed("plan direction"),
        policy_sha256=hashed("trusted policy"),
        required_inputs=(required_input,),
        stopping_condition="Stop at the G1 acceptance gate.",
        resource_ceiling=ceiling,
        status="queued",
    )
    context_requests = (
        RequestContextMetric(
            request_id="g0-author-1",
            ordinal=1,
            purpose="author",
            local_input_bytes=1200,
            local_input_breakdown=ContextInputBreakdown(
                system_instruction_bytes=200,
                tool_schema_bytes=300,
                project_guidance_bytes=200,
                conversation_bytes=400,
                tool_output_bytes=100,
            ),
            admitted=True,
            provider_usage="confirmed",
            provider_input_tokens=300,
            cached_input_tokens=100,
            provider_output_tokens=50,
            latency_milliseconds=100,
            substantial_tool_calls=2,
        ),
        RequestContextMetric(
            request_id="g0-review-1",
            ordinal=2,
            purpose="review",
            local_input_bytes=900,
            local_input_breakdown=ContextInputBreakdown(
                system_instruction_bytes=200,
                tool_schema_bytes=300,
                project_guidance_bytes=200,
                conversation_bytes=200,
            ),
            admitted=True,
        ),
        RequestContextMetric(
            request_id="g0-handoff-1",
            ordinal=3,
            purpose="handoff",
            local_input_bytes=100,
            local_input_breakdown=ContextInputBreakdown(
                project_guidance_bytes=50,
                checkpoint_bytes=50,
            ),
            handoff_revalidation_input_bytes=100,
            admitted=True,
        ),
    )
    metrics = accumulate_context_metrics(context_requests)
    workspace = WorkspaceState(
        repository_sha256=hashed("repository"),
        branch="docs/session-shape-lifecycle",
        revision="fixture-tree-1",
        tree_sha256=hashed("tree"),
        dirty_state_sha256=hashed("dirty state"),
    )
    checkpoint = MilestoneCheckpoint(
        scope=scope,
        checkpoint_id="g0-checkpoint",
        revision=1,
        objective="Complete G0 only.",
        current_work_unit=completed_work.reference,
        workspace=workspace,
        main_files=("src/mos_eisley/task_state.py",),
        active_decisions=(decision.reference,),
        completed_outcomes=(outcome.reference,),
        verifications=(
            VerificationRecord(
                verification_id="focused-tests",
                command="python -m unittest tests.test_task_state_g0",
                status="passed",
                bound_workspace_sha256=workspace.sha256,
                bound_input_sha256=workspace.dirty_state_sha256,
                result=artifact,
            ),
        ),
        next_actions=(queued_work.reference,),
        outstanding_work=(queued_work.reference,),
        view=CheckpointView(
            summary="G0 is complete; G1 remains queued and was not started.",
            included_record_ids=(queued_work.work_unit_id,),
            complete=True,
        ),
        context_metrics=metrics,
        task_ledger=ledger,
        lineage_sha256=hashed("g0 lineage"),
    )
    instruction = InstructionProfileEntry(
        rule_id="private-records",
        source_sha256=hashed("guidance source"),
        content_sha256=hashed("keep records private"),
        bytes=200,
        scope="all task-state persistence",
        required=True,
        selected=True,
        selection_reason="Required by the G0 owner-boundary gate.",
        location="root",
        classification="stable_rule",
    )
    tool = ToolProfileEntry(
        tool_id="bounded-file-read",
        schema_sha256=hashed("bounded file schema"),
        schema_bytes=300,
        required=True,
        selected=True,
        authorized=True,
        availability="available",
        selection_reason="Required to replay bounded private artifacts.",
    )
    profile = TaskProfileManifest(
        scope=scope,
        profile_id="g0-offline",
        work_unit=completed_work.reference,
        policy_sha256=hashed("trusted policy"),
        instructions=(instruction,),
        tools=(tool,),
        sizes=ProfileSizes(
            root_instruction_bytes=200,
            instruction_bytes=200,
            tool_schema_bytes=300,
            total_bytes=500,
        ),
    )
    assessment = ProfileAssessment(
        manifest=profile,
        report=diagnose_task_profile(profile),
    )
    bundle = TaskStateBundle(
        scope=scope,
        revision=1,
        clauses=(clause,),
        decisions=(decision,),
        outcomes=(outcome,),
        work_units=(completed_work, queued_work),
        checkpoint=checkpoint,
        context_requests=context_requests,
        context_metrics=metrics,
        profiles=(assessment,),
    )
    return G0Fixture(
        scope=scope,
        artifact_payload=artifact_payload,
        artifact=artifact,
        evidence_view=evidence_view,
        clause=clause,
        decision=decision,
        completed_work=completed_work,
        queued_work=queued_work,
        checkpoint=checkpoint,
        profile=profile,
        bundle=bundle,
    )


class TaskContractTests(TestCase):
    def test_clause_identity_and_work_unit_completion_are_fail_closed(self) -> None:
        fixture = g0_fixture()
        changed_clause = fixture.clause.model_dump()
        changed_clause["text"] = "substituted clause"
        with self.assertRaisesRegex(ValidationError, "text does not match"):
            ClauseRecord.model_validate(changed_clause)

        failed = fixture.completed_work.model_dump()
        failed_evidence = failed["evidence"][0]
        assert isinstance(failed_evidence, dict)
        failed_evidence["verification_status"] = "failed"
        failed_evidence["view"] = None
        with self.assertRaisesRegex(ValidationError, "lacks current evidence"):
            WorkUnitRecord.model_validate(failed)

        stale_input = fixture.completed_work.model_dump()
        required_input = stale_input["required_inputs"][0]
        assert isinstance(required_input, dict)
        required_input["freshness"] = "stale"
        with self.assertRaisesRegex(ValidationError, "required current input"):
            WorkUnitRecord.model_validate(stale_input)

    def test_bounded_views_disclose_loss_and_unavailable_originals(self) -> None:
        fixture = g0_fixture()
        hidden_loss = fixture.evidence_view.model_dump()
        hidden_loss["visible_bytes"] = fixture.artifact.bytes - 1
        hidden_loss["content"] = fixture.artifact_payload[1:].decode("utf-8")
        with self.assertRaisesRegex(ValidationError, "disclose omitted ranges"):
            BoundedEvidenceView.model_validate(hidden_loss)

        unavailable = fixture.evidence_view.model_dump()
        full_artifact = unavailable["full_artifact"]
        assert isinstance(full_artifact, dict)
        full_artifact["availability"] = "missing"
        with self.assertRaisesRegex(ValidationError, "cannot be complete"):
            BoundedEvidenceView.model_validate(unavailable)

        disclosed = fixture.evidence_view.model_copy(
            update={
                "visible_bytes": fixture.artifact.bytes - 1,
                "content": fixture.artifact_payload[1:].decode("utf-8"),
                "complete": False,
                "omissions": (
                    OmittedRange(
                        stream="stdout",
                        start=0,
                        end=1,
                        reason="Bounded fixture excerpt.",
                    ),
                ),
            }
        )
        self.assertFalse(
            BoundedEvidenceView.model_validate(disclosed.model_dump()).complete
        )
        verify_bounded_evidence(disclosed, fixture.artifact_payload)
        with self.assertRaisesRegex(ValueError, "does not match its reference"):
            verify_bounded_evidence(disclosed, b"substituted")

    def test_checkpoint_preserves_and_discloses_omitted_outstanding_work(self) -> None:
        fixture = g0_fixture()
        third = fixture.queued_work.model_copy(
            update={"work_unit_id": "g1-followup", "dependencies": ()}
        )
        invalid = fixture.checkpoint.model_dump()
        invalid["outstanding_work"] = (
            fixture.queued_work.reference.model_dump(),
            third.reference.model_dump(),
        )
        with self.assertRaisesRegex(ValidationError, "disclose every omitted"):
            MilestoneCheckpoint.model_validate(invalid)
        invalid["view"] = CheckpointView(
            summary="One follow-up is outside the short next-action view.",
            included_record_ids=(fixture.queued_work.work_unit_id,),
            omissions=(
                CheckpointOmission(
                    kind="work_unit",
                    record_id=third.work_unit_id,
                    reason="Outside the three-item next-action view.",
                ),
            ),
            complete=False,
        ).model_dump()
        self.assertEqual(
            len(MilestoneCheckpoint.model_validate(invalid).outstanding_work), 2
        )
        wrong_revision = fixture.checkpoint.model_copy(
            update={
                "next_actions": (
                    fixture.queued_work.reference.model_copy(update={"revision": 2}),
                )
            }
        )
        with self.assertRaisesRegex(ValidationError, "remain in outstanding work"):
            MilestoneCheckpoint.model_validate(wrong_revision.model_dump())
        stale_verification = fixture.checkpoint.model_copy(
            update={
                "verifications": (
                    fixture.checkpoint.verifications[0].model_copy(
                        update={"bound_workspace_sha256": hashed("older workspace")}
                    ),
                )
            }
        )
        with self.assertRaisesRegex(ValidationError, "stale passing verification"):
            MilestoneCheckpoint.model_validate(stale_verification.model_dump())

    def test_cumulative_metrics_preserve_unknown_provider_usage(self) -> None:
        metrics = g0_fixture().checkpoint.context_metrics
        self.assertEqual(metrics.request_count, 3)
        self.assertEqual(metrics.local_input_bytes, 2200)
        self.assertEqual(metrics.local_input_breakdown.system_instruction_bytes, 400)
        self.assertEqual(metrics.local_input_breakdown.tool_schema_bytes, 600)
        self.assertEqual(metrics.local_input_breakdown.checkpoint_bytes, 50)
        self.assertEqual(metrics.local_input_breakdown.total_bytes, 2200)
        self.assertEqual(metrics.handoff_revalidation_input_bytes, 100)
        self.assertEqual(metrics.provider_input.value, 300)
        self.assertEqual(metrics.provider_input.known_items, 1)
        self.assertEqual(metrics.provider_input.unknown_items, 2)
        self.assertEqual(metrics.confirmed_usage_request_count, 1)
        self.assertEqual(metrics.unknown_usage_request_count, 2)
        self.assertFalse(metrics.provider_input.complete)
        with self.assertRaisesRegex(ValueError, "request IDs must be unique"):
            item = RequestContextMetric(
                request_id="duplicate",
                ordinal=1,
                purpose="author",
                local_input_bytes=1,
                local_input_breakdown=ContextInputBreakdown(other_bytes=1),
                admitted=False,
            )
            accumulate_context_metrics((item, item))

    def test_metric_claims_and_aggregate_shapes_reject_invalid_states(self) -> None:
        base = {
            "request_id": "metric-boundary",
            "ordinal": 1,
            "purpose": "author",
            "local_input_bytes": 10,
            "local_input_breakdown": ContextInputBreakdown(other_bytes=10),
            "admitted": True,
        }
        invalid_cases = (
            ({**base, "local_input_bytes": 11}, "local input categories"),
            (
                {**base, "handoff_revalidation_input_bytes": 11},
                "handoff revalidation input exceeds",
            ),
            ({**base, "provider_input_tokens": 1}, "unavailable provider usage"),
            ({**base, "provider_usage": "confirmed"}, "requires input and output"),
            (
                {
                    **base,
                    "provider_usage": "confirmed",
                    "provider_input_tokens": 1,
                    "provider_output_tokens": 1,
                    "cached_input_tokens": 2,
                },
                "cached input cannot exceed",
            ),
            (
                {
                    **base,
                    "original_tool_output_bytes": 1,
                    "visible_tool_output_bytes": 2,
                },
                "visible tool output cannot exceed",
            ),
            (
                {
                    **base,
                    "admitted": False,
                    "latency_milliseconds": 1,
                },
                "unadmitted request cannot claim provider observations",
            ),
        )
        for values, message in invalid_cases:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValidationError, message),
            ):
                RequestContextMetric.model_validate(values)
        with self.assertRaisesRegex(ValidationError, "without observations"):
            PartialTotal(
                value=1,
                known_items=0,
                unknown_items=1,
                unit="tokens",
            )
        metric = RequestContextMetric.model_validate(base)
        with self.assertRaisesRegex(ValueError, "ordinals must be contiguous"):
            accumulate_context_metrics((metric.model_copy(update={"ordinal": 2}),))

    def test_work_unit_lifecycle_and_resource_invariants(self) -> None:
        fixture = g0_fixture()
        cases = (
            (
                {"dependencies": (fixture.completed_work.reference,)},
                "depend on itself",
            ),
            (
                {
                    "ledger": fixture.completed_work.ledger.model_copy(
                        update={"attempts": 99}
                    )
                },
                "exceeds its ceiling",
            ),
            ({"terminal_reason": None}, "require exactly one reason"),
        )
        for updates, message in cases:
            changed = fixture.completed_work.model_copy(update=updates)
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValidationError, message),
            ):
                WorkUnitRecord.model_validate(changed.model_dump())
        nonterminal = fixture.queued_work.model_copy(
            update={"terminal_reason": fixture.completed_work.terminal_reason}
        )
        with self.assertRaisesRegex(ValidationError, "nonterminal work units"):
            WorkUnitRecord.model_validate(nonterminal.model_dump())
        unknown_requirement = fixture.queued_work.model_copy(
            update={"evidence": fixture.completed_work.evidence}
        )
        with self.assertRaisesRegex(ValidationError, "unknown requirement"):
            WorkUnitRecord.model_validate(unknown_requirement.model_dump())
        other_scope = fixture.scope.model_copy(update={"owner_uid": os.getuid() + 1})
        cross_scope_evidence = fixture.completed_work.evidence[0].model_copy(
            update={
                "view": fixture.evidence_view.model_copy(update={"scope": other_scope})
            }
        )
        cross_scope_work = fixture.completed_work.model_copy(
            update={"evidence": (cross_scope_evidence,)}
        )
        with self.assertRaisesRegex(ValidationError, "crosses an owner"):
            WorkUnitRecord.model_validate(cross_scope_work.model_dump())

    def test_bounded_view_metadata_and_reproduction_fail_closed(self) -> None:
        fixture = g0_fixture()
        changes = (
            ({"visible_lines": 2}, "line count"),
            ({"original_bytes": fixture.artifact.bytes + 1}, "full artifact"),
            ({"stdout_sha256": hashed("other stream")}, "stream digest"),
        )
        for updates, message in changes:
            changed = fixture.evidence_view.model_copy(update=updates)
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValidationError, message),
            ):
                BoundedEvidenceView.model_validate(changed.model_dump())
        wrong_lines = fixture.evidence_view.model_copy(update={"original_lines": 2})
        with self.assertRaisesRegex(ValueError, "line count does not reproduce"):
            verify_bounded_evidence(wrong_lines, fixture.artifact_payload)
        wrong_content = fixture.evidence_view.model_copy(
            update={"content": "different"}
        )
        with self.assertRaisesRegex(ValueError, "content does not reproduce"):
            verify_bounded_evidence(wrong_content, fixture.artifact_payload)
        invalid_utf8 = b"\xff"
        invalid_artifact = fixture.artifact.model_copy(
            update={"sha256": digest(invalid_utf8), "bytes": len(invalid_utf8)}
        )
        invalid_view = fixture.evidence_view.model_copy(
            update={
                "stdout_sha256": invalid_artifact.sha256,
                "original_bytes": len(invalid_utf8),
                "visible_bytes": 0,
                "original_lines": 0,
                "visible_lines": 0,
                "content": "",
                "full_artifact": invalid_artifact,
                "omissions": (
                    OmittedRange(
                        stream="stdout",
                        start=0,
                        end=1,
                        reason="Invalid source byte.",
                    ),
                ),
                "complete": False,
            }
        )
        invalid_view = BoundedEvidenceView.model_validate(invalid_view.model_dump())
        with self.assertRaisesRegex(ValueError, "not valid UTF-8"):
            verify_bounded_evidence(invalid_view, invalid_utf8)

    def test_bundle_recomputes_totals_and_exact_outcome_inventory(self) -> None:
        fixture = g0_fixture()
        reset = fixture.bundle.model_dump()
        reset["context_metrics"] = accumulate_context_metrics(()).model_dump()
        with self.assertRaisesRegex(ValidationError, "totals do not reproduce"):
            TaskStateBundle.model_validate(reset)

        changed_outcome = fixture.bundle.model_dump()
        outcome = changed_outcome["outcomes"][0]
        assert isinstance(outcome, dict)
        outcome["summary"] = "Substituted outcome summary."
        with self.assertRaisesRegex(ValidationError, "differs from its inventory"):
            TaskStateBundle.model_validate(changed_outcome)

        terminal_outstanding = fixture.bundle.model_dump()
        terminal_outstanding["checkpoint"]["next_actions"] = (
            fixture.completed_work.reference.model_dump(),
        )
        terminal_outstanding["checkpoint"]["outstanding_work"] = (
            fixture.completed_work.reference.model_dump(),
        )
        terminal_outstanding["checkpoint"]["view"] = CheckpointView(
            summary="A terminal unit cannot remain outstanding.",
            included_record_ids=(fixture.completed_work.work_unit_id,),
            complete=True,
        ).model_dump()
        with self.assertRaisesRegex(ValidationError, "must be nonterminal"):
            TaskStateBundle.model_validate(terminal_outstanding)


class ProfileDiagnosticTests(TestCase):
    def test_valid_offline_profile_passes_without_granting_authority(self) -> None:
        profile = g0_fixture().profile
        report = diagnose_task_profile(profile)
        self.assertEqual(report.status, "pass")
        self.assertTrue(report.offline_only)
        self.assertFalse(profile.grants_authority)
        self.assertFalse(profile.executable_checks)
        self.assertFalse(profile.network_probes)

    def test_required_tool_omission_and_unknown_availability_fail(self) -> None:
        profile = g0_fixture().profile
        tool = profile.tools[0]
        omitted = profile.model_copy(
            update={
                "tools": (tool.model_copy(update={"selected": False}),),
                "omitted_tool_ids": (tool.tool_id,),
                "sizes": profile.sizes.model_copy(
                    update={"tool_schema_bytes": 0, "total_bytes": 200}
                ),
            }
        )
        omitted = TaskProfileManifest.model_validate(omitted.model_dump())
        report = diagnose_task_profile(omitted)
        self.assertEqual(report.status, "fail")
        self.assertEqual(report.diagnostics[0].code, "required_tool_omitted")

        unknown = profile.model_copy(
            update={"tools": (tool.model_copy(update={"availability": "unknown"}),)}
        )
        unknown = TaskProfileManifest.model_validate(unknown.model_dump())
        report = diagnose_task_profile(unknown)
        self.assertEqual(report.status, "fail")
        self.assertEqual(
            report.diagnostics[0].code, "required_tool_availability_unknown"
        )

    def test_required_instruction_omission_and_unauthorized_tool_fail(self) -> None:
        profile = g0_fixture().profile
        instruction = profile.instructions[0]
        tool = profile.tools[0]
        changed = profile.model_copy(
            update={
                "instructions": (instruction.model_copy(update={"selected": False}),),
                "tools": (tool.model_copy(update={"authorized": False}),),
                "omitted_instruction_ids": (instruction.rule_id,),
                "sizes": ProfileSizes(
                    root_instruction_bytes=0,
                    instruction_bytes=0,
                    tool_schema_bytes=300,
                    total_bytes=300,
                ),
            }
        )
        changed = TaskProfileManifest.model_validate(changed.model_dump())
        codes = {item.code for item in diagnose_task_profile(changed).diagnostics}
        self.assertEqual(
            codes,
            {"required_instruction_omitted", "selected_tool_unauthorized"},
        )

    def test_advisory_profile_findings_remain_visible(self) -> None:
        profile = g0_fixture().profile
        first_instruction = profile.instructions[0]
        temporary = first_instruction.model_copy(
            update={
                "rule_id": "temporary-note",
                "bytes": 4000,
                "required": False,
                "classification": "temporary_state",
            }
        )
        first_tool = profile.tools[0].model_copy(
            update={"overlaps_with": ("alternate-read",)}
        )
        alternate = ToolProfileEntry(
            tool_id="alternate-read",
            schema_sha256=hashed("alternate schema"),
            schema_bytes=100,
            required=False,
            selected=True,
            authorized=True,
            availability="available",
            selection_reason="Offline overlap diagnostic fixture.",
            overlaps_with=(first_tool.tool_id,),
        )
        unused = alternate.model_copy(
            update={
                "tool_id": "unused-read",
                "schema_sha256": hashed("unused schema"),
                "selected": False,
                "overlaps_with": (),
            }
        )
        changed = profile.model_copy(
            update={
                "instructions": (first_instruction, temporary),
                "tools": (first_tool, alternate, unused),
                "omitted_tool_ids": (unused.tool_id,),
                "sizes": ProfileSizes(
                    root_instruction_bytes=4200,
                    instruction_bytes=4200,
                    tool_schema_bytes=400,
                    total_bytes=4600,
                ),
            }
        )
        changed = TaskProfileManifest.model_validate(changed.model_dump())
        report = diagnose_task_profile(changed)
        self.assertEqual(report.status, "warning")
        self.assertEqual(
            {item.code for item in report.diagnostics},
            {
                "duplicate_instruction",
                "optional_tool_omitted",
                "overlapping_tools",
                "root_instructions_oversized",
                "temporary_state_instruction",
            },
        )

    def test_profile_inventory_and_size_mismatches_are_rejected(self) -> None:
        profile = g0_fixture().profile
        bad_size = profile.model_copy(
            update={"sizes": profile.sizes.model_copy(update={"total_bytes": 999})}
        )
        with self.assertRaisesRegex(ValidationError, "profile total"):
            TaskProfileManifest.model_validate(bad_size.model_dump())
        bad_overlap = profile.model_copy(
            update={
                "tools": (
                    profile.tools[0].model_copy(
                        update={"overlaps_with": ("absent-tool",)}
                    ),
                )
            }
        )
        with self.assertRaisesRegex(ValidationError, "unique peer candidates"):
            TaskProfileManifest.model_validate(bad_overlap.model_dump())


class ContinuationValidationTests(TestCase):
    def selection(self) -> tuple[G0Fixture, ContinuationSelection]:
        fixture = g0_fixture()
        selection = ContinuationSelection(
            scope=fixture.scope,
            checkpoint_id=fixture.checkpoint.checkpoint_id,
            checkpoint_revision=fixture.checkpoint.revision,
            checkpoint_sha256=fixture.checkpoint.sha256,
            selected_work_unit=fixture.queued_work.reference,
            workspace=fixture.checkpoint.workspace,
            required_inputs=fixture.queued_work.required_inputs,
            context_baseline=fixture.checkpoint.context_metrics,
            ledger_baseline=fixture.checkpoint.task_ledger,
        )
        return fixture, selection

    def test_exact_selection_validates_without_enabling_runtime(self) -> None:
        fixture, selection = self.selection()
        validate_continuation(fixture.checkpoint, fixture.queued_work, selection)
        self.assertFalse(selection.grants_authority)
        self.assertFalse(fixture.bundle.runtime_continuation_enabled)

    def test_stale_workspace_and_checkpoint_are_rejected(self) -> None:
        fixture, selection = self.selection()
        stale_workspace = selection.model_copy(
            update={
                "workspace": selection.workspace.model_copy(
                    update={"tree_sha256": hashed("changed tree")}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "workspace state is stale"):
            validate_continuation(
                fixture.checkpoint, fixture.queued_work, stale_workspace
            )
        stale_checkpoint = selection.model_copy(update={"checkpoint_revision": 2})
        with self.assertRaisesRegex(ValueError, "stale checkpoint"):
            validate_continuation(
                fixture.checkpoint, fixture.queued_work, stale_checkpoint
            )

    def test_context_and_budget_resets_are_rejected(self) -> None:
        fixture, selection = self.selection()
        reset_context = selection.model_copy(
            update={"context_baseline": accumulate_context_metrics(())}
        )
        with self.assertRaisesRegex(ValueError, "reset cumulative context"):
            validate_continuation(
                fixture.checkpoint, fixture.queued_work, reset_context
            )
        reset_ledger = selection.model_copy(
            update={"ledger_baseline": ResourceLedger()}
        )
        with self.assertRaisesRegex(ValueError, "reset or replace"):
            validate_continuation(fixture.checkpoint, fixture.queued_work, reset_ledger)

    def test_invalid_continuation_inputs_and_terminal_work_are_rejected(self) -> None:
        fixture, selection = self.selection()
        missing = selection.model_copy(update={"required_inputs": ()})
        with self.assertRaisesRegex(ValueError, "input inventory differs"):
            validate_continuation(fixture.checkpoint, fixture.queued_work, missing)
        extra_input = fixture.queued_work.required_inputs[0].model_copy(
            update={"input_id": "unrequested-input"}
        )
        extra = selection.model_copy(
            update={"required_inputs": (*selection.required_inputs, extra_input)}
        )
        with self.assertRaisesRegex(ValueError, "input inventory differs"):
            validate_continuation(fixture.checkpoint, fixture.queued_work, extra)

        terminal_checkpoint = fixture.checkpoint.model_copy(
            update={
                "next_actions": (fixture.completed_work.reference,),
                "outstanding_work": (fixture.completed_work.reference,),
                "view": CheckpointView(
                    summary="Invalid terminal continuation fixture.",
                    included_record_ids=(fixture.completed_work.work_unit_id,),
                    complete=True,
                ),
            }
        )
        terminal_selection = ContinuationSelection(
            scope=fixture.scope,
            checkpoint_id=terminal_checkpoint.checkpoint_id,
            checkpoint_revision=terminal_checkpoint.revision,
            checkpoint_sha256=terminal_checkpoint.sha256,
            selected_work_unit=fixture.completed_work.reference,
            workspace=terminal_checkpoint.workspace,
            required_inputs=fixture.completed_work.required_inputs,
            context_baseline=terminal_checkpoint.context_metrics,
            ledger_baseline=terminal_checkpoint.task_ledger,
        )
        with self.assertRaisesRegex(ValueError, "terminal work unit"):
            validate_continuation(
                terminal_checkpoint, fixture.completed_work, terminal_selection
            )


class TaskStateStoreTests(TestCase):
    def test_private_archive_roundtrip_and_owner_scope(self) -> None:
        fixture = g0_fixture()
        with TemporaryDirectory() as directory:
            root = Path(directory) / "task-state"
            path = save_task_state(
                root,
                fixture.bundle,
                {fixture.artifact.sha256: fixture.artifact_payload},
            )
            loaded, artifacts = load_task_state(
                path,
                owner_uid=os.getuid(),
                project_id=fixture.scope.project_id,
                workspace_sha256=fixture.scope.workspace_sha256,
            )
            self.assertEqual(loaded, fixture.bundle)
            self.assertEqual(
                artifacts[fixture.artifact.sha256], fixture.artifact_payload
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            self.assertEqual((path / "state.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "owner or project boundary"):
                load_task_state(
                    path,
                    owner_uid=os.getuid(),
                    project_id="another-project",
                    workspace_sha256=fixture.scope.workspace_sha256,
                )

    def test_missing_or_tampered_artifacts_never_replay(self) -> None:
        fixture = g0_fixture()
        with TemporaryDirectory() as directory:
            root = Path(directory) / "task-state"
            with self.assertRaisesRegex(ValueError, "exactly match"):
                save_task_state(root, fixture.bundle, {})
            path = save_task_state(
                root,
                fixture.bundle,
                {fixture.artifact.sha256: fixture.artifact_payload},
            )
            artifact_path = path / "artifacts" / fixture.artifact.sha256
            artifact_path.write_bytes(b"substituted")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                load_task_state(
                    path,
                    owner_uid=os.getuid(),
                    project_id=fixture.scope.project_id,
                    workspace_sha256=fixture.scope.workspace_sha256,
                )

    def test_interrupted_publication_leaves_no_replayable_archive(self) -> None:
        fixture = g0_fixture()
        original = task_state_store.private_write
        calls = 0

        def fail_second_write(path: Path, payload: bytes) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected write failure")
            original(path, payload)

        with TemporaryDirectory() as directory:
            root = Path(directory) / "task-state"
            with (
                patch.object(task_state_store, "private_write", fail_second_write),
                self.assertRaisesRegex(OSError, "injected write failure"),
            ):
                save_task_state(
                    root,
                    fixture.bundle,
                    {fixture.artifact.sha256: fixture.artifact_payload},
                )
            self.assertEqual(tuple(root.iterdir()), ())

    def test_symlink_root_and_incompatible_manifest_fail_closed(self) -> None:
        fixture = g0_fixture()
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            actual = temporary / "actual"
            actual.mkdir(mode=0o700)
            link = temporary / "link"
            link.symlink_to(actual, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "private owned directory"):
                save_task_state(
                    link,
                    fixture.bundle,
                    {fixture.artifact.sha256: fixture.artifact_payload},
                )

            path = save_task_state(
                temporary / "store",
                fixture.bundle,
                {fixture.artifact.sha256: fixture.artifact_payload},
            )
            manifest_path = path / "manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["schema_version"] = 2
            manifest_path.write_bytes(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
            with self.assertRaisesRegex(ValueError, "invalid task-state manifest"):
                load_task_state(
                    path,
                    owner_uid=os.getuid(),
                    project_id=fixture.scope.project_id,
                    workspace_sha256=fixture.scope.workspace_sha256,
                )

    def test_manifest_artifact_names_must_match_their_digests(self) -> None:
        fixture = g0_fixture()
        second_payload = b"second verification result\n"
        second_artifact = fixture.artifact.model_copy(
            update={
                "artifact_id": "second-result",
                "sha256": digest(second_payload),
                "bytes": len(second_payload),
            }
        )
        second_verification = VerificationRecord(
            verification_id="second-verification",
            command="python -m unittest second.fixture",
            status="failed",
            bound_workspace_sha256=fixture.checkpoint.workspace.sha256,
            bound_input_sha256=fixture.checkpoint.workspace.dirty_state_sha256,
            result=second_artifact,
        )
        checkpoint = fixture.checkpoint.model_copy(
            update={
                "verifications": (
                    *fixture.checkpoint.verifications,
                    second_verification,
                )
            }
        )
        bundle = TaskStateBundle.model_validate(
            fixture.bundle.model_copy(update={"checkpoint": checkpoint}).model_dump()
        )
        with TemporaryDirectory() as directory:
            path = save_task_state(
                Path(directory) / "store",
                bundle,
                {
                    fixture.artifact.sha256: fixture.artifact_payload,
                    second_artifact.sha256: second_payload,
                },
            )
            manifest_path = path / "manifest.json"
            manifest = TaskStateManifest.model_validate_json(manifest_path.read_bytes())
            first, second = manifest.files[1:]
            swapped = manifest.model_copy(
                update={
                    "files": (
                        manifest.files[0],
                        first.model_copy(update={"name": second.name}),
                        second.model_copy(update={"name": first.name}),
                    )
                }
            )
            manifest_path.write_bytes(canonical_bytes(swapped))
            with self.assertRaisesRegex(ValueError, "artifact names are invalid"):
                load_task_state(
                    path,
                    owner_uid=os.getuid(),
                    project_id=fixture.scope.project_id,
                    workspace_sha256=fixture.scope.workspace_sha256,
                )

    def test_extra_or_public_archive_files_are_rejected(self) -> None:
        fixture = g0_fixture()
        with TemporaryDirectory() as directory:
            path = save_task_state(
                Path(directory) / "store",
                fixture.bundle,
                {fixture.artifact.sha256: fixture.artifact_payload},
            )
            extra = path / "untracked"
            extra.write_bytes(b"not in manifest")
            os.chmod(extra, 0o600)
            with self.assertRaisesRegex(ValueError, "top-level inventory"):
                load_task_state(
                    path,
                    owner_uid=os.getuid(),
                    project_id=fixture.scope.project_id,
                    workspace_sha256=fixture.scope.workspace_sha256,
                )
            extra.unlink()
            artifact_path = path / "artifacts" / fixture.artifact.sha256
            os.chmod(artifact_path, 0o644)
            with self.assertRaisesRegex(ValueError, "nonprivate file"):
                load_task_state(
                    path,
                    owner_uid=os.getuid(),
                    project_id=fixture.scope.project_id,
                    workspace_sha256=fixture.scope.workspace_sha256,
                )

    def test_duplicate_json_keys_and_nonprivate_archive_are_rejected(self) -> None:
        fixture = g0_fixture()
        with TemporaryDirectory() as directory:
            path = save_task_state(
                Path(directory) / "store",
                fixture.bundle,
                {fixture.artifact.sha256: fixture.artifact_payload},
            )
            state_path = path / "state.json"
            state_payload = state_path.read_bytes().replace(
                b'{"checkpoint":', b'{"schema_version":1,"checkpoint":', 1
            )
            state_path.write_bytes(state_payload)
            manifest_path = path / "manifest.json"
            manifest = TaskStateManifest.model_validate_json(manifest_path.read_bytes())
            files = tuple(
                item.model_copy(update={"sha256": digest(state_payload)})
                if item.name == "state.json"
                else item
                for item in manifest.files
            )
            manifest_path.write_bytes(
                canonical_bytes(manifest.model_copy(update={"files": files}))
            )
            with self.assertRaisesRegex(ValueError, "invalid task-state bundle"):
                load_task_state(
                    path,
                    owner_uid=os.getuid(),
                    project_id=fixture.scope.project_id,
                    workspace_sha256=fixture.scope.workspace_sha256,
                )
            os.chmod(path, 0o755)
            with self.assertRaisesRegex(ValueError, "private owner directory"):
                load_task_state(
                    path,
                    owner_uid=os.getuid(),
                    project_id=fixture.scope.project_id,
                    workspace_sha256=fixture.scope.workspace_sha256,
                )


class LegacyReplayCompatibilityTests(TestCase):
    def test_schema_one_recorded_run_still_replays(self) -> None:
        brief, cassette = demo_inputs()
        policy = ReviewPolicy()
        result = asyncio.run(
            review(
                brief,
                tuple(item.critic for item in cassette.critics),
                RecordedReviewer(cassette),
                policy,
            )
        )
        with TemporaryDirectory() as directory:
            path = save_run(Path(directory), brief, cassette, policy, result)
            manifest = Manifest.model_validate_json(
                (path / "manifest.json").read_bytes()
            )
            self.assertEqual(manifest.schema_version, 1)
            self.assertEqual(load_run(path), (brief, cassette, policy, result))
