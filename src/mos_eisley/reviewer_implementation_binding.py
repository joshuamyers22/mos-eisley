"""Immutable offline bindings from frozen reviewer tests to implementation code."""

from __future__ import annotations

import ast
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.reviewer_test_package import (
    FROZEN_PACKAGE_BYTES,
    FrozenReviewerTestPackage,
    decode_frozen_reviewer_test_package,
)

BINDING_MANIFEST_BYTES = 2_000_000
BINDING_RECORD_BYTES = 4_000_000
IMPLEMENTATION_FILE_BYTES = 2_000_000
TOTAL_IMPLEMENTATION_BYTES = 32_000_000
MAX_IMPLEMENTATION_FILES = 2_048
MAX_INVENTORY_ENTRIES = 4_096
MAX_INVENTORY_DEPTH = 64
REVIEWER_ADAPTER_MODULE = "mos_eisley_reviewer_adapter"

RelativePath = Annotated[str, Field(min_length=1, max_length=4096)]
DottedName = Annotated[
    str,
    Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"),
]
SymbolName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
SourceRevision = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
BindingFileKind = Literal[
    "implementation_source",
    "implementation_resource",
    "dependency_lock",
    "build_metadata",
]
BindingMediaType = Literal[
    "text/x-python",
    "text/plain",
    "application/json",
    "application/toml",
    "application/octet-stream",
]


def _relative_path(value: str) -> str:
    if "\\" in value or "\x00" in value:
        raise ValueError("binding paths must use canonical POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("binding paths must remain below the implementation root")
    canonical = path.as_posix()
    if canonical != value or canonical == ".":
        raise ValueError("binding paths must be canonical relative paths")
    return value


class ImplementationFileDeclaration(Contract):
    path: RelativePath
    kind: BindingFileKind
    media_type: BindingMediaType
    content_sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=IMPLEMENTATION_FILE_BYTES)]

    @field_validator("path")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        return _relative_path(value)

    @model_validator(mode="after")
    def coherent_type(self) -> Self:
        is_python = self.path.endswith(".py")
        if is_python != (self.kind == "implementation_source"):
            raise ValueError("Python files must be declared implementation sources")
        if is_python != (self.media_type == "text/x-python"):
            raise ValueError("Python source paths and media types must agree")
        if self.kind == "dependency_lock" and not (
            self.path.endswith(".lock")
            or PurePosixPath(self.path).name.startswith("requirements")
            and self.path.endswith(".txt")
        ):
            raise ValueError("dependency locks require a lock or requirements file")
        return self


class DirectSymbolBinding(Contract):
    """One alias to a directly defined implementation symbol; no wrapper code."""

    exposed_name: SymbolName
    target_module: DottedName
    target_symbol: SymbolName
    target_file: RelativePath

    @field_validator("target_file")
    @classmethod
    def canonical_target_file(cls, value: str) -> str:
        return _relative_path(value)


class AllowlistedImplementationAdapter(Contract):
    """Declarative direct-import surface consumed only by a later isolated runner."""

    schema_version: Literal[1] = 1
    kind: Literal["direct_symbol_allowlist"] = "direct_symbol_allowlist"
    reviewer_module: Literal["mos_eisley_reviewer_adapter"] = REVIEWER_ADAPTER_MODULE
    exports: Annotated[
        tuple[DirectSymbolBinding, ...], Field(min_length=1, max_length=256)
    ]
    wrapper_code_authorized: Literal[False] = False
    monkeypatch_authorized: Literal[False] = False
    result_substitution_authorized: Literal[False] = False
    exception_translation_authorized: Literal[False] = False
    discovery_override_authorized: Literal[False] = False
    test_result_interception_authorized: Literal[False] = False

    @model_validator(mode="after")
    def unique_sorted_exports(self) -> Self:
        keys = tuple(item.exposed_name for item in self.exports)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("adapter exports must be unique and sorted")
        targets = tuple(
            (item.target_module, item.target_symbol, item.target_file)
            for item in self.exports
        )
        if len(targets) != len(set(targets)):
            raise ValueError("adapter targets must be unique")
        return self


