"""Bounded, immutable discovery for prompt-only Agent Skills packages."""

from __future__ import annotations

import os
import stat
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field
from yaml.nodes import MappingNode
from yaml.tokens import (
    AliasToken,
    AnchorToken,
    BlockEndToken,
    BlockMappingStartToken,
    BlockSequenceStartToken,
    FlowMappingEndToken,
    FlowMappingStartToken,
    FlowSequenceEndToken,
    FlowSequenceStartToken,
    TagToken,
)

from mos_eisley.core.models import digest
from mos_eisley.core.skills import (
    MAX_ARCHIVED_FILES,
    MAX_ARCHIVED_PACKAGE_BYTES,
    MAX_ARCHIVED_PATH_DEPTH,
    MAX_ARCHIVED_RESOURCE_BYTES,
    MAX_ARCHIVED_SIDECAR_BYTES,
    MAX_ARCHIVED_SKILL_BYTES,
    ArchivedSkillFile,
    PromptAsset,
    SkillDescriptor,
    SkillIdentity,
    SkillPackageArchive,
    SkillRoster,
    SkillRunAssignment,
    SkillRunManifest,
    skill_package_digest,
)
from mos_eisley.providers.recorded import Cassette
from mos_eisley.run.files import read_bounded

MAX_SKILLS = 64
MAX_FILES_PER_SKILL = MAX_ARCHIVED_FILES
MAX_ENTRIES_PER_SKILL = 128
MAX_FRONTMATTER_BYTES = MAX_ARCHIVED_SIDECAR_BYTES
MAX_SKILL_FILE_BYTES = MAX_ARCHIVED_SKILL_BYTES
MAX_RESOURCE_BYTES = MAX_ARCHIVED_RESOURCE_BYTES
MAX_PACKAGE_BYTES = MAX_ARCHIVED_PACKAGE_BYTES
MAX_CATALOG_BYTES = 16_000_000
MAX_PATH_DEPTH = MAX_ARCHIVED_PATH_DEPTH
MAX_PERSONA_BYTES = 8_000
MAX_YAML_TOKENS = 1024
MAX_YAML_DEPTH = 16

SkillSource = Literal["user", "project"]


class _StrictLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _StrictLoader, node: MappingNode, deep: bool = False
) -> dict[object, object]:
    loader.flatten_mapping(node)
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = cast(
            object,
            loader.construct_object(  # pyright: ignore[reportUnknownMemberType]
                key_node, deep=deep
            ),
        )
        if not isinstance(key, (str, int, float, bool, type(None))):
            raise ValueError("YAML mapping keys must be scalar")
        if key in result:
            raise ValueError("duplicate YAML mapping key")
        result[key] = cast(
            object,
            loader.construct_object(  # pyright: ignore[reportUnknownMemberType]
                value_node, deep=deep
            ),
        )
    return result


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


