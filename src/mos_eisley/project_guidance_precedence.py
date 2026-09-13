"""Explicit combined review of accepted requirements and advisory guidance."""

import json
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Identifier, canonical_bytes, digest
from mos_eisley.project_guidance import Detail
from mos_eisley.project_guidance_binding import PinnedGuidance
from mos_eisley.project_guidance_conflicts import ASSESSMENT_BYTES, GuidanceBasis
from mos_eisley.project_guidance_overrides import effective_rules
from mos_eisley.project_guidance_storage import GUIDANCE_FILE_BYTES
from mos_eisley.project_requirements import SavedRequirements


class ProjectRuleReference(Contract):
    kind: Literal["requirement", "advisory"]
    rule_id: Identifier
    template_id: Identifier | None = None

    @model_validator(mode="after")
    def qualified_reference(self) -> Self:
        if (self.kind == "advisory") != (self.template_id is not None):
            raise ValueError("Only advisory references require a template ID.")
        return self

    @property
    def key(self) -> tuple[str, str, str]:
        return self.kind, self.template_id or "", self.rule_id


class ProjectConflict(Contract):
    id: Identifier
    rules: Annotated[
        tuple[ProjectRuleReference, ...], Field(min_length=2, max_length=8)
    ]
    explanation: Detail
    preferred_rule: ProjectRuleReference | None = None
    resolution_rationale: Detail | None = None

    @model_validator(mode="after")
    def valid_resolution(self) -> Self:
        keys = {item.key for item in self.rules}
        if len(keys) != len(self.rules):
            raise ValueError("Conflict participants must be distinct qualified rules.")
        if (self.preferred_rule is None) != (self.resolution_rationale is None):
            raise ValueError("A resolution requires a preferred rule and rationale.")
        if self.preferred_rule is not None:
            if self.preferred_rule.key not in keys:
                raise ValueError("The preferred rule must participate in the conflict.")
            if sum(item.kind == "requirement" for item in self.rules) > 1:
                raise ValueError(
                    "Revise contradictory accepted requirements before resolving them."
                )
        for value in (self.explanation, self.resolution_rationale):
            if value is not None:
                if not value.strip():
                    raise ValueError(
                        "Conflict explanation and rationale cannot be blank."
                    )
                value.encode("utf-8")
        return self


