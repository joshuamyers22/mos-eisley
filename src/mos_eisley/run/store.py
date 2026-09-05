"""Private run directories are authoritative; SQLite is a rebuildable index."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Literal
from uuid import uuid4

from mos_eisley.core.models import (
    Brief,
    Contract,
    Digest,
    ReviewPolicy,
    ReviewResult,
    canonical_bytes,
    digest,
)
from mos_eisley.providers.recorded import Cassette
from mos_eisley.run.files import read_bounded

ARTIFACTS = (
    "brief.json",
    "cassette.json",
    "policy.json",
    "result.json",
    "events.jsonl",
)
MAX_ARTIFACT_BYTES = 16_000_000


class ArtifactHash(Contract):
    name: str
    sha256: Digest


class Manifest(Contract):
    schema_version: Literal[1] = 1
    run_id: str
    mode: Literal["recorded"] = "recorded"
    brief_id: Digest
    artifacts: tuple[ArtifactHash, ...]


def private_write(path: Path, payload: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def save_run(
    root: Path,
    brief: Brief,
    cassette: Cassette,
    policy: ReviewPolicy,
    result: ReviewResult,
) -> Path:
    run_id = uuid4().hex
    path = root / run_id
    events = (
        {"type": "session.started", "run_id": run_id, "mode": "recorded"},
        *(
            {"type": "critic.completed", "critic": r.critic.id, "status": r.status}
            for r in result.critics
        ),
        {"type": "verdict", "decision": result.verdict.decision},
        {"type": "session.completed", "run_id": run_id},
    )
    payloads = {
        "brief.json": canonical_bytes(brief),
        "cassette.json": canonical_bytes(cassette),
        "policy.json": canonical_bytes(policy),
        "result.json": canonical_bytes(result),
        "events.jsonl": (
            "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n"
        ).encode(),
    }
    if any(len(payload) > MAX_ARTIFACT_BYTES for payload in payloads.values()):
        raise ValueError("run artifact exceeds replay byte limit")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.mkdir(mode=0o700)
    for name, payload in payloads.items():
        private_write(path / name, payload)
    manifest = Manifest(
        run_id=run_id,
        brief_id=brief.brief_id,
        artifacts=tuple(
            ArtifactHash(name=name, sha256=digest(payload))
            for name, payload in payloads.items()
        ),
    )
    # A manifest is the completion marker. Partial directories are not replayable.
    private_write(path / "manifest.json", canonical_bytes(manifest))
    return path


def index_run(root: Path, path: Path, result: ReviewResult) -> None:
    database = root / "index.sqlite"
    # This index lives in a trusted controller-owned directory. O_NOFOLLOW is
    # defense in depth, not containment against another process with our UID.
    fd = os.open(database, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, "
                "brief_id TEXT NOT NULL, decision TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT OR REPLACE INTO runs VALUES (?, ?, ?)",
                (path.name, result.verdict.brief_id, result.verdict.decision),
            )
    finally:
        connection.close()


def load_run(path: Path) -> tuple[Brief, Cassette, ReviewPolicy, ReviewResult]:
    manifest = Manifest.model_validate_json(read_bounded(path / "manifest.json"))
    names = tuple(item.name for item in manifest.artifacts)
    if len(names) != len(ARTIFACTS) or set(names) != set(ARTIFACTS):
        raise ValueError("manifest artifact set is invalid")
    payloads: dict[str, bytes] = {}
    for artifact in manifest.artifacts:
        payload = read_bounded(path / artifact.name, MAX_ARTIFACT_BYTES)
        if digest(payload) != artifact.sha256:
            raise ValueError(f"artifact digest mismatch: {artifact.name}")
        payloads[artifact.name] = payload
    brief = Brief.model_validate_json(payloads["brief.json"])
    cassette = Cassette.model_validate_json(payloads["cassette.json"])
    policy = ReviewPolicy.model_validate_json(payloads["policy.json"])
    result = ReviewResult.model_validate_json(payloads["result.json"])
    if (
        brief.brief_id != manifest.brief_id
        or brief.brief_id != cassette.brief_id
        or result.verdict.brief_id != brief.brief_id
    ):
        raise ValueError("run brief identity mismatch")
    return brief, cassette, policy, result