class ImplementationBindingManifest(Contract):
    """Expected code tree and the complete declarative reviewer adapter."""

    schema_version: Literal[1] = 1
    kind: Literal["reviewer_implementation_binding_manifest"] = (
        "reviewer_implementation_binding_manifest"
    )
    binding_id: Identifier
    source_revision: SourceRevision
    frozen_reviewer_test_package_sha256: Digest
    source_roots: Annotated[
        tuple[RelativePath, ...], Field(min_length=1, max_length=32)
    ]
    files: Annotated[
        tuple[ImplementationFileDeclaration, ...],
        Field(min_length=2, max_length=MAX_IMPLEMENTATION_FILES),
    ]
    adapter: AllowlistedImplementationAdapter
    implementation_inspected: Literal[True] = True
    reviewer_package_mutation_authorized: Literal[False] = False
    test_execution_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("source_roots")
    @classmethod
    def canonical_roots(cls, roots: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_relative_path(root) for root in roots)

    @model_validator(mode="after")
    def complete_binding(self) -> Self:
        roots = tuple(PurePosixPath(item) for item in self.source_roots)
        if self.source_roots != tuple(sorted(self.source_roots)) or len(roots) != len(
            set(roots)
        ):
            raise ValueError("source roots must be unique and sorted")
        if any(
            left.is_relative_to(right) or right.is_relative_to(left)
            for index, left in enumerate(roots)
            for right in roots[index + 1 :]
        ):
            raise ValueError("source roots must not overlap")

        paths = tuple(item.path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("implementation files must be unique and sorted")
        if sum(item.bytes for item in self.files) > TOTAL_IMPLEMENTATION_BYTES:
            raise ValueError("implementation binding exceeds 32 MB")
        sources = {
            item.path: item
            for item in self.files
            if item.kind == "implementation_source"
        }
        if not sources or not any(
            item.kind == "dependency_lock" for item in self.files
        ):
            raise ValueError("binding requires source files and a dependency lock")
        if not any(item.kind == "build_metadata" for item in self.files):
            raise ValueError("binding requires build metadata")
        bound_source_paths = {
            item.path
            for item in self.files
            if item.kind in {"implementation_source", "implementation_resource"}
        }
        if any(
            sum(PurePosixPath(path).is_relative_to(root) for root in roots) != 1
            for path in bound_source_paths
        ):
            raise ValueError("every implementation file requires one source root")
        if any(
            PurePosixPath(item.path).is_relative_to(root)
            for item in self.files
            if item.kind in {"dependency_lock", "build_metadata"}
            for root in roots
        ):
            raise ValueError(
                "dependency and build files must remain outside source roots"
            )

        for export in self.adapter.exports:
            declaration = sources.get(export.target_file)
            if declaration is None:
                raise ValueError(
                    "adapter targets must be declared implementation source"
                )
            matching_root = next(
                root
                for root in roots
                if PurePosixPath(export.target_file).is_relative_to(root)
            )
            if export.target_module != _module_name(export.target_file, matching_root):
                raise ValueError("adapter target module must match its source path")
        if len(canonical_bytes(self)) > BINDING_MANIFEST_BYTES:
            raise ValueError("implementation-binding manifest exceeds 2 MB")
        return self

    @property
    def manifest_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ImplementationTreeIdentity(Contract):
    source_revision: SourceRevision
    files: Annotated[
        tuple[ImplementationFileDeclaration, ...],
        Field(min_length=2, max_length=MAX_IMPLEMENTATION_FILES),
    ]


class ImplementationBindingPayload(Contract):
    manifest: ImplementationBindingManifest
    binding_manifest_sha256: Digest
    frozen_reviewer_test_package_sha256: Digest
    reviewer_test_payload_sha256: Digest
    implementation_tree_sha256: Digest
    adapter_sha256: Digest

    @model_validator(mode="after")
    def exact_identities(self) -> Self:
        if self.binding_manifest_sha256 != self.manifest.manifest_sha256:
            raise ValueError("binding manifest digest is invalid")
        if self.frozen_reviewer_test_package_sha256 != (
            self.manifest.frozen_reviewer_test_package_sha256
        ):
            raise ValueError("reviewer-test package identity differs from the manifest")
        tree = ImplementationTreeIdentity(
            source_revision=self.manifest.source_revision,
            files=self.manifest.files,
        )
        if self.implementation_tree_sha256 != digest(canonical_bytes(tree)):
            raise ValueError("implementation tree digest is invalid")
        if self.adapter_sha256 != digest(canonical_bytes(self.manifest.adapter)):
            raise ValueError("implementation adapter digest is invalid")
        return self


class ImmutableImplementationBindingRecord(Contract):
    """Content-addressed binding evidence; never execution or mutation authority."""

    schema_version: Literal[1] = 1
    kind: Literal["immutable_reviewer_implementation_binding"] = (
        "immutable_reviewer_implementation_binding"
    )
    payload: ImplementationBindingPayload
    payload_sha256: Digest
    reviewer_package_before_sha256: Digest
    reviewer_package_after_sha256: Digest
    binding_validated: Literal[True] = True
    implementation_binding_authorized: Literal[False] = False
    test_execution_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exact_record(self) -> Self:
        if self.payload_sha256 != digest(canonical_bytes(self.payload)):
            raise ValueError("implementation-binding payload digest is invalid")
        expected = self.payload.frozen_reviewer_test_package_sha256
        if (
            self.reviewer_package_before_sha256 != expected
            or self.reviewer_package_after_sha256 != expected
        ):
            raise ValueError(
                "reviewer-test package changed across implementation binding"
            )
        if len(canonical_bytes(self)) > BINDING_RECORD_BYTES:
            raise ValueError("implementation-binding record exceeds 4 MB")
        return self

    @property
    def binding_record_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _module_name(path: str, root: PurePosixPath) -> str:
    relative = PurePosixPath(path).relative_to(root)
    if relative.name == "__init__.py":
        parts = relative.parent.parts
    else:
        parts = (*relative.parent.parts, relative.stem)
    if not parts or any(not part.isidentifier() for part in parts):
        raise ValueError("implementation source path is not an importable module")
    return ".".join(parts)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def decode_implementation_binding_manifest(
    payload: bytes,
) -> ImplementationBindingManifest:
    if len(payload) > BINDING_MANIFEST_BYTES:
        raise ValueError("implementation-binding manifest exceeds 2 MB")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=_unique_object)
        return ImplementationBindingManifest.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("invalid implementation-binding manifest") from None


