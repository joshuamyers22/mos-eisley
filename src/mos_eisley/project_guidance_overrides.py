"""Pinned advisory overrides and deterministic project-guidance inspection."""

import json
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Identifier, canonical_bytes, digest
from mos_eisley.project_guidance import Detail, GuidanceRule
from mos_eisley.project_guidance_binding import PinnedGuidance, ProjectGuidanceBindings
from mos_eisley.project_guidance_storage import GUIDANCE_FILE_BYTES

OVERRIDE_INPUT_BYTES = 64 * 1024


class RuleOverride(Contract):
    template_id: Identifier
    rule_id: Identifier
    action: Literal["replace", "omit"]
    reason: Detail
    replacement: GuidanceRule | None = None

    @model_validator(mode="after")
    def valid_override(self) -> Self:
        if not self.reason.strip():
            raise ValueError("Overrides require an explicit reason.")
        self.reason.encode("utf-8")
        if (self.action == "replace") != (self.replacement is not None):
            raise ValueError(
                "Replace requires an advisory rule; omit accepts no replacement."
            )
        if self.replacement is not None and self.replacement.id != self.rule_id:
            raise ValueError("An override cannot change the stable rule ID.")
        return self


class OverrideProfile(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["advisory_project_overrides"] = "advisory_project_overrides"
    overrides: Annotated[tuple[RuleOverride, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def unique_rules(self) -> Self:
        keys = {(item.template_id, item.rule_id) for item in self.overrides}
        if len(keys) != len(self.overrides):
            raise ValueError("Each qualified rule can have only one project override.")
        if len(canonical_bytes(self)) > OVERRIDE_INPUT_BYTES:
            raise ValueError("Override profile exceeds 64 KiB.")
        return self


def decode_profile(payload: bytes) -> OverrideProfile:
    if len(payload) > OVERRIDE_INPUT_BYTES:
        raise ValueError("Override input exceeds 64 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return OverrideProfile.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid advisory override profile.") from None


class SavedOverrides(Contract):
    schema_version: Literal[1] = 1
    revision: Annotated[int, Field(ge=1)]
    basis: ProjectGuidanceBindings
    source_json: Annotated[str | None, Field(max_length=OVERRIDE_INPUT_BYTES)]
    profile: OverrideProfile | None
    context_materialized: Literal[False] = False

    @model_validator(mode="after")
    def matching_source(self) -> Self:
        if (self.source_json is None) != (self.profile is None):
            raise ValueError("Saved overrides require matching source and profile.")
        if (
            self.source_json is not None
            and decode_profile(self.source_json.encode("utf-8")) != self.profile
        ):
            raise ValueError("Saved override source does not match its profile.")
        if len(canonical_bytes(self)) > GUIDANCE_FILE_BYTES:
            raise ValueError("Saved overrides exceed 512 KiB.")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


def effective_rules(
    bindings: ProjectGuidanceBindings,
    snapshots: tuple[PinnedGuidance, ...],
    overrides: SavedOverrides | None,
) -> list[dict[str, object]]:
    if tuple(
        (item.template_id, item.snapshot_sha256) for item in bindings.templates
    ) != tuple(
        (item.inspection.descriptor.template_id, item.sha256) for item in snapshots
    ) or any(
        item.workspace != bindings.workspace
        or item.inspection.owner_uid != bindings.owner_uid
        for item in snapshots
    ):
        raise ValueError("Effective guidance requires the exact bound snapshots.")
    if (
        overrides is not None
        and overrides.profile is not None
        and overrides.basis != bindings
    ):
        raise ValueError("Project bindings changed; review the override profile again.")
    replacements = (
        {}
        if overrides is None or overrides.profile is None
        else {
            (item.template_id, item.rule_id): item
            for item in overrides.profile.overrides
        }
    )
    result: list[dict[str, object]] = []
    for snapshot in snapshots:
        template = snapshot.inspection.descriptor
        for rule in template.rules:
            override = replacements.pop((template.template_id, rule.id), None)
            effective = rule if override is None else override.replacement
            result.append(
                {
                    "template_id": template.template_id,
                    "rule_id": rule.id,
                    "template_snapshot_sha256": snapshot.sha256,
                    "source": "advisory_default"
                    if override is None
                    else "approved_project_override",
                    "omitted": effective is None,
                    "base_rule": rule.model_dump(mode="json"),
                    "effective_rule": None
                    if effective is None
                    else effective.model_dump(mode="json"),
                    "override": None
                    if override is None
                    else override.model_dump(mode="json"),
                    "override_snapshot_sha256": None
                    if overrides is None or override is None
                    else overrides.sha256,
                }
            )
    if replacements:
        raise ValueError("Override refers to a rule outside the attached templates.")
    return result
