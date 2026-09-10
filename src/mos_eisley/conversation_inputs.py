"""Per-open admission for active memory and recorded provider inputs."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.conversation_memory import ConversationMemory
from mos_eisley.core.models import CanonicalFingerprint, Contract, canonical_fingerprint
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.files import read_bounded

DEFAULT_ACTIVE_MEMORY_BYTES = 131_072
MAX_ACTIVE_MEMORY_BYTES = 262_144
DEFAULT_RECORDING_BYTES = 2_000_000
MAX_RECORDING_BYTES = 32_000_000
MIN_ACTIVE_INPUT_BYTES = 4_096
InputField = Literal["memory", "retained_cassette"]


class ActiveInputLimitError(ValueError):
    """Admission failed before recovery, saving or dispatch."""

    def __init__(self, field: InputField, required: int | None, maximum: int) -> None:
        label, flag = (
            ("Active memory", "--active-memory-max-bytes")
            if field == "memory"
            else ("Recording", "--recording-max-bytes")
        )
        detail = (
            f"{label} needs {required} bytes; input limit is {maximum}."
            if required is not None
            else f"{label} file exceeds the {maximum}-byte input limit."
        )
        super().__init__(f"{detail} Reopen with {flag} BYTES to increase this limit.")


class ActiveInputLimits(Contract):
    memory_max_bytes: Annotated[
        int, Field(ge=MIN_ACTIVE_INPUT_BYTES, le=MAX_ACTIVE_MEMORY_BYTES)
    ] = DEFAULT_ACTIVE_MEMORY_BYTES
    recording_max_bytes: Annotated[
        int, Field(ge=MIN_ACTIVE_INPUT_BYTES, le=MAX_RECORDING_BYTES)
    ] = DEFAULT_RECORDING_BYTES

    def admit_size(self, field: InputField, required: int) -> None:
        maximum = (
            self.memory_max_bytes if field == "memory" else self.recording_max_bytes
        )
        if required > maximum:
            raise ActiveInputLimitError(field, required, maximum)

    def admit(
        self, memory: ConversationMemory | None, cassette: AgentCassette | None
    ) -> None:
        self.admit_memory(memory)
        if cassette is not None:
            self.admit_recording(cassette)

    def admit_memory(self, memory: ConversationMemory | None) -> None:
        if memory is not None:
            self.admit_size("memory", canonical_fingerprint(memory).bytes)

    def admit_recording(self, cassette: AgentCassette) -> CanonicalFingerprint:
        fingerprint = canonical_fingerprint(cassette)
        self.admit_size("retained_cassette", fingerprint.bytes)
        return fingerprint


def active_memory_byte_limit(value: str) -> int:
    maximum = int(value)
    if not MIN_ACTIVE_INPUT_BYTES <= maximum <= MAX_ACTIVE_MEMORY_BYTES:
        raise ValueError("active memory limit must be between 4096 and 262144")
    return maximum


def recording_byte_limit(value: str) -> int:
    maximum = int(value)
    if not MIN_ACTIVE_INPUT_BYTES <= maximum <= MAX_RECORDING_BYTES:
        raise ValueError("recording limit must be between 4096 and 32000000")
    return maximum


def read_recording(path: Path, limits: ActiveInputLimits) -> AgentCassette:
    try:
        payload = read_bounded(path, limits.recording_max_bytes)
    except ValueError as error:
        if str(error) != "input exceeds the byte limit":
            raise
        raise ActiveInputLimitError(
            "retained_cassette", None, limits.recording_max_bytes
        ) from None
    recording = AgentCassette.model_validate_json(payload)
    limits.admit(None, recording)
    return recording
