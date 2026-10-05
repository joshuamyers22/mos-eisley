"""Cancellation-safe offline child execution through the existing no-mount broker."""

from mos_eisley.conversation_local_child import LocalChildExecution, LocalChildJob
from mos_eisley.core.agent import run_agent
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.demo_agent import fixture_registry
from mos_eisley.providers.agent_recorded import RecordedAgentClient
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.journal import MemoryJournal
from mos_eisley.tools.none import NoToolsDispatcher


class LocalChildOffer(Contract):
    job_sha256: Digest


class LocalChildAck(Contract):
    job_sha256: Digest
    execution_sha256: Digest


async def replay_child(job: LocalChildJob, image_id: str) -> LocalChildExecution:
    journal = MemoryJournal()
    result = await run_agent(
        job.config,
        fixture_registry(),
        RecordedAgentClient(job.cassette),
        NoToolsDispatcher(),
        journal,
    )
    return LocalChildExecution(
        image_id=image_id, result=result, events=tuple(journal.events)
    )


class DockerLocalChild:
    """One read-only child, depth one; no providers, tools, mounts or credentials."""

    def __init__(self, container: OfflineContainer):
        self.container = container

    @property
    def image_id(self) -> str:
        return self.container.image_id

    async def execute(self, job: LocalChildJob) -> LocalChildExecution:
        job = LocalChildJob.model_validate_json(job.model_dump_json())
        wire = canonical_bytes(job)
        if len(wire) > 128_000:
            raise ValueError("Child brief/recording exceeds its byte limit.")
        # The host verifies deterministic recorded output; worker output cannot
        # invent completion or verification evidence.
        payload = canonical_bytes(ChildWire(job=job, image_id=self.image_id))
        if len(payload) > 128_000:
            raise ValueError("Child wire exceeds its byte limit.")
        expected = await replay_child(job, self.image_id)
        offer = LocalChildOffer(job_sha256=digest(wire))

        async def supply(claim: bytes) -> bytes:
            if LocalChildOffer.model_validate_json(claim) != offer:
                raise ValueError("Child requested another brief.")
            return payload

        output = await self.container.exchange_async(
            ("-m", "mos_eisley.run.local_child_worker"),
            canonical_bytes(offer),
            supply,
            timeout=5,
        )
        acknowledgement = LocalChildAck.model_validate_json(output)
        if acknowledgement != LocalChildAck(
            job_sha256=offer.job_sha256,
            execution_sha256=digest(canonical_bytes(expected)),
        ):
            raise ValueError("Child acknowledgement differs from its exact execution.")
        return expected


class ChildWire(Contract):
    job: LocalChildJob
    image_id: str
