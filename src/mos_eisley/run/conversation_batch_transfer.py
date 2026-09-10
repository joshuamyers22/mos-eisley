"""Bounded cross-root copies with explicit selection and per-session transactions."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation_state import SessionID
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.conversation_batch_migration import (
    MAX_BATCH_SESSIONS,
    BatchMigrationPlan,
    plan_batch_sources,
)
from mos_eisley.run.conversation_transfer import (
    ConversationTransferPlan,
    ConversationTransferReceipt,
    TransferLocation,
    inspect_transfer_destination,
    transfer_conversation,
)


class BatchTransferPlan(Contract):
    schema_version: Literal[1] = 1
    sources: BatchMigrationPlan
    destination: TransferLocation

    @model_validator(mode="after")
    def separate_roots(self) -> Self:
        if self.destination.identity == (
            self.sources.storage_device,
            self.sources.storage_inode,
        ):
            raise ValueError("batch transfer requires different storage roots")
        return self

    def session_plan(self, index: int) -> ConversationTransferPlan:
        source = self.sources
        return ConversationTransferPlan(
            owner_uid=source.owner_uid,
            workspace=source.workspace,
            source=TransferLocation(
                path=source.storage_root,
                device=source.storage_device,
                inode=source.storage_inode,
            ),
            destination=self.destination,
            selection=source.entries[index],
        )


class BatchTransferReceipt(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["preview", "apply"]
    status: Literal["planned", "completed", "stopped"]
    batch_sha256: Digest
    plan: BatchTransferPlan
    receipts: Annotated[
        tuple[ConversationTransferReceipt, ...], Field(max_length=MAX_BATCH_SESSIONS)
    ]
    imported: Annotated[int, Field(ge=0, le=MAX_BATCH_SESSIONS)]
    already_present: Annotated[int, Field(ge=0, le=MAX_BATCH_SESSIONS)]
    failed_session_id: SessionID | None = None
    failure: Literal["source_or_destination_invalid", "storage_unavailable"] | None = (
        None
    )
    source_retained: Literal[True] = True

    @model_validator(mode="after")
    def verified_results(self) -> Self:
        entries = self.plan.sources.entries
        if (
            self.batch_sha256 != digest(canonical_bytes(self.plan))
            or len(self.receipts) > len(entries)
            or self.imported != sum(item.status == "imported" for item in self.receipts)
            or self.already_present
            != sum(item.status == "already_present" for item in self.receipts)
        ):
            raise ValueError("invalid batch transfer receipt hash or counts")
        for index, actual in enumerate(self.receipts):
            if actual.plan != self.plan.session_plan(index):
                raise ValueError("batch transfer receipt does not match selection")
            if actual.status == ("imported" if self.mode == "preview" else "planned"):
                raise ValueError("batch transfer result does not match mode")
        if self.status == "stopped":
            if (
                len(self.receipts) >= len(entries)
                or self.failed_session_id != entries[len(self.receipts)].session_id
                or self.failure is None
            ):
                raise ValueError("invalid stopped batch transfer result")
        elif (
            len(self.receipts) != len(entries)
            or self.failed_session_id is not None
            or self.failure is not None
            or self.status != ("planned" if self.mode == "preview" else "completed")
        ):
            raise ValueError("invalid completed batch transfer result")
        return self


class BatchTransferError(ValueError):
    def __init__(self, receipt: BatchTransferReceipt) -> None:
        self.receipt = receipt
        super().__init__(
            f"Batch transfer stopped at session {receipt.failed_session_id}; "
            "completed copies remain saved and JSON sources are retained. "
            "Resolve the source/destination problem, then retry the unchanged "
            "selection with the same hash or preview a changed selection again."
        )


def _receipt(
    plan: BatchTransferPlan,
    receipts: list[ConversationTransferReceipt],
    *,
    apply: bool,
    failed: str | None = None,
    failure: Literal["source_or_destination_invalid", "storage_unavailable"]
    | None = None,
) -> BatchTransferReceipt:
    return BatchTransferReceipt(
        mode="apply" if apply else "preview",
        status="stopped" if failed is not None else "completed" if apply else "planned",
        batch_sha256=digest(canonical_bytes(plan)),
        plan=plan,
        receipts=tuple(receipts),
        imported=sum(item.status == "imported" for item in receipts),
        already_present=sum(item.status == "already_present" for item in receipts),
        failed_session_id=failed,
        failure=failure,
    )


def transfer_batch(
    source_root: Path,
    destination_root: Path,
    session_ids: tuple[str, ...],
    workspace: Path,
    *,
    expected_sha256: str | None = None,
    apply: bool = False,
) -> BatchTransferReceipt:
    """Preflight all sources, then copy or verify each under both session locks."""
    try:
        expected = (
            None
            if expected_sha256 is None
            else TypeAdapter[str](Digest).validate_python(expected_sha256)
        )
    except ValueError:
        raise ValueError("invalid batch transfer expected hash") from None
    if apply and expected is None:
        raise ValueError("--apply requires --expected-sha256 from a batch preview")
    sources = plan_batch_sources(source_root, session_ids, workspace)
    plan = BatchTransferPlan(
        sources=sources, destination=inspect_transfer_destination(destination_root)
    )
    if expected is not None and expected != digest(canonical_bytes(plan)):
        raise ValueError(
            "batch transfer selection changed; preview again before applying"
        )
    receipts: list[ConversationTransferReceipt] = []
    for index, entry in enumerate(sources.entries):
        try:
            selected = plan.session_plan(index)
            receipt = transfer_conversation(
                source_root,
                destination_root,
                entry.session_id,
                workspace,
                expected_sha256=digest(canonical_bytes(selected)),
                apply=apply,
                source_max_bytes=entry.source_bytes,
            )
            receipts.append(receipt)
        except (OSError, ValueError) as error:
            raise BatchTransferError(
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
