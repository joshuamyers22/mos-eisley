"""Observable safety and review-policy behavior without network access."""

import asyncio
from unittest import IsolatedAsyncioTestCase, TestCase

from pydantic import ValidationError

from mos_eisley.core.models import (
    Brief,
    CriticRequest,
    CriticResult,
    CriticSpec,
    Critique,
    JudgeDecision,
    JudgeRequest,
    ReviewPolicy,
    canonical_bytes,
)
from mos_eisley.core.ports import ProviderError
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.recorded import RecordedReviewer
from mos_eisley.review.pipeline import adjudicate, review, validate_roster


class PipelineTests(IsolatedAsyncioTestCase):
    async def test_dedupe_preserves_originals_and_replay_is_deterministic(self) -> None:
        brief, cassette = demo_inputs()
        roster = tuple(r.critic for r in cassette.critics)
        first = await review(brief, roster, RecordedReviewer(cassette), ReviewPolicy())
        second = await review(brief, roster, RecordedReviewer(cassette), ReviewPolicy())
        self.assertEqual(first, second)
        self.assertEqual(first.verdict.decision, "revise")
        self.assertEqual(len(first.verdict.findings), 1)
        self.assertEqual(len(first.critics), 2)
        self.assertEqual(len(first.verdict.required_changes), 1)

    async def test_missing_critic_cannot_accept(self) -> None:
        brief, cassette = demo_inputs()
        broken = cassette.model_copy(
            update={
                "critics": (
                    cassette.critics[0].model_copy(update={"response": None}),
                    cassette.critics[1],
                )
            }
        )
        result = await review(
            brief,
            tuple(r.critic for r in broken.critics),
            RecordedReviewer(broken),
            ReviewPolicy(),
        )
        self.assertEqual(result.verdict.decision, "infrastructure_error")
        self.assertIsNone(result.judge_request)

    async def test_request_mismatch_fails_closed(self) -> None:
        brief, cassette = demo_inputs()
        result = await review(
            brief.model_copy(update={"spec": "Different specification"}),
            tuple(r.critic for r in cassette.critics),
            RecordedReviewer(cassette),
            ReviewPolicy(),
        )
        self.assertEqual(result.verdict.decision, "infrastructure_error")

    async def test_unknown_judge_id_cannot_accept(self) -> None:
        brief, cassette = demo_inputs()
        broken = cassette.model_copy(
            update={
                "judge_response": JudgeDecision(upheld=("0" * 64,), rationale="Unknown")
            }
        )
        result = await review(
            brief,
            tuple(r.critic for r in broken.critics),
            RecordedReviewer(broken),
            ReviewPolicy(),
        )
        self.assertEqual(result.verdict.decision, "infrastructure_error")

    async def test_missing_judge_fails_closed(self) -> None:
        brief, cassette = demo_inputs()
        broken = cassette.model_copy(update={"judge_response": None})
        result = await review(
            brief,
            tuple(r.critic for r in broken.critics),
            RecordedReviewer(broken),
            ReviewPolicy(),
        )
        self.assertEqual(result.verdict.decision, "infrastructure_error")

    async def test_fabricated_citation_is_rejected(self) -> None:
        brief, cassette = demo_inputs()
        original = cassette.critics[0].response
        assert original is not None
        finding = original.findings[0]
        invalid = finding.model_copy(
            update={
                "evidence": finding.evidence.model_copy(
                    update={"quote": "not in source"}
                )
            }
        )
        broken = cassette.model_copy(
            update={
                "critics": (
                    cassette.critics[0].model_copy(
                        update={"response": Critique(findings=(invalid,))}
                    ),
                    cassette.critics[1],
                )
            }
        )
        result = await review(
            brief,
            tuple(r.critic for r in broken.critics),
            RecordedReviewer(broken),
            ReviewPolicy(),
        )
        self.assertEqual(result.critics[0].error, "invalid_evidence")
        self.assertEqual(result.verdict.decision, "infrastructure_error")

    async def test_budget_exhaustion_prevents_dispatch(self) -> None:
        brief, cassette = demo_inputs()
        brief = brief.model_copy(update={"spec": "x" * 2000})
        result = await review(
            brief,
            tuple(r.critic for r in cassette.critics),
            RecordedReviewer(cassette),
            ReviewPolicy(max_request_bytes=1024),
        )
        self.assertTrue(all(r.error == "budget_exceeded" for r in result.critics))

    async def test_critic_timeout_and_cancellation(self) -> None:
        brief, cassette = demo_inputs()
        roster = tuple(r.critic for r in cassette.critics)
        cancelled: list[str] = []

        class SlowReviewer:
            async def critique(
                self, critic: CriticSpec, request: CriticRequest
            ) -> Critique:
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.append(critic.id)
                return Critique()

            async def judge(self, request: JudgeRequest) -> JudgeDecision:
                raise AssertionError("judge must not run")

        result = await review(
            brief, roster, SlowReviewer(), ReviewPolicy(timeout_seconds=0.01)
        )
        self.assertTrue(all(r.error == "timeout" for r in result.critics))
        self.assertEqual(set(cancelled), {r.id for r in roster})
        task = asyncio.create_task(
            review(brief, roster, SlowReviewer(), ReviewPolicy())
        )
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_concurrent_critics_receive_only_brief_and_persona(self) -> None:
        brief, cassette = demo_inputs()
        roster = tuple(r.critic for r in cassette.critics)
        requests: list[CriticRequest] = []
        ready = asyncio.Event()

        class Inspector:
            async def critique(
                self, critic: CriticSpec, request: CriticRequest
            ) -> Critique:
                requests.append(request)
                if len(requests) == 2:
                    ready.set()
                await ready.wait()
                return Critique()

            async def judge(self, request: JudgeRequest) -> JudgeDecision:
                if request.findings:
                    raise AssertionError("unexpected findings")
                return JudgeDecision(rationale="No findings in fixture.")

        result = await review(brief, roster, Inspector(), ReviewPolicy())
        self.assertEqual(result.verdict.decision, "accept")
        for request in requests:
            self.assertEqual(
                set(request.model_dump()), {"schema_version", "brief", "persona"}
            )
            for critic in roster:
                self.assertNotIn(critic.model, canonical_bytes(request).decode())

    async def test_recording_requires_exact_persona_and_judge_request(self) -> None:
        brief, cassette = demo_inputs()
        provider = RecordedReviewer(cassette)
        critic = cassette.critics[0].critic
        with self.assertRaises(ProviderError):
            await provider.critique(
                critic, CriticRequest(brief=brief, persona="changed")
            )
        with self.assertRaises(ProviderError):
            await provider.critique(
                critic.model_copy(update={"id": "unknown"}),
                CriticRequest(brief=brief, persona=critic.persona),
            )
        with self.assertRaises(ProviderError):
            await provider.judge(JudgeRequest(brief=brief, findings=()))


