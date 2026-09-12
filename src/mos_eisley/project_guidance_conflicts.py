"""Explicit advisory conflict assessments; no automatic semantic classification."""

import json
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Identifier, canonical_bytes, digest
from mos_eisley.project_guidance import Detail
from mos_eisley.project_guidance_binding import PinnedGuidance, ProjectGuidanceBindings
from mos_eisley.project_guidance_overrides import SavedOverrides, effective_rules
from mos_eisley.project_guidance_storage import GUIDANCE_FILE_BYTES

ASSESSMENT_BYTES = 64 * 1024


class RuleReference(Contract):
    template_id: Identifier
    rule_id: Identifier

    @property
    def key(self) -> tuple[str, str]:
        return self.template_id, self.rule_id


class GuidanceConflict(Contract):
    id: Identifier
    rules: Annotated[tuple[RuleReference, ...], Field(min_length=2, max_length=8)]
    explanation: Detail
    preferred_rule: RuleReference | None = None
    resolution_rationale: Detail | None = None

    @model_validator(mode="after")
    def valid_resolution(self) -> Self:
        keys = {item.key for item in self.rules}
        if len(keys) != len(self.rules):
            raise ValueError("Conflict participants must be distinct qualified rules.")
        if (self.preferred_rule is None) != (self.resolution_rationale is None):
            raise ValueError(
                "A resolution requires both a preferred rule and rationale."
            )
        if self.preferred_rule is not None and self.preferred_rule.key not in keys:
            raise ValueError("The preferred rule must participate in the conflict.")
        for text in (self.explanation, self.resolution_rationale):
            if text is not None:
                if not text.strip():
                    raise ValueError(
                        "Conflict explanation and rationale cannot be blank."
                    )
                text.encode("utf-8")
        return self


class ConflictAssessment(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["advisory_conflict_assessment"] = "advisory_conflict_assessment"
    review_rationale: Detail
    conflicts: Annotated[tuple[GuidanceConflict, ...], Field(max_length=64)]

    @model_validator(mode="after")
    def unique_conflicts(self) -> Self:
        if not self.review_rationale.strip():
            raise ValueError("An assessment requires a nonblank review rationale.")
        self.review_rationale.encode("utf-8")
        if len({item.id for item in self.conflicts}) != len(self.conflicts):
            raise ValueError("Conflict IDs must be unique.")
        groups = {frozenset(rule.key for rule in item.rules) for item in self.conflicts}
        if len(groups) != len(self.conflicts):
            raise ValueError("A participant group can be assessed only once.")
        if len(canonical_bytes(self)) > ASSESSMENT_BYTES:
            raise ValueError("Conflict assessment exceeds 64 KiB.")
        return self


def decode_assessment(payload: bytes) -> ConflictAssessment:
    if len(payload) > ASSESSMENT_BYTES:
        raise ValueError("Conflict input exceeds 64 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return ConflictAssessment.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid advisory conflict assessment.") from None


class GuidanceBasis(Contract):
    bindings: ProjectGuidanceBindings
    overrides: SavedOverrides | None = None

    @model_validator(mode="after")
    def matching_owner_project(self) -> Self:
        if self.overrides is not None and (
            self.overrides.basis.owner_uid != self.bindings.owner_uid
            or self.overrides.basis.workspace != self.bindings.workspace
        ):
            raise ValueError("Conflict basis requires matching owner and project.")
        return self

    @property
    def overrides_stale(self) -> bool:
        return (
            self.overrides is not None
            and self.overrides.profile is not None
            and self.overrides.basis != self.bindings
        )

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class SavedConflictAssessment(Contract):
    schema_version: Literal[1] = 1
    revision: Annotated[int, Field(ge=1)]
    basis: GuidanceBasis
    source_json: Annotated[str | None, Field(max_length=ASSESSMENT_BYTES)]
    assessment: ConflictAssessment | None
    context_materialized: Literal[False] = False

    @model_validator(mode="after")
    def matching_source(self) -> Self:
        if (self.source_json is None) != (self.assessment is None):
            raise ValueError("Saved assessment requires matching source data.")
        if (
            self.source_json is not None
            and decode_assessment(self.source_json.encode("utf-8")) != self.assessment
        ):
            raise ValueError("Retained conflict source does not match its assessment.")
        if self.assessment is not None and self.basis.overrides_stale:
            raise ValueError("Review project overrides before assessing conflicts.")
        if len(canonical_bytes(self)) > GUIDANCE_FILE_BYTES:
            raise ValueError("Saved conflict assessment exceeds 512 KiB.")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


def resolution_report(
    basis: GuidanceBasis,
    snapshots: tuple[PinnedGuidance, ...],
    assessment: ConflictAssessment | None,
) -> dict[str, object]:
    if basis.overrides_stale:
        return {
            "guidance_stale": True,
            "rules": None,
            "unresolved_conflict_ids": [],
            "advisory_resolution_complete": False,
        }
    rules = effective_rules(basis.bindings, snapshots, basis.overrides)
    inventory = {
        (cast(str, item["template_id"]), cast(str, item["rule_id"])): item
        for item in rules
        if not item["omitted"]
    }
    priority = {"advisory_default": 1, "approved_project_override": 2}
    losers: dict[tuple[str, str], list[str]] = {}
    winners: set[tuple[str, str]] = set()
    unresolved: list[str] = []
    for conflict in () if assessment is None else assessment.conflicts:
        keys = {item.key for item in conflict.rules}
        if not keys <= inventory.keys():
            raise ValueError(
                "Conflict participants must be active attached advisory rules."
            )
        if conflict.preferred_rule is None:
            unresolved.append(conflict.id)
            continue
        winner = conflict.preferred_rule.key
        winner_priority = priority[cast(str, inventory[winner]["source"])]
        if winner_priority < max(
            priority[cast(str, inventory[key]["source"])] for key in keys
        ):
            raise ValueError(
                "A conflict resolution cannot prefer a lower-priority rule."
            )
        winners.add(winner)
        for key in keys - {winner}:
            losers.setdefault(key, []).append(conflict.id)
    if winners & losers.keys():
        raise ValueError(
            "Overlapping resolutions cannot exclude another preferred rule."
        )
    for rule in rules:
        key = cast(str, rule["template_id"]), cast(str, rule["rule_id"])
        rule["pre_conflict_rule"] = rule["effective_rule"]
        rule["excluded_by_conflicts"] = sorted(losers.get(key, []))
        if key in losers:
            rule["effective_rule"] = None
        rule["selected"] = rule["effective_rule"] is not None
    return {
        "guidance_stale": False,
        "rules": rules,
        "unresolved_conflict_ids": sorted(unresolved),
        "advisory_resolution_complete": assessment is not None and not unresolved,
    }
