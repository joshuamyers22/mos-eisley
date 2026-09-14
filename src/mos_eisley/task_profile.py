"""Diagnostics and inert materialization for task-scoped request profiles."""

from __future__ import annotations

import json
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import ToolCallBlock, ToolDefinition, ToolResultBlock
from mos_eisley.task_state import OwnerProjectScope, WorkUnitReference

TaskCategory = Literal[
    "implementation",
    "debugging",
    "verification",
    "review",
    "documentation",
    "research",
    "maintenance",
    "other",
]


class InstructionProfileEntry(Contract):
    rule_id: Identifier
    source_sha256: Digest
    content_sha256: Digest
    bytes: Annotated[int, Field(ge=1)]
    scope: Annotated[str, Field(min_length=1, max_length=1000)]
    required: bool
    selected: bool
    selection_reason: Annotated[str, Field(min_length=1, max_length=1000)]
    location: Literal["root", "nested", "reference"]
    classification: Literal["stable_rule", "temporary_state", "unknown"]


class ToolProfileEntry(Contract):
    tool_id: Identifier
    schema_sha256: Digest
    schema_bytes: Annotated[int, Field(ge=1)]
    required: bool
    selected: bool
    authorized: bool
    availability: Literal["available", "unavailable", "unknown"]
    selection_reason: Annotated[str, Field(min_length=1, max_length=1000)]
    overlaps_with: Annotated[tuple[Identifier, ...], Field(max_length=32)] = ()


class ProfileSizes(Contract):
    root_instruction_bytes: Annotated[int, Field(ge=0)]
    instruction_bytes: Annotated[int, Field(ge=0)]
    tool_schema_bytes: Annotated[int, Field(ge=0)]
    total_bytes: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def exact_total(self) -> Self:
        if self.total_bytes != self.instruction_bytes + self.tool_schema_bytes:
            raise ValueError("profile total does not match its categories")
        if self.root_instruction_bytes > self.instruction_bytes:
            raise ValueError("root instructions exceed all selected instructions")
        return self


class TaskProfileManifest(Contract):
    schema_version: Literal[1] = 1
    scope: OwnerProjectScope
    profile_id: Identifier
    work_unit: WorkUnitReference
    policy_sha256: Digest
    instructions: Annotated[
        tuple[InstructionProfileEntry, ...], Field(max_length=128)
    ] = ()
    tools: Annotated[tuple[ToolProfileEntry, ...], Field(max_length=128)] = ()
    omitted_instruction_ids: Annotated[
        tuple[Identifier, ...], Field(max_length=128)
    ] = ()
    omitted_tool_ids: Annotated[tuple[Identifier, ...], Field(max_length=128)] = ()
    sizes: ProfileSizes
    root_instruction_advisory_bytes: Annotated[int, Field(ge=1024, le=64_000)] = 3072
    grants_authority: Literal[False] = False
    executable_checks: Literal[False] = False
    network_probes: Literal[False] = False
    automatic_rewrites: Literal[False] = False

    @model_validator(mode="after")
    def exact_inventory(self) -> Self:
        instruction_ids = tuple(item.rule_id for item in self.instructions)
        tool_ids = tuple(item.tool_id for item in self.tools)
        if len(set(instruction_ids)) != len(instruction_ids):
            raise ValueError("instruction profile IDs must be unique")
        if len(set(tool_ids)) != len(tool_ids):
            raise ValueError("tool profile IDs must be unique")
        tool_id_set = set(tool_ids)
        for tool in self.tools:
            if (
                len(set(tool.overlaps_with)) != len(tool.overlaps_with)
                or tool.tool_id in tool.overlaps_with
                or not set(tool.overlaps_with) <= tool_id_set
            ):
                raise ValueError("tool overlaps must name unique peer candidates")
        omitted_instructions = tuple(
            item.rule_id for item in self.instructions if not item.selected
        )
        omitted_tools = tuple(item.tool_id for item in self.tools if not item.selected)
        if self.omitted_instruction_ids != omitted_instructions:
            raise ValueError(
                "instruction omissions do not match the candidate inventory"
            )
        if self.omitted_tool_ids != omitted_tools:
            raise ValueError("tool omissions do not match the candidate inventory")
        selected_instructions = tuple(
            item for item in self.instructions if item.selected
        )
        expected_sizes = ProfileSizes(
            root_instruction_bytes=sum(
                item.bytes for item in selected_instructions if item.location == "root"
            ),
            instruction_bytes=sum(item.bytes for item in selected_instructions),
            tool_schema_bytes=sum(
                item.schema_bytes for item in self.tools if item.selected
            ),
            total_bytes=sum(item.bytes for item in selected_instructions)
            + sum(item.schema_bytes for item in self.tools if item.selected),
        )
        if self.sizes != expected_sizes:
            raise ValueError("profile size categories do not match selected entries")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class ProfileDiagnostic(Contract):
    code: Literal[
        "required_instruction_omitted",
        "required_tool_omitted",
        "selected_tool_unauthorized",
        "selected_tool_unavailable",
        "required_tool_availability_unknown",
        "optional_tool_omitted",
        "root_instructions_oversized",
        "duplicate_instruction",
        "temporary_state_instruction",
        "instruction_classification_unknown",
        "overlapping_tools",
    ]
    severity: Literal["warning", "error"]
    subject_id: Identifier
    detail: Annotated[str, Field(min_length=1, max_length=1000)]


