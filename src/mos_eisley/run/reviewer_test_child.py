"""Stdlib-only clean interpreter for materialized G4 reviewer tests."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import stat
import sys
import unittest
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import cast

MAX_WIRE_BYTES = 16_000_000
MAX_OUTPUT_BYTES = 65_536
MAX_TEST_ID_BYTES = 1_000_000


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(message)
    candidate = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in candidate):
        raise ValueError(message)
    return cast(dict[str, object], candidate)


def _sequence(value: object, message: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(message)
    return cast(list[object], value)


def _safe_relative(value: str) -> PurePosixPath:
    if "\\" in value or "\x00" in value:
        raise ValueError("materialized path is not canonical")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError("materialized path escapes its root")
    return path


def _write_material(root: Path, relative: str, payload: bytes) -> Path:
    path = root.joinpath(*_safe_relative(relative).parts)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(payload)
    path.chmod(0o400)
    return path


def _material_digest(root: Path) -> str:
    files: list[tuple[str, str, int]] = []
    for directory, names, filenames in os.walk(root, followlinks=False):
        names.sort()
        filenames.sort()
        directory_path = Path(directory)
        for name in names:
            path = directory_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ValueError("materialized tree contains an unsafe directory")
        for name in filenames:
            path = directory_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise ValueError("materialized tree contains an unsafe file")
            payload = path.read_bytes()
            files.append(
                (path.relative_to(root).as_posix(), _digest(payload), len(payload))
            )
    return _digest(_canonical(files))


def _make_read_only(root: Path) -> None:
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o500)
    root.chmod(0o500)


class _BoundedTextSink(io.TextIOBase):
    def __init__(self) -> None:
        self.bytes_written = 0

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        size = len(value.encode("utf-8", errors="replace"))
        if self.bytes_written + size > MAX_OUTPUT_BYTES:
            raise ValueError("reviewer-test output exceeds 64 KB")
        self.bytes_written += size
        return len(value)


class _CountingResult(unittest.TestResult):
    def __init__(self) -> None:
        super().__init__()
        self.started_ids: list[str] = []
        self.skipped_ids: list[str] = []
        self._id_bytes = 0

    def _append(self, target: list[str], test: unittest.case.TestCase) -> None:
        identifier = test.id()
        size = len(identifier.encode("utf-8"))
        if self._id_bytes + size > MAX_TEST_ID_BYTES:
            raise ValueError("reviewer-test identities exceed 1 MB")
        self._id_bytes += size
        target.append(identifier)

    def startTest(self, test: unittest.case.TestCase) -> None:
        self._append(self.started_ids, test)
        super().startTest(test)

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        self._append(self.skipped_ids, test)
        super().addSkip(test, reason)


def _test_ids(suite: unittest.TestSuite) -> list[str]:
    identifiers: list[str] = []
    total_bytes = 0

    def visit(value: unittest.TestSuite | unittest.case.TestCase) -> None:
        nonlocal total_bytes
        if isinstance(value, unittest.TestSuite):
            for nested in value:
                visit(nested)
            return
        identifier = value.id()
        total_bytes += len(identifier.encode("utf-8"))
        if total_bytes > MAX_TEST_ID_BYTES:
            raise ValueError("reviewer-test identities exceed 1 MB")
        identifiers.append(identifier)

    visit(suite)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("reviewer-test collection contains duplicate identities")
    return identifiers


def _ids_digest(identifiers: list[str]) -> str:
    return _digest(_canonical(identifiers))


def _decode_file(item: dict[str, object]) -> tuple[str, bytes, str, int]:
    declaration = _mapping(item["declaration"], "invalid material declaration")
    path = declaration["path"]
    expected_digest = declaration["content_sha256"]
    expected_bytes = declaration["bytes"]
    encoded = item["content_base64"]
    if not (
        isinstance(path, str)
        and isinstance(expected_digest, str)
        and isinstance(expected_bytes, int)
        and isinstance(encoded, str)
    ):
        raise ValueError("invalid material file")
    payload = base64.b64decode(encoded, validate=True)
    if len(payload) != expected_bytes or _digest(payload) != expected_digest:
        raise ValueError("material file differs from its declaration")
    return path, payload, expected_digest, expected_bytes


def _run(job: dict[str, object], job_sha256: str) -> dict[str, object]:
    binding = _mapping(job["binding"], "invalid implementation binding")
    package = _mapping(job["reviewer_package"], "invalid reviewer package")
    implementation_files = _sequence(
        job["implementation_files"], "invalid implementation material"
    )
    binding_payload = _mapping(binding["payload"], "invalid binding payload")
    package_payload = _mapping(package["payload"], "invalid package payload")
    manifest = _mapping(binding_payload["manifest"], "invalid binding manifest")
    package_manifest = _mapping(package_payload["manifest"], "invalid package manifest")
    package_files = _sequence(package_payload["files"], "invalid reviewer material")
    source_roots = _sequence(manifest["source_roots"], "invalid source roots")
    adapter = _mapping(manifest["adapter"], "invalid adapter")
    collection = _mapping(
        package_manifest["collection"], "invalid collection configuration"
    )

    with TemporaryDirectory(prefix="mos-g4-reviewer-") as directory:
        root = Path(directory)
        implementation_root = root / "implementation"
        reviewer_root = root / "reviewer"
        adapter_root = root / "adapter"
        implementation_root.mkdir(mode=0o700)
        reviewer_root.mkdir(mode=0o700)
        adapter_root.mkdir(mode=0o700)

        for item in implementation_files:
            path, payload, _, _ = _decode_file(
                _mapping(item, "invalid implementation material")
            )
            _write_material(implementation_root, path, payload)
        for item in package_files:
            path, payload, _, _ = _decode_file(
                _mapping(item, "invalid reviewer material")
            )
            _write_material(reviewer_root, path, payload)

        exports = _sequence(adapter["exports"], "invalid adapter exports")
        adapter_lines: list[str] = []
        for value in exports:
            export = _mapping(value, "invalid adapter export")
            module = export["target_module"]
            symbol = export["target_symbol"]
            exposed = export["exposed_name"]
            if not all(isinstance(value, str) for value in (module, symbol, exposed)):
                raise ValueError("invalid direct-symbol adapter")
            adapter_lines.append(f"from {module} import {symbol} as {exposed}\n")
        adapter_path = _write_material(
            adapter_root,
            "mos_eisley_reviewer_adapter.py",
            "".join(adapter_lines).encode("utf-8"),
        )
        if adapter_path.parent != adapter_root:
            raise ValueError("adapter materialized outside its root")

        initial_material_digest = _material_digest(root)
        _make_read_only(implementation_root)
        _make_read_only(reviewer_root)
        _make_read_only(adapter_root)

        source_paths: list[str] = []
        for value in source_roots:
            if not isinstance(value, str):
                raise ValueError("invalid source root")
            source_paths.append(
                str(implementation_root.joinpath(*_safe_relative(value).parts))
            )
        top = reviewer_root.joinpath(
            *_safe_relative(str(collection["top_level_directory"])).parts
        )
        start = reviewer_root.joinpath(
            *_safe_relative(str(collection["start_directory"])).parts
        )
        pattern = collection["pattern"]
        if not isinstance(pattern, str):
            raise ValueError("invalid collection pattern")

        sys.dont_write_bytecode = True
        sys.path[:0] = [str(adapter_root), *source_paths, str(top)]
        sink = _BoundedTextSink()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            suite = unittest.TestLoader().discover(
                start_dir=str(start), pattern=pattern, top_level_dir=str(top)
            )
            collected_ids = _test_ids(suite)
            result = _CountingResult()
            suite.run(result)

        if _material_digest(root) != initial_material_digest:
            raise ValueError("reviewer-test execution mutated its materialized inputs")
        if result.started_ids != collected_ids:
            raise ValueError("reviewer-test execution order differs from collection")
        skipped = set(result.skipped_ids)
        if len(skipped) != len(result.skipped_ids):
            raise ValueError("reviewer-test execution reported duplicate skips")
        executed_ids = [item for item in result.started_ids if item not in skipped]
        failed_ids = [test.id() for test, _traceback in result.failures]
        if len(set(failed_ids)) != len(failed_ids):
            raise ValueError("reviewer-test failures have duplicate identities")
        if any(item not in executed_ids for item in failed_ids):
            raise ValueError("reviewer-test failure was not executed")
        observation: dict[str, object] = {
            "schema_version": 2,
            "kind": "isolated_reviewer_test_observation",
            "job_sha256": job_sha256,
            "collected_tests": len(collected_ids),
            "started_tests": result.testsRun,
            "executed_tests": result.testsRun - len(result.skipped),
            "skipped_tests": len(result.skipped),
            "failures": len(result.failures),
            "failed_test_ids": failed_ids,
            "errors": len(result.errors),
            "expected_failures": len(result.expectedFailures),
            "unexpected_successes": len(result.unexpectedSuccesses),
            "collected_test_ids_sha256": _ids_digest(collected_ids),
            "started_test_ids_sha256": _ids_digest(result.started_ids),
            "executed_test_ids_sha256": _ids_digest(executed_ids),
            "output_bytes": sink.bytes_written,
            "suite_successful": result.wasSuccessful(),
        }
        return observation


def main() -> int:
    payload = sys.stdin.buffer.read(MAX_WIRE_BYTES + 1)
    if len(payload) > MAX_WIRE_BYTES:
        raise ValueError("isolated reviewer-test job exceeds the wire limit")
    decoded = cast(object, json.loads(payload))
    job = _mapping(decoded, "invalid isolated reviewer-test job")
    if job.get("kind") != "isolated_reviewer_test_job":
        raise ValueError("invalid isolated reviewer-test job")
    observation = _run(job, _digest(payload))
    sys.stdout.buffer.write(_canonical(observation))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
