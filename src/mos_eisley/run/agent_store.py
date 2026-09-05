"""Content-verified artifacts for deterministic canonical agent-loop replay."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import uuid4

from mos_eisley.core.agent import AgentConfig, AgentResult
from mos_eisley.core.models import Contract, canonical_bytes, digest
from mos_eisley.core.protocol import JournalEvent
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.files import read_bounded
from mos_eisley.run.journal import JsonlJournal
from mos_eisley.run.store import (
    MAX_ARTIFACT_BYTES,
    ArtifactHash,
    private_write,
)
from mos_eisley.tools.fixture import FixtureValues

AGENT_ARTIFACTS = (
    "config.json",
    "fixtures.json",
    "cassette.json",
    "requests.jsonl",
    "result.json",
)


class AgentManifest(Contract):
    schema_version: Literal[1] = 1
    run_id: str
    mode: Literal["recorded_agent"] = "recorded_agent"
    artifacts: tuple[ArtifactHash, ...]


class AgentRunSession:
    def __init__(self, path: Path, journal: JsonlJournal) -> None:
        self.path = path
        self.journal = journal
        self._state: Literal["open", "completed", "aborted"] = "open"

    def complete(self, result: AgentResult) -> None:
        if self._state != "open":
            raise ValueError(f"agent run is already {self._state}")
        self.journal.close()
        payload = canonical_bytes(result)
        if len(payload) > MAX_ARTIFACT_BYTES:
            raise ValueError("agent result exceeds artifact byte limit")
        private_write(self.path / "result.json", payload)
        artifacts: list[ArtifactHash] = []
        for name in AGENT_ARTIFACTS:
            artifact = read_bounded(self.path / name, MAX_ARTIFACT_BYTES)
            artifacts.append(ArtifactHash(name=name, sha256=digest(artifact)))
        manifest = AgentManifest(run_id=self.path.name, artifacts=tuple(artifacts))
        private_write(self.path / "manifest.json", canonical_bytes(manifest))
        self._state = "completed"

    def abort(self) -> None:
        self.journal.close()
        if self._state == "open":
            self._state = "aborted"


def begin_agent_run(
    root: Path,
    config: AgentConfig,
    fixtures: FixtureValues,
    cassette: AgentCassette,
) -> AgentRunSession:
    payloads = {
        "config.json": canonical_bytes(config),
        "fixtures.json": canonical_bytes(fixtures),
        "cassette.json": canonical_bytes(cassette),
    }
    if any(len(payload) > MAX_ARTIFACT_BYTES for payload in payloads.values()):
        raise ValueError("agent input exceeds artifact byte limit")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / uuid4().hex
    path.mkdir(mode=0o700)
    for name, payload in payloads.items():
        private_write(path / name, payload)
    return AgentRunSession(path, JsonlJournal(path / "requests.jsonl"))


def load_agent_run(
    path: Path,
) -> tuple[
    AgentConfig,
    FixtureValues,
    AgentCassette,
    tuple[JournalEvent, ...],
    AgentResult,
]:
    manifest = AgentManifest.model_validate_json(
        read_bounded(path / "manifest.json", MAX_ARTIFACT_BYTES)
    )
    names = tuple(artifact.name for artifact in manifest.artifacts)
    if manifest.run_id != path.name:
        raise ValueError("agent run identity does not match its directory")
    if len(names) != len(AGENT_ARTIFACTS) or set(names) != set(AGENT_ARTIFACTS):
        raise ValueError("agent manifest artifact set is invalid")
    payloads: dict[str, bytes] = {}
    for artifact in manifest.artifacts:
        payload = read_bounded(path / artifact.name, MAX_ARTIFACT_BYTES)
        if digest(payload) != artifact.sha256:
            raise ValueError(f"agent artifact digest mismatch: {artifact.name}")
        payloads[artifact.name] = payload
    events = tuple(
        JournalEvent.model_validate_json(line)
        for line in payloads["requests.jsonl"].splitlines()
    )
    if tuple(event.sequence for event in events) != tuple(range(len(events))):
        raise ValueError("agent journal sequence is invalid")
    return (
        AgentConfig.model_validate_json(payloads["config.json"]),
        FixtureValues.model_validate_json(payloads["fixtures.json"]),
        AgentCassette.model_validate_json(payloads["cassette.json"]),
        events,
        AgentResult.model_validate_json(payloads["result.json"]),
    )
