"""Provider-neutral agent loop with bounded context and explicit tool dispatch."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.budget import Budget, BudgetPolicy, resolve_budget
from mos_eisley.core.models import Contract, Identifier, canonical_bytes, digest
from mos_eisley.core.ports import Journal, ModelClient, ProviderError, ToolDispatcher
from mos_eisley.core.protocol import (
    Effort,
    JournalEvent,
    ModelRequest,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
    Turn,
    validate_turn_sequence,
)
from mos_eisley.core.registry import ModelRegistry, ResolvedModel


class AgentFailure(Exception):
    """The loop could not produce a valid completed turn."""


class AgentConfig(Contract):
    schema_version: Literal[1] = 1
    provider: Identifier
    model: Identifier
    effort: Effort | None = None
    system: Annotated[str, Field(max_length=64_000)] = ""
    initial_turns: Annotated[tuple[Turn, ...], Field(min_length=1, max_length=32)]
    max_iterations: Annotated[int, Field(ge=1, le=32)] = 8
    max_tool_calls: Annotated[int, Field(ge=0, le=128)] = 32
    request_timeout_seconds: Annotated[float, Field(gt=0, le=300)] = 30.0
    tool_timeout_seconds: Annotated[float, Field(gt=0, le=300)] = 5.0
    budget: BudgetPolicy = BudgetPolicy()

    @model_validator(mode="after")
    def valid_initial_turns(self) -> Self:
        validate_turn_sequence(self.initial_turns)
        return self


class AgentUsage(Contract):
    unit: Literal["bytes"] = "bytes"
    requests: Annotated[int, Field(ge=0)]
    tools: Annotated[int, Field(ge=0)]
    billed_input: Annotated[int, Field(ge=0)]
    billed_output: Annotated[int, Field(ge=0)]
    largest_request: Annotated[int, Field(ge=0)]


class AgentResult(Contract):
    schema_version: Literal[1] = 1
    resolved_model: ResolvedModel
    budget: Budget
    turns: tuple[Turn, ...]
    final_text: str
    usage: AgentUsage


def build_request(
    config: AgentConfig,
    resolved: ResolvedModel,
    budget: Budget,
    dispatcher: ToolDispatcher,
    turns: tuple[Turn, ...],
) -> ModelRequest:
    return ModelRequest(
        provider=resolved.spec.provider,
        model=resolved.spec.id,
        effort=resolved.effort,
        system=config.system,
        tools=dispatcher.definitions,
        turns=turns,
        max_output=budget.output_reserve,
    )


async def run_agent(
    config: AgentConfig,
    registry: ModelRegistry,
    client: ModelClient,
    dispatcher: ToolDispatcher,
    journal: Journal | None = None,
) -> AgentResult:
    resolved = registry.resolve(config.provider, config.model, config.effort)
    if dispatcher.definitions and not resolved.spec.tool_calling:
        raise AgentFailure("selected model does not support tools")
    budget = resolve_budget(resolved.spec, resolved.effort, config.budget)
    turns = config.initial_turns
    used_call_ids = {
        block.id
        for turn in turns
        for block in turn.blocks
        if isinstance(block, ToolCallBlock)
    }
    billed_input = 0
    billed_output = 0
    largest_request = 0
    tool_count = 0
    sequence = 0

    def record(
        event_type: Literal[
            "model.request.started",
            "model.response.completed",
            "model.request.failed",
            "tool.completed",
            "tool.failed",
        ],
        request_id: str,
        payload: Contract,
        detail: str = "",
    ) -> None:
        nonlocal sequence
        if journal is not None:
            journal.record(
                JournalEvent(
                    type=event_type,
                    request_id=request_id,
                    sequence=sequence,
                    payload_sha256=digest(canonical_bytes(payload)),
                    detail=detail,
                )
            )
        sequence += 1

    for iteration in range(1, config.max_iterations + 1):
        request = build_request(config, resolved, budget, dispatcher, turns)
        request_size = len(canonical_bytes(request))
        if request_size > budget.usable_input:
            raise AgentFailure("model request exceeds usable input budget")
        largest_request = max(largest_request, request_size)
        request_id = f"model-{iteration:04d}"
        record("model.request.started", request_id, request)
        try:
            async with asyncio.timeout(config.request_timeout_seconds):
                response = await client.complete(request)
        except TimeoutError as error:
            record("model.request.failed", request_id, request, "timeout")
            raise AgentFailure("provider request timed out") from error
        except ProviderError as error:
            record("model.request.failed", request_id, request, "provider_error")
            raise AgentFailure("provider request failed") from error
        except Exception as error:
            record("model.request.failed", request_id, request, "client_exception")
            raise AgentFailure("model client failed unexpectedly") from error
        record("model.response.completed", request_id, response)
        response_size = len(canonical_bytes(response.turn))
        if response_size > budget.output_reserve:
            raise AgentFailure("model response exceeds output reserve")
        if response.usage.input > budget.usable_input:
            raise AgentFailure("provider reported input usage above budget")
        if response.usage.output > budget.output_reserve:
            raise AgentFailure("provider reported output usage above budget")
        billed_input += response.usage.input
        billed_output += response.usage.output
        turns += (response.turn,)
        if response.stop_reason == "end_turn":
            text = "\n".join(
                block.text
                for block in response.turn.blocks
                if isinstance(block, TextBlock)
            )
            if not text:
                raise AgentFailure("completed response contains no text")
            return AgentResult(
                resolved_model=resolved,
                budget=budget,
                turns=turns,
                final_text=text,
                usage=AgentUsage(
                    requests=iteration,
                    tools=tool_count,
                    billed_input=billed_input,
                    billed_output=billed_output,
                    largest_request=largest_request,
                ),
            )
        if response.stop_reason != "tool_use":
            raise AgentFailure(
                f"model stopped without completing: {response.stop_reason}"
            )
        calls = tuple(
            block for block in response.turn.blocks if isinstance(block, ToolCallBlock)
        )
        if any(call.id in used_call_ids for call in calls):
            raise AgentFailure("tool call ID was reused across responses")
        if tool_count + len(calls) > config.max_tool_calls:
            raise AgentFailure("agent tool-call limit reached")
        results: list[ToolResultBlock] = []
        for call in calls:
            used_call_ids.add(call.id)
            try:
                async with asyncio.timeout(config.tool_timeout_seconds):
                    result = await dispatcher.dispatch(call)
            except TimeoutError as error:
                record("tool.failed", call.id, call, "timeout")
                raise AgentFailure("tool call timed out") from error
            except Exception as error:
                record("tool.failed", call.id, call, "dispatcher_exception")
                raise AgentFailure("tool dispatcher failed unexpectedly") from error
            if result.call_id != call.id or result.name != call.name:
                record("tool.failed", call.id, result, "result_mismatch")
                raise AgentFailure("tool result does not match its call")
            if len(canonical_bytes(result)) > budget.output_reserve:
                record("tool.failed", call.id, result, "output_budget")
                raise AgentFailure("tool result exceeds output reserve")
            tool_count += 1
            record(
                "tool.completed", call.id, result, "error" if result.is_error else ""
            )
            results.append(result)
        turns += (Turn(role="user", blocks=tuple(results)),)
    raise AgentFailure("agent iteration limit reached")