def decode_implementation_binding_record(
    payload: bytes,
) -> ImmutableImplementationBindingRecord:
    if len(payload) > BINDING_RECORD_BYTES:
        raise ValueError("implementation-binding record exceeds 4 MB")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=_unique_object)
        record = ImmutableImplementationBindingRecord.model_validate_json(payload)
        if payload != canonical_bytes(record):
            raise ValueError("implementation-binding record must be canonical")
        return record
    except (ValueError, RecursionError):
        raise ValueError("invalid implementation-binding record") from None


def _open_directory(root_fd: int, relative: str) -> int:
    directory_fd = os.dup(root_fd)
    try:
        for part in PurePosixPath(relative).parts:
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd
    except BaseException:
        os.close(directory_fd)
        raise


def _source_inventory(
    directory_fd: int,
    prefix: PurePosixPath,
    *,
    entry_count: list[int],
    depth: int,
) -> tuple[str, ...]:
    if depth > MAX_INVENTORY_DEPTH:
        raise ValueError("source inventory exceeds its directory-depth limit")
    found: list[str] = []
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            name = entry.name
            entry_count[0] += 1
            if entry_count[0] > MAX_INVENTORY_ENTRIES:
                raise ValueError("source inventory exceeds its entry limit")
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            path = prefix / name
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("source inventory must not contain symlinks")
            if stat.S_ISDIR(info.st_mode):
                if name == "__pycache__":
                    raise ValueError(
                        "source inventory must not contain generated bytecode"
                    )
                child_fd = os.open(
                    name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
                try:
                    found.extend(
                        _source_inventory(
                            child_fd,
                            path,
                            entry_count=entry_count,
                            depth=depth + 1,
                        )
                    )
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                if name.endswith((".pyc", ".pyo")):
                    raise ValueError(
                        "source inventory must not contain generated bytecode"
                    )
                found.append(path.as_posix())
            else:
                raise ValueError(
                    "source inventory must contain only files and directories"
                )
    return tuple(sorted(found))


def _read_root_file(
    root_fd: int, relative: str, limit: int
) -> tuple[bytes, tuple[int, int]]:
    parts = PurePosixPath(relative).parts
    directory_fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
        with os.fdopen(file_fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("binding input must be a regular file")
            if before.st_nlink != 1:
                raise ValueError("binding input must not have filesystem aliases")
            payload = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        if len(payload) > limit:
            raise ValueError("binding input exceeds its byte limit")
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise ValueError("binding input changed while being read")
        return payload, (before.st_dev, before.st_ino)
    finally:
        os.close(directory_fd)


def _read_stable_file(path: Path, limit: int) -> bytes:
    file_fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(file_fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("binding input must be a regular file")
        if before.st_nlink != 1:
            raise ValueError("binding input must not have filesystem aliases")
        payload = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(payload) > limit:
        raise ValueError("binding input exceeds its byte limit")
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
    ):
        raise ValueError("binding input changed while being read")
    return payload


def _direct_definitions(path: str, payload: bytes) -> set[str]:
    try:
        tree = ast.parse(payload.decode("utf-8"), filename=path)
    except (SyntaxError, UnicodeDecodeError):
        raise ValueError(f"invalid implementation Python source: {path}") from None
    definitions: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            definitions.update(
                target.id for target in targets if isinstance(target, ast.Name)
            )
    return definitions


def _verify_reviewer_import_surface(
    package: FrozenReviewerTestPackage,
    manifest: ImplementationBindingManifest,
) -> None:
    imported_exports: set[str] = set()
    target_roots = {
        item.target_module.split(".", 1)[0] for item in manifest.adapter.exports
    }
    for frozen_file in package.payload.files:
        if frozen_file.declaration.media_type != "text/x-python":
            continue
        try:
            tree = ast.parse(
                frozen_file.content.decode("utf-8"),
                filename=frozen_file.declaration.path,
            )
        except (SyntaxError, UnicodeDecodeError):
            raise ValueError("invalid Python in frozen reviewer-test package") from None
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level == 0 and module == REVIEWER_ADAPTER_MODULE:
                    if any(alias.name == "*" for alias in node.names):
                        raise ValueError("reviewer adapter star imports are forbidden")
                    imported_exports.update(alias.name for alias in node.names)
                if node.level == 0 and module.split(".", 1)[0] in target_roots:
                    raise ValueError(
                        "reviewer tests must not import implementation directly"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if alias.name == REVIEWER_ADAPTER_MODULE:
                        raise ValueError(
                            "reviewer adapter requires explicit from-imports"
                        )
                    if root in target_roots:
                        raise ValueError(
                            "reviewer tests must not import implementation directly"
                        )
    expected = {item.exposed_name for item in manifest.adapter.exports}
    if imported_exports != expected:
        raise ValueError("reviewer imports must exactly match adapter exports")


def _snapshot_implementation(
    manifest: ImplementationBindingManifest, implementation_root: Path
) -> dict[str, bytes]:
    root_fd = os.open(implementation_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        discovered: list[str] = []
        entry_count = [0]
        for source_root in manifest.source_roots:
            source_fd = _open_directory(root_fd, source_root)
            try:
                discovered.extend(
                    _source_inventory(
                        source_fd,
                        PurePosixPath(source_root),
                        entry_count=entry_count,
                        depth=0,
                    )
                )
            finally:
                os.close(source_fd)
        declared = tuple(
            item.path
            for item in manifest.files
            if item.kind in {"implementation_source", "implementation_resource"}
        )
        if tuple(sorted(discovered)) != declared:
            raise ValueError(
                "declared files differ from the complete source-root inventory"
            )

        identities: set[tuple[int, int]] = set()
        payloads: dict[str, bytes] = {}
        for declaration in manifest.files:
            payload, identity = _read_root_file(
                root_fd, declaration.path, IMPLEMENTATION_FILE_BYTES
            )
            if identity in identities:
                raise ValueError("binding files must not alias one filesystem object")
            identities.add(identity)
            if (
                len(payload) != declaration.bytes
                or digest(payload) != declaration.content_sha256
            ):
                raise ValueError("implementation file differs from its declaration")
            payloads[declaration.path] = payload
        return payloads
    finally:
        os.close(root_fd)


def create_implementation_binding_record(
    manifest: ImplementationBindingManifest,
    reviewer_package_path: Path,
    implementation_root: Path,
) -> ImmutableImplementationBindingRecord:
    """Bind exact package and code identities without importing or executing either."""
    package_before = _read_stable_file(reviewer_package_path, FROZEN_PACKAGE_BYTES)
    package = decode_frozen_reviewer_test_package(package_before)
    if package_before != canonical_bytes(package):
        raise ValueError("frozen reviewer-test package must use canonical encoding")
    package_sha256 = digest(package_before)
    if package_sha256 != manifest.frozen_reviewer_test_package_sha256:
        raise ValueError(
            "frozen reviewer-test package differs from the binding manifest"
        )

    payloads = _snapshot_implementation(manifest, implementation_root)
    _verify_reviewer_import_surface(package, manifest)
    for export in manifest.adapter.exports:
        if export.target_symbol not in _direct_definitions(
            export.target_file, payloads[export.target_file]
        ):
            raise ValueError(
                "adapter target must be defined directly in its source file"
            )

    package_after = _read_stable_file(reviewer_package_path, FROZEN_PACKAGE_BYTES)
    if package_after != package_before:
        raise ValueError("frozen reviewer-test package changed during binding")
    tree = ImplementationTreeIdentity(
        source_revision=manifest.source_revision,
        files=manifest.files,
    )
    payload = ImplementationBindingPayload(
        manifest=manifest,
        binding_manifest_sha256=manifest.manifest_sha256,
        frozen_reviewer_test_package_sha256=package_sha256,
        reviewer_test_payload_sha256=package.payload_sha256,
        implementation_tree_sha256=digest(canonical_bytes(tree)),
        adapter_sha256=digest(canonical_bytes(manifest.adapter)),
    )
    return ImmutableImplementationBindingRecord(
        payload=payload,
        payload_sha256=digest(canonical_bytes(payload)),
        reviewer_package_before_sha256=package_sha256,
        reviewer_package_after_sha256=digest(package_after),
    )


def verify_implementation_binding_record(
    record: ImmutableImplementationBindingRecord,
    reviewer_package_path: Path,
    implementation_root: Path,
) -> None:
    current = create_implementation_binding_record(
        record.payload.manifest, reviewer_package_path, implementation_root
    )
    if current != record:
        raise ValueError("implementation binding record differs from current inputs")
