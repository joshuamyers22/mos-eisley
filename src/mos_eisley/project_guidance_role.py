"""Bounded relevant guidance for frozen role briefs; no session history loading."""

import json
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.project_guidance import Detail, RuleText
from mos_eisley.project_guidance_policy import decode_policy
from mos_eisley.project_guidance_precedence import ProjectRuleReference
from mos_eisley.project_guidance_storage import GUIDANCE_FILE_BYTES

SELECTION_BYTES = 32 * 1024
ROLE_CONTEXT_BYTES = 64 * 1024
Role = Literal["creator", "coder", "critic", "judge"]


class RequirementOmission(Contract):
    rule_id: Identifier
    reason: Detail

    @model_validator(mode="after")
    def nonblank_reason(self) -> Self:
        if not self.reason.strip():
            raise ValueError("Omitting a requirement needs an explicit reason.")
        self.reason.encode("utf-8")
        return self


class RoleSelection(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["project_role_guidance_selection"] = "project_role_guidance_selection"
    role: Role
    scope: Detail
    review_rationale: Detail
    rules: Annotated[
        tuple[ProjectRuleReference, ...], Field(min_length=1, max_length=64)
    ]
    omitted_requirements: Annotated[
        tuple[RequirementOmission, ...], Field(max_length=64)
    ] = ()

    @model_validator(mode="after")
    def valid_selection(self) -> Self:
        for text in (self.scope, self.review_rationale):
            if not text.strip():
                raise ValueError("Role selection needs scope and review rationale.")
            text.encode("utf-8")
        if len({rule.key for rule in self.rules}) != len(self.rules) or len(
            {item.rule_id for item in self.omitted_requirements}
        ) != len(self.omitted_requirements):
            raise ValueError("Role rule references and omission IDs must be unique.")
        if len(canonical_bytes(self)) > SELECTION_BYTES:
            raise ValueError("Role selection exceeds 32 KiB.")
        return self


def decode_role_selection(payload: bytes) -> RoleSelection:
    if len(payload) > SELECTION_BYTES:
        raise ValueError("Role selection exceeds 32 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return RoleSelection.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid role guidance selection.") from None


class RoleRule(Contract):
    reference: ProjectRuleReference
    source: Literal[
        "accepted_project_requirement", "approved_project_override", "advisory_default"
    ]
    text: RuleText
    applies_when: Detail
    rationale: Detail
    checks: Annotated[tuple[Detail, ...], Field(min_length=1, max_length=8)]
    override_reason: Detail | None = None
    template_snapshot_sha256: Digest | None = None
    override_snapshot_sha256: Digest | None = None
    requirement_snapshot_sha256: Digest | None = None
    source_content_sha256: Digest | None = None


class RoleContext(Contract):
    schema_version: Literal[1] = 1
    role: Role
    scope: Detail
    assessment_snapshot_sha256: Digest
    policy_source_sha256: Digest
    rules: Annotated[tuple[RoleRule, ...], Field(min_length=1, max_length=64)]
    omitted_requirements: Annotated[
        tuple[RequirementOmission, ...], Field(max_length=64)
    ]
    history_loaded: Literal[False] = False
    execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bounded_context(self) -> Self:
        if len(canonical_bytes(self)) > ROLE_CONTEXT_BYTES:
            raise ValueError("Role guidance context exceeds 64 KiB.")
        return self


def project_role_context(
    selection: RoleSelection,
    rules: list[dict[str, object]],
    assessment_sha256: str,
    policy_sha256: str,
) -> RoleContext:
    inventory = {
        ProjectRuleReference.model_validate(rule["reference"]).key: rule
        for rule in rules
    }
    selected = {reference.key for reference in selection.rules}
    if not selected <= inventory.keys() or any(
        not inventory[key]["selected"] for key in selected
    ):
        raise ValueError("Role references must identify current selected rules.")
    requirements = {key[2] for key in inventory if key[0] == "requirement"}
    included = {key[2] for key in selected if key[0] == "requirement"}
    if {
        item.rule_id for item in selection.omitted_requirements
    } != requirements - included:
        raise ValueError(
            "Give a reason for every omitted accepted requirement, and no others."
        )
    projected: list[RoleRule] = []
    for reference in selection.rules:
        item = inventory[reference.key]
        rule = cast(dict[str, object], item["effective_rule"])
        override = cast(dict[str, object] | None, item.get("override"))
        provenance = cast(dict[str, object] | None, item.get("provenance"))
        source = (
            None
            if provenance is None
            else cast(dict[str, object], provenance["source"])
        )
        projected.append(
            RoleRule.model_validate_json(
                json.dumps(
                    {
                        "reference": reference.model_dump(mode="json"),
                        "source": item["source"],
                        "text": rule["text"],
                        "applies_when": rule["applies_when"],
                        "rationale": rule["rationale"],
                        "checks": rule["checks"],
                        "override_reason": None
                        if override is None
                        else override["reason"],
                        "template_snapshot_sha256": item.get(
                            "template_snapshot_sha256"
                        ),
                        "override_snapshot_sha256": item.get(
                            "override_snapshot_sha256"
                        ),
                        "requirement_snapshot_sha256": item.get(
                            "requirement_snapshot_sha256"
                        ),
                        "source_content_sha256": None
                        if source is None
                        else source["content_sha256"],
                    }
                )
            )
        )
    return RoleContext(
        role=selection.role,
        scope=selection.scope,
        assessment_snapshot_sha256=assessment_sha256,
        policy_source_sha256=policy_sha256,
        rules=tuple(projected),
        omitted_requirements=selection.omitted_requirements,
    )


class FrozenRoleContext(Contract):
    schema_version: Literal[1] = 1
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: MappedDirectory
    selection_json: Annotated[str, Field(min_length=1, max_length=SELECTION_BYTES)]
    selection: RoleSelection
    policy_source_json: Annotated[str, Field(min_length=1, max_length=64 * 1024)]
    context: RoleContext
    context_materialized: Literal[True] = True
    provider_context_loaded: Literal[False] = False

    @model_validator(mode="after")
    def valid_sources(self) -> Self:
        if decode_role_selection(self.selection_json.encode("utf-8")) != self.selection:
            raise ValueError("Frozen role selection differs from retained source.")
        policy_bytes = self.policy_source_json.encode("utf-8")
        policy = decode_policy(policy_bytes)
        if (
            policy.owner_uid != self.owner_uid
            or policy.workspace != self.workspace
            or digest(policy_bytes) != self.context.policy_source_sha256
        ):
            raise ValueError("Frozen role policy identity or source differs.")
        if len(canonical_bytes(self)) > GUIDANCE_FILE_BYTES:
            raise ValueError("Frozen role snapshot exceeds 512 KiB.")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))
