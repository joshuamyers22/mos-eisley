"""Immutable offline reviewer-test packages with no execution authority."""

from __future__ import annotations

import ast
import base64
import binascii
import fnmatch
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.files import read_bounded

MANIFEST_BYTES = 256_000
REFERENCE_BYTES = 1_000_000
TOTAL_REFERENCE_BYTES = 4_000_000
PACKAGE_FILE_BYTES = 1_000_000
TOTAL_PACKAGE_BYTES = 8_000_000
FROZEN_PACKAGE_BYTES = 16_000_000

RelativePath = Annotated[str, Field(min_length=1, max_length=4096)]
MarkerReason = Annotated[str, Field(min_length=1, max_length=1000)]
EncodedFile = Annotated[str, Field(min_length=4, max_length=1_333_336)]
ReferenceKind = Literal[
    "approved_plan",
    "interface",
    "rubric",
    "creator_approval",
    "marker_approval",
]
FileKind = Literal[
    "test",
    "fixture",
    "input",
    "expected_value",
    "parameter",
    "oracle",
    "collection_config",
]
MediaType = Literal[
    "text/x-python",
    "application/json",
    "text/plain",
    "application/octet-stream",
]
MarkerKind = Literal["skip", "xfail"]
_REQUIRED_REFERENCE_KINDS = (
    "approved_plan",
    "interface",
    "rubric",
    "creator_approval",
    "marker_approval",
)


def _relative_path(value: str, *, allow_dot: bool = False) -> str:
    if "\\" in value or "\x00" in value:
        raise ValueError("package paths must use canonical POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("package paths must remain below the package root")
    canonical = path.as_posix()
    if canonical != value or (canonical == "." and not allow_dot):
        raise ValueError("package paths must be canonical relative paths")
    return value


class BlindReviewReference(Contract):
    """One approved derivation input identified without retaining its contents."""

    reference_id: Identifier
    kind: ReferenceKind
    content_sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=REFERENCE_BYTES)]


class TestFileDeclaration(Contract):
    path: RelativePath
    kind: FileKind
    media_type: MediaType
    content_sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=PACKAGE_FILE_BYTES)]

    @field_validator("path")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        return _relative_path(value)

    @model_validator(mode="after")
    def coherent_python_file(self) -> Self:
        is_python_path = self.path.endswith(".py")
        is_python_media = self.media_type == "text/x-python"
        if is_python_path != is_python_media:
            raise ValueError("Python paths and media types must agree")
        if self.kind == "test" and not is_python_media:
            raise ValueError("reviewer tests must be Python source files")
        return self


class DeclaredTestMarker(Contract):
    path: RelativePath
    line: Annotated[int, Field(ge=1, le=1_000_000)]
    kind: MarkerKind
    reason: MarkerReason
    approval_reference_id: Identifier

    @field_validator("path")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        return _relative_path(value)


class TestCollectionContract(Contract):
    runner: Literal["unittest_discover"] = "unittest_discover"
    start_directory: RelativePath
    pattern: Annotated[
        str, Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9*?_.-]+$")
    ] = "test*.py"
    top_level_directory: RelativePath = "."
    expected_collected_tests: Annotated[int, Field(ge=1, le=10_000)]
    expected_executed_tests: Annotated[int, Field(ge=1, le=10_000)]
    expected_skipped_tests: Annotated[int, Field(ge=0, le=10_000)] = 0

    @field_validator("start_directory")
    @classmethod
    def canonical_start(cls, value: str) -> str:
        return _relative_path(value, allow_dot=True)

    @field_validator("top_level_directory")
    @classmethod
    def canonical_top_level(cls, value: str) -> str:
        return _relative_path(value, allow_dot=True)

    @model_validator(mode="after")
    def coherent_counts_and_directories(self) -> Self:
        if self.expected_executed_tests + self.expected_skipped_tests != (
            self.expected_collected_tests
        ):
            raise ValueError("executed and skipped tests must equal collected tests")
        start = PurePosixPath(self.start_directory)
        top = PurePosixPath(self.top_level_directory)
        if not start.is_relative_to(top):
            raise ValueError(
                "collection start must remain below its top-level directory"
            )
        return self


