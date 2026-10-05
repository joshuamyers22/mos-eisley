"""Bounded separate semantic evaluation; mechanical checks remain authoritative."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.conversation_goal import DurableGoal, GoalEvidence
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest


class GoalEvaluationInput(Contract):
    definition_sha256: Digest
    evidence_sha256: Digest
    criteria: Annotated[tuple[str, ...], Field(min_length=1, max_length=16)]
    evidence: GoalEvidence


class GoalSemanticVerdict(Contract):
    definition_sha256: Digest
    evidence_sha256: Digest
    decision: Literal["passed", "failed", "blocked"]
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


GoalEvaluator = Callable[[GoalEvaluationInput], Awaitable[GoalSemanticVerdict]]


def evaluation_input(goal: DurableGoal, evidence: GoalEvidence) -> GoalEvaluationInput:
    return GoalEvaluationInput(
        definition_sha256=goal.definition.sha256,
        evidence_sha256=digest(canonical_bytes(evidence)),
        criteria=goal.definition.success_criteria,
        evidence=evidence,
    )


async def run_goal_evaluation(
    evaluator: GoalEvaluator,
    request: GoalEvaluationInput,
    *,
    timeout: float = 2.0,
    observe_task: Callable[[asyncio.Future[GoalSemanticVerdict]], None] | None = None,
) -> GoalSemanticVerdict:
    task = asyncio.ensure_future(evaluator(request))
    if observe_task is not None:
        observe_task(task)

    def consume(done: asyncio.Future[GoalSemanticVerdict]) -> None:
        if not done.cancelled():
            done.exception()

    task.add_done_callback(consume)
    try:
        done, _pending = await asyncio.wait((task,), timeout=timeout)
        if not done:
            task.cancel()
            raise TimeoutError("Goal semantic evaluation deadline exceeded.")
        result = task.result()
    except asyncio.CancelledError:
        task.cancel()
        raise
    result = GoalSemanticVerdict.model_validate(result.model_dump(mode="python"))
    if (
        result.definition_sha256 != request.definition_sha256
        or result.evidence_sha256 != request.evidence_sha256
    ):
        raise ValueError("Semantic evaluation belongs to another revision or evidence.")
    return result