class PolicyTests(TestCase):
    def test_impact_is_separate_from_category(self) -> None:
        brief, cassette = demo_inputs()
        critique = cassette.critics[0].response
        assert critique is not None
        finding = critique.findings[0]
        preference = finding.model_copy(
            update={"category": "preference", "impact": "blocker"}
        )
        self.assertEqual(adjudicate(brief, (preference,), "Style").decision, "accept")
        blocker = finding.model_copy(update={"impact": "blocker"})
        self.assertEqual(adjudicate(brief, (blocker,), "Bug").decision, "reject")

    def test_schema_rejects_unknown_fields_wrong_types_and_versions(self) -> None:
        for payload in (
            '{"spec":"a","diff":"b","shell":"rm"}',
            '{"spec":1,"diff":"b"}',
            '{"schema_version":2,"spec":"a","diff":"b"}',
        ):
            with self.assertRaises(ValidationError):
                Brief.model_validate_json(payload)
        with self.assertRaises(ValidationError):
            ReviewPolicy(min_critics=1, min_providers=2)

    def test_status_and_roster_invariants(self) -> None:
        _, cassette = demo_inputs()
        critic = cassette.critics[0].critic
        with self.assertRaises(ValidationError):
            CriticResult(critic=critic, status="completed")
        with self.assertRaises(ValidationError):
            CriticResult(critic=critic, status="error")
        for roster in (
            (),
            (critic, critic),
            (critic, critic.model_copy(update={"id": "other"})),
        ):
            with self.assertRaises(ValueError):
                validate_roster(roster, ReviewPolicy())

    def test_hash_tracks_content_and_ignores_json_whitespace(self) -> None:
        brief, _ = demo_inputs()
        parsed = Brief.model_validate_json(brief.model_dump_json(indent=2))
        self.assertEqual(brief.brief_id, parsed.brief_id)
        self.assertNotEqual(
            brief.brief_id, brief.model_copy(update={"constraints": "new"}).brief_id
        )