class ReviewerTestPackageManifest(Contract):
    """Blind package declaration authored before implementation is revealed."""

    schema_version: Literal[1] = 1
    kind: Literal["reviewer_test_package_manifest"] = "reviewer_test_package_manifest"
    package_id: Identifier
    references: Annotated[
        tuple[BlindReviewReference, ...], Field(min_length=4, max_length=32)
    ]
    collection: TestCollectionContract
    files: Annotated[
        tuple[TestFileDeclaration, ...], Field(min_length=1, max_length=256)
    ]
    declared_markers: Annotated[
        tuple[DeclaredTestMarker, ...], Field(max_length=64)
    ] = ()
    implementation_inspected: Literal[False] = False
    author_telemetry_included: Literal[False] = False
    test_execution_authorized: Literal[False] = False
    implementation_binding_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False

    @model_validator(mode="after")
    def complete_canonical_manifest(self) -> Self:
        reference_keys = tuple(
            (item.kind, item.reference_id) for item in self.references
        )
        if reference_keys != tuple(sorted(reference_keys)) or len(
            reference_keys
        ) != len(set(reference_keys)):
            raise ValueError("references must be unique and sorted by kind and id")
        reference_ids = tuple(item.reference_id for item in self.references)
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("reference ids must be globally unique")
        reference_digests = tuple(item.content_sha256 for item in self.references)
        if len(reference_digests) != len(set(reference_digests)):
            raise ValueError("reference contents must be distinct")
        reference_counts = {
            kind: sum(item.kind == kind for item in self.references)
            for kind in _REQUIRED_REFERENCE_KINDS
        }
        if (
            reference_counts["approved_plan"] != 1
            or reference_counts["interface"] < 1
            or reference_counts["rubric"] != 1
            or reference_counts["creator_approval"] != 1
        ):
            raise ValueError(
                "references require one plan, rubric and creator approval "
                "plus one or more interfaces"
            )
        if sum(item.bytes for item in self.references) > TOTAL_REFERENCE_BYTES:
            raise ValueError("approved derivation references exceed 4 MB")

        paths = tuple(item.path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("package files must be unique and sorted by path")
        if sum(item.bytes for item in self.files) > TOTAL_PACKAGE_BYTES:
            raise ValueError("reviewer-test package exceeds 8 MB")
        start = PurePosixPath(self.collection.start_directory)
        declared_tests = tuple(item for item in self.files if item.kind == "test")
        matching_tests = tuple(
            item
            for item in declared_tests
            if PurePosixPath(item.path).is_relative_to(start)
            and fnmatch.fnmatchcase(
                PurePosixPath(item.path).name, self.collection.pattern
            )
        )
        if not declared_tests or matching_tests != declared_tests:
            raise ValueError("collection configuration must select every declared test")

        marker_keys = tuple(
            (item.path, item.line, item.kind) for item in self.declared_markers
        )
        if marker_keys != tuple(sorted(marker_keys)) or len(marker_keys) != len(
            set(marker_keys)
        ):
            raise ValueError("declared markers must be unique and sorted")
        file_paths = set(paths)
        marker_approval_ids = {
            item.reference_id
            for item in self.references
            if item.kind == "marker_approval"
        }
        marker_approval_sequence = tuple(
            item.approval_reference_id for item in self.declared_markers
        )
        if (
            len(marker_approval_sequence) != len(set(marker_approval_sequence))
            or set(marker_approval_sequence) != marker_approval_ids
        ):
            raise ValueError("marker approvals must be exact and fully referenced")
        if any(item.path not in file_paths for item in self.declared_markers):
            raise ValueError("declared marker path is not in the package")
        test_paths = {item.path for item in declared_tests}
        if any(item.path not in test_paths for item in self.declared_markers):
            raise ValueError("test markers require declared test source")
        if len(canonical_bytes(self)) > MANIFEST_BYTES:
            raise ValueError("reviewer-test manifest exceeds 256 KB")
        return self

    @property
    def manifest_sha256(self) -> str:
        return digest(canonical_bytes(self))


class FrozenTestFile(Contract):
    declaration: TestFileDeclaration
    content_base64: EncodedFile

    @model_validator(mode="after")
    def exact_canonical_content(self) -> Self:
        try:
            payload = base64.b64decode(self.content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("frozen file content must be canonical base64") from None
        if base64.b64encode(payload).decode("ascii") != self.content_base64:
            raise ValueError("frozen file content must be canonical base64")
        if (
            len(payload) != self.declaration.bytes
            or digest(payload) != self.declaration.content_sha256
        ):
            raise ValueError("frozen file differs from its declaration")
        return self

    @property
    def content(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)


class ReviewerTestPackagePayload(Contract):
    manifest: ReviewerTestPackageManifest
    files: Annotated[tuple[FrozenTestFile, ...], Field(min_length=1, max_length=256)]

    @model_validator(mode="after")
    def exact_files_and_markers(self) -> Self:
        if tuple(item.declaration for item in self.files) != self.manifest.files:
            raise ValueError("frozen files must exactly match the manifest")
        detected: list[tuple[str, int, MarkerKind]] = []
        for item in self.files:
            if item.declaration.media_type == "text/x-python":
                detected.extend(_python_markers(item.declaration.path, item.content))
        expected = tuple(
            (item.path, item.line, item.kind) for item in self.manifest.declared_markers
        )
        if tuple(sorted(detected)) != expected:
            raise ValueError("detected skip/xfail markers differ from the manifest")
        return self


class FrozenReviewerTestPackage(Contract):
    """Self-contained package bytes; identity only, never execution authority."""

    schema_version: Literal[1] = 1
    kind: Literal["frozen_reviewer_test_package"] = "frozen_reviewer_test_package"
    payload: ReviewerTestPackagePayload
    payload_sha256: Digest
    test_execution_authorized: Literal[False] = False
    implementation_binding_authorized: Literal[False] = False
    repository_write_authorized: Literal[False] = False
    vcs_authorized: Literal[False] = False
    correction_authorized: Literal[False] = False
    acceptance_authorized: Literal[False] = False
    network_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    provider_dispatch_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exact_payload(self) -> Self:
        if self.payload_sha256 != digest(canonical_bytes(self.payload)):
            raise ValueError("frozen reviewer-test payload digest is invalid")
        if len(canonical_bytes(self)) > FROZEN_PACKAGE_BYTES:
            raise ValueError("frozen reviewer-test package exceeds 16 MB")
        return self

    @property
    def frozen_package_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def decode_reviewer_test_manifest(payload: bytes) -> ReviewerTestPackageManifest:
    if len(payload) > MANIFEST_BYTES:
        raise ValueError("reviewer-test manifest exceeds 256 KB")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=_unique_object)
        return ReviewerTestPackageManifest.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("invalid reviewer-test package manifest") from None


def decode_frozen_reviewer_test_package(payload: bytes) -> FrozenReviewerTestPackage:
    if len(payload) > FROZEN_PACKAGE_BYTES:
        raise ValueError("frozen reviewer-test package exceeds 16 MB")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=_unique_object)
        return FrozenReviewerTestPackage.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("invalid frozen reviewer-test package") from None


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent is not None else node.attr
    return None