class ProfileDiagnosticReport(Contract):
    schema_version: Literal[1] = 1
    profile_sha256: Digest
    status: Literal["pass", "warning", "fail"]
    diagnostics: Annotated[tuple[ProfileDiagnostic, ...], Field(max_length=512)]
    offline_only: Literal[True] = True

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        expected = (
            "fail"
            if any(item.severity == "error" for item in self.diagnostics)
            else "warning"
            if self.diagnostics
            else "pass"
        )
        if self.status != expected:
            raise ValueError("profile diagnostic status does not match its findings")
        return self


def diagnose_task_profile(manifest: TaskProfileManifest) -> ProfileDiagnosticReport:
    diagnostics: list[ProfileDiagnostic] = []
    instruction_digests: dict[str, str] = {}
    for instruction in manifest.instructions:
        if instruction.required and not instruction.selected:
            diagnostics.append(
                ProfileDiagnostic(
                    code="required_instruction_omitted",
                    severity="error",
                    subject_id=instruction.rule_id,
                    detail="Required instruction is absent from the selected profile.",
                )
            )
        if instruction.classification == "temporary_state":
            diagnostics.append(
                ProfileDiagnostic(
                    code="temporary_state_instruction",
                    severity="warning",
                    subject_id=instruction.rule_id,
                    detail=(
                        "Candidate guidance appears to contain temporary task state."
                    ),
                )
            )
        if instruction.classification == "unknown":
            diagnostics.append(
                ProfileDiagnostic(
                    code="instruction_classification_unknown",
                    severity="warning",
                    subject_id=instruction.rule_id,
                    detail="Instruction stability classification is unknown.",
                )
            )
        first_rule_id = instruction_digests.setdefault(
            instruction.content_sha256, instruction.rule_id
        )
        if first_rule_id != instruction.rule_id:
            diagnostics.append(
                ProfileDiagnostic(
                    code="duplicate_instruction",
                    severity="warning",
                    subject_id=instruction.rule_id,
                    detail=(f"Instruction duplicates the content of {first_rule_id}."),
                )
            )
    selected_tools = {item.tool_id for item in manifest.tools if item.selected}
    overlap_pairs: set[tuple[str, str]] = set()
    for tool in manifest.tools:
        if tool.required and not tool.selected:
            diagnostics.append(
                ProfileDiagnostic(
                    code="required_tool_omitted",
                    severity="error",
                    subject_id=tool.tool_id,
                    detail="Required tool is absent from the selected profile.",
                )
            )
        if not tool.required and not tool.selected:
            diagnostics.append(
                ProfileDiagnostic(
                    code="optional_tool_omitted",
                    severity="warning",
                    subject_id=tool.tool_id,
                    detail="Optional tool is unused by the selected task profile.",
                )
            )
        if tool.selected and not tool.authorized:
            diagnostics.append(
                ProfileDiagnostic(
                    code="selected_tool_unauthorized",
                    severity="error",
                    subject_id=tool.tool_id,
                    detail="Selected tool is outside the trusted capability set.",
                )
            )
        if tool.required and tool.selected and tool.availability == "unknown":
            diagnostics.append(
                ProfileDiagnostic(
                    code="required_tool_availability_unknown",
                    severity="error",
                    subject_id=tool.tool_id,
                    detail="Required tool availability is unknown.",
                )
            )
        elif tool.selected and tool.availability != "available":
            diagnostics.append(
                ProfileDiagnostic(
                    code="selected_tool_unavailable",
                    severity="error",
                    subject_id=tool.tool_id,
                    detail="Selected tool is unavailable.",
                )
            )
        if tool.selected:
            for other in set(tool.overlaps_with) & selected_tools:
                pair = (
                    (tool.tool_id, other)
                    if tool.tool_id < other
                    else (other, tool.tool_id)
                )
                overlap_pairs.add(pair)
    for first, _second in sorted(overlap_pairs):
        diagnostics.append(
            ProfileDiagnostic(
                code="overlapping_tools",
                severity="warning",
                subject_id=first,
                detail="Selected tool overlaps another selected integration.",
            )
        )
    if manifest.sizes.root_instruction_bytes > manifest.root_instruction_advisory_bytes:
        diagnostics.append(
            ProfileDiagnostic(
                code="root_instructions_oversized",
                severity="warning",
                subject_id=manifest.profile_id,
                detail=(
                    "Selected root guidance exceeds the configured editorial target."
                ),
            )
        )
    diagnostics.sort(
        key=lambda item: (item.severity != "error", item.code, item.subject_id)
    )
    status: Literal["pass", "warning", "fail"] = (
        "fail"
        if any(item.severity == "error" for item in diagnostics)
        else "warning"
        if diagnostics
        else "pass"
    )
    return ProfileDiagnosticReport(
        profile_sha256=manifest.sha256,
        status=status,
        diagnostics=tuple(diagnostics),
    )


