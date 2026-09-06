"""Pre-registered contracts for empirical prompt-difficulty routing studies."""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    Text,
    canonical_bytes,
    digest,
)
from mos_eisley.evaluation.models import EvaluationDataset, SweepPlan


class ObservablePromptFeatures(Contract):
    """One exact, label-free feature vector available before dispatch."""

    schema_version: Literal[1] = 1
    role: Identifier
    input_bytes: Annotated[int, Field(gt=0, le=1_000_000)]
    changed_files: Annotated[int, Field(ge=0, le=100_000)]
    changed_lines: Annotated[int, Field(ge=0, le=10_000_000)]
    language_count: Annotated[int, Field(ge=0, le=1_000)]
    output_contract: Identifier
    tool_requirements: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()
    risk_tags: Annotated[tuple[Identifier, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def canonical_and_consistent(self) -> Self:
        for label, values in (
            ("tool requirements", self.tool_requirements),
            ("risk tags", self.risk_tags),
        ):
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{label} must be unique and sorted")
        if self.changed_files == 0 and (
            self.changed_lines != 0 or self.language_count != 0
        ):
            raise ValueError(
                "line and language counts require at least one changed file"
            )
        return self


class CaseFeatureAssignment(Contract):
    case_id: Identifier
    brief_sha256: Digest
    features: ObservablePromptFeatures


class PromptFeatureManifest(Contract):
    """An exact dataset-to-feature join with no evaluation outcomes."""

    schema_version: Literal[1] = 1
    input_measurement: Literal["canonical_brief_bytes_v1"] = "canonical_brief_bytes_v1"
    dataset_sha256: Digest
    assignments: Annotated[
        tuple[CaseFeatureAssignment, ...], Field(min_length=2, max_length=5000)
    ]

    @model_validator(mode="after")
    def unique_and_canonical(self) -> Self:
        case_ids = tuple(item.case_id for item in self.assignments)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("feature assignments must have unique case ids")
        if tuple(sorted(case_ids)) != case_ids:
            raise ValueError("feature assignments must be sorted by case id")
        return self

    @property
    def manifest_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def validate_dataset(self, dataset: EvaluationDataset) -> None:
        if self.dataset_sha256 != dataset.dataset_sha256:
            raise ValueError("feature manifest does not match the evaluation dataset")
        cases = {case.id: case for case in dataset.cases}
        assignments = {item.case_id: item for item in self.assignments}
        if set(assignments) != set(cases):
            raise ValueError(
                "feature manifest must exactly cover the evaluation dataset"
            )
        for case_id, case in cases.items():
            item = assignments[case_id]
            if item.brief_sha256 != case.brief.brief_id:
                raise ValueError("feature assignment brief identity mismatch")
            if item.features.input_bytes != len(canonical_bytes(case.brief)):
                raise ValueError("feature assignment input byte count mismatch")
            if item.features.risk_tags != tuple(sorted(case.risk_tags)):
                raise ValueError("feature assignment risk tags differ from the dataset")


class FeaturePartition(Contract):
    """Pre-registered numeric bins; categorical features remain exact."""

    schema_version: Literal[1] = 1
    input_bytes_upper_bounds: Annotated[tuple[int, ...], Field(max_length=64)] = ()
    changed_files_upper_bounds: Annotated[tuple[int, ...], Field(max_length=64)] = ()
    changed_lines_upper_bounds: Annotated[tuple[int, ...], Field(max_length=64)] = ()
    language_count_upper_bounds: Annotated[tuple[int, ...], Field(max_length=64)] = ()

    @model_validator(mode="after")
    def increasing_bounds(self) -> Self:
        fields = (
            ("input byte", self.input_bytes_upper_bounds, 1),
            ("changed file", self.changed_files_upper_bounds, 0),
            ("changed line", self.changed_lines_upper_bounds, 0),
            ("language count", self.language_count_upper_bounds, 0),
        )
        for label, bounds, minimum in fields:
            if any(value < minimum for value in bounds):
                raise ValueError(f"{label} bounds are outside the feature range")
            if tuple(sorted(set(bounds))) != bounds:
                raise ValueError(f"{label} bounds must be unique and increasing")
        return self

    def profile(self, features: ObservablePromptFeatures) -> DifficultyProfile:
        return DifficultyProfile(
            role=features.role,
            input_bytes_bucket=bisect_left(
                self.input_bytes_upper_bounds, features.input_bytes
            ),
            changed_files_bucket=bisect_left(
                self.changed_files_upper_bounds, features.changed_files
            ),
            changed_lines_bucket=bisect_left(
                self.changed_lines_upper_bounds, features.changed_lines
            ),
            language_count_bucket=bisect_left(
                self.language_count_upper_bounds, features.language_count
            ),
            output_contract=features.output_contract,
            tool_requirements=features.tool_requirements,
            risk_tags=features.risk_tags,
        )


class DifficultyProfile(Contract):
    """Interpretable partition key derived without labels or a model call."""

    schema_version: Literal[1] = 1
    role: Identifier
    input_bytes_bucket: Annotated[int, Field(ge=0, le=64)]
    changed_files_bucket: Annotated[int, Field(ge=0, le=64)]
    changed_lines_bucket: Annotated[int, Field(ge=0, le=64)]
    language_count_bucket: Annotated[int, Field(ge=0, le=64)]
    output_contract: Identifier
    tool_requirements: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()
    risk_tags: Annotated[tuple[Identifier, ...], Field(max_length=32)] = ()

    @property
    def profile_id(self) -> str:
        return digest(canonical_bytes(self))


class RoleRouteConstraint(Contract):
    """Operator-reviewed hard floor and conservative fallback for one role."""

    role: Identifier
    minimum_rationale: Text
    permitted_candidate_ids: Annotated[
        tuple[Digest, ...], Field(min_length=1, max_length=128)
    ]
    fallback_candidate_id: Digest

    @model_validator(mode="after")
    def canonical_candidates(self) -> Self:
        if tuple(sorted(set(self.permitted_candidate_ids))) != (
            self.permitted_candidate_ids
        ):
            raise ValueError("permitted candidate ids must be unique and sorted")
        if self.fallback_candidate_id not in self.permitted_candidate_ids:
            raise ValueError("role fallback must satisfy the declared route floor")
        return self


class RoutingStudyProtocol(Contract):
    """A sealed design artifact; it cannot activate or promote a router."""

    schema_version: Literal[1] = 1
    study_id: Identifier
    activation_authorized: Literal[False] = False
    feature_schema_version: Literal[1] = 1
    dataset_sha256: Digest
    plan_sha256: Digest
    feature_manifest_sha256: Digest
    feature_partition: FeaturePartition
    selection_objective: Literal["min_mean_cost_then_p95_latency_then_candidate_id"] = (
        "min_mean_cost_then_p95_latency_then_candidate_id"
    )
    missing_cost_evidence: Literal["profile_uncalibrated"] = "profile_uncalibrated"
    uncalibrated_action: Literal["role_fallback", "fail_closed"]
    holdout_rule: Literal["freeze_then_evaluate_once"] = "freeze_then_evaluate_once"
    statistical_family: Literal["all_profiles_routes_metrics_both_splits"] = (
        "all_profiles_routes_metrics_both_splits"
    )
    role_constraints: Annotated[
        tuple[RoleRouteConstraint, ...], Field(min_length=1, max_length=32)
    ]

    @model_validator(mode="after")
    def unique_and_canonical_roles(self) -> Self:
        roles = tuple(item.role for item in self.role_constraints)
        if len(roles) != len(set(roles)):
            raise ValueError("routing study roles must be unique")
        if tuple(sorted(roles)) != roles:
            raise ValueError("routing study roles must be sorted")
        return self

    @property
    def protocol_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def validate_sources(
        self,
        dataset: EvaluationDataset,
        plan: SweepPlan,
        manifest: PromptFeatureManifest,
    ) -> None:
        plan.validate_dataset(dataset)
        manifest.validate_dataset(dataset)
        if self.dataset_sha256 != dataset.dataset_sha256:
            raise ValueError("routing study does not match the evaluation dataset")
        if self.plan_sha256 != plan.plan_sha256:
            raise ValueError("routing study does not match the sweep plan")
        if self.feature_manifest_sha256 != manifest.manifest_sha256:
            raise ValueError("routing study does not match the feature manifest")

        route_ids = {route.candidate_id for route in plan.routes}
        constraints = {item.role: item for item in self.role_constraints}
        feature_roles = {item.features.role for item in manifest.assignments}
        if set(constraints) != feature_roles:
            raise ValueError("routing study roles must exactly cover feature roles")
        for constraint in self.role_constraints:
            if not set(constraint.permitted_candidate_ids) <= route_ids:
                raise ValueError("routing study permits a route outside the sweep plan")

        by_profile_split: dict[tuple[str, str], list[bool]] = defaultdict(list)
        cases = {case.id: case for case in dataset.cases}
        for assignment in manifest.assignments:
            case = cases[assignment.case_id]
            profile_id = self.feature_partition.profile(assignment.features).profile_id
            by_profile_split[(profile_id, case.split)].append(
                bool(case.expected_findings)
            )
        for profile_id in self.profile_ids(manifest):
            for split in ("calibration", "holdout"):
                labels = by_profile_split.get((profile_id, split), [])
                if not labels or not any(labels) or all(labels):
                    raise ValueError(
                        "every profile and split needs clean and defective cases"
                    )

    def profile_ids(self, manifest: PromptFeatureManifest) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    self.feature_partition.profile(item.features).profile_id
                    for item in manifest.assignments
                }
            )
        )


