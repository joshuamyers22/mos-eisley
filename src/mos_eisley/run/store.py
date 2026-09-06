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
from mos_eisley.core.skills import SkillRunManifest
from mos_eisley.providers.recorded import Cassette
from mos_eisley.run.files import read_bounded
from mos_eisley.run.skills import verify_skill_run_manifest

ARTIFACTS = (
    "brief.json",
    "cassette.json",
    "policy.json",
    "result.json",
    "events.jsonl",
)
SKILL_ARTIFACT = "skills.json"
MAX_ARTIFACT_BYTES = 16_000_000


class ArtifactHash(Contract):
    name: str
    sha256: Digest


class Manifest(Contract):
    schema_version: Literal[1, 2] = 1
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
    skill_manifest: SkillRunManifest | None = None,
) -> Path:
    run_id = uuid4().hex
    path = root / run_id
    skill_events = (
        tuple(
            {
                "type": "skill.loaded",
                "critic": item.critic_id,
                "name": item.skill.name,
                "version": item.skill.version,
                "source": item.skill.source,
                "package_sha256": item.skill.package_sha256,
                "instruction_bytes": item.instruction_bytes,
            }
            for item in skill_manifest.assignments
        )
        if skill_manifest is not None
        else ()
    )
    events = (
        {"type": "session.started", "run_id": run_id, "mode": "recorded"},
        *skill_events,
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
    if skill_manifest is not None:
        verify_skill_run_manifest(cassette, skill_manifest)
        payloads[SKILL_ARTIFACT] = canonical_bytes(skill_manifest)
    if any(len(payload) > MAX_ARTIFACT_BYTES for payload in payloads.values()):
        raise ValueError("run artifact exceeds replay byte limit")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.mkdir(mode=0o700)
    for name, payload in payloads.items():
        private_write(path / name, payload)
    manifest = Manifest(
        schema_version=2 if skill_manifest is not None else 1,
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


def _load_run_bundle(
    path: Path,
) -> tuple[tuple[Brief, Cassette, ReviewPolicy, ReviewResult], SkillRunManifest | None]:
    manifest = Manifest.model_validate_json(read_bounded(path / "manifest.json"))
    names = tuple(item.name for item in manifest.artifacts)
    expected: set[str] = set(ARTIFACTS)
    if manifest.schema_version == 2:
        expected.add(SKILL_ARTIFACT)
    if len(names) != len(expected) or set(names) != expected:
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
    skill_manifest = None
    if manifest.schema_version == 2:
        skill_manifest = SkillRunManifest.model_validate_json(payloads[SKILL_ARTIFACT])
        verify_skill_run_manifest(cassette, skill_manifest)
    if (
        brief.brief_id != manifest.brief_id
        or brief.brief_id != cassette.brief_id
        or result.verdict.brief_id != brief.brief_id
    ):
        raise ValueError("run brief identity mismatch")
    return (brief, cassette, policy, result), skill_manifest


def load_run(path: Path) -> tuple[Brief, Cassette, ReviewPolicy, ReviewResult]:
    return _load_run_bundle(path)[0]


def load_skill_run_manifest(path: Path) -> SkillRunManifest | None:
    """Return verified skill provenance, if the recorded run used skills."""

    # The same bounded reads supply both verification and the returned contract.
    return _load_run_bundle(path)[1]
