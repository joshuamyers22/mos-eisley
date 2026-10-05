"""Inert signed event ingress; no network, credentials, artifact reads or dispatch."""

from collections.abc import Callable
from threading import Lock
from time import monotonic
from typing import TYPE_CHECKING, Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field, model_validator

from mos_eisley.conversation_branch_controller import observe_branch_workspace
from mos_eisley.conversation_schedule import (
    InertScheduleState,
    IngressRate,
    LocalSourcePin,
    LocalWakeupEvent,
    ScheduleBinding,
)
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest

if TYPE_CHECKING:
    from mos_eisley.conversation_schedule_sources import LocalResultBatch

DOMAIN = b"mos-eisley:schedule-event:v1\x00"
MAX_PACKET_BYTES = 16_384
MAX_ATTEMPTS_PER_SECOND = 16


class ExternalSourceAuthorization(Contract):
    source_id: Identifier
    kind: Literal["external"] = "external"
    binding: ScheduleBinding
    key_id: Identifier
    verification_key_sha256: Digest
    not_after: Annotated[float, Field(ge=0)]
    maximum_age_seconds: Annotated[int, Field(ge=1, le=3600)] = 300
    maximum_events_per_window: Annotated[int, Field(ge=1, le=16)] = 4
    window_seconds: Annotated[int, Field(ge=1, le=3600)] = 60

    @property
    def pin(self) -> LocalSourcePin:
        return LocalSourcePin(
            source_id=self.source_id,
            kind="external",
            authorization_sha256=digest(canonical_bytes(self)),
        )


class ExternalEventBody(Contract):
    schema_version: Literal[1] = 1
    source_id: Identifier
    key_id: Identifier
    event_id: Identifier
    sequence: Annotated[int, Field(ge=1, le=2**63 - 1)]
    binding: ScheduleBinding
    occurred_at: Annotated[float, Field(ge=0)]
    expires_at: Annotated[float, Field(ge=0)]
    payload: Annotated[str, Field(min_length=1, max_length=4096)]

    @model_validator(mode="after")
    def bounded_payload(self) -> Self:
        if len(self.payload.encode()) > 4096 or self.expires_at <= self.occurred_at:
            raise ValueError("External event payload/lifetime is invalid.")
        return self


class SignedExternalEvent(Contract):
    body: ExternalEventBody
    signature: Annotated[str, Field(pattern=r"^[0-9a-f]{128}$")]


class InertExternalIngress:
    """Owner-provisioned verification key and trusted workspace broker only."""

    def __init__(
        self,
        authorization: ExternalSourceAuthorization,
        verification_key: bytes,
        workspace: str,
        *,
        observe_workspace: Callable[[str], str] = observe_branch_workspace,
    ) -> None:
        self.authorization = ExternalSourceAuthorization.model_validate_json(
            canonical_bytes(authorization)
        )
        if (
            len(verification_key) != 32
            or digest(verification_key) != authorization.verification_key_sha256
            or digest(workspace.encode()) != authorization.binding.workspace_sha256
        ):
            raise ValueError(
                "External source key/workspace differs from authorization."
            )
        self._key = Ed25519PublicKey.from_public_bytes(verification_key)
        self._workspace = workspace
        self._observe_workspace = observe_workspace
        self._attempt_lock = Lock()
        self._attempts: tuple[float, ...] = ()

    def admit_attempt(self) -> None:
        """Cap parsing/signature work, including rejected and replayed envelopes."""
        now = monotonic()
        with self._attempt_lock:
            retained = tuple(t for t in self._attempts if now - t < 1)
            if len(retained) >= MAX_ATTEMPTS_PER_SECOND:
                raise ValueError("External ingress attempt limit exhausted.")
            self._attempts = (*retained, now)

    def authenticate(self, packet: bytes, *, now: float) -> LocalWakeupEvent:
        if not 0 < len(packet) <= MAX_PACKET_BYTES:
            raise ValueError("External envelope exceeds the wire limit.")
        envelope = SignedExternalEvent.model_validate_json(packet)
        if canonical_bytes(envelope) != packet:
            raise ValueError(
                "External envelope must have one canonical interpretation."
            )
        auth, body = self.authorization, envelope.body
        try:
            self._key.verify(
                bytes.fromhex(envelope.signature), DOMAIN + canonical_bytes(body)
            )
        except InvalidSignature:
            raise ValueError("External envelope authentication failed.") from None
        if (
            body.source_id != auth.source_id
            or body.key_id != auth.key_id
            or body.binding != auth.binding
            or not body.occurred_at <= now < body.expires_at <= auth.not_after
            or now - body.occurred_at > auth.maximum_age_seconds
            or body.expires_at - body.occurred_at > auth.maximum_age_seconds
        ):
            raise ValueError(
                "External envelope scope/lifetime differs from authorization."
            )
        # Read only the host-selected workspace; never follow a sender path/reference.
        if self._observe_workspace(self._workspace) != body.binding.revision_sha256:
            raise ValueError(
                "External revision assertion differs from trusted observation."
            )
        payload = body.payload.encode()
        return LocalWakeupEvent(
            source_id=auth.source_id,
            kind="external",
            event_id=body.event_id,
            sequence=body.sequence,
            binding=auth.binding,
            payload_sha256=digest(payload),
            payload_bytes=len(payload),
        )

    def validate_packet(
        self, packet: bytes, event: LocalWakeupEvent, *, now: float
    ) -> None:
        if self.authenticate(packet, now=now) != event:
            raise ValueError(
                "External notification differs from its authenticated envelope."
            )

    def validate(self, event: LocalWakeupEvent) -> None:
        raise ValueError("External notifications require their signed envelope.")

    def events(self, after_sequence: int) -> "LocalResultBatch":
        # No mailbox: the owner receives one bounded packet explicitly, then drops it.
        from mos_eisley.conversation_schedule_sources import LocalResultBatch

        return LocalResultBatch()


def charge_ingress(
    state: InertScheduleState, auth: ExternalSourceAuthorization, *, now: float
) -> IngressRate:
    previous = next(
        (r for r in state.ingress_rates if r.source_id == auth.source_id), None
    )
    times = () if previous is None else previous.accepted_at
    if times and now < times[-1]:
        raise ValueError("External ingress clock moved backwards.")
    retained = tuple(t for t in times if now - t < auth.window_seconds)
    if len(retained) >= auth.maximum_events_per_window:
        raise ValueError("External ingress rate allowance exhausted.")
    return IngressRate(source_id=auth.source_id, accepted_at=(*retained, now))
