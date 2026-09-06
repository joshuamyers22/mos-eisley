"""Bind retained skill bytes to current promotion evidence without installing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.skills import SkillIdentity, SkillPackageArchive
from mos_eisley.evaluation.models import EvaluationDataset, SweepPlan
from mos_eisley.evaluation.skill_comparison import (
    SealedSkillComparison,
    SkillComparisonReport,
    SkillHoldoutUseClaim,
)
from mos_eisley.evaluation.skill_promotion import (
    AuthenticatedSkillPromotion,
    SkillEvaluationLineage,
    SkillPromotionAuthorityPolicy,
    verify_authenticated_skill_promotion,
)
from mos_eisley.run.skills import verify_skill_archive

UtcTimestamp = Annotated[datetime, Field()]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class SkillReleaseEvidence(Contract):
    """Exact current evidence binding; deliberately grants no deployment authority."""

    schema_version: Literal[1] = 1
    mode: Literal["skill_release_evidence"] = "skill_release_evidence"
    archive_sha256: Digest
    promotion_receipt_sha256: Digest
    candidate_skill: SkillIdentity
    archive: SkillPackageArchive
    promotion: AuthenticatedSkillPromotion
    checked_at: UtcTimestamp
    valid_until: UtcTimestamp
    package_retained: Literal[True] = True
    promotion_ready: Literal[True] = True
    installation_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @field_validator("checked_at", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def exact_current_binding(self) -> Self:
        if (
            self.archive_sha256 != self.archive.archive_sha256
            or self.promotion_receipt_sha256 != self.promotion.promotion_receipt_sha256
            or self.candidate_skill != self.archive.descriptor.identity
            or self.candidate_skill != self.promotion.candidate_skill
            or self.valid_until != self.promotion.valid_until
            or not self.promotion.promotion_ready
            or not self.promotion.authenticated_at <= self.checked_at < self.valid_until
        ):
            raise ValueError("skill release evidence source or validity mismatch")
        return self

    @property
    def release_evidence_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def check_current(self, now: datetime | None = None) -> None:
        current = now if now is not None else datetime.now(UTC)
        _require_utc(current)
        if not self.checked_at <= current < self.valid_until:
            raise ValueError("skill release evidence is outside its validity window")


def bind_skill_release_evidence(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    authority_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    now: datetime,
) -> SkillReleaseEvidence:
    """Reverify every source and bind the current receipt to exact retained bytes."""

    current = _require_utc(now)
    verify_skill_archive(archive)
    verify_authenticated_skill_promotion(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        authority_policy,
    )
    if not promotion.promotion_ready:
        raise ValueError("skill release evidence requires passing promotion")
    if archive.descriptor.identity != promotion.candidate_skill:
        raise ValueError("retained skill package differs from promoted skill")
    if not promotion.authenticated_at <= current < promotion.valid_until:
        raise ValueError("skill promotion receipt is not current")
    return SkillReleaseEvidence(
        archive_sha256=archive.archive_sha256,
        promotion_receipt_sha256=promotion.promotion_receipt_sha256,
        candidate_skill=promotion.candidate_skill,
        archive=archive,
        promotion=promotion,
        checked_at=current,
        valid_until=promotion.valid_until,
    )


def verify_skill_release_evidence(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration: SkillEvaluationLineage,
    holdout: SkillEvaluationLineage,
    sealed: SealedSkillComparison,
    holdout_claim: SkillHoldoutUseClaim,
    calibration_report: SkillComparisonReport,
    holdout_report: SkillComparisonReport,
    promotion: AuthenticatedSkillPromotion,
    authority_policy: SkillPromotionAuthorityPolicy,
    archive: SkillPackageArchive,
    artifact: SkillReleaseEvidence,
    now: datetime | None = None,
) -> None:
    """Rebuild a binding and optionally require that it remains current now."""

    rebuilt = bind_skill_release_evidence(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        holdout_claim,
        calibration_report,
        holdout_report,
        promotion,
        authority_policy,
        archive,
        artifact.checked_at,
    )
    if rebuilt != artifact:
        raise ValueError("skill release evidence provenance mismatch")
    artifact.check_current(now)
