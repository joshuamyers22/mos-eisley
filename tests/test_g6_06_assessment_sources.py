"""Synthetic G606-05 source coverage and decision-readiness denials."""

from __future__ import annotations

import io
import stat
from contextlib import redirect_stdout
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import TestCase

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.cohort_assessment_handoff import (
    FrozenR6AssessmentAnchor,
    OfflineR6AssessmentPacket,
    OfflineR6AssessmentResult,
)
from mos_eisley.run.cohort_close_handoff import OfflineR5CloseResult
from mos_eisley.run.cohort_closeout import CohortCloseoutPacket, FrozenCloseoutProtocol
from tests import test_cohort_r6_assessment_handoff as r6_fixture
from tools.g6_06_assessment_sources import (
    BASE_KINDS,
    COMPARISON_KINDS,
    AssessmentSourceAssessment,
    AssessmentSourceReviewIndex,
    FrozenAssessmentSourceAnchor,
    SourceCoverageReview,
    SourceKind,
    expected_source_digests,
    main,
    validate_assessment_sources,
)


def _sha(label: str) -> str:
    return digest(label.encode())


@dataclass(frozen=True)
class Package:
    anchor: FrozenAssessmentSourceAnchor
    r6_anchor: FrozenR6AssessmentAnchor
    r6_packet: OfflineR6AssessmentPacket
    r6_result: OfflineR6AssessmentResult
    protocol: FrozenCloseoutProtocol
    closeout: CohortCloseoutPacket
    r5_result: OfflineR5CloseResult
    reviews: AssessmentSourceReviewIndex
    now: datetime


def _assess(package: Package) -> AssessmentSourceAssessment:
    return validate_assessment_sources(
        anchor=package.anchor,
        r6_anchor=package.r6_anchor,
        r6_packet=package.r6_packet,
        r6_result=package.r6_result,
        protocol=package.protocol,
        closeout=package.closeout,
        r5_result=package.r5_result,
        reviews=package.reviews,
        now=package.now,
    )


