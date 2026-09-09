"""Opt-in private, bounded analytical bundles and exports from captured results."""

import csv
import io
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, JsonValue, model_validator

from mos_eisley.analysis.controller import AnalysisResult
from mos_eisley.analysis.evidence import complete_table
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.providers.openai_spend import SpendReceipt
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import private_write

MAX_BYTES = 8_000_000


class AnalysisArtifact(Contract):
    schema_version: Literal[1] = 1
    result: AnalysisResult
    spend_receipt: SpendReceipt | None = None

    @model_validator(mode="after")
    def spending_matches_usage(self) -> "AnalysisArtifact":
        if self.result.provider == "openai":
            receipt = self.spend_receipt
            if (
                receipt is None
                or receipt.ledger_id is None
                or receipt.status != "settled"
                or receipt.input_tokens
                != sum(u.input for u in self.result.provider_usage)
                or receipt.output_tokens
                != sum(u.output for u in self.result.provider_usage)
                or receipt.cache_write_tokens
                != sum(u.cache_write for u in self.result.provider_usage)
            ):
                raise ValueError("artifact receipt does not match returned usage")
        elif self.spend_receipt is not None:
            raise ValueError("fixture artifacts cannot carry a live spending receipt")
        return self


class BundleManifest(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["analysis", "csv"]
    run_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    created_at: datetime
    expires_at: datetime
    payload_sha256: Digest
    parent_sha256: Digest | None = None
    result_id: Identifier | None = None
    result_sha256: Digest | None = None
    escaped_csv_cells: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def coherent(self) -> "BundleManifest":
        if (
            self.created_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or not timedelta(0) < self.expires_at - self.created_at <= timedelta(days=7)
        ):
            raise ValueError("invalid artifact lifetime")
        lineage = (self.parent_sha256, self.result_id, self.result_sha256)
        if self.kind == "csv":
            if any(value is None for value in lineage):
                raise ValueError("export requires exact source lineage")
        elif any(value is not None for value in lineage) or self.escaped_csv_cells:
            raise ValueError("analysis bundle cannot have export lineage")
        return self


def private_directory(path: Path) -> Path:
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("artifact directory must be private and owned by this user")
    return path.absolute()


def _private_file(path: Path, limit: int) -> bytes:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_nlink != 1
    ):
        raise ValueError("artifact file must be private and singly linked")
    return read_bounded(path, limit)


def _write_bundle(root: Path, manifest: BundleManifest, payload: bytes) -> Path:
    root = private_directory(root)
    if len(payload) > MAX_BYTES:
        raise ValueError("artifact payload exceeds byte limit")
    path = root / manifest.run_id
    path.mkdir(mode=0o700)
    name = "result.json" if manifest.kind == "analysis" else "result.csv"
    private_write(path / name, payload)
    # Manifest is the completion marker; a partial bundle cannot verify or export.
    private_write(path / "manifest.json", canonical_bytes(manifest))
    for directory in (path, root):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return path


def save_artifact(root: Path, artifact: AnalysisArtifact, ttl_seconds: int) -> Path:
    artifact = AnalysisArtifact.model_validate_json(artifact.model_dump_json())
    if artifact.result.retention != "private":
        raise ValueError("result retention was not explicitly enabled")
    if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 604800:
        raise ValueError("invalid artifact retention interval")
    payload = canonical_bytes(artifact)
    now = datetime.now(UTC)
    return _write_bundle(
        root,
        BundleManifest(
            kind="analysis",
            run_id=uuid4().hex,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            payload_sha256=digest(payload),
        ),
        payload,
    )


