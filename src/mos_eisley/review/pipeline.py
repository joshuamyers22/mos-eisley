"""Bounded review fan-out with deterministic, identity-free adjudication."""

import asyncio

from mos_eisley.core.models import (
    Brief,
    CriticRequest,
    CriticResult,
    CriticSpec,
    Finding,
    JudgeRequest,
    ReviewPolicy,
    ReviewResult,
    Verdict,
    canonical_bytes,
)
from mos_eisley.core.ports import ProviderError, Reviewer


def validate_roster(roster: tuple[CriticSpec, ...], policy: ReviewPolicy) -> None:
    if not policy.min_critics <= len(roster) <= 8:
        raise ValueError("roster must satisfy quorum and contain at most 8 critics")
    if len({critic.id for critic in roster}) != len(roster):
        raise ValueError("critic IDs must be unique")
    if len({critic.provider for critic in roster}) < policy.min_providers:
        raise ValueError("roster cannot satisfy provider quorum")


def validate_evidence(brief: Brief, findings: tuple[Finding, ...]) -> None:
    for finding in findings:
        source: str = getattr(brief, finding.evidence.source)
        if finding.evidence.quote not in source:
            raise ValueError("citation does not occur in its declared brief source")


def adjudicate(brief: Brief, findings: tuple[Finding, ...], rationale: str) -> Verdict:
    blocking = tuple(
        finding
        for finding in findings
        if finding.category != "preference"
        and finding.impact in {"blocker", "high", "medium"}
    )
    decision = "accept"
    if blocking:
        decision = (
            "reject" if any(f.impact == "blocker" for f in blocking) else "revise"
        )
    return Verdict(
        brief_id=brief.brief_id,
        decision=decision,
        findings=findings,
        required_changes=tuple(f.finding_id for f in blocking),
        rationale=rationale,
    )


async def review(
    brief: Brief,
    roster: tuple[CriticSpec, ...],
    provider: Reviewer,
    policy: ReviewPolicy,
) -> ReviewResult:
    validate_roster(roster, policy)

    async def run_critic(critic: CriticSpec) -> CriticResult:
        request = CriticRequest(brief=brief, persona=critic.persona)
        if len(canonical_bytes(request)) > policy.max_request_bytes:
            return CriticResult(critic=critic, status="error", error="budget_exceeded")
        try:
            async with asyncio.timeout(policy.timeout_seconds):
                critique = await provider.critique(critic, request)
        except TimeoutError:
            return CriticResult(critic=critic, status="error", error="timeout")
        except ProviderError:
            return CriticResult(critic=critic, status="error", error="provider_error")
        try:
            validate_evidence(brief, critique.findings)
        except ValueError:
            return CriticResult(critic=critic, status="error", error="invalid_evidence")
        return CriticResult(critic=critic, status="completed", critique=critique)

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(run_critic(critic)) for critic in roster]
    results = tuple(task.result() for task in tasks)
    completed = tuple(result for result in results if result.status == "completed")

    def failed(reason: str, request: JudgeRequest | None = None) -> ReviewResult:
        return ReviewResult(
            critics=results,
            judge_request=request,
            verdict=Verdict(
                brief_id=brief.brief_id,
                decision="infrastructure_error",
                rationale=reason,
            ),
        )

    if (
        len(completed) < policy.min_critics
        or len({r.critic.provider for r in completed}) < policy.min_providers
    ):
        return failed("Critic quorum was not met.")
    # Exact-content dedupe preserves conflicting evidence and fixes. Original
    # contributions remain in results. Hash order is independent of roster order.
    unique: dict[str, Finding] = {}
    for result in completed:
        if result.critique is not None:
            for finding in result.critique.findings:
                unique[finding.finding_id] = finding
    findings = tuple(unique[key] for key in sorted(unique))
    request = JudgeRequest(brief=brief, findings=findings)
    if len(canonical_bytes(request)) > policy.max_request_bytes:
        return failed("Judge request exceeds the byte budget.", request)
    try:
        async with asyncio.timeout(policy.timeout_seconds):
            decision = await provider.judge(request)
    except (TimeoutError, ProviderError):
        return failed("Judge did not return a valid decision.", request)
    if (
        len(set(decision.upheld)) != len(decision.upheld)
        or not set(decision.upheld) <= unique.keys()
    ):
        return failed("Judge returned duplicate or unknown finding IDs.", request)
    upheld = tuple(f for f in findings if f.finding_id in decision.upheld)
    return ReviewResult(
        critics=results,
        judge_request=request,
        judge_decision=decision,
        verdict=adjudicate(brief, upheld, decision.rationale),
    )
