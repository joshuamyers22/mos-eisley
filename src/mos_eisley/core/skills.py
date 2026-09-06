"""Provider- and filesystem-independent contracts for prompt-only skills."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    Text,
    canonical_bytes,
    digest,
)

SkillName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
SkillVersion = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._+-]{0,63}$",
    ),
]
SkillReference = Annotated[str, Field(min_length=78, max_length=160)]


class SkillIdentity(Contract):
    """Content identity; names and versions are labels, not authority."""

    schema_version: Literal[2] = 2
    source: Literal["user", "project"]
    name: SkillName
    version: SkillVersion | None = None
    kind: Literal["persona", "procedure"]
    package_sha256: Digest
    instructions_sha256: Digest

    @property
    def qualified_reference(self) -> str:
        return f"{self.source}:{self.name}@sha256:{self.package_sha256}"


class PromptAsset(Contract):
    """Exact reviewer instructions; skill metadata confers no authority."""

    schema_version: Literal[1] = 1
    mode: Literal["inline", "skill"]
    instructions: Text
    skill: SkillIdentity | None = None

    @model_validator(mode="after")
    def valid_source(self) -> Self:
        if self.mode == "inline" and self.skill is not None:
            raise ValueError("inline prompt assets cannot claim a skill identity")
        if self.mode == "skill" and (
            self.skill is None or self.skill.kind != "persona"
        ):
            raise ValueError("skill prompt assets require a persona identity")
        if self.skill is not None and (
            self.skill.instructions_sha256 != self.instructions_sha256
        ):
            raise ValueError("skill prompt instructions differ from its identity")
        return self

    @property
    def instructions_sha256(self) -> str:
        return digest(self.instructions.encode("utf-8"))

    @property
    def prompt_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillDescriptor(Contract):
    """Discovery metadata; deliberately excludes the instruction body."""

    schema_version: Literal[1] = 1
    identity: SkillIdentity
    description: Annotated[str, Field(min_length=1, max_length=1024)]
    license: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    compatibility: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    package_bytes: Annotated[int, Field(ge=1, le=4_000_000)]
    file_count: Annotated[int, Field(ge=1, le=64)]
    frontmatter_bytes: Annotated[int, Field(ge=1, le=16_000)]
    body_bytes: Annotated[int, Field(ge=1, le=32_000)]


class SkillRosterAssignment(Contract):
    critic_id: Identifier
    skill: SkillReference


class SkillRoster(Contract):
    """Explicit, digest-pinned bindings; no name-only or closest-path lookup."""

    schema_version: Literal[1] = 1
    assignments: Annotated[
        tuple[SkillRosterAssignment, ...], Field(min_length=1, max_length=8)
    ]

    @model_validator(mode="after")
    def unique_critics(self) -> Self:
        if len({item.critic_id for item in self.assignments}) != len(self.assignments):
            raise ValueError("duplicate skill-roster critic ID")
        return self


class SkillRunAssignment(Contract):
    critic_id: Identifier
    skill: SkillIdentity
    instructions_sha256: Digest
    instruction_bytes: Annotated[int, Field(ge=1, le=8000)]


class SkillRunManifest(Contract):
    """Exact skill provenance committed into a recorded run."""

    schema_version: Literal[1] = 1
    assignments: Annotated[
        tuple[SkillRunAssignment, ...], Field(min_length=1, max_length=8)
    ]

    @model_validator(mode="after")
    def unique_bindings(self) -> Self:
        critic_ids = [item.critic_id for item in self.assignments]
        if len(set(critic_ids)) != len(critic_ids):
            raise ValueError("duplicate skill-run critic ID")
        return self