def read_bundle(
    path: Path, *, allow_expired: bool = False
) -> tuple[BundleManifest, bytes]:
    path = private_directory(path)
    manifest = BundleManifest.model_validate_json(
        _private_file(path / "manifest.json", 8192)
    )
    name = "result.json" if manifest.kind == "analysis" else "result.csv"
    if path.name != manifest.run_id or {item.name for item in path.iterdir()} != {
        "manifest.json",
        name,
    }:
        raise ValueError("bundle identity or file set mismatch")
    now = datetime.now(UTC)
    if now < manifest.created_at or (not allow_expired and now >= manifest.expires_at):
        raise ValueError("bundle is outside its access window")
    payload = _private_file(path / name, MAX_BYTES)
    if digest(payload) != manifest.payload_sha256:
        raise ValueError("bundle payload hash mismatch")
    return manifest, payload


def load_artifact(path: Path) -> tuple[BundleManifest, AnalysisArtifact]:
    manifest, payload = read_bundle(path)
    if manifest.kind != "analysis":
        raise ValueError("expected an analytical result bundle")
    artifact = AnalysisArtifact.model_validate_json(payload)
    if (
        artifact.result.retention != "private"
        or artifact.result.completed_at > manifest.created_at
    ):
        raise ValueError(
            "artifact lacks coherent completion or private retention intent"
        )
    return manifest, artifact


def _csv_payload(columns: list[str], rows: list[list[JsonValue]]) -> tuple[bytes, int]:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    escaped = 0

    def cell(value: object) -> str:
        nonlocal escaped
        rendered = (
            value
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False, allow_nan=False)
        )
        # CSV quoting alone does not neutralize spreadsheet formulas. Preserve the
        # original JSON in the parent bundle and report these representation changes.
        if isinstance(value, str) and rendered.lstrip().startswith(
            ("=", "+", "-", "@")
        ):
            escaped += 1
            return "'" + rendered
        return rendered

    writer.writerow([cell(column) for column in columns])
    for row in rows:
        writer.writerow([cell(value) for value in row])
    return stream.getvalue().encode("utf-8"), escaped


def export_csv(path: Path, result_id: str, root: Path) -> Path:
    manifest, artifact = load_artifact(path)
    trace = next(
        (t for t in artifact.result.tool_trace if t.result_id == result_id), None
    )
    if trace is None or trace.call.name in {"get_semantic_context", "list_metrics"}:
        raise ValueError("export source is not a captured query result")
    columns, rows = complete_table(trace)
    payload, escaped = _csv_payload(columns, rows)
    evidence = next(e for e in artifact.result.evidence if e.result_id == result_id)
    now = datetime.now(UTC)
    return _write_bundle(
        root,
        BundleManifest(
            kind="csv",
            run_id=uuid4().hex,
            created_at=now,
            expires_at=manifest.expires_at,
            payload_sha256=digest(payload),
            parent_sha256=manifest.payload_sha256,
            result_id=result_id,
            result_sha256=evidence.result_sha256,
            escaped_csv_cells=escaped,
        ),
        payload,
    )


def delete_expired(path: Path) -> None:
    """Explicit cleanup of one verified expired bundle; never recursive discovery."""
    manifest, _ = read_bundle(path, allow_expired=True)
    if datetime.now(UTC) < manifest.expires_at:
        raise ValueError("cannot delete an unexpired bundle with expiry cleanup")
    name = "result.json" if manifest.kind == "analysis" else "result.csv"
    (path / name).unlink()
    (path / "manifest.json").unlink()
    path.rmdir()


def verify_export(path: Path, parent: Path) -> BundleManifest:
    manifest, payload = read_bundle(path)
    source_manifest, artifact = load_artifact(parent)
    trace = next(
        (t for t in artifact.result.tool_trace if t.result_id == manifest.result_id),
        None,
    )
    if manifest.kind != "csv" or trace is None or trace.response is None:
        raise ValueError("export lineage is unavailable")
    expected, escaped = _csv_payload(*complete_table(trace))
    if (
        manifest.parent_sha256 != source_manifest.payload_sha256
        or manifest.result_sha256 != digest(canonical_bytes(trace.response))
        or manifest.expires_at != source_manifest.expires_at
        or manifest.created_at < source_manifest.created_at
        or manifest.escaped_csv_cells != escaped
        or payload != expected
    ):
        raise ValueError("export differs from captured source")
    return manifest
