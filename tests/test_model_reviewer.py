"""Exercise the canonical review boundary without credentials or network calls."""

from __future__ import annotations

import asyncio
import json
import unittest
from collections.abc import Callable

from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import (
    Brief,
    Contract,
    CriticRequest,
    CriticSpec,
    Critique,
    Evidence,
    Finding,
    JudgeDecision,
    JudgeRequest,
    ReviewPolicy,
    canonical_bytes,
)
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
    Turn,
    Usage,
)
from mos_eisley.core.registry import ModelRegistry, ModelSpec
from mos_eisley.providers.model_reviewer import ModelReviewer
from mos_eisley.review.pipeline import review


def response(value: Contract | str) -> ModelResponse:
    text = canonical_bytes(value).decode() if isinstance(value, Contract) else value
    return ModelResponse(
        turn=Turn(role="assistant", blocks=(TextBlock(text=text),)),
        stop_reason="end_turn",
        usage=Usage(input=10, output=10),
    )


def input_text(request: ModelRequest) -> str:
    return "".join(
        block.text
        for turn in request.turns
        for block in turn.blocks
        if isinstance(block, TextBlock)
    )


class Client:
    def __init__(self, reply: Callable[[ModelRequest], ModelResponse]) -> None:
        self.reply: Callable[[ModelRequest], ModelResponse] = reply
        self.requests: list[ModelRequest] = []
        self.wait = False
        self.started = asyncio.Event()
        self.cancelled = False

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        self.started.set()
        if self.wait:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return self.reply(request)


class ModelReviewerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.brief = Brief(spec="Reject invalid input", diff="+ accept(input)")
        self.finding = Finding(
            location="input handler",
            category="correctness",
            impact="high",
            claim="Invalid input is accepted",
            evidence=Evidence(
                source="diff", quote="accept(input)", explanation="No validation"
            ),
        )
        self.critic = CriticSpec(
            id="private-critic-id", provider="alpha", model="model", persona="security"
        )
        self.request = CriticRequest(brief=self.brief, persona=self.critic.persona)
        self.registry = ModelRegistry(
            models=tuple(
                ModelSpec(
                    provider=provider,
                    id="model",
                    context_bytes=128_000,
                    max_output_bytes=16_000,
                    context_tokens=32_000,
                    max_output_tokens=4096,
                    efforts=("low", "medium"),
                    default_effort="medium",
                    tool_calling=False,
                    structured_output=False,
                    verification="fixture",
                )
                for provider in ("alpha", "beta", "judge")
            )
        )
        self.client = Client(lambda _: response(Critique()))
        self.reviewer = self.make_reviewer()

    def make_reviewer(self, budget: BudgetPolicy | None = None) -> ModelReviewer:
        return ModelReviewer(
            self.client,
            self.registry,
            judge_provider="judge",
            judge_model="model",
            budget=budget,
        )

    async def test_critic_isolated_request_and_exact_guidance(self) -> None:
        brief = self.brief.model_copy(update={"constraints": "Frozen project rubric"})
        request = CriticRequest(brief=brief, persona="security")
        self.assertEqual(await self.reviewer.critique(self.critic, request), Critique())
        sent = self.client.requests[0]
        self.assertEqual(json.loads(input_text(sent)), request.model_dump(mode="json"))
        self.assertEqual(
            (sent.provider, sent.model, sent.effort), ("alpha", "model", "medium")
        )
        self.assertEqual(sent.tools, ())
        self.assertEqual(len(sent.turns), 1)
        self.assertNotIn(self.critic.id, canonical_bytes(sent).decode())
        self.assertNotIn("Frozen project rubric", sent.system)
        self.assertEqual(sent.max_output_tokens, 4096)

    async def test_judge_receives_exact_ids_without_critic_metadata(self) -> None:
        decision = JudgeDecision(
            upheld=(self.finding.finding_id,), rationale="Supported"
        )
        self.client.reply = lambda _: response(decision)
        request = JudgeRequest(brief=self.brief, findings=(self.finding,))
        self.assertEqual(await self.reviewer.judge(request), decision)
        sent = self.client.requests[0]
        payload = json.loads(input_text(sent))
        self.assertEqual(
            payload["findings"],
            [
                {
                    "id": self.finding.finding_id,
                    "finding": self.finding.model_dump(mode="json"),
                }
            ],
        )
        self.assertEqual(payload["brief"], self.brief.model_dump(mode="json"))
        self.assertEqual(sent.provider, "judge")
        self.assertNotIn(self.critic.id, canonical_bytes(sent).decode())
        self.assertNotIn("persona", input_text(sent))

    async def test_unknown_model_and_persona_mismatch_do_not_dispatch(self) -> None:
        for critic in (
            self.critic.model_copy(update={"provider": "unknown"}),
            self.critic.model_copy(update={"persona": "different"}),
            self.critic.model_copy(update={"id": "invalid id"}),
        ):
            with self.subTest(critic=critic), self.assertRaises(ProviderError):
                await self.reviewer.critique(critic, self.request)
        self.assertEqual(self.client.requests, [])

    def test_unknown_judge_rejected_at_configuration(self) -> None:
        with self.assertRaises(ValueError):
            ModelReviewer(
                self.client,
                self.registry,
                judge_provider="unknown",
                judge_model="model",
            )

    async def test_effort_fallback_is_explicit_in_dispatched_request(self) -> None:
        reviewer = ModelReviewer(
            self.client,
            self.registry,
            judge_provider="judge",
            judge_model="model",
            effort="high",
        )
        await reviewer.critique(self.critic, self.request)
        self.assertEqual(self.client.requests[0].effort, "medium")

    async def test_complete_request_budget_includes_schema_and_unicode(self) -> None:
        reviewer = self.make_reviewer(BudgetPolicy(session_cap_bytes=9000))
        with self.assertRaises(ProviderError):
            await reviewer.critique(self.critic, self.request)
        self.assertEqual(self.client.requests, [])
        brief = self.brief.model_copy(update={"spec": "🌍" * 24_000})
        with self.assertRaises(ProviderError):
            await self.reviewer.critique(
                self.critic, CriticRequest(brief=brief, persona="security")
            )
        self.assertEqual(self.client.requests, [])

    async def test_long_json_input_survives_block_boundaries(self) -> None:
        brief = self.brief.model_copy(update={"spec": 'quote"🌍' * 3000})
        request = CriticRequest(brief=brief, persona="security")
        await self.reviewer.critique(self.critic, request)
        sent = self.client.requests[0]
        self.assertGreater(len(sent.turns[0].blocks), 1)
        self.assertEqual(input_text(sent).encode(), canonical_bytes(request))

    async def test_split_response_and_reasoning_are_not_mixed(self) -> None:
        raw = canonical_bytes(Critique()).decode()
        reply = response(Critique()).model_copy(
            update={
                "turn": Turn(
                    role="assistant",
                    blocks=(
                        ReasoningBlock(
                            provider="alpha",
                            visible="not JSON",
                            opaque={"data": "private"},
                        ),
                        TextBlock(text=raw[:10]),
                        TextBlock(text=raw[10:]),
                    ),
                )
            }
        )
        self.client.reply = lambda _: reply
        self.assertEqual(
            await self.reviewer.critique(self.critic, self.request), Critique()
        )

    async def test_malformed_missing_extra_and_duplicate_json_rejected(self) -> None:
        for raw in (
            "{}",
            "[]",
            "null",
            "not JSON",
            '```json\n{"schema_version":1,"findings":[]}\n```',
            '{"schema_version":1,"findings":[]} trailing',
            '{"schema_version":1,"findings":[],"extra":true}',
            '{"schema_version":1,"findings":[],"findings":[]}',
            '{"schema_version":true,"findings":[]}',
            '{"schema_version":1.0,"findings":[]}',
            '{"schema_version":1,"findings":null}',
            '{"schema_version":1,"findings":[{"evidence":{"quote":"a","quote":"b"}}]}',
        ):
            with self.subTest(raw=raw), self.assertRaises(ProviderError):
                self.client.reply = lambda _, raw=raw: response(raw)
                await self.reviewer.critique(self.critic, self.request)

    async def test_judge_cannot_omit_upheld_or_version(self) -> None:
        for raw in ('{"rationale":"fine"}', '{"upheld":[],"rationale":"fine"}'):
            self.client.reply = lambda _, raw=raw: response(raw)
            with self.assertRaises(ProviderError):
                await self.reviewer.judge(JudgeRequest(brief=self.brief, findings=()))

    def test_retained_decoders_normalize_excessive_json_nesting(self) -> None:
        registry = self.registry.model_copy(
            update={
                "models": tuple(
                    spec.model_copy(update={"max_output_bytes": 32_000})
                    for spec in self.registry.models
                )
            }
        )
        reviewer = ModelReviewer(
            self.client,
            registry,
            judge_provider="judge",
            judge_model="model",
            budget=BudgetPolicy(reserve_medium_bytes=32_000),
        )
        raw = "[" * 10_000 + "]" * 10_000
        reply = ModelResponse(
            turn=Turn(
                role="assistant",
                blocks=tuple(
                    TextBlock(text=raw[offset : offset + 8000])
                    for offset in range(0, len(raw), 8000)
                ),
            ),
            stop_reason="end_turn",
            usage=Usage(input=10, output=10),
        )
        with self.assertRaisesRegex(ValueError, "decoder nesting limit"):
            reviewer.parse_critique(self.critic, self.request, reply)
        with self.assertRaisesRegex(ValueError, "decoder nesting limit"):
            reviewer.parse_judge(JudgeRequest(brief=self.brief, findings=()), reply)
        self.assertEqual(self.client.requests, [])

    async def test_reasoning_only_is_not_an_answer(self) -> None:
        self.client.reply = lambda _: response(Critique()).model_copy(
            update={
                "turn": Turn(
                    role="assistant",
                    blocks=(ReasoningBlock(provider="alpha", opaque={}),),
                )
            }
        )
        with self.assertRaises(ProviderError):
            await self.reviewer.critique(self.critic, self.request)

    async def test_noncompletion_and_tool_calls_rejected_without_retry(self) -> None:
        for stop in ("max_output", "filtered", "error"):
            self.client.reply = lambda _, stop=stop: response(Critique()).model_copy(
                update={"stop_reason": stop}
            )
            with self.assertRaises(ProviderError):
                await self.reviewer.critique(self.critic, self.request)
        self.client.reply = lambda _: ModelResponse(
            turn=Turn(
                role="assistant",
                blocks=(ToolCallBlock(id="call", name="write", args={}),),
            ),
            stop_reason="tool_use",
            usage=Usage(input=0, output=0),
        )
        with self.assertRaises(ProviderError):
            await self.reviewer.critique(self.critic, self.request)
        self.assertEqual(len(self.client.requests), 4)

    async def test_whole_response_budget_includes_opaque_reasoning(self) -> None:
        self.client.reply = lambda _: response(Critique()).model_copy(
            update={
                "turn": Turn(
                    role="assistant",
                    blocks=(
                        ReasoningBlock(
                            provider="alpha", opaque={"payload": "x" * 8000}
                        ),
                        TextBlock(text=canonical_bytes(Critique()).decode()),
                    ),
                )
            }
        )
        with self.assertRaises(ProviderError):
            await self.reviewer.critique(self.critic, self.request)

    async def test_usage_ceilings_and_tampered_response_revalidated(self) -> None:
        for usage in (
            Usage(input=100_000, output=0),
            Usage(input=0, output=8001),
            Usage(unit="tokens", input=0, output=4097),
            Usage(unit="tokens", input=32_000, output=1),
            Usage(input=0, output=0).model_copy(update={"output": -1}),
        ):
            self.client.reply = lambda _, usage=usage: response(Critique()).model_copy(
                update={"usage": usage}
            )
            with self.subTest(usage=usage), self.assertRaises(ProviderError):
                await self.reviewer.critique(self.critic, self.request)

    async def test_provider_errors_are_coarse_and_never_retried(self) -> None:
        def fail(_: ModelRequest) -> ModelResponse:
            raise RuntimeError("SECRET provider body")

        self.client.reply = fail
        with self.assertRaises(ProviderError) as caught:
            await self.reviewer.critique(self.critic, self.request)
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertEqual(len(self.client.requests), 1)

    async def test_cancel_propagates_to_client(self) -> None:
        self.client.wait = True
        task = asyncio.create_task(self.reviewer.critique(self.critic, self.request))
        await self.client.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.client.cancelled)
        self.assertEqual(len(self.client.requests), 1)

    def roster(self) -> tuple[CriticSpec, ...]:
        return (
            self.critic,
            self.critic.model_copy(update={"id": "second", "provider": "beta"}),
        )

    async def test_pipeline_fanout_and_identity_free_adjudication(self) -> None:
        self.client.reply = lambda request: response(
            JudgeDecision(upheld=(self.finding.finding_id,), rationale="Supported")
            if request.provider == "judge"
            else Critique(findings=(self.finding,))
        )
        result = await review(self.brief, self.roster(), self.reviewer, ReviewPolicy())
        self.assertEqual(result.verdict.decision, "revise")
        self.assertEqual(len(result.verdict.findings), 1)
        self.assertEqual(len(self.client.requests), 3)
        self.assertEqual(self.client.requests[-1].provider, "judge")

    async def test_invalid_evidence_prevents_judge_dispatch(self) -> None:
        finding = self.finding.model_copy(
            update={
                "evidence": Evidence(source="spec", quote="invented", explanation="bad")
            }
        )
        self.client.reply = lambda _: response(Critique(findings=(finding,)))
        result = await review(self.brief, self.roster(), self.reviewer, ReviewPolicy())
        self.assertEqual(result.verdict.decision, "infrastructure_error")
        self.assertEqual([r.error for r in result.critics], ["invalid_evidence"] * 2)
        self.assertEqual(len(self.client.requests), 2)

    async def test_malformed_critic_cannot_satisfy_quorum(self) -> None:
        self.client.reply = lambda request: response(
            "{}" if request.provider == "alpha" else Critique()
        )
        result = await review(self.brief, self.roster(), self.reviewer, ReviewPolicy())
        self.assertEqual(result.verdict.decision, "infrastructure_error")
        self.assertEqual(len(self.client.requests), 2)

    async def test_duplicate_or_unknown_judge_ids_cannot_accept(self) -> None:
        for upheld in (("0" * 64,), (self.finding.finding_id,) * 2):
            self.client.reply = lambda request, upheld=upheld: response(
                JudgeDecision(upheld=upheld, rationale="bad")
                if request.provider == "judge"
                else Critique(findings=(self.finding,))
            )
            result = await review(
                self.brief, self.roster(), self.reviewer, ReviewPolicy()
            )
            self.assertEqual(result.verdict.decision, "infrastructure_error")

    async def test_malformed_judge_cannot_accept(self) -> None:
        self.client.reply = lambda request: response(
            "{}" if request.provider == "judge" else Critique()
        )
        result = await review(self.brief, self.roster(), self.reviewer, ReviewPolicy())
        self.assertEqual(result.verdict.decision, "infrastructure_error")
        self.assertEqual(len(self.client.requests), 3)
        self.assertIsNone(result.judge_decision)

    async def test_timeout_cancels_critics_and_does_not_dispatch_judge(self) -> None:
        self.client.wait = True
        result = await review(
            self.brief, self.roster(), self.reviewer, ReviewPolicy(timeout_seconds=0.01)
        )
        self.assertEqual(result.verdict.decision, "infrastructure_error")
        self.assertEqual([r.error for r in result.critics], ["timeout"] * 2)
        self.assertEqual(len(self.client.requests), 2)
        self.assertTrue(self.client.cancelled)


if __name__ == "__main__":
    unittest.main()
