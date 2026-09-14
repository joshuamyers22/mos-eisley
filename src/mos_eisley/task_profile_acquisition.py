"""Acquire request profiles from current frozen author-guidance contexts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self, cast

from pydantic import model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.project_guidance_role import RoleContext, RoleRule
from mos_eisley.project_guidance_role_admission import (
    RoleContextAdmissionStore,
    RoleContextSelection,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.task_profile import (
    InstructionProfileEntry,
    MaterializedInstruction,
    ProfileSizes,
    RuntimeTaskProfile,
    TaskProfileAcquisitionEvidence,
    TaskProfileManifest,
    conversation_workspace_sha256,
    validate_task_profile_scope,
)
from mos_eisley.task_state import OwnerProjectScope, WorkUnitReference

TASK_PROFILE_SELECTION_BYTES = 32 * 1024


class FrozenRoleTaskProfileSelection(Contract):
    """Reviewed launch selection for automatic author-profile acquisition."""

    schema_version: Literal[1] = 1
    kind: Literal["frozen_role_task_profile"] = "frozen_role_task_profile"
    profile_id: Identifier
    project_id: Identifier
    work_unit: WorkUnitReference
    guidance: RoleContextSelection
    expected_policy_sha256: Digest

    @model_validator(mode="after")
    def author_role_only(self) -> Self:
        if self.guidance.role not in ("creator", "coder"):
            raise ValueError(
                "automatic conversation profiles require a creator or coder context"
            )
        if len(canonical_bytes(self)) > TASK_PROFILE_SELECTION_BYTES:
            raise ValueError("automatic task-profile selection exceeds 32 KiB")
        return self


def decode_task_profile_selection(payload: bytes) -> FrozenRoleTaskProfileSelection:
    if len(payload) > TASK_PROFILE_SELECTION_BYTES:
        raise ValueError("Automatic task-profile selection exceeds 32 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return FrozenRoleTaskProfileSelection.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid automatic task-profile selection.") from None


def _instruction_id(rule: RoleRule) -> str:
    return "r-" + digest(canonical_bytes(rule.reference))


def _source_sha256(rule: RoleRule) -> str:
    source = (
        rule.requirement_snapshot_sha256
        if rule.source == "accepted_project_requirement"
        else rule.override_snapshot_sha256
        if rule.source == "approved_project_override"
        else rule.template_snapshot_sha256
    )
    if source is None:
        raise ValueError("selected role guidance lacks pinned source provenance")
    return source


def _instruction_content(rule: RoleRule) -> str:
    lines = [
        rule.text,
        f"Applies when: {rule.applies_when}",
        f"Rationale: {rule.rationale}",
        "Checks:",
        *(f"- {check}" for check in rule.checks),
    ]
    if rule.override_reason is not None:
        lines.append(f"Approved override reason: {rule.override_reason}")
    return "\n".join(lines)


def materialize_role_task_profile(
    selection: FrozenRoleTaskProfileSelection,
    context: RoleContext,
    *,
    owner_uid: int,
    workspace: str,
    selection_source_sha256: str,
) -> RuntimeTaskProfile:
    """Project one guarded role packet into an exact, inert request profile."""
    if (
        context.role != selection.guidance.role
        or context.scope != selection.guidance.scope
        or digest(canonical_bytes(context)) != selection.guidance.context_sha256
        or context.policy_source_sha256 != selection.expected_policy_sha256
    ):
        raise ValueError(
            "acquired role context differs from the task-profile selection"
        )
    instructions = tuple(
        MaterializedInstruction(
            rule_id=_instruction_id(rule), content=_instruction_content(rule)
        )
        for rule in context.rules
    )
    inventory = tuple(
        InstructionProfileEntry(
            rule_id=materialized.rule_id,
            source_sha256=_source_sha256(rule),
            content_sha256=digest(materialized.content.encode("utf-8")),
            bytes=len(materialized.content.encode("utf-8")),
            scope=context.scope,
            required=rule.source == "accepted_project_requirement",
            selected=True,
            selection_reason=f"Selected by the reviewed {context.role} role context.",
            location="reference",
            classification="stable_rule",
        )
        for rule, materialized in zip(context.rules, instructions, strict=True)
    )
    instruction_bytes = sum(item.bytes for item in inventory)
    acquisition = TaskProfileAcquisitionEvidence(
        selection_source_sha256=selection_source_sha256,
        role_context_snapshot_sha256=selection.guidance.snapshot_sha256,
        role_context_sha256=selection.guidance.context_sha256,
        assessment_snapshot_sha256=context.assessment_snapshot_sha256,
        policy_source_sha256=context.policy_source_sha256,
        role=cast(Literal["creator", "coder"], context.role),
        omitted_requirement_ids=tuple(
            item.rule_id for item in context.omitted_requirements
        ),
    )
    profile = RuntimeTaskProfile(
        manifest=TaskProfileManifest(
            scope=OwnerProjectScope(
                owner_uid=owner_uid,
                project_id=selection.project_id,
                workspace_sha256=conversation_workspace_sha256(workspace),
            ),
            profile_id=selection.profile_id,
            work_unit=selection.work_unit,
            policy_sha256=context.policy_source_sha256,
            instructions=inventory,
            sizes=ProfileSizes(
                root_instruction_bytes=0,
                instruction_bytes=instruction_bytes,
                tool_schema_bytes=0,
                total_bytes=instruction_bytes,
            ),
        ),
        instructions=instructions,
        acquisition=acquisition,
    )
    validate_task_profile_scope(profile, owner_uid=owner_uid, workspace=workspace)
    return profile


@dataclass(frozen=True)
class FrozenRoleTaskProfileAcquirer:
    """Revalidate and acquire a frozen author profile at each request boundary."""

    guidance_storage: Path
    policy_path: Path
    selection_payload: bytes

    def __post_init__(self) -> None:
        decode_task_profile_selection(self.selection_payload)

    @classmethod
    def from_paths(
        cls,
        guidance_storage: Path,
        selection_path: Path,
        policy_path: Path,
    ) -> Self:
        payload = read_bounded(selection_path, TASK_PROFILE_SELECTION_BYTES)
        return cls(
            guidance_storage=guidance_storage,
            policy_path=policy_path,
            selection_payload=payload,
        )

    def acquire(
        self, *, owner_uid: int, workspace: str, task_text: str | None = None
    ) -> RuntimeTaskProfile:
        if owner_uid != os.getuid():
            raise ValueError("automatic task profile belongs to another owner")
        selection = decode_task_profile_selection(self.selection_payload)
        store = RoleContextAdmissionStore(self.guidance_storage)
        with store.guard_context(
            Path(workspace),
            selection.guidance,
            self.policy_path,
            selection.expected_policy_sha256,
        ) as context:
            return materialize_role_task_profile(
                selection,
                context,
                owner_uid=owner_uid,
                workspace=workspace,
                selection_source_sha256=digest(self.selection_payload),
            )
