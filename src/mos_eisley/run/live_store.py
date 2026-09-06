"""Content-verified storage for non-replayable live provider runs."""

from pathlib import Path
from typing import Literal
from uuid import uuid4

from mos_eisley.core.agent import AgentConfig, AgentResult
from mos_eisley.core.models import Contract, canonical_bytes, digest
from mos_eisley.core.protocol import JournalEvent
from mos_eisley.providers.openai_spend import (
    SpendPolicy,
    SpendReceipt,
    SpendReservation,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.journal import JsonlJournal
from mos_eisley.run.store import MAX_ARTIFACT_BYTES, ArtifactHash, private_write

LIVE_ARTIFACTS = ("config.json", "requests.jsonl", "result.json")
SPEND_ARTIFACTS = ("spend-policy.json", "spend-reservation.json", "spend-receipt.json")


class LiveManifest(Contract):
    schema_version: Literal[1] = 1
    run_id: str
    mode: Literal["live_openai"] = "live_openai"
    spend_control: bool = False
    artifacts: tuple[ArtifactHash, ...]


class LiveRunSession:
    def __init__(
        self, path: Path, journal: JsonlJournal, spend_control: bool = False
    ) -> None:
        self.path = path
        self.journal = journal
        self.spend_control = spend_control
        self._state: Literal["open", "completed", "aborted"] = "open"

    def complete(self, result: AgentResult) -> None:
        if self._state != "open":
            raise ValueError(f"live run is already {self._state}")
        self.journal.close()
        payload = canonical_bytes(result)
        if len(payload) > MAX_ARTIFACT_BYTES:
            raise ValueError("live result exceeds artifact byte limit")
        private_write(self.path / "result.json", payload)
        names = LIVE_ARTIFACTS + (SPEND_ARTIFACTS if self.spend_control else ())
        if self.spend_control:
            _validate_spend(
                {
                    name: read_bounded(self.path / name, MAX_ARTIFACT_BYTES)
                    for name in SPEND_ARTIFACTS
                },
                result,
            )
        artifacts = tuple(
            ArtifactHash(
                name=name,
                sha256=digest(read_bounded(self.path / name, MAX_ARTIFACT_BYTES)),
            )
            for name in names
        )
        manifest = LiveManifest(
            run_id=self.path.name, artifacts=artifacts, spend_control=self.spend_control
        )
        private_write(self.path / "manifest.json", canonical_bytes(manifest))
        self._state = "completed"

    def abort(self) -> None:
        self.journal.close()
        if self._state == "open":
            self._state = "aborted"


def begin_live_run(
    root: Path, config: AgentConfig, spend_policy: SpendPolicy | None = None
) -> LiveRunSession:
    if config.provider != "openai":
        raise ValueError("live run store currently accepts only OpenAI")
    payload = canonical_bytes(config)
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise ValueError("live config exceeds artifact byte limit")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / uuid4().hex
    path.mkdir(mode=0o700)
    private_write(path / "config.json", payload)
    if spend_policy is not None:
        private_write(path / "spend-policy.json", canonical_bytes(spend_policy))
    return LiveRunSession(
        path, JsonlJournal(path / "requests.jsonl"), spend_policy is not None
    )


def _validate_spend(payloads: dict[str, bytes], result: AgentResult) -> None:
    policy = SpendPolicy.model_validate_json(payloads["spend-policy.json"])
    reservation = SpendReservation.model_validate_json(
        payloads["spend-reservation.json"]
    )
    receipt = SpendReceipt.model_validate_json(payloads["spend-receipt.json"])
    if (
        reservation.policy_sha256 != policy.policy_sha256
        or receipt.reservation_sha256 != digest(canonical_bytes(reservation))
        or receipt.status != "settled"
        or policy.model != result.resolved_model.spec.id
        or result.usage.requests != 1
        or result.usage.tools != 0
        or receipt.input_tokens != result.usage.billed_input
        or receipt.output_tokens != result.usage.billed_output
        or result.usage.billed_input > reservation.input_tokens
        or result.usage.billed_output > reservation.max_output_tokens
        or reservation.input_tokens > policy.max_input_tokens
        or reservation.max_output_tokens > policy.max_output_tokens
        or reservation.reserved_microusd
        != policy.cost(reservation.input_tokens, reservation.max_output_tokens)
        or receipt.retained_microusd
        != policy.cost(result.usage.billed_input, result.usage.billed_output)
        or receipt.retained_microusd > reservation.reserved_microusd
        or reservation.reserved_microusd > policy.max_cost_microusd
    ):
        raise ValueError("live spending artifacts do not match the result")


def load_live_run(
    path: Path,
) -> tuple[AgentConfig, tuple[JournalEvent, ...], AgentResult]:
    manifest = LiveManifest.model_validate_json(
        read_bounded(path / "manifest.json", MAX_ARTIFACT_BYTES)
    )
    if manifest.run_id != path.name:
        raise ValueError("live run identity does not match its directory")
    names = tuple(artifact.name for artifact in manifest.artifacts)
    expected_names = LIVE_ARTIFACTS + (
        SPEND_ARTIFACTS if manifest.spend_control else ()
    )
    if len(names) != len(expected_names) or set(names) != set(expected_names):
        raise ValueError("live manifest artifact set is invalid")
    payloads: dict[str, bytes] = {}
    for artifact in manifest.artifacts:
        payload = read_bounded(path / artifact.name, MAX_ARTIFACT_BYTES)
        if digest(payload) != artifact.sha256:
            raise ValueError(f"live artifact digest mismatch: {artifact.name}")
        payloads[artifact.name] = payload
    events = tuple(
        JournalEvent.model_validate_json(line)
        for line in payloads["requests.jsonl"].splitlines()
    )
    if tuple(event.sequence for event in events) != tuple(range(len(events))):
        raise ValueError("live journal sequence is invalid")
    config = AgentConfig.model_validate_json(payloads["config.json"])
    result = AgentResult.model_validate_json(payloads["result.json"])
    if manifest.spend_control:
        _validate_spend(payloads, result)
    if (
        config.provider != "openai"
        or result.resolved_model.spec.provider != "openai"
        or result.resolved_model.spec.id != config.model
        or result.turns[: len(config.initial_turns)] != config.initial_turns
        or result.usage.unit != "tokens"
    ):
        raise ValueError("live run provider is invalid")
    started = tuple(event for event in events if event.type == "model.request.started")
    completed = tuple(
        event for event in events if event.type == "model.response.completed"
    )
    if (
        any(event.type == "model.request.failed" for event in events)
        or len(started) != result.usage.requests
        or len(completed) != result.usage.requests
        or len(result.responses) != result.usage.requests
        or tuple(event.payload_sha256 for event in completed)
        != tuple(digest(canonical_bytes(response)) for response in result.responses)
    ):
        raise ValueError("live run journal does not match its result")
    return config, events, result
