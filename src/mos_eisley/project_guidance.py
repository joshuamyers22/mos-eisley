"""Bounded inspection contracts for unbound, advisory local project templates."""

import json
import os
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.files import read_bounded

DESCRIPTOR_BYTES = 32 * 1024
MARKDOWN_BYTES = 64 * 1024
RuleText = Annotated[str, Field(min_length=1, max_length=4000)]
Detail = Annotated[str, Field(min_length=1, max_length=1000)]


class GuidanceRule(Contract):
    id: Identifier
    kind: Literal["advisory"] = "advisory"
    text: RuleText
    applies_when: Detail
    rationale: Detail
    checks: Annotated[tuple[Detail, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def nonempty_text(self) -> Self:
        for value in (self.text, self.applies_when, self.rationale, *self.checks):
            if not value.strip():
                raise ValueError("guidance fields require nonempty text")
            value.encode("utf-8")
        return self


class GuidanceDescriptor(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["advisory_project_guidance"] = "advisory_project_guidance"
    template_id: Identifier
    version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", max_length=40)]
    source_revision: Identifier
    content_sha256: Digest
    rules: Annotated[tuple[GuidanceRule, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def unique_rule_ids(self) -> Self:
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("guidance rule IDs must be unique")
        if len(canonical_bytes(self)) > DESCRIPTOR_BYTES:
            raise ValueError("guidance descriptor exceeds 32 KiB")
        return self


class LocatedGuidanceRule(Contract):
    id: Identifier
    character_start: Annotated[int, Field(ge=0)]
    character_end: Annotated[int, Field(gt=0)]


class GuidanceSnapshot(Contract):
    schema_version: Literal[1] = 1
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    descriptor_path: Annotated[str, Field(min_length=1, max_length=4096)]
    markdown_path: Annotated[str, Field(min_length=1, max_length=4096)]
    descriptor_sha256: Digest
    descriptor_json: Annotated[str, Field(min_length=1, max_length=DESCRIPTOR_BYTES)]
    descriptor: GuidanceDescriptor
    markdown: Annotated[str, Field(min_length=1, max_length=MARKDOWN_BYTES)]
    rules: Annotated[
        tuple[LocatedGuidanceRule, ...], Field(min_length=1, max_length=64)
    ]
    binding: Literal["unbound"] = "unbound"
    accepted_requirements: Literal[False] = False
    execution_authorized: Literal[False] = False
    history_loading_authorized: Literal[False] = False

    @model_validator(mode="after")
    def valid_snapshot(self) -> Self:
        if any(
            not Path(value).is_absolute()
            for value in (
                self.workspace,
                self.descriptor_path,
                self.markdown_path,
            )
        ):
            raise ValueError("guidance inspection paths must be absolute")
        raw = self.descriptor_json.encode("utf-8")
        if len(raw) > DESCRIPTOR_BYTES or digest(raw) != self.descriptor_sha256:
            raise ValueError("guidance descriptor bytes do not match their digest")
        try:
            json.loads(raw, object_pairs_hook=_unique_object)
            parsed = GuidanceDescriptor.model_validate_json(raw)
        except (ValueError, RecursionError):
            raise ValueError("invalid retained guidance descriptor") from None
        if parsed != self.descriptor:
            raise ValueError("retained guidance descriptor does not match")
        payload = self.markdown.encode("utf-8")
        if (
            len(payload) > MARKDOWN_BYTES
            or digest(payload) != self.descriptor.content_sha256
        ):
            raise ValueError("guidance content does not match its descriptor")
        if tuple(rule.id for rule in self.rules) != tuple(
            rule.id for rule in self.descriptor.rules
        ):
            raise ValueError("guidance rule inventory does not match")
        for rule, location in zip(self.descriptor.rules, self.rules, strict=True):
            start = self.markdown.find(rule.text)
            if (
                start < 0
                or self.markdown.find(rule.text, start + 1) >= 0
                or location.character_start != start
                or location.character_end != start + len(rule.text)
            ):
                raise ValueError(
                    "each guidance rule must identify one unique exact Markdown span"
                )
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate descriptor key")
        result[key] = value
    return result


def inspect_guidance(
    workspace: Path, descriptor_path: Path, markdown_path: Path
) -> GuidanceSnapshot:
    target = workspace.resolve(strict=True)
    if not target.is_dir():
        raise ValueError("guidance target must be an existing directory")
    # Input paths are explicitly selected. No descriptor field or Markdown link
    # chooses another file, and the final path component cannot be a symlink.
    descriptor_payload = read_bounded(descriptor_path, DESCRIPTOR_BYTES)
    try:
        json.loads(descriptor_payload, object_pairs_hook=_unique_object)
        descriptor = GuidanceDescriptor.model_validate_json(descriptor_payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid advisory guidance descriptor.") from None
    markdown = read_bounded(markdown_path, MARKDOWN_BYTES).decode("utf-8")
    locations: list[LocatedGuidanceRule] = []
    for rule in descriptor.rules:
        start = markdown.find(rule.text)
        if start < 0:
            raise ValueError("Declared guidance rule text is missing from Markdown.")
        locations.append(
            LocatedGuidanceRule(
                id=rule.id,
                character_start=start,
                character_end=start + len(rule.text),
            )
        )
    return GuidanceSnapshot(
        owner_uid=os.getuid(),
        workspace=str(target),
        descriptor_path=str(descriptor_path.absolute()),
        markdown_path=str(markdown_path.absolute()),
        descriptor_sha256=digest(descriptor_payload),
        descriptor_json=descriptor_payload.decode("utf-8"),
        descriptor=descriptor,
        markdown=markdown,
        rules=tuple(locations),
    )
