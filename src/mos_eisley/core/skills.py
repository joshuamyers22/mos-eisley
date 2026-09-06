"""Provider- and filesystem-independent contracts for prompt-only skills."""

from __future__ import annotations

import base64
import binascii
import hashlib
import unicodedata
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

MAX_ARCHIVED_FILES = 64
MAX_ARCHIVED_SKILL_BYTES = 64_000
MAX_ARCHIVED_SIDECAR_BYTES = 16_000
MAX_ARCHIVED_RESOURCE_BYTES = 1_000_000
MAX_ARCHIVED_PACKAGE_BYTES = 4_000_000
MAX_ARCHIVED_PATH_DEPTH = 4


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


def skill_package_digest(files: tuple[tuple[str, bytes], ...]) -> str:
    """Commit to canonical ordered package paths and exact file bytes."""

    hasher = hashlib.sha256(b"mos-eisley.skill-package.v1\0")
    for relative, payload in files:
        encoded = relative.encode("utf-8")
        hasher.update(len(encoded).to_bytes(8, "big"))
        hasher.update(encoded)
        hasher.update(len(payload).to_bytes(8, "big"))
        hasher.update(payload)
    return hasher.hexdigest()


class ArchivedSkillFile(Contract):
    """One exact inert file payload retained inside a skill archive."""

    schema_version: Literal[1] = 1
    path: Annotated[str, Field(min_length=1, max_length=1024)]
    content_base64: Annotated[str, Field(min_length=0, max_length=1_333_336)]
    content_sha256: Digest
    byte_count: Annotated[int, Field(ge=0, le=MAX_ARCHIVED_RESOURCE_BYTES)]

    @model_validator(mode="after")
    def valid_file(self) -> Self:
        parts = self.path.split("/")
        if (
            self.path.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)
            or len(parts) > MAX_ARCHIVED_PATH_DEPTH
            or parts[0] == "scripts"
            or "\x00" in self.path
        ):
            raise ValueError("archived skill path is invalid")
        try:
            payload = base64.b64decode(self.content_base64, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError(
                "archived skill content is not canonical base64"
            ) from error
        if base64.b64encode(payload).decode("ascii") != self.content_base64:
            raise ValueError("archived skill content is not canonical base64")
        if len(payload) != self.byte_count or digest(payload) != self.content_sha256:
            raise ValueError("archived skill file digest or byte count differs")
        limit = (
            MAX_ARCHIVED_SKILL_BYTES
            if self.path == "SKILL.md"
            else (
                MAX_ARCHIVED_SIDECAR_BYTES
                if self.path == "mos.yaml"
                else MAX_ARCHIVED_RESOURCE_BYTES
            )
        )
        if len(payload) > limit:
            raise ValueError("archived skill file exceeds its byte limit")
        return self

    @property
    def payload(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)

    @classmethod
    def retain(cls, path: str, payload: bytes) -> Self:
        return cls(
            path=path,
            content_base64=base64.b64encode(payload).decode("ascii"),
            content_sha256=digest(payload),
            byte_count=len(payload),
        )


class SkillPackageArchive(Contract):
    """Deterministic retained bytes; never installation or activation authority."""

    schema_version: Literal[1] = 1
    mode: Literal["retained_skill_package"] = "retained_skill_package"
    descriptor: SkillDescriptor
    files: Annotated[
        tuple[ArchivedSkillFile, ...],
        Field(min_length=1, max_length=MAX_ARCHIVED_FILES),
    ]
    activation_authorized: Literal[False] = False
    installation_authorized: Literal[False] = False
    configuration_mutation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def valid_package(self) -> Self:
        paths = [item.path for item in self.files]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError(
                "archived skill files must be unique and canonically ordered"
            )
        collision_keys = [
            unicodedata.normalize("NFC", path).casefold() for path in paths
        ]
        if len(collision_keys) != len(set(collision_keys)):
            raise ValueError("archived skill package has a path collision")
        if "SKILL.md" not in paths:
            raise ValueError("archived skill package is missing SKILL.md")
        files = tuple((item.path, item.payload) for item in self.files)
        total = sum(len(payload) for _, payload in files)
        if total > MAX_ARCHIVED_PACKAGE_BYTES:
            raise ValueError("archived skill package exceeds its total byte limit")
        if (
            self.descriptor.file_count != len(files)
            or self.descriptor.package_bytes != total
            or self.descriptor.identity.package_sha256 != skill_package_digest(files)
        ):
            raise ValueError("archived skill package differs from its descriptor")
        return self

    @property
    def archive_sha256(self) -> str:
        return digest(canonical_bytes(self))


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
