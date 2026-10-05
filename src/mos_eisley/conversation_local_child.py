"""Owner-scoped, unpaid, text-only child contracts; no execution authority."""

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from mos_eisley.coding_child import CodingRetention
from mos_eisley.conversation_agents import (
    AgentInspectionScope,
    ImplementationAssignment,
    ImplementationReport,
)
from mos_eisley.core.agent import AgentConfig, AgentResult
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import JournalEvent, TextBlock, Turn
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.task_state import ResourceLedger


class LocalChildAuthorization(Contract):
    scope: AgentInspectionScope
    assignment_sha256: Digest
    workspace_observation_sha256: Digest
    expires_at: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    mode: Literal["recorded_read_only", "recorded_coding"] = "recorded_read_only"
    brief_sha256: Digest | None = None
    review_sha256: Digest | None = None

    @model_validator(mode="after")
    def exact_mode(self) -> Self:
        if (self.mode == "recorded_coding") != (
            self.brief_sha256 is not None and self.review_sha256 is not None
        ):
            raise ValueError(
                "Coding approval requires an exact brief and plan/test review."
            )
        if self.mode == "recorded_read_only" and (
            self.brief_sha256 is not None or self.review_sha256 is not None
        ):
            raise ValueError("Read-only approval cannot carry coding authority.")
        return self


class LocalChildJob(Contract):
    assignment: ImplementationAssignment
    config: AgentConfig
    cassette: AgentCassette

    @model_validator(mode="after")
    def fresh_read_only_brief(self) -> Self:
        a, c = self.assignment, self.config
        if (
            a.provider != "fixture"
            or (c.provider, c.model, c.effort) != (a.provider, a.model, a.effort)
            or c.max_iterations != 1
            or c.max_tool_calls != 0
            or c.initial_turns
            != (Turn(role="user", blocks=(TextBlock(text=a.objective),)),)
            or c.system != child_system(a)
            or len(self.cassette.exchanges) != 1
            or a.allowance.cost_microusd
            or a.allowance.attempts != 1
            or a.allowance.review_rounds
            or a.allowance.correction_cycles
            or a.worktree is not None
        ):
            raise ValueError("Local children require a fresh unpaid, tool-free brief.")
        return self


def child_system(assignment: ImplementationAssignment) -> str:
    return (
        "Analyze only this explicit creator-approved implementation brief. "
        "Return a proposed result for creator integration; execution and review "
        "approval are unavailable. Plan "
        + assignment.plan_sha256
        + "; tests "
        + assignment.tests_sha256
        + "."
    )


class LocalChildExecution(Contract):
    image_id: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    result: AgentResult
    events: Annotated[tuple[JournalEvent, ...], Field(max_length=4)]

    @model_validator(mode="after")
    def exact_journal(self) -> Self:
        if (
            tuple(e.sequence for e in self.events) != (0, 1)
            or tuple(e.type for e in self.events)
            != ("model.request.started", "model.response.completed")
            or len(self.result.responses) != 1
            or self.events[1].payload_sha256
            != digest(canonical_bytes(self.result.responses[0]))
        ):
            raise ValueError(
                "Child execution requires its exact request/response journal."
            )
        return self


class LocalChildExecutor(Protocol):
    @property
    def image_id(self) -> str: ...

    async def execute(self, job: LocalChildJob) -> LocalChildExecution: ...


class LocalChildRecord(Contract):
    coding: CodingRetention | None = Field(default=None, exclude_if=lambda v: v is None)
    child_id: Identifier
    authorization: LocalChildAuthorization
    assignment: ImplementationAssignment
    goal_definition_sha256: Digest
    request_sha256: Digest
    cassette_sha256: Digest
    image_id: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    reserved: ResourceLedger
    state: Literal["running", "completed", "cancelled", "uncertain"] = "running"
    execution_sha256: Digest | None = None
    report: ImplementationReport | None = None
    usage: ResourceLedger | None = None

    @model_validator(mode="after")
    def bound_result(self) -> Self:
        if (self.authorization.mode == "recorded_coding") != (self.coding is not None):
            raise ValueError("Coding records need their complete frozen workflow.")
        if self.coding is not None and (
            self.coding.brief.assignment != self.assignment
            or self.authorization.brief_sha256 != self.coding.brief.sha256
            or self.authorization.review_sha256
            != digest(canonical_bytes(self.coding.plan_review))
            or (self.state == "completed") != (self.coding.handoff is not None)
        ):
            raise ValueError(
                "Coding record differs from its assignment, approval or handoff."
            )
        if self.authorization.assignment_sha256 != self.assignment.sha256:
            raise ValueError("Child authorization differs from the frozen assignment.")
        if (
            self.reserved.attempts != 1
            or self.reserved.cost_microusd
            or self.reserved.uncertain_effects
            or any(
                getattr(self.reserved, field)
                > getattr(self.assignment.allowance, field)
                for field in type(self.assignment.allowance).model_fields
            )
        ):
            raise ValueError("Child reservations must fit the frozen unpaid allowance.")
        if (self.state == "completed") != (
            self.report is not None
            and self.execution_sha256 is not None
            and self.usage is not None
        ):
            raise ValueError("A completed child requires its exact committed result.")
        if self.report is not None and (
            self.report.scope != self.authorization.scope
            or self.report.child_id != self.child_id
            or self.report.assignment_sha256 != self.assignment.sha256
        ):
            raise ValueError("Child report crosses scope or assignment boundaries.")
        return self

    @property
    def report_sha256(self) -> str | None:
        return None if self.report is None else digest(canonical_bytes(self.report))
