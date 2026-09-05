"""Explicit model capabilities and canonical effort resolution."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Identifier
from mos_eisley.core.protocol import Effort

EFFORT_LADDER: tuple[Effort, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


class ModelSpec(Contract):
    provider: Identifier
    id: Identifier
    context_bytes: Annotated[int, Field(gt=0)]
    max_output_bytes: Annotated[int, Field(gt=0)]
    efforts: Annotated[tuple[Effort, ...], Field(min_length=1)]
    default_effort: Effort
    tool_calling: bool
    structured_output: bool
    verification: Literal["fixture", "live_conformance"]

    @model_validator(mode="after")
    def valid_capabilities(self) -> Self:
        if len(self.efforts) != len(set(self.efforts)):
            raise ValueError("model effort levels must be unique")
        if self.default_effort not in self.efforts:
            raise ValueError("default effort must be supported")
        if self.max_output_bytes >= self.context_bytes:
            raise ValueError("model output limit must be below context limit")
        return self


class ResolvedModel(Contract):
    spec: ModelSpec
    effort: Effort
    substituted: bool


class ModelRegistry(Contract):
    schema_version: Literal[1] = 1
    models: Annotated[tuple[ModelSpec, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_models(self) -> Self:
        keys = tuple((model.provider, model.id) for model in self.models)
        if len(keys) != len(set(keys)):
            raise ValueError("provider/model pairs must be unique")
        return self

    def resolve(
        self, provider: str, model_id: str, requested: Effort | None
    ) -> ResolvedModel:
        try:
            spec = next(
                model
                for model in self.models
                if model.provider == provider and model.id == model_id
            )
        except StopIteration as error:
            raise ValueError(f"unknown model: {provider}/{model_id}") from error
        target = requested or spec.default_effort
        if target in spec.efforts:
            return ResolvedModel(spec=spec, effort=target, substituted=False)
        target_index = EFFORT_LADDER.index(target)
        for effort in reversed(EFFORT_LADDER[:target_index]):
            if effort in spec.efforts:
                return ResolvedModel(spec=spec, effort=effort, substituted=True)
        raise ValueError(f"unsupported effort: {target}")


def fixture_registry() -> ModelRegistry:
    return ModelRegistry(
        models=(
            ModelSpec(
                provider="fixture",
                id="tool-reviewer-v1",
                context_bytes=128_000,
                max_output_bytes=16_000,
                efforts=("low", "medium", "high"),
                default_effort="medium",
                tool_calling=True,
                structured_output=True,
                verification="fixture",
            ),
        )
    )
