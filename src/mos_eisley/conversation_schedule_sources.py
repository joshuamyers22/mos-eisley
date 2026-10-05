"""Authorized metadata from existing committed jobs and retained child controllers."""

from collections.abc import Callable
from typing import Annotated, Literal, Protocol

from pydantic import Field, model_validator

from mos_eisley.conversation_agents import (
    AgentInspectionScope,
    ChildInspectionSource,
    inspect_children,
)
from mos_eisley.conversation_goal import GoalTestReceipt
from mos_eisley.conversation_schedule import (
    LocalSourcePin,
    LocalWakeupEvent,
    ScheduleBinding,
)
from mos_eisley.conversation_schedule_ingress import ExternalSourceAuthorization
from mos_eisley.conversation_state import RuntimeConversationState
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest


class LocalResultAuthorization(Contract):
    source_id: Identifier
    binding: ScheduleBinding
    kind: Literal["local_test", "local_child"]
    operation_ids: Annotated[tuple[Identifier, ...], Field(max_length=16)] = ()
    child_id: Identifier | None = None
    child_assignment_sha256: Digest | None = None
    test_workspace_sha256: Digest | None = None
    test_inputs_sha256: Digest | None = None

    @model_validator(mode="after")
    def explicit_target(self) -> "LocalResultAuthorization":
        if self.kind == "local_test":
            if (
                not self.operation_ids
                or len(set(self.operation_ids)) != len(self.operation_ids)
                or self.child_id is not None
                or self.child_assignment_sha256 is not None
                or self.test_workspace_sha256 is None
                or self.test_inputs_sha256 is None
            ):
                raise ValueError(
                    "Test sources require frozen operations and execution identities."
                )
        elif (
            self.child_id is None
            or self.child_assignment_sha256 is None
            or self.operation_ids
            or self.test_workspace_sha256
            or self.test_inputs_sha256
        ):
            raise ValueError(
                "Child sources require one authorized implementation child."
            )
        return self

    @property
    def pin(self) -> LocalSourcePin:
        return LocalSourcePin(
            source_id=self.source_id,
            kind=self.kind,
            authorization_sha256=digest(canonical_bytes(self)),
        )


class LocalResultBatch(Contract):
    events: Annotated[tuple[LocalWakeupEvent, ...], Field(max_length=16)] = ()


class LocalResultSource(Protocol):
    @property
    def authorization(
        self,
    ) -> LocalResultAuthorization | ExternalSourceAuthorization: ...

    def events(self, after_sequence: int) -> LocalResultBatch: ...

    def validate(self, event: LocalWakeupEvent) -> None: ...


def notification(
    authorization: LocalResultAuthorization,
    operation: str,
    sequence: int,
    payload: bytes,
) -> LocalWakeupEvent:
    if not 0 < len(payload) <= 4096:
        raise ValueError("Committed result exceeds the local notification limit.")
    return LocalWakeupEvent(
        source_id=authorization.source_id,
        event_id=digest(
            canonical_bytes(authorization)
            + operation.encode()
            + digest(payload).encode()
        ),
        sequence=sequence,
        binding=authorization.binding,
        payload_sha256=digest(payload),
        payload_bytes=len(payload),
        kind=authorization.kind,
    )


