"""Sealed context-policy arms and metadata-only independent label inventory."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.authentication import GradingTrustPolicy
from mos_eisley.evaluation.models import Split

_LABEL_DOMAIN = b"mos-eisley/independent-label-claim/v1\x00"
_TARGET_COMPONENTS = (
    "bounded_work_units",
    "explicit_checkpoints",
    "narrow_tool_views",
    "task_profiles",
)
_OUTCOME_METRICS = (
    "completion",
    "missed_evidence",
    "stale_state_error",
    "verifier_disagreement",
    "harmful_action",
    "cumulative_input",
    "latency",
    "whole_task_cost",
)

EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
ProbabilityPpm = Annotated[int, Field(ge=1, le=1_000_000)]
LabelClass = Literal["clean", "defective"]
LabelSource = Literal["ordinary_task", "seeded_mutant", "historical_bug"]
SamplingFrame = Literal[
    "random_ordinary_audit", "selected_challenge", "historical_case"
]
ExclusionReason = Literal[
    "grader_disagreement",
    "selection_probability_unknown",
    "label_observation_probability_unknown",
]
ContextComponent = Literal[
    "existing_selection",
    "bounded_work_units",
    "explicit_checkpoints",
    "narrow_tool_views",
    "task_profiles",
]
OutcomeMetric = Literal[
    "completion",
    "missed_evidence",
    "stale_state_error",
    "verifier_disagreement",
    "harmful_action",
    "cumulative_input",
    "latency",
    "whole_task_cost",
]


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


class IndependentLabelClaim(Contract):
    """A grader's metadata-only ground-truth decision for one private case."""

    schema_version: Literal[1] = 1
    case_id: Digest
    split: Split
    case_artifact_sha256: Digest
    independence_group: Digest
    label_class: LabelClass
    expected_finding_count: Annotated[int, Field(ge=0, le=50)]
    source: LabelSource
    sampling_frame: SamplingFrame
    sampling_manifest_sha256: Digest
    selection_probability_ppm: ProbabilityPpm | None
    label_observation_probability_ppm: ProbabilityPpm | None
    rubric_sha256: Digest
    grader_id: Identifier
    completed_at: Annotated[
        str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    ]
    holdout_session_inspected: Literal[False] = False
    session_outcomes_included: Literal[False] = False

    @field_validator("completed_at")
    @classmethod
    def valid_utc_timestamp(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as error:
            raise ValueError("completion time must be a valid UTC timestamp") from error
        return value

    @model_validator(mode="after")
    def coherent_label(self) -> Self:
        if (self.label_class == "clean") != (self.expected_finding_count == 0):
            raise ValueError("clean labels must have zero expected findings")
        if self.source == "ordinary_task" and self.sampling_frame not in {
            "random_ordinary_audit",
            "selected_challenge",
        }:
            raise ValueError("ordinary tasks require an ordinary-task sampling frame")
        if self.source == "historical_bug" and self.sampling_frame != "historical_case":
            raise ValueError("historical bugs require the historical sampling frame")
        if (
            self.source == "seeded_mutant"
            and self.sampling_frame != "selected_challenge"
        ):
            raise ValueError("seeded mutants require the selected-challenge frame")
        if self.source in {"seeded_mutant", "historical_bug"} and self.label_class != (
            "defective"
        ):
            raise ValueError("mutant and historical-bug sources must be defective")
        return self

    @property
    def claim_sha256(self) -> str:
        return digest(canonical_bytes(self))


class LabelClaimSignature(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    signer_id: Identifier
    public_key_sha256: Digest
    claim_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedLabelClaim(Contract):
    schema_version: Literal[1] = 1
    claim: IndependentLabelClaim
    signature: LabelClaimSignature

    @model_validator(mode="after")
    def bound_claim(self) -> Self:
        if (
            self.signature.signer_id != self.claim.grader_id
            or self.signature.claim_sha256 != self.claim.claim_sha256
        ):
            raise ValueError("signature does not identify this label claim")
        return self

    @property
    def signed_claim_sha256(self) -> str:
        return digest(canonical_bytes(self))


class IndependentLabelEvidence(Contract):
    """Two separately signed label claims for the same opaque case identity."""

    schema_version: Literal[1] = 1
    left: SignedLabelClaim
    right: SignedLabelClaim

    @model_validator(mode="after")
    def independent_pair(self) -> Self:
        if self.left.claim.case_id != self.right.claim.case_id:
            raise ValueError("label evidence must identify one case")
        if (
            self.left.signature.signer_id == self.right.signature.signer_id
            or self.left.signature.public_key_sha256
            == self.right.signature.public_key_sha256
        ):
            raise ValueError(
                "label evidence requires distinct grader identities and keys"
            )
        return self

    @property
    def evidence_sha256(self) -> str:
        return digest(canonical_bytes(self))


class IndependentLabelCatalog(Contract):
    schema_version: Literal[1] = 1
    grading_trust_policy_sha256: Digest
    evidence: Annotated[
        tuple[IndependentLabelEvidence, ...], Field(min_length=1, max_length=5000)
    ]

    @model_validator(mode="after")
    def canonical_cases(self) -> Self:
        case_ids = tuple(item.left.claim.case_id for item in self.evidence)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("label catalog case ids must be unique")
        if tuple(sorted(case_ids)) != case_ids:
            raise ValueError("label catalog cases must be sorted by case id")
        return self

    @property
    def catalog_sha256(self) -> str:
        return digest(canonical_bytes(self))


class EligibleLabel(Contract):
    case_id: Digest
    split: Split
    case_artifact_sha256: Digest
    independence_group: Digest
    label_class: LabelClass
    expected_finding_count: Annotated[int, Field(ge=0, le=50)]
    source: LabelSource
    sampling_frame: SamplingFrame
    sampling_manifest_sha256: Digest
    selection_probability_ppm: ProbabilityPpm
    label_observation_probability_ppm: ProbabilityPpm
    evidence_sha256: Digest


class ExcludedLabel(Contract):
    case_id: Digest
    evidence_sha256: Digest
    reasons: Annotated[tuple[ExclusionReason, ...], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def canonical_reasons(self) -> Self:
        if tuple(sorted(set(self.reasons))) != self.reasons:
            raise ValueError("label exclusion reasons must be unique and sorted")
        return self


class EligibleLabelInventory(Contract):
    """Metadata-only label inventory; it contains no case or session payload."""

    schema_version: Literal[1] = 1
    catalog_sha256: Digest
    grading_trust_policy_sha256: Digest
    rubric_sha256: Digest
    eligible: Annotated[tuple[EligibleLabel, ...], Field(max_length=5000)]
    excluded: Annotated[tuple[ExcludedLabel, ...], Field(max_length=5000)]
    calibration_clean: Annotated[int, Field(ge=0, le=5000)]
    calibration_defective: Annotated[int, Field(ge=0, le=5000)]
    holdout_clean: Annotated[int, Field(ge=0, le=5000)]
    holdout_defective: Annotated[int, Field(ge=0, le=5000)]
    calibration_independent_groups: Annotated[int, Field(ge=0, le=5000)]
    holdout_independent_groups: Annotated[int, Field(ge=0, le=5000)]
    calibration_random_ordinary_audit: Annotated[int, Field(ge=0, le=5000)]
    holdout_random_ordinary_audit: Annotated[int, Field(ge=0, le=5000)]
    holdout_sessions_inspected: Literal[False] = False
    session_outcomes_included: Literal[False] = False
    study_execution_authorized: Literal[False] = False
    promotion_ready: Literal[False] = False

    @model_validator(mode="after")
    def consistent_counts_and_groups(self) -> Self:
        eligible_ids = tuple(item.case_id for item in self.eligible)
        excluded_ids = tuple(item.case_id for item in self.excluded)
        if tuple(sorted(eligible_ids)) != eligible_ids:
            raise ValueError("eligible labels must be sorted by case id")
        if tuple(sorted(excluded_ids)) != excluded_ids:
            raise ValueError("excluded labels must be sorted by case id")
        if set(eligible_ids) & set(excluded_ids):
            raise ValueError("a label cannot be both eligible and excluded")
        artifact_ids = tuple(item.case_artifact_sha256 for item in self.eligible)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("eligible label case artifacts must be unique")
        group_splits: dict[str, Split] = {}
        for item in self.eligible:
            prior = group_splits.setdefault(item.independence_group, item.split)
            if prior != item.split:
                raise ValueError("an independence group cannot cross splits")
        expected = {
            "calibration_clean": sum(
                item.split == "calibration" and item.label_class == "clean"
                for item in self.eligible
            ),
            "calibration_defective": sum(
                item.split == "calibration" and item.label_class == "defective"
                for item in self.eligible
            ),
            "holdout_clean": sum(
                item.split == "holdout" and item.label_class == "clean"
                for item in self.eligible
            ),
            "holdout_defective": sum(
                item.split == "holdout" and item.label_class == "defective"
                for item in self.eligible
            ),
            "calibration_independent_groups": len(
                {
                    item.independence_group
                    for item in self.eligible
                    if item.split == "calibration"
                }
            ),
            "holdout_independent_groups": len(
                {
                    item.independence_group
                    for item in self.eligible
                    if item.split == "holdout"
                }
            ),
            "calibration_random_ordinary_audit": sum(
                item.split == "calibration"
                and item.sampling_frame == "random_ordinary_audit"
                for item in self.eligible
            ),
            "holdout_random_ordinary_audit": sum(
                item.split == "holdout"
                and item.sampling_frame == "random_ordinary_audit"
                for item in self.eligible
            ),
        }
        if any(getattr(self, field) != count for field, count in expected.items()):
            raise ValueError("label inventory counts are inconsistent")
        return self

    @property
    def inventory_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ContextPolicyArm(Contract):
    arm_id: Identifier
    kind: Literal["baseline", "full_candidate", "ablation"]
    availability: Literal["available", "unavailable"] = "available"
    implementation_sha256: Digest | None
    enabled_components: Annotated[
        tuple[ContextComponent, ...], Field(min_length=1, max_length=4)
    ]
    parent_arm_id: Identifier | None = None
    ablated_component: ContextComponent | None = None
    unavailable_reason: Identifier | None = None

    @model_validator(mode="after")
    def coherent_arm(self) -> Self:
        if tuple(sorted(set(self.enabled_components))) != self.enabled_components:
            raise ValueError("context-policy components must be unique and sorted")
        if self.availability == "available" and (
            self.implementation_sha256 is None or self.unavailable_reason is not None
        ):
            raise ValueError("available arms require an implementation and no reason")
        if self.availability == "unavailable" and (
            self.implementation_sha256 is not None or self.unavailable_reason is None
        ):
            raise ValueError("unavailable arms require a reason and no implementation")
        if self.kind == "ablation":
            if self.parent_arm_id is None or self.ablated_component is None:
                raise ValueError("ablation arms require a parent and removed component")
        elif self.parent_arm_id is not None or self.ablated_component is not None:
            raise ValueError(
                "only ablation arms identify a parent or removed component"
            )
        return self


class BaselineAblationPolicy(Contract):
    """Pre-registered matched context-policy comparison, never execution authority."""

    schema_version: Literal[1] = 1
    study_id: Identifier
    model_routes_sha256: Digest
    rubric_sha256: Digest
    quality_gate_sha256: Digest
    resource_plan_sha256: Digest
    label_inventory_sha256: Digest
    randomization_seed: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]
    follow_up_window_days: Annotated[int, Field(ge=1, le=365)]
    baseline_arm_id: Identifier
    full_candidate_arm_id: Identifier
    arms: Annotated[tuple[ContextPolicyArm, ...], Field(min_length=6, max_length=6)]
    outcome_metrics: tuple[OutcomeMetric, ...] = _OUTCOME_METRICS
    assignment_rule: Literal["matched_case_balanced_order"] = (
        "matched_case_balanced_order"
    )
    missing_label_rule: Literal["exclude_and_report_no_imputation"] = (
        "exclude_and_report_no_imputation"
    )
    holdout_rule: Literal["seal_before_holdout_then_evaluate_once"] = (
        "seal_before_holdout_then_evaluate_once"
    )
    cost_rule: Literal["include_every_stage_child_retry_repair_and_abandonment"] = (
        "include_every_stage_child_retry_repair_and_abandonment"
    )
    baseline_retention_rule: Literal["inconclusive_retains_baseline"] = (
        "inconclusive_retains_baseline"
    )
    study_execution_authorized: Literal[False] = False
    promotion_ready: Literal[False] = False

    @model_validator(mode="after")
    def complete_baseline_and_ablations(self) -> Self:
        if self.outcome_metrics != _OUTCOME_METRICS:
            raise ValueError("context study must retain the complete outcome family")
        arm_ids = tuple(item.arm_id for item in self.arms)
        if len(arm_ids) != len(set(arm_ids)) or tuple(sorted(arm_ids)) != arm_ids:
            raise ValueError("context-policy arms must be unique and sorted")
        by_id = {item.arm_id: item for item in self.arms}
        baseline = by_id.get(self.baseline_arm_id)
        candidate = by_id.get(self.full_candidate_arm_id)
        if baseline is None or baseline.kind != "baseline":
            raise ValueError("baseline arm id must identify the baseline")
        if candidate is None or candidate.kind != "full_candidate":
            raise ValueError("candidate arm id must identify the full candidate")
        if baseline.enabled_components != ("existing_selection",):
            raise ValueError("baseline must preserve the existing selection policy")
        if candidate.enabled_components != _TARGET_COMPONENTS:
            raise ValueError("full candidate must enable every target component")
        if (
            baseline.availability != "available"
            or candidate.availability != "available"
        ):
            raise ValueError("baseline and full candidate must be available")
        ablations = [item for item in self.arms if item.kind == "ablation"]
        removed_components: list[ContextComponent] = []
        for arm in ablations:
            if arm.ablated_component is None:
                raise ValueError("ablation arm is missing its removed component")
            removed_components.append(arm.ablated_component)
        removed = tuple(sorted(removed_components))
        if removed != _TARGET_COMPONENTS:
            raise ValueError("policy must declare exactly one ablation per component")
        for arm in ablations:
            assert arm.ablated_component is not None
            if arm.parent_arm_id != candidate.arm_id or arm.enabled_components != tuple(
                component
                for component in candidate.enabled_components
                if component != arm.ablated_component
            ):
                raise ValueError("ablation must remove exactly one candidate component")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SealedBaselineAblationPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["sealed_context_baseline_ablation_policy"] = (
        "sealed_context_baseline_ablation_policy"
    )
    policy: BaselineAblationPolicy
    policy_sha256: Digest
    label_inventory_sha256: Digest
    eligible_label_count: Annotated[int, Field(ge=4, le=5000)]
    available_arm_ids: Annotated[
        tuple[Identifier, ...], Field(min_length=2, max_length=16)
    ]
    unavailable_arm_ids: Annotated[tuple[Identifier, ...], Field(max_length=14)]
    holdout_sessions_inspected: Literal[False] = False
    session_outcomes_included: Literal[False] = False
    study_execution_authorized: Literal[False] = False
    promotion_ready: Literal[False] = False

    @model_validator(mode="after")
    def consistent_seal(self) -> Self:
        available = tuple(
            item.arm_id for item in self.policy.arms if item.availability == "available"
        )
        unavailable = tuple(
            item.arm_id
            for item in self.policy.arms
            if item.availability == "unavailable"
        )
        if (
            self.policy_sha256 != self.policy.policy_sha256
            or self.label_inventory_sha256 != self.policy.label_inventory_sha256
            or self.available_arm_ids != available
            or self.unavailable_arm_ids != unavailable
        ):
            raise ValueError("sealed baseline/ablation policy is inconsistent")
        return self

    @property
    def sealed_policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_independent_label_claim(
    claim: IndependentLabelClaim, private_key: bytes
) -> SignedLabelClaim:
    """Sign one metadata-only claim; callers retain private-key custody."""
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
    except (UnsupportedAlgorithm, ValueError):
        raise ValueError("Ed25519 signing unavailable or private key invalid") from None
    public_key = key.public_key().public_bytes_raw()
    return SignedLabelClaim(
        claim=claim,
        signature=LabelClaimSignature(
            signer_id=claim.grader_id,
            public_key_sha256=digest(public_key),
            claim_sha256=claim.claim_sha256,
            signature_base64=base64.b64encode(
                key.sign(_LABEL_DOMAIN + canonical_bytes(claim))
            ).decode("ascii"),
        ),
    )


def _verify_label_claim(signed: SignedLabelClaim, policy: GradingTrustPolicy) -> None:
    claim = signed.claim
    if claim.rubric_sha256 != policy.rubric_sha256:
        raise ValueError("label claim rubric differs from the trust policy")
    matches = [
        item for item in policy.adjudicators if item.adjudicator_id == claim.grader_id
    ]
    if len(matches) != 1:
        raise ValueError("label grader is not trusted by this policy")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("label signature key differs from the trust policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _LABEL_DOMAIN + canonical_bytes(claim),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError("label claim signature verification failed") from None


def _claim_decision(claim: IndependentLabelClaim) -> tuple[object, ...]:
    return (
        claim.split,
        claim.case_artifact_sha256,
        claim.independence_group,
        claim.label_class,
        claim.expected_finding_count,
        claim.source,
        claim.sampling_frame,
        claim.sampling_manifest_sha256,
        claim.selection_probability_ppm,
        claim.label_observation_probability_ppm,
        claim.rubric_sha256,
    )


def inventory_independent_labels(
    catalog: IndependentLabelCatalog, policy: GradingTrustPolicy
) -> EligibleLabelInventory:
    """Verify label receipts and inventory only opaque eligibility metadata."""
    if catalog.grading_trust_policy_sha256 != policy.policy_sha256:
        raise ValueError("label catalog does not match the grading trust policy")
    eligible: list[EligibleLabel] = []
    excluded: list[ExcludedLabel] = []
    for evidence in catalog.evidence:
        _verify_label_claim(evidence.left, policy)
        _verify_label_claim(evidence.right, policy)
        left = evidence.left.claim
        right = evidence.right.claim
        reasons: list[ExclusionReason] = []
        if _claim_decision(left) != _claim_decision(right):
            reasons.append("grader_disagreement")
        else:
            if left.selection_probability_ppm is None:
                reasons.append("selection_probability_unknown")
            if left.label_observation_probability_ppm is None:
                reasons.append("label_observation_probability_unknown")
        if reasons:
            excluded.append(
                ExcludedLabel(
                    case_id=left.case_id,
                    evidence_sha256=evidence.evidence_sha256,
                    reasons=tuple(sorted(reasons)),
                )
            )
            continue
        assert left.selection_probability_ppm is not None
        assert left.label_observation_probability_ppm is not None
        eligible.append(
            EligibleLabel(
                case_id=left.case_id,
                split=left.split,
                case_artifact_sha256=left.case_artifact_sha256,
                independence_group=left.independence_group,
                label_class=left.label_class,
                expected_finding_count=left.expected_finding_count,
                source=left.source,
                sampling_frame=left.sampling_frame,
                sampling_manifest_sha256=left.sampling_manifest_sha256,
                selection_probability_ppm=left.selection_probability_ppm,
                label_observation_probability_ppm=(
                    left.label_observation_probability_ppm
                ),
                evidence_sha256=evidence.evidence_sha256,
            )
        )
    eligible_tuple = tuple(sorted(eligible, key=lambda item: item.case_id))
    excluded_tuple = tuple(sorted(excluded, key=lambda item: item.case_id))
    return EligibleLabelInventory(
        catalog_sha256=catalog.catalog_sha256,
        grading_trust_policy_sha256=policy.policy_sha256,
        rubric_sha256=policy.rubric_sha256,
        eligible=eligible_tuple,
        excluded=excluded_tuple,
        calibration_clean=sum(
            item.split == "calibration" and item.label_class == "clean"
            for item in eligible_tuple
        ),
        calibration_defective=sum(
            item.split == "calibration" and item.label_class == "defective"
            for item in eligible_tuple
        ),
        holdout_clean=sum(
            item.split == "holdout" and item.label_class == "clean"
            for item in eligible_tuple
        ),
        holdout_defective=sum(
            item.split == "holdout" and item.label_class == "defective"
            for item in eligible_tuple
        ),
        calibration_independent_groups=len(
            {
                item.independence_group
                for item in eligible_tuple
                if item.split == "calibration"
            }
        ),
        holdout_independent_groups=len(
            {
                item.independence_group
                for item in eligible_tuple
                if item.split == "holdout"
            }
        ),
        calibration_random_ordinary_audit=sum(
            item.split == "calibration"
            and item.sampling_frame == "random_ordinary_audit"
            for item in eligible_tuple
        ),
        holdout_random_ordinary_audit=sum(
            item.split == "holdout" and item.sampling_frame == "random_ordinary_audit"
            for item in eligible_tuple
        ),
    )


def verify_eligible_label_inventory(
    catalog: IndependentLabelCatalog,
    policy: GradingTrustPolicy,
    artifact: EligibleLabelInventory,
) -> None:
    """Rebuild stored eligibility from its signed claims and trust policy."""
    rebuilt = inventory_independent_labels(catalog, policy)
    if rebuilt != artifact:
        raise ValueError("eligible label inventory provenance mismatch")


def seal_baseline_ablation_policy(
    policy: BaselineAblationPolicy,
    catalog: IndependentLabelCatalog,
    grading_policy: GradingTrustPolicy,
    inventory: EligibleLabelInventory,
) -> SealedBaselineAblationPolicy:
    """Seal exact policy arms using inventory metadata, never session outcomes."""
    verify_eligible_label_inventory(catalog, grading_policy, inventory)
    if policy.label_inventory_sha256 != inventory.inventory_sha256:
        raise ValueError("baseline/ablation policy does not match the label inventory")
    if policy.rubric_sha256 != inventory.rubric_sha256:
        raise ValueError("baseline/ablation rubric differs from the label inventory")
    required = (
        inventory.calibration_clean,
        inventory.calibration_defective,
        inventory.holdout_clean,
        inventory.holdout_defective,
        inventory.calibration_random_ordinary_audit,
        inventory.holdout_random_ordinary_audit,
    )
    if any(value == 0 for value in required):
        raise ValueError(
            "policy sealing requires clean, defective and random-audit labels "
            "in both splits"
        )
    return SealedBaselineAblationPolicy(
        policy=policy,
        policy_sha256=policy.policy_sha256,
        label_inventory_sha256=inventory.inventory_sha256,
        eligible_label_count=len(inventory.eligible),
        available_arm_ids=tuple(
            item.arm_id for item in policy.arms if item.availability == "available"
        ),
        unavailable_arm_ids=tuple(
            item.arm_id for item in policy.arms if item.availability == "unavailable"
        ),
    )


def verify_sealed_baseline_ablation_policy(
    catalog: IndependentLabelCatalog,
    grading_policy: GradingTrustPolicy,
    inventory: EligibleLabelInventory,
    artifact: SealedBaselineAblationPolicy,
) -> None:
    rebuilt = seal_baseline_ablation_policy(
        artifact.policy, catalog, grading_policy, inventory
    )
    if rebuilt != artifact:
        raise ValueError("sealed baseline/ablation policy provenance mismatch")
