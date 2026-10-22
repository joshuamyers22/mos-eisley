"""Bounded operation journal inside the existing verified session record.

An operation is the entire admitted turn, child attempt, or integration. No
intermediate provider/tool cursor is replayable. Hashes are integrity references,
not independent authorization or a substitute for the spending ledger.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest

if TYPE_CHECKING:
    from mos_eisley.conversation_state import (
        ArchivedConversationEntry,
        ConversationEntry,
        RuntimeConversationState,
    )


def fingerprint(*values: Contract | str | int | None) -> str:
    return digest(
        json.dumps(
            [
                v.model_dump(mode="json") if isinstance(v, Contract) else v
                for v in values
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


class RecoveryDecision(Contract):
    policy_sha256: Digest
    target_sha256: Digest
    request_sha256: Digest
    reservation_sha256: Digest


class RecoveryEvent(Contract):
    sequence: Annotated[int, Field(ge=1, le=96)]
    operation_id: Digest
    key: Annotated[
        str,
        Field(
            pattern=r"^(turn-[0-9]+|(?:child|integrate|side|fork)-[A-Za-z0-9_-]+)$",
            max_length=128,
        ),
    ]
    revision: Annotated[int, Field(ge=1)]
    phase: Literal["dispatch", "completed", "uncertain"]
    decision: RecoveryDecision | None = None
    result_sha256: Digest | None = None

    @model_validator(mode="after")
    def exact_phase(self) -> Self:
        if (self.phase == "dispatch") != (self.decision is not None):
            raise ValueError("Recovery dispatch requires its exact decision.")
        if (self.phase == "completed") != (self.result_sha256 is not None):
            raise ValueError("Recovery completion requires its exact result.")
        return self


class RecoveryJournal(Contract):
    schema_version: Literal[1] = 1
    events: Annotated[tuple[RecoveryEvent, ...], Field(max_length=96)] = ()
    cursor: Annotated[int, Field(ge=0, le=96)] = 0

    @model_validator(mode="after")
    def ordered(self) -> Self:
        pending: set[str] = set()
        seen: set[str] = set()
        revision = 0
        cursor = 0
        for sequence, event in enumerate(self.events, 1):
            if event.sequence != sequence or event.revision < revision:
                raise ValueError("Recovery journal sequence or revision is invalid.")
            revision = event.revision
            if event.phase == "dispatch":
                if event.operation_id in seen:
                    raise ValueError("Recovery operation cannot be dispatched twice.")
                seen.add(event.operation_id)
                pending.add(event.operation_id)
            else:
                if event.operation_id not in pending:
                    raise ValueError("Recovery terminal event has no open dispatch.")
                pending.remove(event.operation_id)
                cursor = sequence
        if self.cursor != cursor:
            raise ValueError("Recovery cursor precedes durable terminal evidence.")
        return self


def operation_id(session_id: str, key: str) -> str:
    return digest(("session-operation-v1:" + session_id + ":" + key).encode())


def turn_result(entry: ConversationEntry | ArchivedConversationEntry) -> str:
    # Memory refresh may materialize a legacy inherited-context reference. It
    # does not change the admitted request or returned outcome.
    return fingerprint(
        entry.text,
        entry.answer,
        entry.usage,
        entry.review_result,
        entry.request_admission,
        entry.status,
    )


def workspace_identity(workspace: str) -> str:
    root = Path(workspace)
    info = root.stat(follow_symlinks=False)
    if root.is_symlink() or not root.is_dir() or info.st_uid != os.getuid():
        raise ValueError("Recovery workspace must be owned and stable.")
    return digest(f"{root.resolve(strict=True)}:{info.st_dev}:{info.st_ino}".encode())


def uncertain_notice(journal: RecoveryJournal | None, key: str) -> str | None:
    if journal is not None and any(
        e.key == key and e.phase == "uncertain" for e in journal.events
    ):
        return (
            "Effect uncertain; the operation will not be replayed. "
            "Retained resource exposure is unchanged."
        )
    return None


def validate_journal(
    journal: RecoveryJournal | None, session_id: str, revision: int
) -> None:
    if journal is None:
        return
    for event in journal.events:
        if (
            event.operation_id != operation_id(session_id, event.key)
            or event.revision > revision
        ):
            raise ValueError("Recovery journal crosses session or revision scope.")


def transition_journal(
    before: RuntimeConversationState,
    after: RuntimeConversationState,
    observe_target: Callable[[int], str],
) -> RecoveryJournal | None:
    """Append decisions/results in the same transaction as authoritative state."""
    events = list(
        () if before.recovery_journal is None else before.recovery_journal.events
    )

    def append(
        key: str,
        phase: Literal["dispatch", "completed", "uncertain"],
        *,
        decision: RecoveryDecision | None = None,
        result_sha256: str | None = None,
    ) -> None:
        events.append(
            RecoveryEvent(
                sequence=len(events) + 1,
                operation_id=operation_id(after.session_id, key),
                key=key,
                revision=after.revision,
                phase=phase,
                decision=decision,
                result_sha256=result_sha256,
            )
        )

    def close(key: str, completed: bool, result: str) -> None:
        # Legacy running records have no decision journal. Do not invent one.
        if any(e.key == key and e.phase == "dispatch" for e in events) and not any(
            e.key == key and e.phase != "dispatch" for e in events
        ):
            append(
                key,
                "completed" if completed else "uncertain",
                result_sha256=result if completed else None,
            )

    for index, entry in enumerate(after.entries):
        old = before.entries[index] if index < len(before.entries) else None
        key = f"turn-{index}"
        if entry.status == "running" and (old is None or old.status != "running"):
            admission = entry.request_admission
            packet = entry.review_packet
            request = fingerprint(packet, admission)
            append(
                key,
                "dispatch",
                decision=RecoveryDecision(
                    policy_sha256=fingerprint(
                        after.live_chat, admission, packet, after.context_byte_limit
                    ),
                    target_sha256=observe_target(index),
                    request_sha256=(
                        request if admission is None else admission.request.sha256
                    ),
                    reservation_sha256=fingerprint(
                        after.exchanges_consumed,
                        None if admission is None else admission.request,
                        *after.goals,
                        after.branch_budget,
                        after.live_chat,
                        packet,
                    ),
                ),
            )
        elif old is not None and old.status == "running" and entry.status != "running":
            close(
                key,
                entry.status == "completed" or entry.review_result is not None,
                turn_result(entry),
            )

    old_children = {c.child_id: c for c in before.local_children}
    for child in after.local_children:
        old_child = old_children.get(child.child_id)
        key = "child-" + child.child_id
        if old_child is None and child.state == "running":
            append(
                key,
                "dispatch",
                decision=RecoveryDecision(
                    policy_sha256=fingerprint(
                        child.authorization, child.image_id, child.recipe_sha256
                    ),
                    target_sha256=child.authorization.workspace_observation_sha256,
                    request_sha256=child.request_sha256,
                    reservation_sha256=digest(canonical_bytes(child.reserved)),
                ),
            )
        elif (
            old_child is not None
            and old_child.state == "running"
            and child.state != "running"
        ):
            close(key, child.state == "completed", digest(canonical_bytes(child)))
        coding = child.coding
        old_coding = None if old_child is None else old_child.coding
        key = "integrate-" + child.child_id
        if (
            coding is not None
            and coding.integration_state == "integrating"
            and (old_coding is None or old_coding.integration_state != "integrating")
        ):
            append(
                key,
                "dispatch",
                decision=RecoveryDecision(
                    policy_sha256=fingerprint(coding, child.recipe_sha256),
                    target_sha256=child.authorization.workspace_observation_sha256,
                    request_sha256=child.request_sha256,
                    reservation_sha256=digest(canonical_bytes(child.reserved)),
                ),
            )
        elif (
            coding is not None
            and old_coding is not None
            and old_coding.integration_state == "integrating"
            and coding.integration_state != "integrating"
        ):
            close(
                key,
                coding.integration_state == "integrated",
                digest(canonical_bytes(coding)),
            )
    old_sides = {s.side_id: s for s in before.sides}
    for side in after.sides:
        old_side = old_sides.get(side.side_id)
        key = "side-" + side.side_id
        if old_side is None and side.state == "running":
            append(
                key,
                "dispatch",
                decision=RecoveryDecision(
                    policy_sha256=fingerprint(
                        side.context_sha256, side.workspace_sha256
                    ),
                    target_sha256=side.workspace_sha256,
                    request_sha256=side.request_sha256,
                    reservation_sha256=fingerprint(after.branch_budget, *after.goals),
                ),
            )
        elif (
            old_side is not None
            and old_side.state == "running"
            and side.state != "running"
        ):
            close(key, side.state == "completed", digest(canonical_bytes(side)))
    old_forks = {f.branch_id: f for f in before.forks}
    for fork in after.forks:
        old_fork = old_forks.get(fork.branch_id)
        key = "fork-" + fork.branch_id
        if old_fork is None and fork.state == "reserved":
            append(
                key,
                "dispatch",
                decision=RecoveryDecision(
                    policy_sha256=fingerprint(fork.context_sha256),
                    target_sha256=workspace_identity(after.workspace),
                    request_sha256=fingerprint(
                        fork.child_session_id, fork.context_sha256
                    ),
                    reservation_sha256=fingerprint(
                        fork.allowance, after.branch_budget, *after.goals
                    ),
                ),
            )
        elif (
            old_fork is not None
            and old_fork.state == "reserved"
            and fork.state != "reserved"
        ):
            close(key, fork.state == "published", digest(canonical_bytes(fork)))
    if not events and before.recovery_journal is None:
        return None
    return RecoveryJournal(
        events=tuple(events),
        cursor=max((e.sequence for e in events if e.phase != "dispatch"), default=0),
    )