class MaterializedInstruction(Contract):
    """Approved instruction content kept out of the persisted profile manifest."""

    rule_id: Identifier
    content: Annotated[str, Field(min_length=1, max_length=64_000)]


class TaskSemanticDiscoveryEvidence(Contract):
    """Text-free binding for one validated semantic profile decision."""

    schema_version: Literal[1] = 1
    discovery_source_sha256: Digest
    decision_sha256: Digest
    task_text_sha256: Digest
    category: TaskCategory
    selected_profile_id: Identifier
    candidate_profile_ids: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=16)
    ]
    omitted_profile_ids: Annotated[tuple[Identifier, ...], Field(max_length=15)] = ()
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_candidate_partition(self) -> Self:
        if len(set(self.candidate_profile_ids)) != len(self.candidate_profile_ids):
            raise ValueError("semantic discovery candidate IDs must be unique")
        if self.selected_profile_id not in self.candidate_profile_ids:
            raise ValueError("semantic discovery selected profile is not a candidate")
        expected = tuple(
            item
            for item in self.candidate_profile_ids
            if item != self.selected_profile_id
        )
        if self.omitted_profile_ids != expected:
            raise ValueError("semantic discovery omissions do not cover all candidates")
        return self


class RuntimeToolCatalogEvidence(Contract):
    """Text-free binding for one approved runtime catalog decision."""

    schema_version: Literal[1] = 1
    catalog_source_sha256: Digest
    selection_source_sha256: Digest
    catalog_id: Identifier
    catalog_revision: Annotated[int, Field(ge=1)]
    decision_sha256: Digest
    task_text_sha256: Digest
    selected_tool_ids: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()
    omitted_tool_ids: Annotated[tuple[Identifier, ...], Field(max_length=128)] = ()
    schema_only: Literal[True] = True
    starts_servers: Literal[False] = False
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def exact_partition(self) -> Self:
        tool_ids = (*self.selected_tool_ids, *self.omitted_tool_ids)
        if len(set(tool_ids)) != len(tool_ids):
            raise ValueError("runtime tool-catalog evidence IDs must be unique")
        return self