class AssessmentSourceTests(TestCase):
    def setUp(self) -> None:
        self.r6 = r6_fixture.CohortR6AssessmentHandoffTests(
            "test_complete_synthetic_handoff_is_reviewable_without_authority"
        )
        self.r6.setUp()
        self.addCleanup(self.r6.doCleanups)

    def package(self, *, comparison: bool = False) -> Package:
        r6_anchor = self.r6.anchor
        r6_packet = self.r6.packet
        if comparison:
            r6_anchor = r6_anchor.model_copy(
                update={
                    "expected_claim_type": "registered_comparison",
                    "baseline_registration_sha256": _sha(
                        "synthetic-baseline-registration"
                    ),
                    "comparison_design_sha256": _sha("synthetic-design-registration"),
                    "comparison_registered_at": r6_anchor.cohort_started_at
                    - timedelta(minutes=1),
                }
            )
            r6_packet = r6_packet.model_copy(
                update={
                    "claim_type": "registered_comparison",
                    "baseline_registration_sha256": (
                        r6_anchor.baseline_registration_sha256
                    ),
                    "comparison_design_sha256": r6_anchor.comparison_design_sha256,
                }
            )
        r6_result = self.r6.validate_reproduced(anchor=r6_anchor, packet=r6_packet)
        self.assertEqual((r6_result.status, r6_result.reasons), ("reviewable", ()))
        frozen_at = r6_packet.reviewed_at + timedelta(seconds=1)
        now = frozen_at + timedelta(seconds=3)
        sources = expected_source_digests(packet=r6_packet, closeout=self.r6.closeout)
        anchor = FrozenAssessmentSourceAnchor(
            manifest_sha256=r6_packet.manifest_sha256,
            r6_anchor_sha256=digest(canonical_bytes(r6_anchor)),
            r6_packet_sha256=digest(canonical_bytes(r6_packet)),
            r6_result_sha256=digest(canonical_bytes(r6_result)),
            closeout_packet_sha256=digest(canonical_bytes(self.r6.closeout)),
            followup_index_sha256=sources["followup"],
            evidence_references_sha256=digest(canonical_bytes(r6_packet.evidence)),
            upstream_handoff_sha256=_sha("synthetic-r5-r6-handoff"),
            source_reviewer_id="source-reviewer",
            final_reviewer_id=r6_packet.reviewer_id,
            custodian_id="restricted-custodian",
            frozen_at=frozen_at,
            valid_until=r6_anchor.valid_until,
        )
        kinds = (*BASE_KINDS, *COMPARISON_KINDS) if comparison else BASE_KINDS
        reviews = AssessmentSourceReviewIndex(
            manifest_sha256=anchor.manifest_sha256,
            r6_anchor_sha256=anchor.r6_anchor_sha256,
            r6_packet_sha256=anchor.r6_packet_sha256,
            r6_result_sha256=anchor.r6_result_sha256,
            upstream_handoff_sha256=anchor.upstream_handoff_sha256,
            final_reviewer_id=anchor.final_reviewer_id,
            reviews=tuple(
                SourceCoverageReview(
                    kind=cast(SourceKind, kind),
                    artifact_sha256=sources[kind],
                    decision="accept",
                    producer_id="source-producer",
                    custodian_id=anchor.custodian_id,
                    reviewer_id=anchor.source_reviewer_id,
                    roster_sha256=r6_packet.roster_sha256,
                    covered_task_count=r6_packet.assignment_count
                    if kind in BASE_KINDS
                    else 0,
                    unknown_task_count=0,
                    disputed_task_count=0,
                    incident_status=r6_packet.incident_status
                    if kind == "stop_incident"
                    else None,
                    reviewed_at=frozen_at + timedelta(seconds=1),
                    valid_until=anchor.valid_until,
                )
                for kind in kinds
            ),
            assembled_at=frozen_at + timedelta(seconds=2),
        )
        return Package(
            anchor,
            r6_anchor,
            r6_packet,
            r6_result,
            self.r6.r5.protocol,
            self.r6.closeout,
            self.r6.r5_result,
            reviews,
            now,
        )

    def test_descriptive_source_coverage_is_only_reviewable(self) -> None:
        result = _assess(self.package())
        self.assertEqual((result.status, result.reasons), ("reviewable", ()))
        self.assertEqual(
            (result.required_source_count, result.reviewed_source_count), (9, 9)
        )
        self.assertEqual(result.assignment_count, 2)
        self.assertFalse(result.source_custody_verified)
        self.assertFalse(result.protected_outcomes_reviewed)
        self.assertFalse(result.assessment_authorized)
        self.assertFalse(result.comparative_claim_authorized)
        self.assertFalse(result.next_cohort_authorized)
        self.assertFalse(result.dispatch_authorized)

    def test_registered_comparison_requires_both_source_reviews(self) -> None:
        package = self.package(comparison=True)
        result = _assess(package)
        self.assertEqual(
            (result.status, result.required_source_count), ("reviewable", 11)
        )
        changed = package.reviews.model_copy(
            update={"reviews": package.reviews.reviews[:-1]}
        )
        result = _assess(replace(package, reviews=changed))
        self.assertIn("source_coverage_invalid", result.reasons)

    def test_missing_rejected_and_substituted_sources_block(self) -> None:
        package = self.package()
        for change in (
            {"decision": "reject"},
            {"decision": "unavailable"},
            {"artifact_sha256": _sha("substituted")},
        ):
            rows = list(package.reviews.reviews)
            rows[1] = rows[1].model_copy(update=change)
            changed = package.reviews.model_copy(update={"reviews": tuple(rows)})
            self.assertIn(
                "source_review_invalid",
                _assess(replace(package, reviews=changed)).reasons,
            )
        changed = package.reviews.model_copy(
            update={"reviews": package.reviews.reviews[:-1]}
        )
        self.assertIn(
            "source_coverage_invalid",
            _assess(replace(package, reviews=changed)).reasons,
        )

    def test_favorable_subset_unknown_dispute_and_incident_block(self) -> None:
        package = self.package()
        for change in (
            {"covered_task_count": 1},
            {"unknown_task_count": 1},
            {"disputed_task_count": 1},
            {"roster_sha256": _sha("subset")},
        ):
            rows = list(package.reviews.reviews)
            rows[1] = rows[1].model_copy(update=change)
            changed = package.reviews.model_copy(update={"reviews": tuple(rows)})
            self.assertIn(
                "source_review_invalid",
                _assess(replace(package, reviews=changed)).reasons,
            )
        rows = list(package.reviews.reviews)
        incident = next(i for i, row in enumerate(rows) if row.kind == "stop_incident")
        rows[incident] = rows[incident].model_copy(update={"incident_status": "severe"})
        changed = package.reviews.model_copy(update={"reviews": tuple(rows)})
        self.assertIn(
            "source_review_invalid", _assess(replace(package, reviews=changed)).reasons
        )

    def test_rebound_packet_result_and_upstream_handoff_block(self) -> None:
        package = self.package()
        changed = package.r6_packet.model_copy(update={"settled_microusd": 0})
        self.assertIn(
            "anchor_binding_mismatch",
            _assess(replace(package, r6_packet=changed)).reasons,
        )
        changed_result = package.r6_result.model_copy(
            update={"r5_reproduction_checked": False}
        )
        self.assertIn(
            "r6_handoff_invalid",
            _assess(replace(package, r6_result=changed_result)).reasons,
        )
        changed_reviews = package.reviews.model_copy(
            update={"upstream_handoff_sha256": _sha("wrong-upstream")}
        )
        self.assertIn(
            "review_index_binding_mismatch",
            _assess(replace(package, reviews=changed_reviews)).reasons,
        )

    def test_stale_or_same_person_review_blocks(self) -> None:
        package = self.package()
        rows = list(package.reviews.reviews)
        rows[0] = rows[0].model_copy(update={"reviewer_id": rows[0].producer_id})
        changed = package.reviews.model_copy(update={"reviews": tuple(rows)})
        self.assertIn(
            "source_review_invalid", _assess(replace(package, reviews=changed)).reasons
        )
        self.assertIn(
            "review_window_or_roles_invalid",
            _assess(replace(package, now=package.anchor.valid_until)).reasons,
        )

    def test_cli_writes_private_metadata_only_result(self) -> None:
        package = self.package()
        with TemporaryDirectory() as directory:
            paths = [Path(directory) / f"{n}.json" for n in range(9)]
            inputs = (
                package.anchor,
                package.r6_anchor,
                package.r6_packet,
                package.r6_result,
                package.protocol,
                package.closeout,
                package.r5_result,
                package.reviews,
            )
            for path, value in zip(paths[:8], inputs, strict=True):
                path.write_text(value.model_dump_json())
            with redirect_stdout(io.StringIO()) as output:
                code = main(
                    [*(str(path) for path in paths), "--now", package.now.isoformat()]
                )
            self.assertEqual(code, 0)
            self.assertIn("reviewable", output.getvalue())
            self.assertEqual(stat.S_IMODE(paths[-1].stat().st_mode), 0o600)
            contents = paths[-1].read_text()
            self.assertNotIn("source-reviewer", contents)
            self.assertNotIn("source-producer", contents)