def _marker_kind(node: ast.expr) -> MarkerKind | None:
    target = node.func if isinstance(node, ast.Call) else node
    name = _dotted_name(target)
    if name is None:
        return None
    terminal = name.rsplit(".", 1)[-1].lower()
    if terminal in {"skip", "skipif", "skipunless", "skiptest"}:
        return "skip"
    if terminal in {"xfail", "expectedfailure"}:
        return "xfail"
    return None


def _python_markers(
    path: str, payload: bytes
) -> tuple[tuple[str, int, MarkerKind], ...]:
    try:
        source = payload.decode("utf-8")
        tree = ast.parse(source, filename=path)
    except (SyntaxError, UnicodeDecodeError):
        raise ValueError(
            f"invalid Python source in reviewer-test package: {path}"
        ) from None
    markers: set[tuple[str, int, MarkerKind]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            kind = _marker_kind(node)
            if kind is not None:
                markers.add((path, node.lineno, kind))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                kind = _marker_kind(decorator)
                if kind is not None:
                    markers.add((path, decorator.lineno, kind))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in targets
            ):
                value = node.value
                if value is None:
                    continue
                for candidate in ast.walk(value):
                    if isinstance(candidate, (ast.Call, ast.Attribute, ast.Name)):
                        kind = _marker_kind(candidate)
                        if kind is not None:
                            markers.add((path, candidate.lineno, kind))
    return tuple(sorted(markers))


def _read_package_file(
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
                raise ValueError("package input must be a regular file")
            if before.st_nlink != 1:
                raise ValueError("package input must not have filesystem aliases")
            payload = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        if len(payload) > limit:
            raise ValueError("package input exceeds its byte limit")
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise ValueError("package input changed while being read")
        return payload, (before.st_dev, before.st_ino)
    finally:
        os.close(directory_fd)


def freeze_reviewer_test_package(
    manifest: ReviewerTestPackageManifest,
    package_root: Path,
    reference_paths: tuple[Path, ...],
) -> FrozenReviewerTestPackage:
    """Freeze exact bytes without execution or implementation binding."""
    if len(reference_paths) != len(manifest.references):
        raise ValueError("provide approved reference paths in manifest order")
    for reference, path in zip(manifest.references, reference_paths, strict=True):
        payload = read_bounded(path, REFERENCE_BYTES)
        if (
            len(payload) != reference.bytes
            or digest(payload) != reference.content_sha256
        ):
            raise ValueError("approved derivation reference differs from the manifest")

    root_fd = os.open(package_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        frozen_files: list[FrozenTestFile] = []
        identities: set[tuple[int, int]] = set()
        for declaration in manifest.files:
            payload, identity = _read_package_file(
                root_fd, declaration.path, PACKAGE_FILE_BYTES
            )
            if identity in identities:
                raise ValueError(
                    "package files must not alias the same filesystem object"
                )
            identities.add(identity)
            if (
                len(payload) != declaration.bytes
                or digest(payload) != declaration.content_sha256
            ):
                raise ValueError("package file differs from its declaration")
            frozen_files.append(
                FrozenTestFile(
                    declaration=declaration,
                    content_base64=base64.b64encode(payload).decode("ascii"),
                )
            )
    finally:
        os.close(root_fd)
    payload = ReviewerTestPackagePayload(manifest=manifest, files=tuple(frozen_files))
    return FrozenReviewerTestPackage(
        payload=payload,
        payload_sha256=digest(canonical_bytes(payload)),
    )
