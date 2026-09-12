"""Reviewed requirement selections and exact, explicitly selected source snapshots."""

import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.project_guidance import Detail, RuleText
from mos_eisley.project_guidance_storage import GUIDANCE_FILE_BYTES
from mos_eisley.run.files import read_bounded

INPUT_BYTES = 64 * 1024
SOURCE_BYTES = 64 * 1024
TOTAL_SOURCE_BYTES = 128 * 1024


class RequirementSource(Contract):
    id: Identifier
    kind: Literal["brief", "adr"]
    content_sha256: Digest


class Requirement(Contract):
    id: Identifier
    source_id: Identifier
    text: RuleText
    applies_when: Detail
    rationale: Detail
    checks: Annotated[tuple[Detail, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def nonempty_text(self) -> Self:
        for value in (self.text, self.applies_when, self.rationale, *self.checks):
            if not value.strip():
                raise ValueError("Requirement fields require nonempty text.")
            value.encode("utf-8")
        return self


class RequirementSelection(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["project_requirement_selection"] = "project_requirement_selection"
    review_rationale: Detail
    sources: Annotated[tuple[RequirementSource, ...], Field(min_length=1, max_length=8)]
    requirements: Annotated[tuple[Requirement, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def valid_selection(self) -> Self:
        if not self.review_rationale.strip():
            raise ValueError("Requirement acceptance needs a review rationale.")
        self.review_rationale.encode("utf-8")
        ids = {source.id for source in self.sources}
        if len(ids) != len(self.sources) or len(
            {r.id for r in self.requirements}
        ) != len(self.requirements):
            raise ValueError("Source and requirement IDs must be unique.")
        if {r.source_id for r in self.requirements} != ids:
            raise ValueError("Every selected source must supply a requirement.")
        if len(canonical_bytes(self)) > INPUT_BYTES:
            raise ValueError("Requirement selection exceeds 64 KiB.")
        return self


def decode_selection(payload: bytes) -> RequirementSelection:
    if len(payload) > INPUT_BYTES:
        raise ValueError("Requirement selection exceeds 64 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return RequirementSelection.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid project requirement selection.") from None


class PinnedRequirementSource(Contract):
    path: Annotated[str, Field(min_length=1, max_length=4096)]
    text: Annotated[str, Field(min_length=1, max_length=SOURCE_BYTES)]


class RequirementProposal(Contract):
    selection_json: Annotated[str, Field(min_length=1, max_length=INPUT_BYTES)]
    selection: RequirementSelection
    sources: Annotated[
        tuple[PinnedRequirementSource, ...], Field(min_length=1, max_length=8)
    ]

    @model_validator(mode="after")
    def valid_provenance(self) -> Self:
        if decode_selection(self.selection_json.encode("utf-8")) != self.selection:
            raise ValueError("Retained requirement selection differs from its source.")
        if len(self.sources) != len(self.selection.sources):
            raise ValueError("Provide one explicit source path per declared source.")
        total = 0
        for declared, pinned in zip(self.selection.sources, self.sources, strict=True):
            payload = pinned.text.encode("utf-8")
            total += len(payload)
            if (
                not Path(pinned.path).is_absolute()
                or len(payload) > SOURCE_BYTES
                or digest(payload) != declared.content_sha256
            ):
                raise ValueError("Requirement source path, size or digest is invalid.")
            for requirement in self.selection.requirements:
                if requirement.source_id != declared.id:
                    continue
                start = pinned.text.find(requirement.text)
                if start < 0 or pinned.text.find(requirement.text, start + 1) >= 0:
                    raise ValueError(
                        "Each requirement must match one exact source span."
                    )
        if total > TOTAL_SOURCE_BYTES:
            raise ValueError("Combined requirement sources exceed 128 KiB.")
        return self


def inspect_requirements(
    input_path: Path, source_paths: tuple[Path, ...]
) -> RequirementProposal:
    payload = read_bounded(input_path, INPUT_BYTES)
    selection = decode_selection(payload)
    if len(source_paths) != len(selection.sources):
        raise ValueError("Provide --source paths in declared source order.")
    return RequirementProposal(
        selection_json=payload.decode("utf-8"),
        selection=selection,
        sources=tuple(
            PinnedRequirementSource(
                path=str(path.absolute()),
                text=read_bounded(path, SOURCE_BYTES).decode("utf-8"),
            )
            for path in source_paths
        ),
    )


class SavedRequirements(Contract):
    schema_version: Literal[1] = 1
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: MappedDirectory
    revision: Annotated[int, Field(ge=1)]
    proposal: RequirementProposal | None
    context_materialized: Literal[False] = False
    execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bounded_record(self) -> Self:
        if len(canonical_bytes(self)) > GUIDANCE_FILE_BYTES:
            raise ValueError("Saved requirements exceed 512 KiB.")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))
