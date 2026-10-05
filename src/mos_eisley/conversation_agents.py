"""Read-only projections from an owner-scoped child controller, never a registry."""

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    Text,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import Effort
from mos_eisley.task_state import ResourceCeiling, ResourceLedger


class AgentInspectionScope(Contract):
    owner_uid: Annotated[int, Field(ge=0)]
    parent_session_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    workspace_sha256: Digest


class AgentReportReference(Contract):
    report_id: Identifier
    assignment_sha256: Digest
    sha256: Digest
    availability: Literal["available", "missing", "partial"]


class ImplementationAssignment(Contract):
    task_id: Identifier
    parent_task_id: Identifier
    objective: Text
    provider: Identifier
    model: Identifier
    effort: Effort | None = None
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    worktree: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    plan_sha256: Digest
    tests_sha256: Digest
    allowance: ResourceCeiling

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class AgentOperationalRecord(Contract):
    """Review records intentionally have no slot for sealed text or findings."""

    child_id: Identifier
    scope: AgentInspectionScope
    role: Literal["implementation", "review"]
    state: Literal["queued", "running", "completed", "failed", "cancelled", "unknown"]
    assignment: ImplementationAssignment | None = None
    assignment_current: bool = False
    usage: ResourceLedger | None = None
    verification: Literal["passed", "failed", "not_run", "stale", "unknown"] = "unknown"
    unresolved: Annotated[tuple[Text, ...], Field(max_length=16)] = ()
    report: AgentReportReference | None = None

    @model_validator(mode="after")
    def visible_fields_only(self) -> Self:
        if self.role == "review" and (
            self.assignment is not None
            or self.assignment_current
            or self.usage is not None
            or self.verification != "unknown"
            or self.unresolved
            or self.report is not None
        ):
            raise ValueError(
                "Review inspection permits only operational identity and state."
            )
        if self.role == "implementation" and self.assignment is None:
            raise ValueError(
                "Implementation inspection requires an authorized assignment."
            )
        return self


class AgentInspectionSnapshot(Contract):
    schema_version: Literal[1] = 1
    scope: AgentInspectionScope
    revision: Annotated[int, Field(ge=1)]
    children: Annotated[tuple[AgentOperationalRecord, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def unique_owned_children(self) -> Self:
        if len({c.child_id for c in self.children}) != len(self.children):
            raise ValueError("Child inspection identities must be unique.")
        if any(c.scope != self.scope for c in self.children):
            raise ValueError("Child inspection scope mismatch.")
        return self


class ImplementationReport(Contract):
    schema_version: Literal[1] = 1
    scope: AgentInspectionScope
    child_id: Identifier
    report_id: Identifier
    assignment_sha256: Digest
    summary: Text
    evidence: Annotated[tuple[Text, ...], Field(max_length=16)] = ()
    unresolved: Annotated[tuple[Text, ...], Field(max_length=16)] = ()
    complete: bool = False
    integration_approved: Literal[False] = False


class AgentInspection(Contract):
    snapshot: AgentInspectionSnapshot
    report: ImplementationReport | None = None
    report_status: Literal[
        "not_requested", "available", "missing", "partial", "stale", "sealed"
    ] = "not_requested"
    inspection_only: Literal[True] = True
    grants_authority: Literal[False] = False


class ChildInspectionSource(Protocol):
    """Trusted existing controller supplies authorized projections, not raw artifacts.

    Methods must be bounded, read-only and internally consistent during dispatch,
    resume and cancellation. No filesystem paths from model output are followed.
    Review rows must be projected before any sealed evidence is opened. Assignment
    currentness is checked against the controller's frozen plan/test authorization.
    A report read must fail on revision change and bind the exact expected reference.
    """

    def snapshot(self, scope: AgentInspectionScope) -> AgentInspectionSnapshot: ...

    def report(
        self,
        scope: AgentInspectionScope,
        child_id: str,
        reference: AgentReportReference,
        *,
        expected_revision: int,
    ) -> ImplementationReport: ...


def inspect_children(
    source: ChildInspectionSource,
    scope: AgentInspectionScope,
    child_id: str | None = None,
) -> AgentInspection:
    snapshot = source.snapshot(scope)
    # Validate even model_copy-created projections; bound the total serialized view.
    if len(canonical_bytes(snapshot)) > 128_000:
        raise ValueError("Child inspection exceeds its byte limit.")
    snapshot = AgentInspectionSnapshot.model_validate_json(canonical_bytes(snapshot))
    if snapshot.scope != scope:
        raise ValueError("Child inspection owner, parent or workspace mismatch.")
    if child_id is None:
        return AgentInspection(snapshot=snapshot)
    child = next((c for c in snapshot.children if c.child_id == child_id), None)
    if child is None:
        raise ValueError("Child is not in the authorized inspection scope.")
    # No report read is attempted for reviews, stale assignments or missing output.
    if child.role == "review":
        return AgentInspection(snapshot=snapshot, report_status="sealed")
    assert child.assignment is not None
    reference = child.report
    if not child.assignment_current or (
        reference is not None and reference.assignment_sha256 != child.assignment.sha256
    ):
        return AgentInspection(snapshot=snapshot, report_status="stale")
    if reference is None or reference.availability == "missing":
        return AgentInspection(snapshot=snapshot, report_status="missing")
    report = source.report(
        scope, child_id, reference, expected_revision=snapshot.revision
    )
    raw = canonical_bytes(report)
    if len(raw) > 128_000:
        raise ValueError("Child report exceeds its byte limit.")
    report = ImplementationReport.model_validate_json(raw)
    if (
        report.scope != scope
        or report.child_id != child_id
        or report.report_id != reference.report_id
        or report.assignment_sha256 != child.assignment.sha256
        or digest(raw) != reference.sha256
    ):
        raise ValueError("Child report differs from its retained authorized reference.")
    # Fail closed if dispatch/resume/reassignment raced with report retrieval.
    if canonical_bytes(source.snapshot(scope)) != canonical_bytes(snapshot):
        raise ValueError(
            "Child inspection changed; inspect the current revision again."
        )
    return AgentInspection(
        snapshot=snapshot,
        report=report,
        report_status="available"
        if reference.availability == "available" and report.complete
        else "partial",
    )
