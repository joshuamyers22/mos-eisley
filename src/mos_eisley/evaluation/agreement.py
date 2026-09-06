"""Descriptive agreement between two separately attributed grading artifacts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    FindingJudgment,
    GradingBatch,
    validate_adjudication,
)
from mos_eisley.evaluation.models import Rate


class GradingConflict(Contract):
    sample_id: Digest
    finding_index: Annotated[int, Field(ge=0, lt=50)]
    left: FindingJudgment
    right: FindingJudgment


class AgreementReport(Contract):
    schema_version: Literal[1] = 1
    method: Literal["exact_finding_labels"] = "exact_finding_labels"
    grading_batch_sha256: Digest
    left_adjudication_sha256: Digest
    right_adjudication_sha256: Digest
    rubric_sha256: Digest
    compared_samples: Annotated[int, Field(ge=0)]
    agreed_samples: Annotated[int, Field(ge=0)]
    compared_findings: Annotated[int, Field(ge=0)]
    agreed_findings: Annotated[int, Field(ge=0)]
    unresolved_findings: Annotated[int, Field(ge=0)]
    finding_agreement_rate: Rate | None
    conflicts: tuple[GradingConflict, ...]
    independence_verified: Literal[False] = False
    promotion_ready: Literal[False] = False

    @property
    def report_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _label_key(item: FindingJudgment) -> tuple[str, tuple[str, ...], int | None]:
    return (
        item.disposition,
        tuple(sorted(item.expected_finding_ids)),
        item.duplicate_of,
    )


def compare_adjudications(
    batch: GradingBatch, left: AdjudicationSet, right: AdjudicationSet
) -> AgreementReport:
    """Keep disagreement and abstention visible without automatically resolving it."""
    validate_adjudication(batch, left, allow_unresolved=True)
    validate_adjudication(batch, right, allow_unresolved=True)
    if left.adjudicator.adjudicator_id == right.adjudicator.adjudicator_id:
        raise ValueError("agreement requires distinct adjudicator identifiers")
    if left.adjudicator.rubric_sha256 != right.adjudicator.rubric_sha256:
        raise ValueError("agreement requires the same rubric")
    if left.adjudicator.method != right.adjudicator.method:
        raise ValueError("agreement cannot mix fixture and human methods")
    left_items = {item.sample_id: item for item in left.judgments}
    right_items = {item.sample_id: item for item in right.judgments}
    conflicts: list[GradingConflict] = []
    compared = agreed = unresolved = agreed_samples = 0
    for sample_id in sorted(left_items):
        lhs = {item.finding_index: item for item in left_items[sample_id].findings}
        rhs = {item.finding_index: item for item in right_items[sample_id].findings}
        sample_agreed = True
        for index in sorted(lhs):
            first, second = lhs[index], rhs[index]
            abstained = "unresolved" in (first.disposition, second.disposition)
            compared += 1
            unresolved += int(abstained)
            if not abstained and _label_key(first) == _label_key(second):
                agreed += 1
            else:
                sample_agreed = False
                conflicts.append(
                    GradingConflict(
                        sample_id=sample_id,
                        finding_index=index,
                        left=first,
                        right=second,
                    )
                )
        agreed_samples += int(sample_agreed)
    return AgreementReport(
        grading_batch_sha256=batch.grading_batch_sha256,
        left_adjudication_sha256=left.adjudication_sha256,
        right_adjudication_sha256=right.adjudication_sha256,
        rubric_sha256=left.adjudicator.rubric_sha256,
        compared_samples=len(batch.items),
        agreed_samples=agreed_samples,
        compared_findings=compared,
        agreed_findings=agreed,
        unresolved_findings=unresolved,
        finding_agreement_rate=agreed / compared if compared else None,
        conflicts=tuple(conflicts),
    )
