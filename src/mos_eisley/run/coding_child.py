"""Recorded coding over stdin; writes and executable tests stay inside Docker."""

from typing import Protocol, Self

from pydantic import model_validator

from mos_eisley.coding_child import (
    CodeSnapshot,
    CodingBrief,
    CodingPatch,
    CodingVerification,
)
from mos_eisley.conversation_local_child import LocalChildExecution
from mos_eisley.core.agent import AgentConfig, run_agent
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.demo_agent import fixture_registry
from mos_eisley.providers.agent_recorded import AgentCassette, RecordedAgentClient
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.journal import MemoryJournal
from mos_eisley.tools.none import NoToolsDispatcher


def coding_config(brief: CodingBrief) -> AgentConfig:
    return AgentConfig(
        provider=brief.assignment.provider,
        model=brief.assignment.model,
        effort=brief.assignment.effort,
        system=(
            "Return only CodingPatch JSON for this creator-approved brief. "
            "Change only owned paths; never alter tests. Implement the task "
            "for creator review. Brief "
        )
        + brief.sha256,
        initial_turns=(
            Turn(
                role="user", blocks=(TextBlock(text=canonical_bytes(brief).decode()),)
            ),
        ),
        max_iterations=1,
        max_tool_calls=0,
        request_timeout_seconds=5,
    )


class CodingJob(Contract):
    brief: CodingBrief
    cassette: AgentCassette

    @model_validator(mode="after")
    def bounded_recording(self) -> Self:
        if len(self.cassette.exchanges) != 1 or len(canonical_bytes(self)) > 192_000:
            raise ValueError("Coding needs one bounded unpaid recorded response.")
        return self


class CodingExecution(Contract):
    execution: LocalChildExecution
    patch: CodingPatch
    verification: CodingVerification


class CodingAck(Contract):
    payload_sha256: Digest
    execution_sha256: Digest
    verification: CodingVerification


class CodingExecutor(Protocol):
    @property
    def image_id(self) -> str: ...
    async def execute(self, job: CodingJob) -> CodingExecution: ...
    async def verify(
        self, brief: CodingBrief, snapshot: CodeSnapshot
    ) -> CodingVerification: ...


async def replay_coding(job: CodingJob, image_id: str) -> LocalChildExecution:
    journal = MemoryJournal()
    result = await run_agent(
        coding_config(job.brief),
        fixture_registry(),
        RecordedAgentClient(job.cassette),
        NoToolsDispatcher(),
        journal,
    )
    return LocalChildExecution(
        image_id=image_id, result=result, events=tuple(journal.events)
    )


class CodingWire(Contract):
    job: CodingJob
    image_id: str


class VerifyWire(Contract):
    brief: CodingBrief
    snapshot: CodeSnapshot


class CodingOffer(Contract):
    payload_sha256: Digest


class CodingContainer(OfflineContainer):
    """Trusted supervisor drops the test subprocess to a distinct unprivileged UID.

    Only SETUID/SETGID/KILL are added, with no mounts/network, read-only root and the
    existing cgroup/watchdog bounds. Untrusted Python never runs as supervisor.
    """

    def create_command(self, name: str, arguments: tuple[str, ...]) -> list[str]:
        command = super().create_command(name, arguments)
        command[command.index("--user") + 1] = "0:0"
        command[command.index("--security-opt") : command.index("--security-opt")] = [
            "--cap-add",
            "SETUID",
            "--cap-add",
            "SETGID",
            "--cap-add",
            "KILL",
        ]
        return command


class DockerCodingChild:
    def __init__(self, container: CodingContainer):
        self.container = container

    @property
    def image_id(self) -> str:
        return self.container.image_id

    async def _exchange(self, mode: str, payload: bytes, wall_seconds: int) -> bytes:
        if len(payload) > 256_000:
            raise ValueError("Coding wire exceeds its byte bound.")
        offer = CodingOffer(payload_sha256=digest(payload))

        async def supply(claim: bytes) -> bytes:
            if CodingOffer.model_validate_json(claim) != offer:
                raise ValueError("Coding worker requested a different brief.")
            return payload

        return await self.container.exchange_async(
            ("-m", "mos_eisley.run.coding_child_worker", mode),
            canonical_bytes(offer),
            supply,
            timeout=wall_seconds,
        )

    async def execute(self, job: CodingJob) -> CodingExecution:
        job = CodingJob.model_validate_json(job.model_dump_json())
        expected = await replay_coding(job, self.image_id)
        patch = CodingPatch.model_validate_json(expected.result.final_text)
        snapshot = patch.apply(job.brief)
        output = await self._exchange(
            "implement",
            canonical_bytes(CodingWire(job=job, image_id=self.image_id)),
            job.brief.wall_seconds,
        )
        acknowledgement = CodingAck.model_validate_json(output)
        actual = CodingExecution(
            execution=expected, patch=patch, verification=acknowledgement.verification
        )
        if (
            acknowledgement.payload_sha256
            != digest(canonical_bytes(CodingWire(job=job, image_id=self.image_id)))
            or acknowledgement.execution_sha256 != digest(canonical_bytes(actual))
            or actual.verification.snapshot_sha256 != snapshot.sha256
            or actual.verification.tests_sha256 != job.brief.assignment.tests_sha256
        ):
            raise ValueError(
                "Coding acknowledgement differs from its execution or tests."
            )
        return actual

    async def verify(
        self, brief: CodingBrief, snapshot: CodeSnapshot
    ) -> CodingVerification:
        original = {f.path: f for f in brief.verification_snapshot.files}
        if set(f.path for f in snapshot.files) - set(original) - set(brief.owned_paths):
            raise ValueError("Verification snapshot expands file authority.")
        if any(
            f != original.get(f.path)
            for f in snapshot.files
            if f.path not in brief.owned_paths
        ) or not set(brief.test_paths) <= {f.path for f in snapshot.files}:
            raise ValueError("Verification cannot change or remove creator tests.")
        raw = await self._exchange(
            "verify",
            canonical_bytes(VerifyWire(brief=brief, snapshot=snapshot)),
            brief.wall_seconds,
        )
        receipt = CodingVerification.model_validate_json(raw)
        if (
            receipt.snapshot_sha256 != snapshot.sha256
            or receipt.tests_sha256 != brief.assignment.tests_sha256
        ):
            raise ValueError("Verification returned another snapshot or test package.")
        return receipt
