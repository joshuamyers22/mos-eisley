"""Host authorization links a blinded assignment to an explicit approved payload."""

from pathlib import Path

from pydantic import JsonValue

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.evaluation.execution import ExecutionBatch
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport, SpendPolicy
from mos_eisley.run.broker_audit import AssignmentAuthorization, BrokerAudit
from mos_eisley.run.provider_broker import ApprovedRequest, RequestBoundBroker
from mos_eisley.run.spend_ledger import SpendLedger


def make_assignment_authorization(
    batch: ExecutionBatch,
    sample_id: str,
    payload: dict[str, JsonValue],
    spend_policy: SpendPolicy,
    ledger: SpendLedger,
    ledger_entry_id: str,
) -> AssignmentAuthorization:
    """Bind one assignment to provider, spending, and shared-ledger identities."""

    matches = [request for request in batch.requests if request.sample_id == sample_id]
    if len(matches) != 1:
        raise ValueError("unique assignment and shared ledger required")
    request = matches[0]
    if payload.get("model") != request.route.model or payload.get("reasoning") != {
        "effort": request.route.effort
    }:
        raise ValueError("approved payload model/effort differs from assignment")
    if spend_policy.model != request.route.model:
        raise ValueError("spending model differs from assignment")
    return AssignmentAuthorization(
        plan_sha256=batch.plan_sha256,
        batch_sha256=batch.batch_sha256,
        sample_id=request.sample_id,
        candidate_id=request.route.candidate_id,
        evaluation_request_sha256=request.request_sha256,
        provider_request_sha256=digest(
            canonical_bytes(ApprovedRequest(payload=payload))
        ),
        spend_policy_sha256=spend_policy.policy_sha256,
        ledger_id=ledger.policy.ledger_id,
        ledger_entry_id=ledger_entry_id,
    )


def authorize_assignment(
    batch: ExecutionBatch,
    sample_id: str,
    payload: dict[str, JsonValue],
    transport: BudgetedOpenAITransport,
) -> AssignmentAuthorization:
    if transport.ledger is None:
        raise ValueError("unique assignment and shared ledger required")
    return make_assignment_authorization(
        batch,
        sample_id,
        payload,
        transport.policy,
        transport.ledger,
        transport.ledger_entry_id,
    )


def make_assignment_broker(
    batch: ExecutionBatch,
    sample_id: str,
    payload: dict[str, JsonValue],
    transport: BudgetedOpenAITransport,
    audit_directory: Path,
    *,
    lifetime_seconds: float = 30,
) -> RequestBoundBroker:
    binding = authorize_assignment(batch, sample_id, payload, transport)
    return RequestBoundBroker(
        payload,
        transport,
        lifetime_seconds=lifetime_seconds,
        audit=BrokerAudit(audit_directory, binding),
    )
