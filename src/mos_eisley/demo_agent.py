"""Synthetic two-turn tool exchange bound to exact canonical requests."""

import json

from mos_eisley.core.agent import AgentConfig, build_request
from mos_eisley.core.budget import resolve_budget
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import (
    ModelResponse,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
    Turn,
    Usage,
)
from mos_eisley.core.registry import fixture_registry
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.tools.fixture import FixtureDispatcher, FixtureValues


def agent_demo_inputs() -> tuple[AgentConfig, FixtureValues, AgentCassette]:
    config = AgentConfig(
        provider="fixture",
        model="tool-reviewer-v1",
        effort="high",
        system="Use the supplied fixture tool once, then report the boundary.",
        initial_turns=(
            Turn(
                role="user",
                blocks=(
                    TextBlock(text="What quantity boundary does the fixture require?"),
                ),
            ),
        ),
    )
    fixtures = FixtureValues(values={"discount_boundary": ">= 10"})
    dispatcher = FixtureDispatcher(fixtures)
    registry = fixture_registry()
    resolved = registry.resolve(config.provider, config.model, config.effort)
    budget = resolve_budget(resolved.spec, resolved.effort, config.budget)

    request_one = build_request(
        config, resolved, budget, dispatcher, config.initial_turns
    )
    tool_turn = Turn(
        role="assistant",
        blocks=(
            ToolCallBlock(
                id="fixture-call-1",
                name="fixture_lookup",
                args={"key": "discount_boundary"},
                native_id="recorded-native-1",
            ),
        ),
    )
    response_one = ModelResponse(
        turn=tool_turn,
        stop_reason="tool_use",
        usage=Usage(
            input=len(canonical_bytes(request_one)),
            output=len(canonical_bytes(tool_turn)),
        ),
        provider_request_id="fixture-request-1",
    )
    tool_result = ToolResultBlock(
        call_id="fixture-call-1",
        name="fixture_lookup",
        content=json.dumps(
            {"key": "discount_boundary", "value": ">= 10"}, sort_keys=True
        ),
    )
    turns_two = config.initial_turns + (
        tool_turn,
        Turn(role="user", blocks=(tool_result,)),
    )
    request_two = build_request(config, resolved, budget, dispatcher, turns_two)
    final_turn = Turn(
        role="assistant",
        blocks=(TextBlock(text="The required quantity boundary is >= 10."),),
    )
    response_two = ModelResponse(
        turn=final_turn,
        stop_reason="end_turn",
        usage=Usage(
            input=len(canonical_bytes(request_two)),
            output=len(canonical_bytes(final_turn)),
        ),
        provider_request_id="fixture-request-2",
    )
    cassette = AgentCassette(
        exchanges=(
            AgentExchange(
                request_sha256=digest(canonical_bytes(request_one)),
                response=response_one,
            ),
            AgentExchange(
                request_sha256=digest(canonical_bytes(request_two)),
                response=response_two,
            ),
        )
    )
    return config, fixtures, cassette