class _Frontmatter(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    name: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str = Field(min_length=1, max_length=1024)
    license: str | None = Field(default=None, min_length=1, max_length=256)
    compatibility: str | None = Field(default=None, min_length=1, max_length=500)
    metadata: dict[str, str] = Field(default_factory=dict)
    allowed_tools: str | None = Field(default=None, alias="allowed-tools")


@dataclass(frozen=True)
class ActivatedSkill:
    descriptor: SkillDescriptor
    instructions: str

    def as_prompt_asset(self) -> PromptAsset:
        if self.descriptor.identity.kind != "persona":
            raise ValueError("only persona skills can become reviewer prompts")
        return PromptAsset(
            mode="skill",
            instructions=self.instructions,
            skill=self.descriptor.identity,
        )


@dataclass(frozen=True)
class _EntryState:
    path: str
    mode: int
    size: int
    mtime_ns: int
    device: int
    inode: int
    links: int


@dataclass(frozen=True)
class _SkillSnapshot:
    descriptor: SkillDescriptor
    files: tuple[tuple[str, bytes], ...]
    body: str

    def activate(self) -> ActivatedSkill:
        return ActivatedSkill(descriptor=self.descriptor, instructions=self.body)

    def archive(self) -> SkillPackageArchive:
        return SkillPackageArchive(
            descriptor=self.descriptor,
            files=tuple(
                ArchivedSkillFile.retain(path, payload) for path, payload in self.files
            ),
        )

    def resource(self, relative_path: str) -> bytes:
        path = PurePosixPath(relative_path)
        if (
            path.is_absolute()
            or not path.parts
            or ".." in path.parts
            or "." in path.parts
            or len(path.parts) > MAX_PATH_DEPTH
        ):
            raise ValueError("skill resource path is invalid")
        normalized = path.as_posix()
        if normalized in {"SKILL.md", "mos.yaml"}:
            raise ValueError("skill control files are not resources")
        for candidate, payload in self.files:
            if candidate == normalized:
                return payload
        raise ValueError("skill resource is not present in the immutable snapshot")


@dataclass(frozen=True)
class SkillCatalog:
    """A complete byte snapshot; filesystem mutations cannot alter activation."""

    _skills: tuple[_SkillSnapshot, ...]

    @property
    def descriptors(self) -> tuple[SkillDescriptor, ...]:
        return tuple(skill.descriptor for skill in self._skills)

    @property
    def shadowed_names(self) -> tuple[str, ...]:
        sources: dict[str, set[str]] = {}
        for descriptor in self.descriptors:
            sources.setdefault(descriptor.identity.name, set()).add(
                descriptor.identity.source
            )
        return tuple(
            sorted(name for name, values in sources.items() if len(values) > 1)
        )

    def activate(
        self, reference: str, *, allow_project: bool = False
    ) -> ActivatedSkill:
        for skill in self._skills:
            identity = skill.descriptor.identity
            if identity.qualified_reference != reference:
                continue
            if identity.source == "project" and not allow_project:
                raise ValueError("project skill activation requires explicit approval")
            return skill.activate()
        raise ValueError("skill reference is absent from the immutable catalog")

    def resource(
        self,
        reference: str,
        relative_path: str,
        *,
        allow_project: bool = False,
    ) -> bytes:
        for skill in self._skills:
            identity = skill.descriptor.identity
            if identity.qualified_reference != reference:
                continue
            if identity.source == "project" and not allow_project:
                raise ValueError("project skill activation requires explicit approval")
            return skill.resource(relative_path)
        raise ValueError("skill reference is absent from the immutable catalog")

    def archive(
        self, reference: str, *, allow_project: bool = False
    ) -> SkillPackageArchive:
        for skill in self._skills:
            identity = skill.descriptor.identity
            if identity.qualified_reference != reference:
                continue
            if identity.source == "project" and not allow_project:
                raise ValueError("project skill retention requires explicit approval")
            return skill.archive()
        raise ValueError("skill reference is absent from the immutable catalog")


def _strict_yaml(payload: bytes, label: str) -> object:
    try:
        text = payload.decode("utf-8")
        depth = 0
        tokens = cast(
            Iterable[object],
            yaml.scan(text),  # pyright: ignore[reportUnknownMemberType]
        )
        for token_count, token in enumerate(tokens, start=1):
            if token_count > MAX_YAML_TOKENS:
                raise ValueError(f"{label} exceeds its YAML token limit")
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                raise ValueError(
                    f"{label} cannot contain YAML aliases, anchors, or tags"
                )
            if isinstance(
                token,
                (
                    BlockMappingStartToken,
                    BlockSequenceStartToken,
                    FlowMappingStartToken,
                    FlowSequenceStartToken,
                ),
            ):
                depth += 1
                if depth > MAX_YAML_DEPTH:
                    raise ValueError(f"{label} exceeds its YAML nesting limit")
            elif isinstance(
                token,
                (
                    BlockEndToken,
                    FlowMappingEndToken,
                    FlowSequenceEndToken,
                ),
            ):
                depth -= 1
        return yaml.load(text, Loader=_StrictLoader)
    except (RecursionError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ValueError(f"{label} is not valid bounded UTF-8 YAML") from error


def _split_skill(payload: bytes) -> tuple[_Frontmatter, bytes, int]:
    if not payload.startswith(b"---\n"):
        raise ValueError("SKILL.md must begin with YAML frontmatter")
    boundary = payload.find(b"\n---\n", 4)
    if boundary < 0:
        raise ValueError("SKILL.md frontmatter is not terminated")
    frontmatter_payload = payload[4:boundary]
    if not frontmatter_payload or len(frontmatter_payload) > MAX_FRONTMATTER_BYTES:
        raise ValueError("SKILL.md frontmatter exceeds its byte limit")
    loaded = _strict_yaml(frontmatter_payload, "SKILL.md frontmatter")
    if not isinstance(loaded, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")
    if "allowed-tools" in loaded:
        raise ValueError("allowed-tools is non-authorizing and unsupported")
    frontmatter = _Frontmatter.model_validate(loaded)
    body = payload[boundary + 5 :]
    if not body.strip() or len(body) > 32_000:
        raise ValueError("SKILL.md body is empty or exceeds its byte limit")
    try:
        body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("SKILL.md body must be UTF-8") from error
    return frontmatter, body, len(frontmatter_payload)


def _state(path: Path, relative: str) -> _EntryState:
    info = path.lstat()
    return _EntryState(
        path=relative,
        mode=info.st_mode,
        size=info.st_size,
        mtime_ns=info.st_mtime_ns,
        device=info.st_dev,
        inode=info.st_ino,
        links=info.st_nlink,
    )


def _inventory(skill_path: Path) -> tuple[_EntryState, ...]:
    root_state = _state(skill_path, ".")
    if not stat.S_ISDIR(root_state.mode) or stat.S_ISLNK(root_state.mode):
        raise ValueError("skill package must be a non-symlink directory")
    states: list[_EntryState] = [root_state]
    collision_keys: set[str] = set()

    def visit(directory: Path, parts: tuple[str, ...]) -> None:
        if len(parts) >= MAX_PATH_DEPTH:
            raise ValueError("skill package path depth exceeds its limit")
        children: list[os.DirEntry[str]] = []
        with os.scandir(directory) as entries:
            for entry in entries:
                children.append(entry)
                if len(states) + len(children) > MAX_ENTRIES_PER_SKILL:
                    raise ValueError("skill package entry count exceeds its limit")
        ordered = sorted(children, key=lambda item: item.name)
        for entry in ordered:
            relative_parts = (*parts, entry.name)
            relative = PurePosixPath(*relative_parts).as_posix()
            key = unicodedata.normalize("NFC", relative).casefold()
            if key in collision_keys:
                raise ValueError("skill package has a case or Unicode path collision")
            collision_keys.add(key)
            entry_state = _state(Path(entry.path), relative)
            if stat.S_ISLNK(entry_state.mode):
                raise ValueError("skill packages cannot contain symlinks")
            if stat.S_ISDIR(entry_state.mode):
                if relative_parts[0] == "scripts":
                    raise ValueError("skill scripts are outside the prompt-only scope")
                states.append(entry_state)
                visit(Path(entry.path), relative_parts)
            elif stat.S_ISREG(entry_state.mode):
                if relative_parts[0] == "scripts":
                    raise ValueError("skill scripts are outside the prompt-only scope")
                if entry_state.mode & 0o111:
                    raise ValueError(
                        "executable skill files are outside the prompt-only scope"
                    )
                if entry_state.links != 1:
                    raise ValueError("skill packages cannot contain hard-linked files")
                states.append(entry_state)
            else:
                raise ValueError("skill packages may contain only regular files")

    visit(skill_path, ())
    return tuple(states)


def _mos_extensions(payload: bytes | None) -> tuple[str | None, str | None]:
    if payload is None:
        return None, None
    if len(payload) > MAX_FRONTMATTER_BYTES:
        raise ValueError("mos.yaml exceeds its byte limit")
    loaded = _strict_yaml(payload, "mos.yaml")
    if not isinstance(loaded, dict):
        raise ValueError("mos.yaml must be a mapping")
    mapping = cast(dict[object, object], loaded)
    if set(mapping) - {"version", "kind"}:
        raise ValueError("mos.yaml permits only version and kind")
    raw_version = mapping.get("version")
    if raw_version is not None and (
        isinstance(raw_version, bool) or not isinstance(raw_version, (str, int))
    ):
        raise ValueError("mos.yaml version must be a string or integer")
    version = str(raw_version) if raw_version is not None else None
    if version is not None and not 1 <= len(version) <= 64:
        raise ValueError("mos.yaml version is invalid")
    raw_kind = mapping.get("kind")
    if raw_kind is not None and raw_kind not in {"persona", "procedure"}:
        raise ValueError("mos.yaml kind must be persona or procedure")
    return version, cast(str | None, raw_kind)


def _describe_package(
    immutable_files: tuple[tuple[str, bytes], ...],
    source: SkillSource,
    package_name: str,
) -> tuple[SkillDescriptor, str]:
    payload_by_name = dict(immutable_files)
    if (
        len(payload_by_name) != len(immutable_files)
        or "SKILL.md" not in payload_by_name
    ):
        raise ValueError("skill package files are invalid")
    frontmatter, body_payload, frontmatter_bytes = _split_skill(
        payload_by_name["SKILL.md"]
    )
    if frontmatter.name != package_name:
        raise ValueError("SKILL.md name must match its package name")
    version, kind = _mos_extensions(payload_by_name.get("mos.yaml"))
    metadata_version = frontmatter.metadata.get("mos.version")
    metadata_kind = frontmatter.metadata.get("mos.kind")
    if (
        version is not None
        and metadata_version is not None
        and version != metadata_version
    ):
        raise ValueError("mos.yaml and metadata disagree on version")
    if kind is not None and metadata_kind is not None and kind != metadata_kind:
        raise ValueError("mos.yaml and metadata disagree on kind")
    effective_version = version or metadata_version
    effective_kind = kind or metadata_kind or "procedure"
    if effective_kind not in {"persona", "procedure"}:
        raise ValueError("metadata mos.kind must be persona or procedure")
    if effective_version is not None and not 1 <= len(effective_version) <= 64:
        raise ValueError("metadata mos.version is invalid")
    body = body_payload.decode("utf-8").strip()
    identity = SkillIdentity(
        source=source,
        name=frontmatter.name,
        version=effective_version,
        kind=cast(Literal["persona", "procedure"], effective_kind),
        package_sha256=skill_package_digest(immutable_files),
        instructions_sha256=digest(body.encode("utf-8")),
    )
    descriptor = SkillDescriptor(
        identity=identity,
        description=frontmatter.description,
        license=frontmatter.license,
        compatibility=frontmatter.compatibility,
        package_bytes=sum(len(payload) for _, payload in immutable_files),
        file_count=len(immutable_files),
        frontmatter_bytes=frontmatter_bytes,
        body_bytes=len(body.encode("utf-8")),
    )
    return descriptor, body


def _load_package(skill_path: Path, source: SkillSource) -> _SkillSnapshot:
    before = _inventory(skill_path)
    file_states = tuple(item for item in before if stat.S_ISREG(item.mode))
    if not file_states or len(file_states) > MAX_FILES_PER_SKILL:
        raise ValueError("skill package file count exceeds its limit")
    if "SKILL.md" not in {item.path for item in file_states}:
        raise ValueError("skill package is missing SKILL.md")
    files: list[tuple[str, bytes]] = []
    total = 0
    for item in sorted(file_states, key=lambda value: value.path):
        if item.path == "SKILL.md":
            limit = MAX_SKILL_FILE_BYTES
        elif item.path == "mos.yaml":
            limit = MAX_FRONTMATTER_BYTES
        else:
            limit = MAX_RESOURCE_BYTES
        payload = read_bounded(skill_path / item.path, limit)
        total += len(payload)
        if total > MAX_PACKAGE_BYTES:
            raise ValueError("skill package exceeds its total byte limit")
        files.append((item.path, payload))
    after = _inventory(skill_path)
    if before != after:
        raise ValueError("skill package changed while being snapshotted")
    immutable_files = tuple(files)
    descriptor, body = _describe_package(immutable_files, source, skill_path.name)
    return _SkillSnapshot(descriptor=descriptor, files=immutable_files, body=body)


def verify_skill_archive(archive: SkillPackageArchive) -> None:
    """Rebuild all semantic metadata from retained bytes without materializing them."""

    if (
        archive.activation_authorized
        or archive.installation_authorized
        or archive.configuration_mutation_authorized
    ):
        raise ValueError("archived skill grants deployment authority")
    files = tuple((item.path, item.payload) for item in archive.files)
    identity = archive.descriptor.identity
    descriptor, _ = _describe_package(files, identity.source, identity.name)
    if descriptor != archive.descriptor:
        raise ValueError("archived skill descriptor does not match retained bytes")


def discover_skills(
    *,
    user_roots: tuple[Path, ...] = (),
    project_roots: tuple[Path, ...] = (),
) -> SkillCatalog:
    """Discover only explicit roots; no cwd, home, or config lookup occurs."""

    snapshots: list[_SkillSnapshot] = []
    identities: set[tuple[str, str]] = set()
    total = 0
    for source, roots in (("user", user_roots), ("project", project_roots)):
        for root in roots:
            root_state = root.lstat()
            if not stat.S_ISDIR(root_state.st_mode) or stat.S_ISLNK(root_state.st_mode):
                raise ValueError("skill root must be a non-symlink directory")
            child_entries: list[os.DirEntry[str]] = []
            with os.scandir(root) as entries:
                for entry in entries:
                    child_entries.append(entry)
                    if len(child_entries) > MAX_SKILLS:
                        raise ValueError("skill root exceeds its entry limit")
            children = sorted(child_entries, key=lambda item: item.name)
            for child in children:
                if child.name.startswith("."):
                    continue
                child_path = Path(child.path)
                child_state = child_path.lstat()
                if not stat.S_ISDIR(child_state.st_mode) or stat.S_ISLNK(
                    child_state.st_mode
                ):
                    raise ValueError("skill roots may contain only skill directories")
                key = (source, child.name)
                if key in identities:
                    raise ValueError("duplicate source-qualified skill name")
                snapshot = _load_package(child_path, cast(SkillSource, source))
                snapshots.append(snapshot)
                identities.add(key)
                total += snapshot.descriptor.package_bytes
                if len(snapshots) > MAX_SKILLS or total > MAX_CATALOG_BYTES:
                    raise ValueError("skill catalog exceeds its discovery limit")
    return SkillCatalog(tuple(snapshots))


def bind_skill_roster(
    cassette: Cassette,
    roster: SkillRoster,
    catalog: SkillCatalog,
    *,
    allow_project: bool = False,
) -> SkillRunManifest:
    """Bind skill bodies to existing request-bound personas without changing them."""

    recordings = {item.critic.id: item.critic for item in cassette.critics}
    assignments = {item.critic_id: item.skill for item in roster.assignments}
    if assignments.keys() != recordings.keys():
        raise ValueError("skill roster must exactly cover cassette critics")
    run_assignments: list[SkillRunAssignment] = []
    for recording in cassette.critics:
        critic = recording.critic
        activated = catalog.activate(
            assignments[critic.id], allow_project=allow_project
        )
        if activated.descriptor.identity.kind != "persona":
            raise ValueError("critic assignments require persona skills")
        encoded = activated.instructions.encode("utf-8")
        if not encoded or len(encoded) > MAX_PERSONA_BYTES:
            raise ValueError("activated persona exceeds the critic byte limit")
        if activated.instructions != critic.persona:
            raise ValueError("skill persona does not match the request-bound cassette")
        run_assignments.append(
            SkillRunAssignment(
                critic_id=critic.id,
                skill=activated.descriptor.identity,
                instructions_sha256=digest(encoded),
                instruction_bytes=len(encoded),
            )
        )
    return SkillRunManifest(assignments=tuple(run_assignments))


def verify_skill_run_manifest(cassette: Cassette, manifest: SkillRunManifest) -> None:
    critics = {item.critic.id: item.critic for item in cassette.critics}
    assignments = {item.critic_id: item for item in manifest.assignments}
    if assignments.keys() != critics.keys():
        raise ValueError("skill run manifest does not cover cassette critics")
    for critic_id, critic in critics.items():
        assignment = assignments[critic_id]
        payload = critic.persona.encode("utf-8")
        if (
            assignment.skill.kind != "persona"
            or assignment.instructions_sha256 != digest(payload)
            or assignment.instruction_bytes != len(payload)
        ):
            raise ValueError("skill run manifest does not match cassette personas")