class SealedRoutingStudy(Contract):
    """Canonical receipt produced after validating every pre-registration source."""

    schema_version: Literal[1] = 1
    activation_authorized: Literal[False] = False
    protocol: RoutingStudyProtocol
    protocol_sha256: Digest
    dataset_sha256: Digest
    plan_sha256: Digest
    feature_manifest_sha256: Digest
    profile_ids: Annotated[tuple[Digest, ...], Field(min_length=1, max_length=5000)]

    @model_validator(mode="after")
    def consistent_protocol(self) -> Self:
        if (
            self.protocol_sha256 != self.protocol.protocol_sha256
            or self.dataset_sha256 != self.protocol.dataset_sha256
            or self.plan_sha256 != self.protocol.plan_sha256
            or self.feature_manifest_sha256 != self.protocol.feature_manifest_sha256
        ):
            raise ValueError("sealed routing study protocol identity mismatch")
        if tuple(sorted(set(self.profile_ids))) != self.profile_ids:
            raise ValueError(
                "sealed routing study profile ids must be unique and sorted"
            )
        return self

    @property
    def sealed_study_sha256(self) -> str:
        return digest(canonical_bytes(self))


def seal_routing_study(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    manifest: PromptFeatureManifest,
    protocol: RoutingStudyProtocol,
) -> SealedRoutingStudy:
    """Validate and seal a routing design without reading evaluation outcomes."""
    protocol.validate_sources(dataset, plan, manifest)
    return SealedRoutingStudy(
        protocol=protocol,
        protocol_sha256=protocol.protocol_sha256,
        dataset_sha256=dataset.dataset_sha256,
        plan_sha256=plan.plan_sha256,
        feature_manifest_sha256=manifest.manifest_sha256,
        profile_ids=protocol.profile_ids(manifest),
    )


def verify_sealed_routing_study(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    manifest: PromptFeatureManifest,
    artifact: SealedRoutingStudy,
) -> None:
    """Rebuild a receipt from independent sources before downstream use."""
    rebuilt = seal_routing_study(dataset, plan, manifest, artifact.protocol)
    if rebuilt != artifact:
        raise ValueError("sealed routing study provenance mismatch")
