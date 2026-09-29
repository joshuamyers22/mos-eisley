"""Conservative byte budgets used before provider token accounting exists."""

from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.core.models import Contract
from mos_eisley.core.protocol import Effort
from mos_eisley.core.registry import ModelSpec


class BudgetPolicy(Contract):
    schema_version: Literal[1] = 1
    session_cap_bytes: Annotated[int, Field(gt=0)] = 96_000
    headroom_pct: Annotated[float, Field(ge=0, lt=0.5)] = 0.05
    reserve_low_bytes: Annotated[int, Field(gt=0)] = 4_000
    reserve_medium_bytes: Annotated[int, Field(gt=0)] = 8_000
    reserve_high_bytes: Annotated[int, Field(gt=0)] = 12_000
    response_envelope_bytes: Annotated[
        int,
        Field(
            gt=0,
            le=16_000_000,
        ),
    ] = 64_000
    max_output_tokens: Annotated[int, Field(gt=0)] = 4_096

    def reserve_for(self, effort: Effort) -> int:
        if effort in {"none", "minimal", "low"}:
            return self.reserve_low_bytes
        if effort == "medium":
            return self.reserve_medium_bytes
        return self.reserve_high_bytes


class Budget(Contract):
    unit: Literal["bytes"] = "bytes"
    cap: int
    output_reserve: int
    usable_input: int
    headroom: int
    max_output_tokens: int | None = None


def resolve_response_envelope(
    model: ModelSpec, policy: BudgetPolicy, output_reserve: int
) -> int:
    """Bound the whole canonical response separately from visible output text."""
    envelope = min(model.max_output_bytes, policy.response_envelope_bytes)
    if envelope < output_reserve:
        raise ValueError("response envelope must cover the output reserve")
    return envelope


def resolve_budget(
    model: ModelSpec,
    effort: Effort,
    policy: BudgetPolicy,
    *,
    output_reserve_bytes: int | None = None,
) -> Budget:
    cap = min(model.context_bytes, policy.session_cap_bytes)
    requested_reserve = (
        policy.reserve_for(effort)
        if output_reserve_bytes is None
        else output_reserve_bytes
    )
    if type(requested_reserve) is not int or requested_reserve <= 0:
        raise ValueError("output reserve must be a positive integer")
    reserve = min(model.max_output_bytes, requested_reserve)
    if reserve >= cap:
        raise ValueError("output reserve must be below the context cap")
    before_headroom = cap - reserve
    usable = int(before_headroom * (1 - policy.headroom_pct))
    if usable <= 0:
        raise ValueError("resolved input budget must be positive")
    return Budget(
        cap=cap,
        output_reserve=reserve,
        usable_input=usable,
        headroom=before_headroom - usable,
        max_output_tokens=(
            min(model.max_output_tokens, policy.max_output_tokens)
            if model.max_output_tokens is not None
            else None
        ),
    )