class ProjectAssessment(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["project_guidance_assessment"] = "project_guidance_assessment"
    review_rationale: Detail
    conflicts: Annotated[tuple[ProjectConflict, ...], Field(max_length=64)]

    @model_validator(mode="after")
    def valid_assessment(self) -> Self:
        if not self.review_rationale.strip():
            raise ValueError("A combined assessment requires a review rationale.")
        self.review_rationale.encode("utf-8")
        if len({item.id for item in self.conflicts}) != len(self.conflicts):
            raise ValueError("Conflict IDs must be unique.")
        groups = {frozenset(rule.key for rule in item.rules) for item in self.conflicts}
        if len(groups) != len(self.conflicts):
            raise ValueError("Assess each participant group once.")
        if len(canonical_bytes(self)) > ASSESSMENT_BYTES:
            raise ValueError("Project assessment exceeds 64 KiB.")
        return self


def decode_project_assessment(payload: bytes) -> ProjectAssessment:
    if len(payload) > ASSESSMENT_BYTES:
        raise ValueError("Project assessment input exceeds 64 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return ProjectAssessment.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid project guidance assessment.") from None


class ProjectBasis(GuidanceBasis):
    requirements: SavedRequirements | None = None

    @model_validator(mode="after")
    def matching_requirements(self) -> Self:
        if self.requirements is not None and (
            self.requirements.owner_uid != self.bindings.owner_uid
            or self.requirements.workspace != self.bindings.workspace
        ):
            raise ValueError(
                "Project assessment requires matching requirement identity."
            )
        return self


class SavedProjectAssessment(Contract):
    schema_version: Literal[1] = 1
    revision: Annotated[int, Field(ge=1)]
    basis: ProjectBasis
    source_json: Annotated[str | None, Field(max_length=ASSESSMENT_BYTES)]
    assessment: ProjectAssessment | None
    context_materialized: Literal[False] = False
    trusted_policy_evaluated: Literal[False] = False

    @model_validator(mode="after")
    def matching_source(self) -> Self:
        if (self.source_json is None) != (self.assessment is None):
            raise ValueError("Saved project assessment requires matching source data.")
        if (
            self.source_json is not None
            and decode_project_assessment(self.source_json.encode("utf-8"))
            != self.assessment
        ):
            raise ValueError("Retained project source differs from its assessment.")
        if self.assessment is not None and self.basis.overrides_stale:
            raise ValueError(
                "Review stale project overrides before combined assessment."
            )
        if len(canonical_bytes(self)) > GUIDANCE_FILE_BYTES:
            raise ValueError("Saved project assessment exceeds 512 KiB.")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


def project_resolution_report(
    basis: ProjectBasis,
    snapshots: tuple[PinnedGuidance, ...],
    assessment: ProjectAssessment | None,
) -> dict[str, object]:
    if basis.overrides_stale:
        return {
            "guidance_stale": True,
            "rules": None,
            "unresolved_conflict_ids": [],
            "project_resolution_complete": False,
        }
    rules = effective_rules(basis.bindings, snapshots, basis.overrides)
    for rule in rules:
        rule["reference"] = ProjectRuleReference(
            kind="advisory",
            template_id=cast(str, rule["template_id"]),
            rule_id=cast(str, rule["rule_id"]),
        ).model_dump(mode="json")
    saved = basis.requirements
    if saved is not None and saved.proposal is not None:
        proposal = saved.proposal
        sources = {
            declared.id: (declared, pinned)
            for declared, pinned in zip(
                proposal.selection.sources, proposal.sources, strict=True
            )
        }
        for requirement in proposal.selection.requirements:
            declared, pinned = sources[requirement.source_id]
            start = pinned.text.index(requirement.text)
            rules.append(
                {
                    "reference": ProjectRuleReference(
                        kind="requirement", rule_id=requirement.id
                    ).model_dump(mode="json"),
                    "rule_id": requirement.id,
                    "template_id": None,
                    "source": "accepted_project_requirement",
                    "omitted": False,
                    "effective_rule": requirement.model_dump(mode="json"),
                    "requirement_snapshot_sha256": saved.sha256,
                    "provenance": {
                        "source": declared.model_dump(mode="json"),
                        "path": pinned.path,
                        "character_start": start,
                        "character_end": start + len(requirement.text),
                    },
                }
            )
    inventory = {
        ProjectRuleReference.model_validate(rule["reference"]).key: rule
        for rule in rules
        if not rule["omitted"]
    }
    priorities = {
        "advisory_default": 1,
        "approved_project_override": 2,
        "accepted_project_requirement": 3,
    }
    losers: dict[tuple[str, str, str], list[str]] = {}
    winners: set[tuple[str, str, str]] = set()
    unresolved: list[str] = []
    for conflict in () if assessment is None else assessment.conflicts:
        keys = {rule.key for rule in conflict.rules}
        if not keys <= inventory.keys():
            raise ValueError(
                "Conflict participants must be current requirements or active "
                "advisory rules."
            )
        if conflict.preferred_rule is None:
            unresolved.append(conflict.id)
            continue
        winner = conflict.preferred_rule.key
        priority = priorities[cast(str, inventory[winner]["source"])]
        if priority < max(
            priorities[cast(str, inventory[key]["source"])] for key in keys
        ):
            raise ValueError("A project conflict cannot prefer a lower-priority rule.")
        winners.add(winner)
        for key in keys - {winner}:
            losers.setdefault(key, []).append(conflict.id)
    if winners & losers.keys():
        raise ValueError(
            "Overlapping project resolutions cannot exclude a preferred rule."
        )
    for rule in rules:
        key = ProjectRuleReference.model_validate(rule["reference"]).key
        rule["pre_conflict_rule"] = rule["effective_rule"]
        rule["excluded_by_conflicts"] = sorted(losers.get(key, []))
        if key in losers:
            rule["effective_rule"] = None
        rule["selected"] = rule["effective_rule"] is not None
    return {
        "guidance_stale": False,
        "rules": rules,
        "unresolved_conflict_ids": sorted(unresolved),
        "project_resolution_complete": assessment is not None and not unresolved,
    }