class TaskProfileAcquisitionEvidence(Contract):
    """Text-free provenance for one automatically acquired author profile."""

    schema_version: Literal[1] = 1
    kind: Literal["frozen_role_context"] = "frozen_role_context"
    selection_source_sha256: Digest
    role_context_snapshot_sha256: Digest
    role_context_sha256: Digest
    assessment_snapshot_sha256: Digest
    policy_source_sha256: Digest
    role: Literal["creator", "coder"]
    omitted_requirement_ids: Annotated[
        tuple[Identifier, ...], Field(max_length=64)
    ] = ()
    semantic_discovery: TaskSemanticDiscoveryEvidence | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    tool_catalog: RuntimeToolCatalogEvidence | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def unique_omissions(self) -> Self:
        if len(set(self.omitted_requirement_ids)) != len(self.omitted_requirement_ids):
            raise ValueError("acquired profile requirement omissions must be unique")
        return self


class RuntimeTaskProfile(Contract):
    """Exact selected prompt material with schema-only, non-executable tools."""

    manifest: TaskProfileManifest
    instructions: Annotated[
        tuple[MaterializedInstruction, ...], Field(max_length=128)
    ] = ()
    tool_definitions: Annotated[tuple[ToolDefinition, ...], Field(max_length=64)] = ()
    acquisition: TaskProfileAcquisitionEvidence | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def exact_selected_material(self) -> Self:
        selected_instructions = tuple(
            item for item in self.manifest.instructions if item.selected
        )
        if any(
            item.classification == "temporary_state" for item in selected_instructions
        ):
            raise ValueError(
                "temporary task state cannot be materialized as an instruction"
            )
        if tuple(item.rule_id for item in self.instructions) != tuple(
            item.rule_id for item in selected_instructions
        ):
            raise ValueError(
                "materialized instructions differ from the selected profile inventory"
            )
        for materialized, selected in zip(
            self.instructions, selected_instructions, strict=True
        ):
            payload = materialized.content.encode("utf-8")
            if len(payload) != selected.bytes or digest(payload) != (
                selected.content_sha256
            ):
                raise ValueError(
                    "materialized instruction differs from its selected profile entry"
                )

        selected_tools = tuple(item for item in self.manifest.tools if item.selected)
        if tuple(item.name for item in self.tool_definitions) != tuple(
            item.tool_id for item in selected_tools
        ):
            raise ValueError(
                "materialized tool schemas differ from the selected profile inventory"
            )
        for definition, selected in zip(
            self.tool_definitions, selected_tools, strict=True
        ):
            payload = canonical_bytes(definition)
            if len(payload) != selected.schema_bytes or digest(payload) != (
                selected.schema_sha256
            ):
                raise ValueError(
                    "materialized tool schema differs from its selected profile entry"
                )

        if diagnose_task_profile(self.manifest).status == "fail":
            raise ValueError("a failing task profile cannot enter a model request")
        if (
            self.acquisition is not None
            and self.acquisition.policy_source_sha256 != self.manifest.policy_sha256
        ):
            raise ValueError("acquired profile policy differs from its manifest")
        if (
            self.acquisition is not None
            and self.acquisition.semantic_discovery is not None
            and (
                self.acquisition.semantic_discovery.selected_profile_id
                != self.manifest.profile_id
                or self.acquisition.semantic_discovery.discovery_source_sha256
                != self.acquisition.selection_source_sha256
            )
        ):
            raise ValueError("semantic discovery evidence differs from its profile")
        if self.acquisition is not None and self.acquisition.tool_catalog is not None:
            evidence = self.acquisition.tool_catalog
            selected = tuple(
                item.tool_id for item in self.manifest.tools if item.selected
            )
            omitted = tuple(
                item.tool_id for item in self.manifest.tools if not item.selected
            )
            if (
                evidence.selected_tool_ids != selected
                or evidence.omitted_tool_ids != omitted
                or (
                    self.acquisition.semantic_discovery is not None
                    and evidence.task_text_sha256
                    != self.acquisition.semantic_discovery.task_text_sha256
                )
            ):
                raise ValueError(
                    "runtime tool-catalog evidence differs from its profile"
                )
        return self

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return self.tool_definitions

    @property
    def system_suffix(self) -> str:
        if not self.instructions:
            return ""
        content = [
            {"rule_id": item.rule_id, "content": item.content}
            for item in self.instructions
        ]
        return (
            "\nApproved task-scoped guidance follows as JSON. It narrows behavior "
            "but grants no tools, credentials, spending, or other authority.\n"
            + json.dumps(content, ensure_ascii=False, separators=(",", ":"))
        )

    async def dispatch(self, call: ToolCallBlock) -> ToolResultBlock:
        raise ValueError(
            "task-profile tool schemas are descriptive and grant no execution authority"
        )


