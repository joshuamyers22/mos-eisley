"""G606-02 signed offline R0/R1 and R5/R6 source handoff denials."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.cohort_shadow import (
    OfflineShadowDecision,
    OfflineShadowDecisionBatch,
)
from tests import test_cohort_r2_entry as r2_module
from tests import test_cohort_r6_assessment_handoff as r6_module
from tools.g6_06_full_offline import (
    PROJECT_ROOT,
    bound_source_files,
)
from tools.g6_06_handoff_evidence import (
    ContractRoster,
    FrozenR2EvidenceAnchor,
    FrozenR5R6EvidenceAnchor,
    Phase,
    PhaseReview,
    PhaseReviewTrust,
    make_r5_source_bundle,
    make_r6_source_bundle,
    sign_synthetic_phase_review,
    validate_r0_r1_to_r2_evidence,
    validate_r5_r6_source_evidence,
)
from tools.g6_06_r0_offline import (
    PROJECT_ROOT as R0_PROJECT_ROOT,
)
from tools.g6_06_r0_offline import (
    SUITES as R0_SUITES,
)
from tools.g6_06_r0_offline import (
    R0OfflineResultIndex,
    R0SuiteResult,
)
from tools.g6_06_r0_offline import (
    bound_source_files as r0_bound_source_files,
)


def _trust(
    phase: Phase, reviewer_id: str, key: Ed25519PrivateKey, now: datetime
) -> PhaseReviewTrust:
    return PhaseReviewTrust(
        phase=phase,
        reviewer_id=reviewer_id,
        public_key_base64=base64.b64encode(
            key.public_key().public_bytes_raw()
        ).decode(),
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=2),
    )


class R0R1ToR2HandoffEvidenceTests(TestCase):
    def setUp(self) -> None:
        self.r2 = r2_module.CohortR2EntryTests()
        self.r2.setUp()
        self.addCleanup(self.r2.doCleanups)
        self.now = self.r2.now
        manifest = self.r2.fixture.manifest
        source_files = r0_bound_source_files(R0_PROJECT_ROOT)
        source_set_sha256 = digest(
            json.dumps(
                [(item.relative_path, item.sha256) for item in source_files],
                separators=(",", ":"),
            ).encode()
        )
        self.r0_index = R0OfflineResultIndex(
            generated_at=self.now - timedelta(seconds=30),
            source_files=source_files,
            bound_source_set_sha256=source_set_sha256,
            suites=tuple(
                R0SuiteResult(
                    suite_id=suite_id,
                    case_ids_sha256=digest(suite_id.encode()),
                    expected_case_count=1,
                    ran_count=1,
                    failure_count=0,
                    error_count=0,
                    skipped_count=0,
                    expected_failure_count=0,
                    unexpected_success_count=0,
                    status="synthetic_pass",
                )
                for suite_id, _ in R0_SUITES
            ),
            status="synthetic_pass",
        )
        state = self.r2.fixture.base.admission.read_current()
        cohort = state.cohort
        assert cohort is not None
        observation = self.r2.fixture.route_probe.current
        decisions = tuple(
            OfflineShadowDecision(
                owner_id=manifest.owner_id,
                cohort_id=manifest.cohort_id,
                task_session_sha256=digest(
                    json.dumps(
                        [
                            manifest.owner_id,
                            manifest.cohort_id,
                            task.task_id,
                            task.session_id,
                            "stage-a",
                        ],
                        separators=(",", ":"),
                    ).encode()
                ),
                manifest_sha256=manifest.manifest_sha256,
                release_sha256=cohort.signed_release.release.release_sha256,
                candidate_policy_sha256=manifest.candidate_policy_sha256,
                witness_generation=state.generation,
                checked_at=self.now - timedelta(seconds=1),
                route_observation_sha256=digest(canonical_bytes(observation)),
                route_observed_at=observation.observed_at,
                route_valid_until=observation.valid_until,
                status="selected",
                selected_candidate_id=self.r2.fixture.base.selection.candidate_id,
                selection_source=self.r2.fixture.base.selection.source,
            )
            for task in manifest.tasks
        )
        self.r1_batch = OfflineShadowDecisionBatch(
            manifest_sha256=manifest.manifest_sha256,
            release_sha256=cohort.signed_release.release.release_sha256,
            candidate_policy_sha256=manifest.candidate_policy_sha256,
            decisions=decisions,
        )
        r0_sha256 = digest(canonical_bytes(self.r0_index))
        r1_sha256 = digest(canonical_bytes(self.r1_batch))
        self.r2.anchor = self.r2.anchor.model_copy(
            update={"r0_review_sha256": r0_sha256, "r1_review_sha256": r1_sha256}
        )
        self.r2.packet = self.r2.packet.model_copy(
            update={
                "r0": self.r2.packet.r0.model_copy(
                    update={"evidence_sha256": r0_sha256}
                ),
                "r1": self.r2.packet.r1.model_copy(
                    update={
                        "evidence_sha256": r1_sha256,
                        "reviewed_at": self.now - timedelta(seconds=1),
                    }
                ),
            }
        )
        self.keys = tuple(Ed25519PrivateKey.generate() for _ in range(3))
        self.trusts = (
            _trust("R0", "independent-r0-reviewer", self.keys[0], self.now),
            _trust("R1", "independent-r1-reviewer", self.keys[1], self.now),
            _trust("ONCALL", "independent-oncall", self.keys[2], self.now),
        )
        self.r0_review = sign_synthetic_phase_review(
            PhaseReview(
                phase="R0",
                decision="accept",
                manifest_sha256=manifest.manifest_sha256,
                broker_build_sha256=manifest.broker_build_sha256,
                artifact_sha256=r0_sha256,
                source_set_sha256=source_set_sha256,
                reviewer_id=self.trusts[0].reviewer_id,
                reviewed_at=self.r2.packet.r0.reviewed_at,
                valid_until=self.r2.packet.r0.valid_until,
            ),
            self.keys[0].private_bytes_raw(),
        )
        self.r1_review = sign_synthetic_phase_review(
            PhaseReview(
                phase="R1",
                decision="accept",
                manifest_sha256=manifest.manifest_sha256,
                broker_build_sha256=manifest.broker_build_sha256,
                artifact_sha256=r1_sha256,
                source_set_sha256=digest(b"synthetic-r1-source-set"),
                upstream_sha256=self.r0_review.review_sha256,
                reviewer_id=self.trusts[1].reviewer_id,
                reviewed_at=self.r2.packet.r1.reviewed_at,
                valid_until=self.r2.packet.r1.valid_until,
            ),
            self.keys[1].private_bytes_raw(),
        )
        self.oncall_review = sign_synthetic_phase_review(
            PhaseReview(
                phase="ONCALL",
                decision="accept",
                manifest_sha256=manifest.manifest_sha256,
                broker_build_sha256=manifest.broker_build_sha256,
                artifact_sha256=self.r2.anchor.oncall_evidence_sha256,
                source_set_sha256=self.r1_review.review.source_set_sha256,
                upstream_sha256=self.r1_review.review_sha256,
                reviewer_id=self.trusts[2].reviewer_id,
                reviewed_at=self.now,
                valid_until=self.now + timedelta(minutes=1),
            ),
            self.keys[2].private_bytes_raw(),
        )
        self.entry_result = self.r2.validate_end_to_end()
        self.anchor = FrozenR2EvidenceAnchor(
            manifest_sha256=manifest.manifest_sha256,
            broker_build_sha256=manifest.broker_build_sha256,
            r0_index_sha256=r0_sha256,
            r1_batch_sha256=r1_sha256,
            entry_result_sha256=digest(canonical_bytes(self.entry_result)),
            r1_source_set_sha256=self.r1_review.review.source_set_sha256,
            oncall_evidence_sha256=self.r2.anchor.oncall_evidence_sha256,
            expected_task_session_sha256=tuple(
                sorted(item.task_session_sha256 for item in decisions)
            ),
            trust_roster_sha256=digest(
                canonical_bytes(ContractRoster(trusts=self.trusts))
            ),
            valid_until=self.now + timedelta(minutes=1),
        )

    def validate(self, **changes: object):
        state = self.r2.fixture.base.admission.read_current()
        cohort = state.cohort
        assert cohort is not None
        values: dict[str, object] = {
            "packet": self.r2.packet,
            "entry_anchor": self.r2.anchor,
            "entry_result": self.entry_result,
            "shadow_release_sha256": cohort.signed_release.release.release_sha256,
            "candidate_policy_sha256": cohort.manifest.candidate_policy_sha256,
            "owner_signer_id": cohort.trust.owner_signer_id,
            "operator_signer_id": cohort.trust.operator_signer_id,
            "anchor": self.anchor,
            "r0_index": self.r0_index,
            "r1_batch": self.r1_batch,
            "trusts": self.trusts,
            "r0_review": self.r0_review,
            "r1_review": self.r1_review,
            "oncall_review": self.oncall_review,
            "now": self.now,
        }
        values.update(changes)
        return validate_r0_r1_to_r2_evidence(**values)  # type: ignore[arg-type]

    def test_exact_signed_chain_is_reviewable_without_authority(self) -> None:
        result = self.validate()
        self.assertEqual((result.status, result.reasons), ("reviewable", ()))
        self.assertFalse(result.independent_custody_verified)
        self.assertFalse(result.cohort_release_authorized)
        self.assertFalse(result.dispatch_authorized)
        self.assertFalse(result.assessment_authorized)

    def test_changed_index_batch_or_task_coverage_blocks(self) -> None:
        changed_result = self.entry_result.model_copy(
            update={"remaining_cohort_microusd": 1}
        )
        self.assertIn(
            "r2_evidence_binding_mismatch",
            self.validate(entry_result=changed_result).reasons,
        )
        changed_index = self.r0_index.model_copy(update={"status": "blocked"})
        self.assertIn("r0_index_invalid", self.validate(r0_index=changed_index).reasons)
        changed_batch = self.r1_batch.model_copy(
            update={"decisions": self.r1_batch.decisions[:-1]}
        )
        self.assertIn("r1_batch_invalid", self.validate(r1_batch=changed_batch).reasons)
        fewer_tasks = self.anchor.expected_task_session_sha256[:-1]
        changed_anchor = self.anchor.model_copy(
            update={"expected_task_session_sha256": fewer_tasks}
        )
        self.assertIn("r1_batch_invalid", self.validate(anchor=changed_anchor).reasons)

    def test_rejected_stale_or_substituted_review_blocks(self) -> None:
        self.assertIn("r0_review_missing", self.validate(r0_review=None).reasons)
        self.assertIn(
            "oncall_review_missing", self.validate(oncall_review=None).reasons
        )
        rejected = sign_synthetic_phase_review(
            self.r1_review.review.model_copy(update={"decision": "reject"}),
            self.keys[1].private_bytes_raw(),
        )
        self.assertIn(
            "r1_review_binding_invalid", self.validate(r1_review=rejected).reasons
        )
        stale = self.r0_review.review.model_copy(update={"valid_until": self.now})
        signed_stale = sign_synthetic_phase_review(
            stale, self.keys[0].private_bytes_raw()
        )
        self.assertIn(
            "r0_review_time_invalid", self.validate(r0_review=signed_stale).reasons
        )
        wrong_key = sign_synthetic_phase_review(
            self.r0_review.review, Ed25519PrivateKey.generate().private_bytes_raw()
        )
        self.assertIn(
            "r0_review_signature_invalid", self.validate(r0_review=wrong_key).reasons
        )


class R5R6HandoffEvidenceTests(TestCase):
    def setUp(self) -> None:
        self.r6 = r6_module.CohortR6AssessmentHandoffTests()
        self.r6.setUp()
        self.addCleanup(self.r6.doCleanups)
        self.now = self.r6.packet.reviewed_at
        build = self.r6.fixture.manifest.broker_build_sha256
        self.r5_bundle = make_r5_source_bundle(
            broker_build_sha256=build,
            anchor=self.r6.r5_anchor,
            r4_packet=self.r6.r4_packet,
            r4_result=self.r6.r4_result,
            preclose_state=self.r6.preclose_state,
            recovery_anchor=self.r6.recovery_anchor,
            reproduction=self.r6.reproduction,
            closeout=self.r6.closeout,
            r5_result=self.r6.r5_result,
        )
        self.r6_result = self.r6.validate_reproduced()
        self.r6_bundle = make_r6_source_bundle(
            broker_build_sha256=build,
            r5_bundle=self.r5_bundle,
            anchor=self.r6.anchor,
            packet=self.r6.packet,
            result=self.r6_result,
        )
        files = bound_source_files(PROJECT_ROOT)
        source_set_sha256 = digest(
            json.dumps(
                [(item.relative_path, item.sha256) for item in files],
                separators=(",", ":"),
            ).encode()
        )
        self.keys = tuple(Ed25519PrivateKey.generate() for _ in range(2))
        self.trusts = (
            _trust("R5", "independent-r5-source", self.keys[0], self.now),
            _trust("R6", self.r6.packet.reviewer_id, self.keys[1], self.now),
        )
        self.r5_review = sign_synthetic_phase_review(
            PhaseReview(
                phase="R5",
                decision="accept",
                manifest_sha256=self.r6.anchor.manifest_sha256,
                broker_build_sha256=build,
                artifact_sha256=digest(canonical_bytes(self.r5_bundle)),
                source_set_sha256=source_set_sha256,
                upstream_sha256=self.r5_bundle.reproduction_sha256,
                reviewer_id=self.trusts[0].reviewer_id,
                reviewed_at=self.r6.closeout.prepared_at,
                valid_until=self.r6.anchor.valid_until,
            ),
            self.keys[0].private_bytes_raw(),
        )
        self.r6_review = sign_synthetic_phase_review(
            PhaseReview(
                phase="R6",
                decision="accept",
                manifest_sha256=self.r6.anchor.manifest_sha256,
                broker_build_sha256=build,
                artifact_sha256=digest(canonical_bytes(self.r6_bundle)),
                source_set_sha256=source_set_sha256,
                upstream_sha256=self.r5_review.review_sha256,
                reviewer_id=self.trusts[1].reviewer_id,
                reviewed_at=self.now,
                valid_until=self.r6.anchor.valid_until,
            ),
            self.keys[1].private_bytes_raw(),
        )
        self.anchor = FrozenR5R6EvidenceAnchor(
            manifest_sha256=self.r6.anchor.manifest_sha256,
            broker_build_sha256=build,
            source_set_sha256=source_set_sha256,
            r5_bundle_sha256=digest(canonical_bytes(self.r5_bundle)),
            r6_bundle_sha256=digest(canonical_bytes(self.r6_bundle)),
            trust_roster_sha256=digest(
                canonical_bytes(ContractRoster(trusts=self.trusts))
            ),
            valid_until=self.r6.anchor.valid_until,
        )

    def validate(self, **changes: object):
        values: dict[str, object] = {
            "anchor": self.anchor,
            "r5_bundle": self.r5_bundle,
            "r6_bundle": self.r6_bundle,
            "r5_anchor": self.r6.r5_anchor,
            "r4_packet": self.r6.r4_packet,
            "r4_result": self.r6.r4_result,
            "preclose_state": self.r6.preclose_state,
            "recovery_anchor": self.r6.recovery_anchor,
            "reproduction": self.r6.reproduction,
            "closeout": self.r6.closeout,
            "r5_result": self.r6.r5_result,
            "r6_anchor": self.r6.anchor,
            "r6_packet": self.r6.packet,
            "r6_result": self.r6_result,
            "trusts": self.trusts,
            "r5_review": self.r5_review,
            "r6_review": self.r6_review,
            "now": self.now,
        }
        values.update(changes)
        return validate_r5_r6_source_evidence(**values)  # type: ignore[arg-type]

    def test_exact_source_bundle_is_reviewable_without_authority(self) -> None:
        result = self.validate()
        self.assertEqual((result.status, result.reasons), ("reviewable", ()))
        self.assertFalse(result.independent_custody_verified)
        self.assertFalse(result.assessment_authorized)
        self.assertFalse(result.dispatch_authorized)

    def test_changed_reproduction_or_assessment_evidence_blocks(self) -> None:
        changed_result = self.r6_result.model_copy(update={"assignment_count": 9})
        self.assertIn(
            "phase_source_binding_mismatch",
            self.validate(r6_result=changed_result).reasons,
        )
        changed_reproduction = self.r6.reproduction.model_copy(
            update={
                "reproduced_at": self.r6.reproduction.reproduced_at
                + timedelta(seconds=1)
            }
        )
        self.assertIn(
            "phase_source_binding_mismatch",
            self.validate(reproduction=changed_reproduction).reasons,
        )
        changed_evidence = self.r6.packet.evidence.model_copy(
            update={"quality_review_sha256": digest(b"changed-quality-ref")}
        )
        changed_packet = self.r6.packet.model_copy(
            update={"evidence": changed_evidence}
        )
        self.assertIn(
            "phase_source_binding_mismatch",
            self.validate(r6_packet=changed_packet).reasons,
        )

    def test_rejected_review_wrong_key_and_rebound_bundle_block(self) -> None:
        self.assertIn("r5_review_missing", self.validate(r5_review=None).reasons)
        self.assertIn("r6_review_missing", self.validate(r6_review=None).reasons)
        rejected = sign_synthetic_phase_review(
            self.r5_review.review.model_copy(update={"decision": "reject"}),
            self.keys[0].private_bytes_raw(),
        )
        self.assertIn(
            "r5_review_binding_invalid", self.validate(r5_review=rejected).reasons
        )
        wrong_key = sign_synthetic_phase_review(
            self.r6_review.review, Ed25519PrivateKey.generate().private_bytes_raw()
        )
        self.assertIn(
            "r6_review_signature_invalid", self.validate(r6_review=wrong_key).reasons
        )
        rebound = self.r6_bundle.model_copy(
            update={"r5_bundle_sha256": digest(b"rebound-r5-bundle")}
        )
        self.assertIn(
            "phase_source_binding_mismatch", self.validate(r6_bundle=rebound).reasons
        )
