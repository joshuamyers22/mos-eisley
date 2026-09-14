"""Request-bound selection from an approved, inert runtime tool catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import ToolDefinition
from mos_eisley.run.files import read_bounded
from mos_eisley.task_profile import (
    ProfileSizes,
    RuntimeTaskProfile,
    RuntimeToolCatalogEvidence,
    TaskProfileAcquirer,
    ToolProfileEntry,
    validate_task_profile_scope,
)
from mos_eisley.task_state import WorkUnitReference

RUNTIME_TOOL_CATALOG_BYTES = 256 * 1024
RUNTIME_TOOL_SELECTION_BYTES = 128 * 1024


class RuntimeToolCatalogEntry(Contract):
    """Approved schema metadata; it is not a dispatcher or server configuration."""

    tool_id: Identifier
    definition: ToolDefinition
    schema_sha256: Digest
    schema_bytes: Annotated[int, Field(ge=1, le=65_536)]
    authorized: bool
    availability: Literal["available", "unavailable", "unknown"]
    overlaps_with: Annotated[tuple[Identifier, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def exact_schema(self) -> Self:
        payload = canonical_bytes(self.definition)
        if self.definition.name != self.tool_id:
            raise ValueError("runtime catalog tool ID must match its schema name")
        if self.schema_sha256 != digest(payload) or self.schema_bytes != len(payload):
            raise ValueError("runtime catalog schema metadata does not match its bytes")
        return self


class RuntimeToolCatalog(Contract):
    """Bounded approved metadata snapshot that never starts integrations."""

    schema_version: Literal[1] = 1
    kind: Literal["runtime_tool_catalog"] = "runtime_tool_catalog"
    catalog_id: Identifier
    revision: Annotated[int, Field(ge=1)]
    project_id: Identifier
    policy_sha256: Digest
    tools: Annotated[
        tuple[RuntimeToolCatalogEntry, ...], Field(min_length=1, max_length=128)
    ]
    approved_metadata: Literal[True] = True
    starts_servers: Literal[False] = False
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def valid_inventory(self) -> Self:
        tool_ids = tuple(item.tool_id for item in self.tools)
        tool_id_set = set(tool_ids)
        if len(tool_id_set) != len(tool_ids):
            raise ValueError("runtime tool catalog IDs must be unique")
        for tool in self.tools:
            if (
                len(set(tool.overlaps_with)) != len(tool.overlaps_with)
                or tool.tool_id in tool.overlaps_with
                or not set(tool.overlaps_with) <= tool_id_set
            ):
                raise ValueError("runtime catalog overlaps must name unique peers")
        if len(canonical_bytes(self)) > RUNTIME_TOOL_CATALOG_BYTES:
            raise ValueError("runtime tool catalog exceeds 256 KiB")
        return self


class RuntimeToolChoice(Contract):
    tool_id: Identifier
    required: bool
    selected: bool
    selection_reason: Annotated[str, Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def nonblank_reason(self) -> Self:
        if not self.selection_reason.strip():
            raise ValueError("runtime tool choice needs a selection reason")
        self.selection_reason.encode("utf-8")
        return self


class RuntimeToolSelectionDecision(Contract):
    """Complete tool decision for one exact queued author message."""

    decision_id: Identifier
    task_text_sha256: Digest
    profile_id: Identifier
    work_unit: WorkUnitReference
    choices: Annotated[
        tuple[RuntimeToolChoice, ...], Field(min_length=1, max_length=128)
    ]
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def unique_choices(self) -> Self:
        tool_ids = tuple(item.tool_id for item in self.choices)
        if len(set(tool_ids)) != len(tool_ids):
            raise ValueError("runtime tool decision IDs must be unique")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class RuntimeToolCatalogSelection(Contract):
    """Decisions pinned to the exact bytes of one approved catalog snapshot."""

    schema_version: Literal[1] = 1
    kind: Literal["runtime_tool_catalog_selection"] = "runtime_tool_catalog_selection"
    expected_catalog_sha256: Digest
    expected_catalog_id: Identifier
    expected_catalog_revision: Annotated[int, Field(ge=1)]
    project_id: Identifier
    expected_policy_sha256: Digest
    decisions: Annotated[
        tuple[RuntimeToolSelectionDecision, ...], Field(min_length=1, max_length=64)
    ]
    schema_only: Literal[True] = True
    starts_servers: Literal[False] = False
    tool_execution_enabled: Literal[False] = False
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def unique_decisions(self) -> Self:
        if len({item.decision_id for item in self.decisions}) != len(self.decisions):
            raise ValueError("runtime tool decision IDs must be unique")
        if len({item.task_text_sha256 for item in self.decisions}) != len(
            self.decisions
        ):
            raise ValueError("runtime tool task-message digests must be unique")
        if len(canonical_bytes(self)) > RUNTIME_TOOL_SELECTION_BYTES:
            raise ValueError("runtime tool selection exceeds 128 KiB")
        return self


def decode_runtime_tool_catalog(payload: bytes) -> RuntimeToolCatalog:
    if len(payload) > RUNTIME_TOOL_CATALOG_BYTES:
        raise ValueError("Runtime tool catalog exceeds 256 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return RuntimeToolCatalog.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid runtime tool catalog.") from None


def decode_runtime_tool_selection(payload: bytes) -> RuntimeToolCatalogSelection:
    if len(payload) > RUNTIME_TOOL_SELECTION_BYTES:
        raise ValueError("Runtime tool selection exceeds 128 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return RuntimeToolCatalogSelection.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid runtime tool selection.") from None


def _validate_catalog_selection(
    catalog: RuntimeToolCatalog,
    selection: RuntimeToolCatalogSelection,
    *,
    catalog_source_sha256: str,
) -> None:
    if (
        selection.expected_catalog_sha256 != catalog_source_sha256
        or selection.expected_catalog_id != catalog.catalog_id
        or selection.expected_catalog_revision != catalog.revision
        or selection.project_id != catalog.project_id
        or selection.expected_policy_sha256 != catalog.policy_sha256
    ):
        raise ValueError("runtime tool selection names a stale or different catalog")
    expected_tool_ids = tuple(item.tool_id for item in catalog.tools)
    for decision in selection.decisions:
        if tuple(item.tool_id for item in decision.choices) != expected_tool_ids:
            raise ValueError(
                "runtime tool decision must cover the ordered catalog inventory"
            )


@dataclass(frozen=True)
class RuntimeToolCatalogSelectingAcquirer:
    """Decorate author-profile acquisition with exact schema-only tool selection."""

    base_acquirer: TaskProfileAcquirer
    catalog_payload: bytes
    selection_payload: bytes

    def __post_init__(self) -> None:
        catalog = decode_runtime_tool_catalog(self.catalog_payload)
        selection = decode_runtime_tool_selection(self.selection_payload)
        _validate_catalog_selection(
            catalog,
            selection,
            catalog_source_sha256=digest(self.catalog_payload),
        )

    @classmethod
    def from_paths(
        cls,
        base_acquirer: TaskProfileAcquirer,
        catalog_path: Path,
        selection_path: Path,
    ) -> Self:
        return cls(
            base_acquirer=base_acquirer,
            catalog_payload=read_bounded(catalog_path, RUNTIME_TOOL_CATALOG_BYTES),
            selection_payload=read_bounded(
                selection_path, RUNTIME_TOOL_SELECTION_BYTES
            ),
        )

    def acquire(
        self, *, owner_uid: int, workspace: str, task_text: str | None = None
    ) -> RuntimeTaskProfile:
        if task_text is None:
            raise ValueError("runtime tool selection requires queued author text")
        catalog = decode_runtime_tool_catalog(self.catalog_payload)
        selection = decode_runtime_tool_selection(self.selection_payload)
        catalog_sha = digest(self.catalog_payload)
        _validate_catalog_selection(
            catalog, selection, catalog_source_sha256=catalog_sha
        )
        task_sha = digest(task_text.encode("utf-8"))
        decision = next(
            (item for item in selection.decisions if item.task_text_sha256 == task_sha),
            None,
        )
        if decision is None:
            raise ValueError("runtime tool selection has no exact queued-task decision")
        profile = self.base_acquirer.acquire(
            owner_uid=owner_uid, workspace=workspace, task_text=task_text
        )
        if profile.manifest.tools or profile.tool_definitions:
            raise ValueError(
                "runtime tool selection requires an empty base tool profile"
            )
        if (
            profile.manifest.scope.project_id != catalog.project_id
            or profile.manifest.policy_sha256 != catalog.policy_sha256
            or profile.manifest.profile_id != decision.profile_id
            or profile.manifest.work_unit != decision.work_unit
        ):
            raise ValueError(
                "runtime tool decision differs from the acquired task profile"
            )
        acquisition = profile.acquisition
        if acquisition is None:
            raise ValueError("runtime tool selection requires acquired author guidance")

        inventory = tuple(
            ToolProfileEntry(
                tool_id=entry.tool_id,
                schema_sha256=entry.schema_sha256,
                schema_bytes=entry.schema_bytes,
                required=choice.required,
                selected=choice.selected,
                authorized=entry.authorized,
                availability=entry.availability,
                selection_reason=choice.selection_reason,
                overlaps_with=entry.overlaps_with,
            )
            for entry, choice in zip(catalog.tools, decision.choices, strict=True)
        )
        definitions = tuple(
            entry.definition
            for entry, choice in zip(catalog.tools, decision.choices, strict=True)
            if choice.selected
        )
        selected_tool_bytes = sum(
            item.schema_bytes for item in inventory if item.selected
        )
        sizes = profile.manifest.sizes
        selected_ids = tuple(item.tool_id for item in inventory if item.selected)
        omitted_ids = tuple(item.tool_id for item in inventory if not item.selected)
        evidence = RuntimeToolCatalogEvidence(
            catalog_source_sha256=catalog_sha,
            selection_source_sha256=digest(self.selection_payload),
            catalog_id=catalog.catalog_id,
            catalog_revision=catalog.revision,
            decision_sha256=decision.sha256,
            task_text_sha256=task_sha,
            selected_tool_ids=selected_ids,
            omitted_tool_ids=omitted_ids,
        )
        manifest = profile.manifest.model_copy(
            update={
                "tools": inventory,
                "omitted_tool_ids": omitted_ids,
                "sizes": ProfileSizes(
                    root_instruction_bytes=sizes.root_instruction_bytes,
                    instruction_bytes=sizes.instruction_bytes,
                    tool_schema_bytes=selected_tool_bytes,
                    total_bytes=sizes.instruction_bytes + selected_tool_bytes,
                ),
            }
        )
        selected_profile = RuntimeTaskProfile.model_validate(
            profile.model_copy(
                update={
                    "manifest": manifest,
                    "tool_definitions": definitions,
                    "acquisition": acquisition.model_copy(
                        update={"tool_catalog": evidence}
                    ),
                }
            ).model_dump()
        )
        validate_task_profile_scope(
            selected_profile, owner_uid=owner_uid, workspace=workspace
        )
        return selected_profile