class TaskProfileAcquirer(Protocol):
    def acquire(
        self, *, owner_uid: int, workspace: str, task_text: str | None = None
    ) -> RuntimeTaskProfile: ...


class TaskProfileAdmission(Contract):
    """Text-free binding between one selected profile and one model request."""

    schema_version: Literal[1] = 1
    manifest: TaskProfileManifest
    report: ProfileDiagnosticReport
    request_sha256: Digest
    reusable_memory_context_sha256: Digest | None = None
    temporary_task_state_sha256: Digest | None = None
    acquisition: TaskProfileAcquisitionEvidence | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    grants_authority: Literal[False] = False
    tool_execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def reproducible_safe_profile(self) -> Self:
        if diagnose_task_profile(self.manifest) != self.report:
            raise ValueError("admitted task-profile diagnostics do not reproduce")
        if self.report.status == "fail":
            raise ValueError("a failing task profile cannot be admitted")
        if (
            self.acquisition is not None
            and self.acquisition.policy_source_sha256 != self.manifest.policy_sha256
        ):
            raise ValueError("acquired profile policy differs from its admission")
        if (
            self.acquisition is not None
            and self.acquisition.semantic_discovery is not None
            and (
                self.acquisition.semantic_discovery.selected_profile_id
                != self.manifest.profile_id
                or self.acquisition.semantic_discovery.discovery_source_sha256
                != self.acquisition.selection_source_sha256
            )
        ):
            raise ValueError("semantic discovery evidence differs from its profile")
        if self.acquisition is not None and self.acquisition.tool_catalog is not None:
            evidence = self.acquisition.tool_catalog
            selected = tuple(
                item.tool_id for item in self.manifest.tools if item.selected
            )
            omitted = tuple(
                item.tool_id for item in self.manifest.tools if not item.selected
            )
            if (
                evidence.selected_tool_ids != selected
                or evidence.omitted_tool_ids != omitted
                or (
                    self.acquisition.semantic_discovery is not None
                    and evidence.task_text_sha256
                    != self.acquisition.semantic_discovery.task_text_sha256
                )
            ):
                raise ValueError(
                    "runtime tool-catalog evidence differs from its admission"
                )
        return self


def admit_task_profile(
    profile: RuntimeTaskProfile,
    *,
    request_sha256: str,
    reusable_memory_context_sha256: str | None,
    temporary_task_state_sha256: str | None = None,
) -> TaskProfileAdmission:
    validated = RuntimeTaskProfile.model_validate(profile.model_dump())
    return TaskProfileAdmission(
        manifest=validated.manifest,
        report=diagnose_task_profile(validated.manifest),
        request_sha256=request_sha256,
        reusable_memory_context_sha256=reusable_memory_context_sha256,
        temporary_task_state_sha256=temporary_task_state_sha256,
        acquisition=validated.acquisition,
    )


def conversation_workspace_sha256(workspace: str) -> str:
    return digest(
        b"mos-eisley/conversation-workspace-scope/v1\x00" + workspace.encode("utf-8")
    )


def validate_task_profile_scope(
    profile: RuntimeTaskProfile, *, owner_uid: int, workspace: str
) -> None:
    validated = RuntimeTaskProfile.model_validate(profile.model_dump())
    validate_task_profile_manifest_scope(
        validated.manifest, owner_uid=owner_uid, workspace=workspace
    )


def validate_task_profile_manifest_scope(
    manifest: TaskProfileManifest, *, owner_uid: int, workspace: str
) -> None:
    scope = manifest.scope
    if scope.owner_uid != owner_uid or scope.workspace_sha256 != (
        conversation_workspace_sha256(workspace)
    ):
        raise ValueError("task profile belongs to a different conversation scope")
