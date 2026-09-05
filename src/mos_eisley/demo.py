"""Synthetic fixture demonstrating plumbing, not model review quality."""

from mos_eisley.core.models import (
    Brief,
    CriticRequest,
    CriticSpec,
    Critique,
    Evidence,
    Finding,
    JudgeDecision,
    JudgeRequest,
    canonical_bytes,
    digest,
)
from mos_eisley.providers.recorded import Cassette, CriticRecording


def demo_inputs() -> tuple[Brief, Cassette]:
    brief = Brief(
        spec="The discount must be applied when quantity is at least 10.",
        diff=(
            "--- a/pricing.py\n+++ b/pricing.py\n@@ -1 +1 @@\n"
            "-if quantity >= 10:\n+if quantity > 10:\n"
        ),
        constraints="Review correctness. Do not execute code.",
    )
    finding = Finding(
        location="pricing.py:1",
        category="correctness",
        impact="high",
        claim="Quantity 10 no longer receives the required discount.",
        evidence=Evidence(
            source="diff",
            quote="+if quantity > 10:",
            explanation="The strict inequality excludes the required boundary.",
        ),
        suggested_fix="Restore quantity >= 10.",
    )
    critics = tuple(
        CriticSpec(
            id=f"critic-{i}",
            provider=f"fixture-{i}",
            model=f"fixture-model-{i}",
            persona=persona,
        )
        for i, persona in enumerate(
            ("Check correctness.", "Check specification compliance."), start=1
        )
    )
    recordings = tuple(
        CriticRecording(
            critic=critic,
            request_sha256=digest(
                canonical_bytes(CriticRequest(brief=brief, persona=critic.persona))
            ),
            response=Critique(findings=(finding,)),
        )
        for critic in critics
    )
    judge_request = JudgeRequest(brief=brief, findings=(finding,))
    return brief, Cassette(
        brief_id=brief.brief_id,
        critics=recordings,
        judge_request_sha256=digest(canonical_bytes(judge_request)),
        judge_response=JudgeDecision(
            upheld=(finding.finding_id,),
            rationale="The cited boundary change contradicts the specification.",
        ),
    )
