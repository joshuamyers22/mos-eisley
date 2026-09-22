"""Offline diagnostics for task-scoped instruction and tool manifests."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.task_state import OwnerProjectScope, WorkUnitReference


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


class TaskInstructionContent(Contract):
    """Exact private bytes selected by one task-profile instruction entry."""

    rule_id: Identifier
    text: Annotated[str, Field(min_length=1, max_length=32_000)]


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


class WorkUnitOwnedTaskProfile(Contract):
    """A work-unit profile plus its exact selected private instruction bytes."""

    schema_version: Literal[1] = 1
    manifest: TaskProfileManifest
    instructions: Annotated[
        tuple[TaskInstructionContent, ...], Field(max_length=128)
    ] = ()

    @model_validator(mode="after")
    def exact_instruction_materialization(self) -> Self:
        selected = tuple(item for item in self.manifest.instructions if item.selected)
        if tuple(item.rule_id for item in selected) != tuple(
            item.rule_id for item in self.instructions
        ):
            raise ValueError(
                "instruction content must match selected profile IDs and order"
            )
        for entry, content in zip(selected, self.instructions, strict=True):
            payload = content.text.encode("utf-8")
            if len(payload) != entry.bytes or digest(payload) != entry.content_sha256:
                raise ValueError(
                    f"instruction content does not match profile entry {entry.rule_id}"
                )
        return self


class WorkUnitProfileAcquisition(Contract):
    """Text-free provenance for a profile selected by a checkpoint work unit."""

    schema_version: Literal[1] = 1
    checkpoint_id: Identifier
    checkpoint_revision: Annotated[int, Field(ge=1)]
    checkpoint_sha256: Digest
    bundle_revision: Annotated[int, Field(ge=1)]
    bundle_sha256: Digest
    work_unit: WorkUnitReference
    profile_id: Identifier
    profile_sha256: Digest
    grants_authority: Literal[False] = False


class AcquiredWorkUnitProfile(Contract):
    """Runtime-only material and the private archive identity that supplied it."""

    profile: WorkUnitOwnedTaskProfile
    acquisition: WorkUnitProfileAcquisition

    @model_validator(mode="after")
    def exact_source(self) -> Self:
        manifest = self.profile.manifest
        source = self.acquisition
        if (
            source.work_unit != manifest.work_unit
            or source.profile_id != manifest.profile_id
            or source.profile_sha256 != manifest.sha256
        ):
            raise ValueError("acquired profile differs from its work-unit source")
        return self


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
