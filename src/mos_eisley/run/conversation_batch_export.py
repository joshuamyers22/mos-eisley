"""Explicit bounded SQLite export with source preflight and verified retries."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation_limits import MAX_SNAPSHOT_BYTES
from mos_eisley.conversation_state import SessionID
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.conversation_export import (
    ConversationExportPlan,
    ConversationExportReceipt,
    export_conversation,
    plan_export,
)

MAX_EXPORT_SESSIONS = 32
MAX_EXPORT_BYTES = 64_000_000


class BatchExportPlan(Contract):
    schema_version: Literal[1] = 1
    output_byte_limit: Literal[64_000_000] = MAX_EXPORT_BYTES
    entries: Annotated[
        tuple[ConversationExportPlan, ...],
        Field(min_length=1, max_length=MAX_EXPORT_SESSIONS),
    ]
    output_bytes: Annotated[int, Field(ge=1, le=MAX_EXPORT_BYTES)]
    messages: Annotated[int, Field(ge=0, le=MAX_EXPORT_SESSIONS * 16)]

    @model_validator(mode="after")
    def exact_selection(self) -> Self:
        ids = [entry.session_id for entry in self.entries]
        first = self.entries[0]
        if (
            ids != sorted(set(ids))
            or self.output_bytes != sum(entry.snapshot_bytes for entry in self.entries)
            or self.messages != sum(entry.messages for entry in self.entries)
            or any(
                any(
                    getattr(entry, field) != getattr(first, field)
                    for field in ("source", "destination", "owner_uid", "workspace")
                )
                for entry in self.entries
            )
        ):
            raise ValueError("invalid batch export selection or totals")
        return self


class BatchExportReceipt(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["preview", "apply"]
    status: Literal["planned", "completed", "stopped"]
    batch_sha256: Digest
    plan: BatchExportPlan
    receipts: Annotated[
        tuple[ConversationExportReceipt, ...], Field(max_length=MAX_EXPORT_SESSIONS)
    ]
    exported: Annotated[int, Field(ge=0, le=MAX_EXPORT_SESSIONS)]
    already_present: Annotated[int, Field(ge=0, le=MAX_EXPORT_SESSIONS)]
    failed_session_id: SessionID | None = None
    failure: Literal["source_or_destination_invalid", "storage_unavailable"] | None = (
        None
    )
    source_retained: Literal[True] = True

    @model_validator(mode="after")
    def verified_results(self) -> Self:
        selected = self.plan.entries
        if (
            self.batch_sha256 != digest(canonical_bytes(self.plan))
            or len(self.receipts) > len(selected)
            or self.exported != sum(item.status == "exported" for item in self.receipts)
            or self.already_present
            != sum(item.status == "already_present" for item in self.receipts)
        ):
            raise ValueError("invalid batch export receipt hash or counts")
        for actual, expected in zip(self.receipts, selected, strict=False):
            if actual.plan != expected:
                raise ValueError("batch export result does not match selection")
            if actual.status == ("exported" if self.mode == "preview" else "planned"):
                raise ValueError("batch export result does not match mode")
        if self.status == "stopped":
            if (
                len(self.receipts) >= len(selected)
                or self.failed_session_id != selected[len(self.receipts)].session_id
                or self.failure is None
            ):
                raise ValueError("invalid stopped batch export result")
        elif (
            len(self.receipts) != len(selected)
            or self.failed_session_id is not None
            or self.failure is not None
            or self.status != ("planned" if self.mode == "preview" else "completed")
        ):
            raise ValueError("invalid completed batch export result")
        return self


class BatchExportError(ValueError):
    def __init__(self, receipt: BatchExportReceipt) -> None:
        self.receipt = receipt
        super().__init__(
            f"Batch export stopped at session {receipt.failed_session_id}; "
            "completed JSON copies remain saved and SQLite sources are retained. "
            "Resolve the source/destination problem, then retry the unchanged "
            "selection with the same hash or preview a changed selection again."
        )


def _plan(
    source: Path, destination: Path, ids: tuple[str, ...], workspace: Path
) -> BatchExportPlan:
    entries: list[ConversationExportPlan] = []
    total = 0
    for sid in ids:
        remaining = MAX_EXPORT_BYTES - total
        if remaining <= 0:
            raise ValueError("batch export exceeds the 64000000-byte output budget")
        try:
            entry = plan_export(
                source,
                destination,
                sid,
                workspace,
                snapshot_max_bytes=min(MAX_SNAPSHOT_BYTES, remaining),
            )
        except (OSError, ValueError) as error:
            raise ValueError(
                f"Batch export source preflight failed for session {sid}; check "
                "ownership, workspace, locks, integrity and the "
                "64000000-byte output budget."
            ) from error
        entries.append(entry)
        total += entry.snapshot_bytes
    return BatchExportPlan(
        entries=tuple(entries),
        output_bytes=total,
        messages=sum(entry.messages for entry in entries),
    )


def _receipt(
    plan: BatchExportPlan,
    receipts: list[ConversationExportReceipt],
    *,
    apply: bool,
    failed: str | None = None,
    failure: Literal["source_or_destination_invalid", "storage_unavailable"]
    | None = None,
) -> BatchExportReceipt:
    return BatchExportReceipt(
        mode="apply" if apply else "preview",
        status="stopped" if failed is not None else "completed" if apply else "planned",
        batch_sha256=digest(canonical_bytes(plan)),
        plan=plan,
        receipts=tuple(receipts),
        exported=sum(item.status == "exported" for item in receipts),
        already_present=sum(item.status == "already_present" for item in receipts),
        failed_session_id=failed,
        failure=failure,
    )


def export_batch(
    source_root: Path,
    destination_root: Path,
    session_ids: tuple[str, ...],
    workspace: Path,
    *,
    expected_sha256: str | None = None,
    apply: bool = False,
) -> BatchExportReceipt:
    """Preflight all SQLite sources, then publish one locked JSON snapshot at a time."""
    if not 1 <= len(session_ids) <= MAX_EXPORT_SESSIONS:
        raise ValueError("an export batch requires 1–32 explicit session IDs")
    try:
        ids = tuple(
            sorted(
                TypeAdapter[str](SessionID).validate_python(sid) for sid in session_ids
            )
        )
        expected = (
            None
            if expected_sha256 is None
            else TypeAdapter[str](Digest).validate_python(expected_sha256)
        )
    except ValueError:
        raise ValueError("invalid batch export session ID or expected hash") from None
    if len(set(ids)) != len(ids):
        raise ValueError("an export batch cannot repeat session IDs")
    if apply and expected is None:
        raise ValueError("--apply requires --expected-sha256 from a batch preview")
    plan = _plan(source_root, destination_root, ids, workspace)
    if expected is not None and expected != digest(canonical_bytes(plan)):
        raise ValueError(
            "batch export selection changed; preview again before applying"
        )
    receipts: list[ConversationExportReceipt] = []
    for entry in plan.entries:
        try:
            receipt = export_conversation(
                source_root,
                destination_root,
                entry.session_id,
                workspace,
                expected_sha256=digest(canonical_bytes(entry)),
                apply=apply,
                snapshot_max_bytes=entry.snapshot_bytes,
            )
            receipts.append(receipt)
        except (OSError, ValueError) as error:
            raise BatchExportError(
                _receipt(
                    plan,
                    receipts,
                    apply=apply,
                    failed=entry.session_id,
                    failure="storage_unavailable"
                    if isinstance(error, OSError)
                    else "source_or_destination_invalid",
                )
            ) from error
    return _receipt(plan, receipts, apply=apply)
