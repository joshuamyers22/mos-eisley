"""Read-only inventory of durable controller records, never resume authority."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest
from mos_eisley.run.broker_audit import BrokerAdmission
from mos_eisley.run.files import read_bounded
from mos_eisley.run.model_evidence import ModelCompletion
from mos_eisley.run.process import MAX_WIRE_BYTES
from mos_eisley.run.review_broker import (
    JudgeTransferAuthorization,
    ReviewAuthorization,
    ReviewSpendingEnvelope,
    verify_review_broker_audit,
)
from mos_eisley.run.review_controller import (
    ControllerJudgePreview,
    ControllerStart,
    ControllerTerminal,
)
from mos_eisley.run.review_evidence import verify_model_completion
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerEntryStatus, SpendLedger

RecordedPhase = Literal[
    "started", "judge_preview", "judge_transfer", "finished", "failed", "cancelled"
]


class CallInventory(Contract):
    authorization_sha256: Digest
    ledger: LedgerEntryStatus | None
    audit: Literal["absent", "partial", "verified"]
    completion: Literal["absent", "unverified", "verified"]


class ControllerInventory(Contract):
    schema_version: Literal[1] = 1
    controller_sha256: Digest
    recorded_phase: RecordedPhase
    deadline_expired: bool
    critics: tuple[CallInventory, ...]
    judge_allowance: LedgerEntryStatus | None
    judge: CallInventory | None
    identified_charged_microusd: int
    ledger_charged_microusd: int
    spending_inventory_complete: bool
    result_present: bool
    result_sha256: Digest | None
    verdict_verified: Literal[False] = False
    retry_permitted: Literal[False] = False
    resume_authorized: Literal[False] = False


def _optional(path: Path, limit: int) -> bytes | None:
    try:
        return read_bounded(path, limit)
    except FileNotFoundError:
        # A dangling symlink is an invalid artifact, not a missing record.
        if path.is_symlink():
            raise ValueError("controller artifact must not be a symlink") from None
        return None


def _entry(ledger: SpendLedger, expected: LedgerEntry) -> LedgerEntryStatus | None:
    status = ledger.entry_status(expected.entry_id)
    if status is not None and (
        status.reservation_sha256 != expected.reservation_sha256
        or status.reserved_microusd != expected.reserved_microusd
    ):
        raise ValueError("controller spending reservation mismatch")
    return status


def _call(
    directory: Path, expected: ReviewAuthorization, ledger: SpendLedger
) -> CallInventory:
    if directory.is_symlink():
        raise ValueError("controller call directory must not be a symlink")
    status = _entry(
        ledger,
        LedgerEntry(
            entry_id=expected.ledger_entry_id,
            reservation_sha256=expected.reservation_sha256,
            reserved_microusd=expected.reserved_microusd,
        ),
    )
    authorization = _optional(directory / "authorization.json", 4096)
    if authorization is not None and authorization != canonical_bytes(expected):
        raise ValueError("controller call authorization mismatch")
    # Check present request artifacts even when a crash left the audit unfinished.
    artifacts = {
        "model-request.json": expected.model_request_sha256,
        "review-input.json": expected.review_input_sha256,
        "spend-policy.json": expected.spend_policy_sha256,
        "spend-plan.json": expected.reservation_sha256,
        "critic.json": expected.critic_sha256,
    }
    present = authorization is not None
    for name, sha256 in artifacts.items():
        raw = _optional(directory / name, MAX_WIRE_BYTES)
        if raw is not None:
            present = True
            if sha256 is None or digest(raw) != sha256:
                raise ValueError("controller call artifact mismatch")
    admission_raw = _optional(directory / "admission.json", 4096)
    if admission_raw is not None:
        present = True
        admission = BrokerAdmission.model_validate_json(admission_raw)
        if admission.authorization_sha256 != digest(canonical_bytes(expected)):
            raise ValueError("controller call admission mismatch")
    outcome_raw = _optional(directory / "outcome.json", 4096)
    outcome = None
    if outcome_raw is not None:
        outcome = verify_review_broker_audit(directory, expected)
    completion_raw = _optional(directory / "model-completion.json", 4096)
    completion: Literal["absent", "unverified", "verified"] = "absent"
    if completion_raw is not None:
        present = True
        receipt = ModelCompletion.model_validate_json(completion_raw)
        if receipt.request_sha256 != expected.model_request_sha256:
            raise ValueError("controller call completion mismatch")
        completion = "unverified"
        if outcome is not None:
            request = ModelRequest.model_validate_json(
                read_bounded(directory / "model-request.json", MAX_WIRE_BYTES)
            )
            verify_model_completion(directory, request, outcome)
            completion = "verified"
    return CallInventory(
        authorization_sha256=digest(canonical_bytes(expected)),
        ledger=status,
        audit="verified" if outcome is not None else "partial" if present else "absent",
        completion=completion,
    )


def inspect_review_controller(
    directory: Path,
    expected: ControllerStart,
    ledger: SpendLedger,
    *,
    expected_judge_preview_sha256: str | None = None,
) -> ControllerInventory:
    """Inventory a stopped run against a separately retained trusted start record.

    The result describes persisted records, not process liveness or a verified
    review verdict. Readers never follow stored paths, dispatch, or repair spend.
    """
    expected = ControllerStart.model_validate_json(canonical_bytes(expected))
    if read_bounded(directory / "controller-start.json", 4096) != canonical_bytes(
        expected
    ):
        raise ValueError("controller start mismatch")
    raw_envelope = read_bounded(directory / "envelope.json", 32_768)
    envelope = ReviewSpendingEnvelope.model_validate_json(raw_envelope)
    if (
        digest(raw_envelope) != expected.authorization.envelope_sha256
        or Path(envelope.artifact_directory).resolve() != directory.resolve()
        or envelope.ledger_policy_sha256 != digest(canonical_bytes(ledger.policy))
        or any(call.ledger_id != ledger.policy.ledger_id for call in envelope.critics)
    ):
        raise ValueError("controller envelope, directory or ledger mismatch")
    if (
        expected.started_at.tzinfo is None
        or expected.expires_at.tzinfo is None
        or not expected.started_at < expected.expires_at <= envelope.expires_at
        or (expected.expires_at - expected.started_at).total_seconds()
        > expected.authorization.total_seconds
    ):
        raise ValueError("controller deadline mismatch")
    controller_sha256 = digest(canonical_bytes(expected.authorization))
    critics = tuple(
        _call(directory / call.ledger_entry_id, call, ledger)
        for call in envelope.critics
    )
    allowance = _entry(ledger, envelope.judge.ledger_entry)
    preview_raw = _optional(directory / "controller-judge-preview.json", MAX_WIRE_BYTES)
    preview = None
    phase: RecordedPhase = "started"
    if preview_raw is not None:
        preview = ControllerJudgePreview.model_validate_json(preview_raw)
        if (
            preview.controller_sha256 != controller_sha256
            or preview.evidence.envelope_sha256
            != expected.authorization.envelope_sha256
            or preview.evidence.policy != expected.authorization.policy
            or digest(canonical_bytes(preview.evidence))
            != preview.authorization.evidence_sha256
        ):
            raise ValueError("controller judge preview mismatch")
        phase = "judge_preview"
    if expected_judge_preview_sha256 is not None and (
        preview is None or preview.sha256 != expected_judge_preview_sha256
    ):
        raise ValueError("controller judge preview differs from independent pin")
    transfer_raw = _optional(directory / "judge-transfer.json", 8192)
    judge = None
    if transfer_raw is not None:
        if expected_judge_preview_sha256 is None:
            raise ValueError(
                "judge transfer inspection requires an independent preview pin"
            )
        transfer = JudgeTransferAuthorization.model_validate_json(transfer_raw)
        if (
            preview is None
            or digest(canonical_bytes(transfer))
            != preview.authorization.transfer_sha256
            or transfer.envelope_sha256 != expected.authorization.envelope_sha256
            or transfer.allowance != envelope.judge.ledger_entry
            or transfer.call.ledger_entry_id
            in {call.ledger_entry_id for call in envelope.critics}
            or transfer.call.brief_sha256 != envelope.judge.brief_sha256
            or transfer.call.spend_policy_sha256
            != envelope.judge.spend_policy.policy_sha256
            or transfer.call.review_input_sha256
            != digest(canonical_bytes(preview.evidence.judge_request))
            or transfer.call.ledger_id != ledger.policy.ledger_id
            or transfer.call.ledger_policy_sha256 != envelope.ledger_policy_sha256
            or transfer.call.guidance_sha256 != envelope.critics[0].guidance_sha256
            or transfer.call.model_request_sha256
            != digest(canonical_bytes(preview.model_request))
            or allowance is None
            or allowance.status != "settled"
            or allowance.charged_microusd != 0
        ):
            raise ValueError("controller judge transfer mismatch")
        judge = _call(directory / "judge", transfer.call, ledger)
        phase = "judge_transfer"
    result = _optional(directory / "review-result.json", MAX_WIRE_BYTES)
    result_sha256 = None if result is None else digest(result)
    terminal_raw = _optional(directory / "controller-terminal.json", 4096)
    if terminal_raw is not None:
        terminal = ControllerTerminal.model_validate_json(terminal_raw)
        if (
            terminal.controller_sha256 != controller_sha256
            or (
                terminal.result_sha256 is not None
                and terminal.result_sha256 != result_sha256
            )
            or (
                terminal.phase == "finished"
                and (result is None or judge is None or terminal.result_sha256 is None)
            )
        ):
            raise ValueError("controller terminal mismatch")
        phase = terminal.phase
    entries = [call.ledger for call in critics] + [allowance]
    if judge is not None:
        entries.append(judge.ledger)
    # A crash can retire the allowance before persisting the target transfer.
    # Its target cannot be inferred from unrelated ledger entries.
    complete = all(entry is not None for entry in entries) and not (
        judge is None and allowance is not None and allowance.status != "held"
    )
    return ControllerInventory(
        controller_sha256=controller_sha256,
        recorded_phase=phase,
        deadline_expired=datetime.now(UTC) >= expected.expires_at,
        critics=critics,
        judge_allowance=allowance,
        judge=judge,
        identified_charged_microusd=sum(
            entry.charged_microusd for entry in entries if entry is not None
        ),
        ledger_charged_microusd=ledger.snapshot().charged_microusd,
        spending_inventory_complete=complete,
        result_present=result is not None,
        result_sha256=result_sha256,
    )