class CommittedTestResults:
    """The host authorizes execution identities and committed artifact lookup."""

    def __init__(
        self,
        authorization: LocalResultAuthorization,
        state: Callable[[], RuntimeConversationState],
        read_result: Callable[[str], bytes],
    ) -> None:
        if authorization.kind != "local_test":
            raise ValueError("Test adapter requires test authorization.")
        self.authorization = LocalResultAuthorization.model_validate_json(
            canonical_bytes(authorization)
        )
        self.state = state
        self.read_result = read_result

    def events(self, after_sequence: int) -> LocalResultBatch:
        auth = self.authorization
        before = self.state()
        binding = auth.binding
        if (
            before.owner_uid != binding.owner_uid
            or before.session_id != binding.session_id
            or digest(before.workspace.encode()) != binding.workspace_sha256
            or before.active_goal_id != binding.goal_id
        ):
            raise ValueError(
                "Test source is outside the selected owner/session/workspace."
            )
        goal = next(g for g in before.goals if g.goal_id == binding.goal_id)
        if goal.definition.sha256 != binding.goal_definition_sha256:
            raise ValueError("Test source goal assignment is stale.")
        events: list[LocalWakeupEvent] = []
        for operation in auth.operation_ids:
            job = next((j for j in goal.jobs if j.operation_id == operation), None)
            if job is None or job.definition_sha256 != goal.definition.sha256:
                raise ValueError(
                    "Test operation is not registered for this definition."
                )
            if (
                job.state not in {"passed", "failed"}
                or job.result_sha256 is None
                or job.committed_revision is None
                or job.committed_revision <= after_sequence
            ):
                continue
            if job.committed_revision > before.revision:
                raise ValueError("Test result has no acknowledged parent commit.")
            raw = self.read_result(job.result_sha256)
            if len(raw) > 4096 or digest(raw) != job.result_sha256:
                raise ValueError(
                    "Test artifact does not match its committed reference."
                )
            receipt = GoalTestReceipt.model_validate_json(raw)
            if (
                receipt.operation_id != operation
                or receipt.executed_tests == 0
                or receipt.failed_tests > receipt.executed_tests
                or receipt.workspace_sha256 != auth.test_workspace_sha256
                or receipt.inputs_sha256 != auth.test_inputs_sha256
                or (job.state == "passed") != (receipt.failed_tests == 0)
            ):
                raise ValueError("Test receipt is empty, inconsistent or stale.")
            events.append(notification(auth, operation, job.committed_revision, raw))
        if self.state().revision != before.revision:
            raise ValueError("Parent changed during committed test inspection.")
        return LocalResultBatch(events=tuple(sorted(events, key=lambda e: e.sequence)))

    def validate(self, event: LocalWakeupEvent) -> None:
        if event not in self.events(event.sequence - 1).events:
            raise ValueError(
                "Notification differs from the retained committed test result."
            )


class CommittedChildResults:
    """Read authorized implementation reports through the existing controller."""

    def __init__(
        self,
        authorization: LocalResultAuthorization,
        source: ChildInspectionSource,
    ) -> None:
        if authorization.kind != "local_child":
            raise ValueError("Child adapter requires child authorization.")
        self.authorization = LocalResultAuthorization.model_validate_json(
            canonical_bytes(authorization)
        )
        self.source = source

    def events(self, after_sequence: int) -> LocalResultBatch:
        auth, binding = self.authorization, self.authorization.binding
        scope = AgentInspectionScope(
            owner_uid=binding.owner_uid,
            parent_session_id=binding.session_id,
            workspace_sha256=binding.workspace_sha256,
        )
        before = self.source.snapshot(scope)
        child = next((c for c in before.children if c.child_id == auth.child_id), None)
        if before.scope != scope or child is None or child.role != "implementation":
            raise ValueError("Child is outside the authorized implementation scope.")
        assignment = child.assignment
        if (
            assignment is None
            or assignment.parent_task_id != binding.task_id
            or digest(assignment.workspace.encode()) != binding.workspace_sha256
            or not child.assignment_current
            or assignment.sha256 != auth.child_assignment_sha256
        ):
            raise ValueError("Child assignment is stale or belongs to another task.")
        view = inspect_children(
            self.source,
            scope,
            auth.child_id,
        )
        if view.snapshot != before:
            raise ValueError("Child changed during source inspection.")
        child = next(c for c in view.snapshot.children if c.child_id == auth.child_id)
        if child.role != "implementation":
            raise ValueError("Sealed review rows are not result sources.")
        assignment = child.assignment
        if assignment is None or assignment.parent_task_id != binding.task_id:
            raise ValueError("Child assignment belongs to another task.")
        if not child.assignment_current or view.report_status == "stale":
            raise ValueError("Child assignment/report is stale.")
        if (
            child.state not in {"completed", "failed", "cancelled"}
            or view.report_status != "available"
            or view.report is None
            or view.snapshot.revision <= after_sequence
        ):
            return LocalResultBatch()
        return LocalResultBatch(
            events=(
                notification(
                    auth,
                    str(auth.child_id),
                    view.snapshot.revision,
                    canonical_bytes(view.report),
                ),
            )
        )

    def validate(self, event: LocalWakeupEvent) -> None:
        if event not in self.events(event.sequence - 1).events:
            raise ValueError("Notification differs from the retained child commit.")
