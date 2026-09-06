"""Composition root for recorded review, replay, and explicit live requests."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sqlite3
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from openai import AsyncOpenAI
from pydantic import ValidationError

from mos_eisley.core.agent import AgentConfig, AgentFailure, AgentResult, run_agent
from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import Brief, Contract, ReviewPolicy, canonical_bytes
from mos_eisley.core.ports import Journal, ProviderError
from mos_eisley.core.protocol import Effort, TextBlock, Turn
from mos_eisley.core.registry import default_registry, fixture_registry, openai_registry
from mos_eisley.core.skills import SkillPackageArchive, SkillRoster
from mos_eisley.demo import demo_inputs
from mos_eisley.demo_agent import agent_demo_inputs
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    GradingBatch,
    compile_observations,
    make_grading_batch,
)
from mos_eisley.evaluation.agreement import compare_adjudications
from mos_eisley.evaluation.authentication import (
    AuthenticatedAdjudication,
    GradingTrustPolicy,
    SignedAdjudication,
    authenticate_adjudication,
)
from mos_eisley.evaluation.execution import (
    BlindingMap,
    EvaluationCassette,
    ExecutionBatch,
    RawResultSet,
    make_execution_batch,
    run_recorded_evaluation,
)
from mos_eisley.evaluation.lineage import (
    DualGradedObservationSet,
    compile_dual_graded_observations,
)
from mos_eisley.evaluation.lineage_scoring import (
    score_dual_graded_observations,
)
from mos_eisley.evaluation.models import (
    CandidateGrid,
    EvaluationDataset,
    EvaluationGate,
    ObservationSet,
    Split,
    SweepPlan,
)
from mos_eisley.evaluation.resolution import (
    DualGradingResolution,
    ResolutionTrustPolicy,
    SignedResolutionSet,
    resolve_authenticated_adjudications,
)
from mos_eisley.evaluation.routing_activation import (
    RoutingActivationAuthorityPolicy,
    RoutingActivationEligibility,
    SignedRoutingActivationControl,
    SignedRoutingActivationPolicy,
    SignedRoutingOperationalSnapshot,
    issue_routing_activation_eligibility,
)
from mos_eisley.evaluation.routing_calibration import (
    RoutingCalibrationReport,
    score_routing_calibration,
)
from mos_eisley.evaluation.routing_holdout import (
    FrozenPolicyHoldoutReport,
    HoldoutUseClaim,
    evaluate_frozen_routing_policy,
    make_holdout_use_claim,
)
from mos_eisley.evaluation.routing_policy import (
    FrozenCandidateRoutingPolicy,
    freeze_candidate_routing_policy,
)
from mos_eisley.evaluation.routing_promotion import (
    AuthenticatedRoutingPromotion,
    RoutingPromotionAuthorityPolicy,
    SignedRoutingPromotionDecision,
    authenticate_routing_promotion,
    make_routing_promotion_decision,
)
from mos_eisley.evaluation.routing_promotion_policy import RoutingPromotionPolicy
from mos_eisley.evaluation.routing_protocol import (
    PromptFeatureManifest,
    RoutingStudyProtocol,
    SealedRoutingStudy,
    seal_routing_study,
)
from mos_eisley.evaluation.scoring import make_plan, score
from mos_eisley.evaluation.skill_comparison import (
    SealedSkillComparison,
    SkillComparisonProtocol,
    SkillComparisonReport,
    SkillHoldoutUseClaim,
    make_skill_holdout_use_claim,
    score_authenticated_skill_comparison,
    seal_skill_comparison,
)
from mos_eisley.evaluation.skill_promotion import (
    AuthenticatedSkillPromotion,
    SignedSkillPromotionDecision,
    SkillEvaluationLineage,
    SkillPromotionAuthorityPolicy,
    authenticate_skill_promotion,
    make_skill_promotion_decision,
)
from mos_eisley.providers.agent_recorded import RecordedAgentClient
from mos_eisley.providers.openai_http import BoundedOpenAIHttpClient
from mos_eisley.providers.openai_live import EphemeralOpenAITransport
from mos_eisley.providers.openai_responses import (
    OpenAIResponsesClient,
    SDKOpenAITransport,
)
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport, SpendPolicy
from mos_eisley.providers.recorded import Cassette, RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.run.activation_control import (
    RoutingControlAnchor,
    RoutingControlAnchorPolicy,
)
from mos_eisley.run.agent_store import begin_agent_run, load_agent_run
from mos_eisley.run.broker_audit import (
    AssignmentAuthorization,
    inspect_broker_recovery,
)
from mos_eisley.run.brokered_evaluation import compile_brokered_evaluation
from mos_eisley.run.evaluation_broker import (
    authorize_assignment,
    make_assignment_broker,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.holdout_use import claim_holdout_use, claim_skill_holdout_use
from mos_eisley.run.isolated_broker import run_isolated_broker
from mos_eisley.run.isolation import OfflineContainer, run_isolated_recorded
from mos_eisley.run.journal import MemoryJournal
from mos_eisley.run.live_store import begin_live_run
from mos_eisley.run.openai_conformance import build_openai_conformance_payload
from mos_eisley.run.routing_preflight import perform_routing_runtime_preflight
from mos_eisley.run.skill_default import (
    AuthenticatedSkillDefault,
    SignedSkillDefaultDecision,
    SkillDefaultAuthorityPolicy,
    SkillDefaultStore,
    SkillDefaultStorePolicy,
    authenticate_skill_default,
    make_skill_default_decision,
    select_authenticated_skill_default,
)
from mos_eisley.run.skill_installation import (
    AuthenticatedSkillInstallation,
    SignedSkillInstallationDecision,
    SkillInstallationAuthorityPolicy,
    SkillInstallationClaimStore,
    SkillInstallationClaimStorePolicy,
    authenticate_skill_installation,
    make_skill_installation_decision,
)
from mos_eisley.run.skill_installed_store import (
    SkillInstalledStore,
    SkillInstalledStorePolicy,
    inspect_skill_install_recovery,
    install_authenticated_skill_release,
)
from mos_eisley.run.skill_release import (
    SkillReleaseEvidence,
    bind_skill_release_evidence,
)
from mos_eisley.run.skill_release_control import (
    AuthenticatedSkillReleaseControl,
    SignedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillReleaseControlAnchorPolicy,
    SkillReleaseControlAuthorityPolicy,
    authenticate_skill_release_control,
    make_skill_release_control_decision,
)
from mos_eisley.run.skill_staging import (
    SkillStagingStore,
    SkillStagingStorePolicy,
    stage_authenticated_skill_release,
)
from mos_eisley.run.skills import (
    bind_skill_roster,
    discover_skills,
    verify_skill_archive,
)
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import index_run, load_run, private_write, save_run
from mos_eisley.tools.fixture import FixtureDispatcher
from mos_eisley.tools.none import NoToolsDispatcher

EXIT_CODES = {"accept": 0, "revise": 1, "reject": 1, "infrastructure_error": 2}


def _utc_datetime_argument(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("timestamp must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise argparse.ArgumentTypeError("timestamp must use an explicit UTC offset")
    return parsed


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="mos-eisley",
        description=(
            "Mos Eisley: recorded adversarial review, offline evals, and an opt-in "
            "OpenAI preview."
        ),
    )
    command.add_argument("--version", action="version", version="mos-eisley 0.1.0")
    subcommands = command.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("demo", "Run the synthetic recorded example"),
        ("review", "Review an explicit brief using a request-bound cassette"),
    ):
        sub = subcommands.add_parser(name, help=help_text)
        sub.add_argument("--output", type=Path, default=Path(".mos-eisley/runs"))
        sub.add_argument(
            "--json", action="store_true", help="Print NDJSON result events"
        )
        if name == "review":
            sub.add_argument(
                "--brief",
                type=Path,
                required=True,
                help="Brief JSON; no implicit repository reads",
            )
            sub.add_argument("--cassette", type=Path, required=True)
            sub.add_argument(
                "--skill-roster",
                type=Path,
                help="Digest-pinned critic-to-skill bindings",
            )
            sub.add_argument(
                "--user-skill-root", type=Path, action="append", default=[]
            )
            sub.add_argument(
                "--project-skill-root", type=Path, action="append", default=[]
            )
            sub.add_argument(
                "--allow-project-skills",
                action="store_true",
                help="Explicitly permit named project-source skills for this run",
            )
    replay = subcommands.add_parser(
        "replay", help="Verify artifacts and replay recorded responses"
    )
    replay.add_argument("run", type=Path)
    agent_demo = subcommands.add_parser(
        "agent-demo", help="Run a recorded two-turn canonical tool exchange"
    )
    agent_demo.add_argument(
        "--output", type=Path, default=Path(".mos-eisley/agent-runs")
    )
    agent_demo.add_argument("--json", action="store_true")
    agent_replay = subcommands.add_parser(
        "agent-replay", help="Verify and replay a recorded canonical agent run"
    )
    agent_replay.add_argument("run", type=Path)
    openai_run = subcommands.add_parser(
        "openai-run", help="Send one explicit prompt file to the OpenAI Responses API"
    )
    openai_run.add_argument("--prompt", type=Path, required=True)
    openai_run.add_argument("--instructions", type=Path)
    openai_run.add_argument(
        "--spend-policy",
        type=Path,
        help="Required reviewed pricing and spending policy JSON",
    )
    openai_run.add_argument("--model", default="gpt-6-astra")
    openai_run.add_argument(
        "--spend-ledger", type=Path, help="Required existing shared spending ledger"
    )
    openai_run.add_argument(
        "--effort",
        choices=("low", "medium", "high", "xhigh", "max"),
        default="medium",
    )
    openai_run.add_argument(
        "--output", type=Path, default=Path(".mos-eisley/live-runs")
    )
    openai_run.add_argument(
        "--allow-data-transfer",
        action="store_true",
        help="Acknowledge that prompt content will be sent to OpenAI",
    )
    openai_run.add_argument("--json", action="store_true")
    ledger_create = subcommands.add_parser(
        "spend-ledger-create", help="Create a new local spending scope; never overwrite"
    )
    ledger_create.add_argument("path", type=Path)
    ledger_create.add_argument("--ceiling-microusd", type=int, required=True)
    ledger_status = subcommands.add_parser(
        "spend-ledger-status", help="Inspect charges and unresolved reservations"
    )
    ledger_status.add_argument("path", type=Path)
    anchor_create = subcommands.add_parser(
        "routing-control-anchor-create",
        help="Create a private monotonic routing-control anchor",
    )
    anchor_create.add_argument("path", type=Path)
    anchor_create.add_argument(
        "--activation-authority-policy", type=Path, required=True
    )
    anchor_create.add_argument("--anchor-policy", type=Path, required=True)
    anchor_advance = subcommands.add_parser(
        "routing-control-anchor-advance",
        help="Append one newer signed routing-control state",
    )
    anchor_advance.add_argument("--anchor", type=Path, required=True)
    anchor_advance.add_argument(
        "--activation-authority-policy", type=Path, required=True
    )
    anchor_advance.add_argument("--signed-control-state", type=Path, required=True)
    anchor_status = subcommands.add_parser(
        "routing-control-anchor-status",
        help="Verify and inspect the complete routing-control anchor chain",
    )
    anchor_status.add_argument("--anchor", type=Path, required=True)
    anchor_status.add_argument(
        "--activation-authority-policy", type=Path, required=True
    )
    broker_status = subcommands.add_parser(
        "broker-audit-status",
        help="Validate one broker audit against trusted authorization and ledger",
    )
    broker_status.add_argument("--audit-dir", type=Path, required=True)
    broker_status.add_argument("--expected-authorization", type=Path, required=True)
    broker_status.add_argument("--spend-ledger", type=Path, required=True)
    conformance = subcommands.add_parser(
        "openai-conformance",
        help="Run one explicitly authorized blinded OpenAI conformance assignment",
    )
    conformance.add_argument("--batch", type=Path, required=True)
    conformance.add_argument("--sample-id", required=True)
    conformance.add_argument("--spend-policy", type=Path, required=True)
    conformance.add_argument("--spend-ledger", type=Path, required=True)
    conformance.add_argument("--docker", type=Path, required=True)
    conformance.add_argument(
        "--image", required=True, help="Locally built immutable sha256 image ID"
    )
    conformance.add_argument("--audit-dir", type=Path, required=True)
    conformance.add_argument("--authorization-output", type=Path, required=True)
    conformance.add_argument("--artifact-output", type=Path, required=True)
    conformance.add_argument(
        "--lifecycle-root",
        type=Path,
        default=Path(".mos-eisley/container-lifecycles"),
    )
    conformance.add_argument("--timeout", type=float, default=30.0)
    conformance.add_argument(
        "--allow-data-transfer",
        action="store_true",
        help="Acknowledge that the blinded brief will be sent to OpenAI",
    )
    eval_plan = subcommands.add_parser(
        "eval-plan", help="Create a deterministic backend/model/effort sweep plan"
    )
    eval_plan.add_argument("--dataset", type=Path, required=True)
    eval_plan.add_argument("--candidates", type=Path, required=True)
    eval_plan.add_argument("--gate", type=Path, required=True)
    eval_plan.add_argument("--repetitions", type=int, required=True)
    eval_plan.add_argument("--seed", type=int, required=True)
    eval_plan.add_argument("--output", type=Path, required=True)
    eval_blind = subcommands.add_parser(
        "eval-blind", help="Export a label-blind execution batch and private mapping"
    )
    eval_blind.add_argument("--dataset", type=Path, required=True)
    eval_blind.add_argument("--plan", type=Path, required=True)
    eval_blind.add_argument(
        "--split", choices=("calibration", "holdout"), required=True
    )
    eval_blind.add_argument("--batch-output", type=Path, required=True)
    eval_blind.add_argument("--mapping-output", type=Path, required=True)
    eval_run = subcommands.add_parser(
        "eval-run-recorded", help="Execute a blinded batch from request-bound fixtures"
    )
    eval_run.add_argument("--batch", type=Path, required=True)
    eval_run.add_argument("--cassette", type=Path, required=True)
    eval_run.add_argument("--output", type=Path, required=True)
    isolated = subcommands.add_parser(
        "eval-run-isolated", help="Run recorded evaluation in an offline container"
    )
    isolated.add_argument("--batch", type=Path, required=True)
    isolated.add_argument("--cassette", type=Path, required=True)
    isolated.add_argument("--output", type=Path, required=True)
    isolated.add_argument("--docker", type=Path, required=True)
    isolated.add_argument(
        "--image", required=True, help="Locally built sha256 image ID"
    )
    isolated.add_argument(
        "--lifecycle-root",
        type=Path,
        default=Path(".mos-eisley/container-lifecycles"),
        help="Private watchdog lease and cleanup records",
    )
    eval_grade = subcommands.add_parser(
        "eval-grade-packet", help="Export route-blind material for an adjudicator"
    )
    eval_grade.add_argument("--dataset", type=Path, required=True)
    eval_grade.add_argument("--plan", type=Path, required=True)
    eval_grade.add_argument("--batch", type=Path, required=True)
    eval_grade.add_argument("--mapping", type=Path, required=True)
    eval_grade.add_argument("--raw-results", type=Path, required=True)
    eval_grade.add_argument("--output", type=Path, required=True)
    eval_compile = subcommands.add_parser(
        "eval-compile", help="Compile provenance-bound judgments into observations"
    )
    eval_compile.add_argument("--dataset", type=Path, required=True)
    eval_compile.add_argument("--plan", type=Path, required=True)
    eval_compile.add_argument("--batch", type=Path, required=True)
    eval_compile.add_argument("--mapping", type=Path, required=True)
    eval_compile.add_argument("--raw-results", type=Path, required=True)
    eval_compile.add_argument("--grading-batch", type=Path, required=True)
    eval_compile.add_argument("--adjudication", type=Path, required=True)
    eval_compile.add_argument("--output", type=Path, required=True)
    eval_compile_dual = subcommands.add_parser(
        "eval-compile-dual",
        help="Compile observations from reverified dual-grade lineage",
    )
    eval_compile_dual.add_argument("--dataset", type=Path, required=True)
    eval_compile_dual.add_argument("--plan", type=Path, required=True)
    eval_compile_dual.add_argument("--batch", type=Path, required=True)
    eval_compile_dual.add_argument("--mapping", type=Path, required=True)
    eval_compile_dual.add_argument("--raw-results", type=Path, required=True)
    eval_compile_dual.add_argument("--grading-batch", type=Path, required=True)
    eval_compile_dual.add_argument(
        "--dual-grading-resolution", type=Path, required=True
    )
    eval_compile_dual.add_argument("--grading-trust-policy", type=Path, required=True)
    eval_compile_dual.add_argument(
        "--resolution-trust-policy", type=Path, required=True
    )
    eval_compile_dual.add_argument("--output", type=Path, required=True)
    eval_agreement = subcommands.add_parser(
        "eval-agreement", help="Compare two grading artifacts and report conflicts"
    )
    eval_agreement.add_argument("--grading-batch", type=Path, required=True)
    eval_agreement.add_argument("--left", type=Path, required=True)
    eval_agreement.add_argument("--right", type=Path, required=True)
    eval_agreement.add_argument("--output", type=Path, required=True)
    eval_authenticate = subcommands.add_parser(
        "eval-authenticate-adjudication",
        help="Verify one human adjudication against a trusted Ed25519 identity",
    )
    eval_authenticate.add_argument("--grading-batch", type=Path, required=True)
    eval_authenticate.add_argument("--signed-adjudication", type=Path, required=True)
    eval_authenticate.add_argument("--trust-policy", type=Path, required=True)
    eval_authenticate.add_argument("--output", type=Path, required=True)
    eval_resolve = subcommands.add_parser(
        "eval-resolve-adjudications",
        help="Verify two authenticated grades and independently resolve conflicts",
    )
    eval_resolve.add_argument("--grading-batch", type=Path, required=True)
    eval_resolve.add_argument("--left-authenticated", type=Path, required=True)
    eval_resolve.add_argument("--right-authenticated", type=Path, required=True)
    eval_resolve.add_argument("--grading-trust-policy", type=Path, required=True)
    eval_resolve.add_argument("--resolution-trust-policy", type=Path, required=True)
    eval_resolve.add_argument("--signed-resolution", type=Path)
    eval_resolve.add_argument("--output", type=Path, required=True)
    eval_score = subcommands.add_parser(
        "eval-score", help="Score one exactly covered evaluation split"
    )
    eval_score.add_argument("--dataset", type=Path, required=True)
    eval_score.add_argument("--plan", type=Path, required=True)
    eval_score.add_argument("--observations", type=Path, required=True)
    eval_score.add_argument(
        "--split", choices=("calibration", "holdout"), required=True
    )
    eval_score.add_argument("--output", type=Path, required=True)
    eval_score_dual = subcommands.add_parser(
        "eval-score-dual",
        help="Score one split after reverifying its complete dual-grade lineage",
    )
    eval_score_dual.add_argument("--dataset", type=Path, required=True)
    eval_score_dual.add_argument("--plan", type=Path, required=True)
    eval_score_dual.add_argument("--batch", type=Path, required=True)
    eval_score_dual.add_argument("--mapping", type=Path, required=True)
    eval_score_dual.add_argument("--raw-results", type=Path, required=True)
    eval_score_dual.add_argument("--grading-batch", type=Path, required=True)
    eval_score_dual.add_argument("--dual-grading-resolution", type=Path, required=True)
    eval_score_dual.add_argument("--dual-graded-observations", type=Path, required=True)
    eval_score_dual.add_argument("--grading-trust-policy", type=Path, required=True)
    eval_score_dual.add_argument("--resolution-trust-policy", type=Path, required=True)
    eval_score_dual.add_argument(
        "--split", choices=("calibration", "holdout"), required=True
    )
    eval_score_dual.add_argument("--output", type=Path, required=True)
    eval_seal_skill = subcommands.add_parser(
        "eval-seal-skill-comparison",
        help="Seal a pre-registered prompt-only persona-skill comparison",
    )
    eval_seal_skill.add_argument("--dataset", type=Path, required=True)
    eval_seal_skill.add_argument("--plan", type=Path, required=True)
    eval_seal_skill.add_argument("--protocol", type=Path, required=True)
    eval_seal_skill.add_argument("--output", type=Path, required=True)
    eval_score_skill = subcommands.add_parser(
        "eval-score-skill-comparison",
        help="Score paired skill evidence after reverifying dual-grade lineage",
    )
    eval_score_skill.add_argument("--dataset", type=Path, required=True)
    eval_score_skill.add_argument("--plan", type=Path, required=True)
    eval_score_skill.add_argument("--batch", type=Path, required=True)
    eval_score_skill.add_argument("--mapping", type=Path, required=True)
    eval_score_skill.add_argument("--raw-results", type=Path, required=True)
    eval_score_skill.add_argument("--grading-batch", type=Path, required=True)
    eval_score_skill.add_argument("--dual-grading-resolution", type=Path, required=True)
    eval_score_skill.add_argument(
        "--dual-graded-observations", type=Path, required=True
    )
    eval_score_skill.add_argument("--grading-trust-policy", type=Path, required=True)
    eval_score_skill.add_argument("--resolution-trust-policy", type=Path, required=True)
    eval_score_skill.add_argument("--sealed-comparison", type=Path, required=True)
    eval_score_skill.add_argument(
        "--holdout-use-directory",
        type=Path,
        help="Existing private directory required when scoring holdout",
    )
    eval_score_skill.add_argument(
        "--split", choices=("calibration", "holdout"), required=True
    )
    eval_score_skill.add_argument("--output", type=Path, required=True)
    eval_derive_skill_promotion = subcommands.add_parser(
        "eval-derive-skill-promotion",
        help="Derive an expiring skill decision for external signing",
    )
    for option in (
        "dataset",
        "plan",
        "sealed-comparison",
        "calibration-report",
        "holdout-report",
        "authority-policy",
        "output",
    ):
        eval_derive_skill_promotion.add_argument(
            f"--{option}", type=Path, required=True
        )
    eval_derive_skill_promotion.add_argument(
        "--issued-at", type=_utc_datetime_argument, required=True
    )
    eval_derive_skill_promotion.add_argument(
        "--valid-until", type=_utc_datetime_argument, required=True
    )
    eval_authenticate_skill_promotion = subcommands.add_parser(
        "eval-authenticate-skill-promotion",
        help="Reverify both split lineages and authenticate skill promotion",
    )
    for option in (
        "dataset",
        "plan",
        "sealed-comparison",
        "holdout-use-claim",
        "calibration-report",
        "holdout-report",
        "signed-promotion",
        "authority-policy",
        "output",
    ):
        eval_authenticate_skill_promotion.add_argument(
            f"--{option}", type=Path, required=True
        )
    for prefix in ("calibration", "holdout"):
        for option in (
            "batch",
            "mapping",
            "raw-results",
            "grading-batch",
            "dual-grading-resolution",
            "dual-graded-observations",
            "grading-trust-policy",
            "resolution-trust-policy",
        ):
            eval_authenticate_skill_promotion.add_argument(
                f"--{prefix}-{option}", type=Path, required=True
            )
    eval_bind_skill_release = subcommands.add_parser(
        "eval-bind-skill-release-evidence",
        help="Bind retained skill bytes to current authenticated promotion evidence",
    )
    for option in (
        "dataset",
        "plan",
        "sealed-comparison",
        "holdout-use-claim",
        "calibration-report",
        "holdout-report",
        "promotion-receipt",
        "authority-policy",
        "archive",
        "output",
    ):
        eval_bind_skill_release.add_argument(f"--{option}", type=Path, required=True)
    for prefix in ("calibration", "holdout"):
        for option in (
            "batch",
            "mapping",
            "raw-results",
            "grading-batch",
            "dual-grading-resolution",
            "dual-graded-observations",
            "grading-trust-policy",
            "resolution-trust-policy",
        ):
            eval_bind_skill_release.add_argument(
                f"--{prefix}-{option}", type=Path, required=True
            )
    eval_derive_skill_release_control = subcommands.add_parser(
        "eval-derive-skill-release-control",
        help="Derive exact expiring skill release control for external signing",
    )
    for option in (
        "dataset",
        "plan",
        "sealed-comparison",
        "holdout-use-claim",
        "calibration-report",
        "holdout-report",
        "promotion-receipt",
        "promotion-authority-policy",
        "archive",
        "release-evidence",
        "control-authority-policy",
        "output",
    ):
        eval_derive_skill_release_control.add_argument(
            f"--{option}", type=Path, required=True
        )
    eval_derive_skill_release_control.add_argument("--rollback-archive", type=Path)
    eval_derive_skill_release_control.add_argument(
        "--sequence", type=int, required=True
    )
    eval_derive_skill_release_control.add_argument(
        "--disposition", choices=("allowed", "revoked"), required=True
    )
    eval_derive_skill_release_control.add_argument(
        "--issued-at", type=_utc_datetime_argument, required=True
    )
    eval_derive_skill_release_control.add_argument(
        "--valid-until", type=_utc_datetime_argument, required=True
    )
    eval_authenticate_skill_release_control = subcommands.add_parser(
        "eval-authenticate-skill-release-control",
        help="Reverify release lineage and authenticate signed release control",
    )
    for option in (
        "dataset",
        "plan",
        "sealed-comparison",
        "holdout-use-claim",
        "calibration-report",
        "holdout-report",
        "promotion-receipt",
        "promotion-authority-policy",
        "archive",
        "release-evidence",
        "signed-control",
        "control-authority-policy",
        "output",
    ):
        eval_authenticate_skill_release_control.add_argument(
            f"--{option}", type=Path, required=True
        )
    eval_authenticate_skill_release_control.add_argument(
        "--rollback-archive", type=Path
    )
    for control_parser in (
        eval_derive_skill_release_control,
        eval_authenticate_skill_release_control,
    ):
        for prefix in ("calibration", "holdout"):
            for option in (
                "batch",
                "mapping",
                "raw-results",
                "grading-batch",
                "dual-grading-resolution",
                "dual-graded-observations",
                "grading-trust-policy",
                "resolution-trust-policy",
            ):
                control_parser.add_argument(
                    f"--{prefix}-{option}", type=Path, required=True
                )
    for control_command, help_text in (
        (
            "skill-release-control-anchor-create",
            "Create a private monotonic anchor for one exact skill release",
        ),
        (
            "skill-release-control-anchor-advance",
            "Append a current signed state to a skill release anchor",
        ),
        (
            "skill-release-control-anchor-status",
            "Verify and inspect a complete skill release control anchor",
        ),
    ):
        control_anchor = subcommands.add_parser(control_command, help=help_text)
        if control_command.endswith("create"):
            control_anchor.add_argument("path", type=Path)
            control_anchor.add_argument("--anchor-policy", type=Path, required=True)
        else:
            control_anchor.add_argument("--anchor", type=Path, required=True)
        control_anchor.add_argument(
            "--control-authority-policy", type=Path, required=True
        )
        if control_command.endswith("advance"):
            control_anchor.add_argument("--signed-control", type=Path, required=True)
    staging_create = subcommands.add_parser(
        "skill-staging-store-create",
        help="Create a private quarantine store pinned to release control",
    )
    staging_create.add_argument("path", type=Path)
    staging_create.add_argument("--store-policy", type=Path, required=True)
    staging_create.add_argument("--anchor-policy", type=Path, required=True)
    staging_status = subcommands.add_parser(
        "skill-staging-store-status",
        help="Verify staged packages and inventory incomplete transactions",
    )
    staging_status.add_argument("--store", type=Path, required=True)
    eval_stage_skill = subcommands.add_parser(
        "eval-stage-skill-release",
        help="Transactionally stage exact latest-controlled bytes into quarantine",
    )
    for option in (
        "dataset",
        "plan",
        "sealed-comparison",
        "holdout-use-claim",
        "calibration-report",
        "holdout-report",
        "promotion-receipt",
        "promotion-authority-policy",
        "archive",
        "release-evidence",
        "control-authority-policy",
        "authenticated-control",
        "control-anchor",
        "staging-store",
        "output",
    ):
        eval_stage_skill.add_argument(f"--{option}", type=Path, required=True)
    eval_stage_skill.add_argument("--rollback-archive", type=Path)
    eval_stage_skill.add_argument(
        "--action", choices=("candidate", "rollback"), required=True
    )
    for prefix in ("calibration", "holdout"):
        for option in (
            "batch",
            "mapping",
            "raw-results",
            "grading-batch",
            "dual-grading-resolution",
            "dual-graded-observations",
            "grading-trust-policy",
            "resolution-trust-policy",
        ):
            eval_stage_skill.add_argument(
                f"--{prefix}-{option}", type=Path, required=True
            )
    eval_derive_installation = subcommands.add_parser(
        "eval-derive-skill-installation",
        help="Derive exact one-use skill installation authority for signing",
    )
    eval_authenticate_installation = subcommands.add_parser(
        "eval-authenticate-skill-installation",
        help="Authenticate exact one-use skill installation authority",
    )
    for installation_parser in (
        eval_derive_installation,
        eval_authenticate_installation,
    ):
        for option in (
            "dataset",
            "plan",
            "sealed-comparison",
            "holdout-use-claim",
            "calibration-report",
            "holdout-report",
            "promotion-receipt",
            "promotion-authority-policy",
            "archive",
            "release-evidence",
            "control-authority-policy",
            "authenticated-control",
            "control-anchor",
            "staging-store",
            "installation-authority-policy",
            "output",
        ):
            installation_parser.add_argument(f"--{option}", type=Path, required=True)
        installation_parser.add_argument("--rollback-archive", type=Path)
        installation_parser.add_argument(
            "--action", choices=("candidate", "rollback"), required=True
        )
        for prefix in ("calibration", "holdout"):
            for option in (
                "batch",
                "mapping",
                "raw-results",
                "grading-batch",
                "dual-grading-resolution",
                "dual-graded-observations",
                "grading-trust-policy",
                "resolution-trust-policy",
            ):
                installation_parser.add_argument(
                    f"--{prefix}-{option}", type=Path, required=True
                )
    eval_derive_installation.add_argument(
        "--issued-at", type=_utc_datetime_argument, required=True
    )
    eval_derive_installation.add_argument(
        "--valid-until", type=_utc_datetime_argument, required=True
    )
    eval_authenticate_installation.add_argument(
        "--signed-installation", type=Path, required=True
    )
    installation_claim_create = subcommands.add_parser(
        "skill-installation-claim-store-create",
        help="Create a private at-most-once skill installation claim store",
    )
    installation_claim_create.add_argument("path", type=Path)
    installation_claim_create.add_argument("--store-policy", type=Path, required=True)
    installation_claim_create.add_argument(
        "--installation-authority-policy", type=Path, required=True
    )
    installation_claim_status = subcommands.add_parser(
        "skill-installation-claim-store-status",
        help="Verify and inspect consumed skill installation authorities",
    )
    installation_claim_status.add_argument("--store", type=Path, required=True)
    installation_claim_status.add_argument(
        "--installation-authority-policy", type=Path, required=True
    )
    installed_create = subcommands.add_parser(
        "skill-installed-store-create",
        help="Create a private inert installed-skill store",
    )
    installed_create.add_argument("path", type=Path)
    for option in (
        "store-policy",
        "installation-authority-policy",
        "staging-store",
        "claim-store-policy",
    ):
        installed_create.add_argument(f"--{option}", type=Path, required=True)
    installed_status = subcommands.add_parser(
        "skill-installed-store-status",
        help="Verify installed packages and inventory incomplete transactions",
    )
    installed_status.add_argument("--store", type=Path, required=True)
    installed_status.add_argument(
        "--installation-authority-policy", type=Path, required=True
    )
    installed_recovery = subcommands.add_parser(
        "skill-install-recovery-status",
        help="Correlate consumed claims with completed and incomplete installs",
    )
    installed_recovery.add_argument("--installed-store", type=Path, required=True)
    installed_recovery.add_argument("--claim-store", type=Path, required=True)
    installed_recovery.add_argument(
        "--installation-authority-policy", type=Path, required=True
    )
    eval_install_skill = subcommands.add_parser(
        "eval-install-skill-release",
        help="Consume exact authority and atomically install inert skill bytes",
    )
    for option in (
        "dataset",
        "plan",
        "sealed-comparison",
        "holdout-use-claim",
        "calibration-report",
        "holdout-report",
        "promotion-receipt",
        "promotion-authority-policy",
        "archive",
        "release-evidence",
        "control-authority-policy",
        "authenticated-control",
        "control-anchor",
        "staging-store",
        "authenticated-installation",
        "installation-authority-policy",
        "claim-store",
        "installed-store",
        "output",
    ):
        eval_install_skill.add_argument(f"--{option}", type=Path, required=True)
    eval_install_skill.add_argument("--rollback-archive", type=Path)
    eval_install_skill.add_argument(
        "--action", choices=("candidate", "rollback"), required=True
    )
    for prefix in ("calibration", "holdout"):
        for option in (
            "batch",
            "mapping",
            "raw-results",
            "grading-batch",
            "dual-grading-resolution",
            "dual-graded-observations",
            "grading-trust-policy",
            "resolution-trust-policy",
        ):
            eval_install_skill.add_argument(
                f"--{prefix}-{option}", type=Path, required=True
            )
    eval_derive_default = subcommands.add_parser(
        "eval-derive-skill-default",
        help="Derive one exact state-bound skill default change for signing",
    )
    eval_authenticate_default = subcommands.add_parser(
        "eval-authenticate-skill-default",
        help="Authenticate one exact state-bound skill default change",
    )
    eval_select_default = subcommands.add_parser(
        "eval-select-skill-default",
        help="Atomically consume authority and change the inert default pointer",
    )
    for default_parser in (
        eval_derive_default,
        eval_authenticate_default,
        eval_select_default,
    ):
        for option in (
            "dataset",
            "plan",
            "sealed-comparison",
            "holdout-use-claim",
            "calibration-report",
            "holdout-report",
            "promotion-receipt",
            "promotion-authority-policy",
            "archive",
            "release-evidence",
            "control-authority-policy",
            "authenticated-control",
            "control-anchor",
            "installed-store",
            "installation-authority-policy",
            "default-store",
            "default-authority-policy",
            "output",
        ):
            default_parser.add_argument(f"--{option}", type=Path, required=True)
        default_parser.add_argument("--rollback-archive", type=Path)
        default_parser.add_argument(
            "--action", choices=("candidate", "rollback"), required=True
        )
        for prefix in ("calibration", "holdout"):
            for option in (
                "batch",
                "mapping",
                "raw-results",
                "grading-batch",
                "dual-grading-resolution",
                "dual-graded-observations",
                "grading-trust-policy",
                "resolution-trust-policy",
            ):
                default_parser.add_argument(
                    f"--{prefix}-{option}", type=Path, required=True
                )
    eval_derive_default.add_argument(
        "--issued-at", type=_utc_datetime_argument, required=True
    )
    eval_derive_default.add_argument(
        "--valid-until", type=_utc_datetime_argument, required=True
    )
    eval_authenticate_default.add_argument("--signed-default", type=Path, required=True)
    eval_select_default.add_argument(
        "--authenticated-default", type=Path, required=True
    )
    default_store_create = subcommands.add_parser(
        "skill-default-store-create",
        help="Create a private atomic skill default-pointer store",
    )
    default_store_create.add_argument("path", type=Path)
    for option in (
        "store-policy",
        "default-authority-policy",
        "installed-store",
    ):
        default_store_create.add_argument(f"--{option}", type=Path, required=True)
    default_store_status = subcommands.add_parser(
        "skill-default-store-status",
        help="Verify the complete skill default-pointer revision chain",
    )
    for option in (
        "store",
        "default-authority-policy",
        "installed-store",
        "installation-authority-policy",
    ):
        default_store_status.add_argument(f"--{option}", type=Path, required=True)
    eval_seal_routing = subcommands.add_parser(
        "eval-seal-routing-study",
        help="Validate and seal a pre-registered difficulty-routing study",
    )
    eval_seal_routing.add_argument("--dataset", type=Path, required=True)
    eval_seal_routing.add_argument("--plan", type=Path, required=True)
    eval_seal_routing.add_argument("--feature-manifest", type=Path, required=True)
    eval_seal_routing.add_argument("--protocol", type=Path, required=True)
    eval_seal_routing.add_argument("--output", type=Path, required=True)
    eval_score_routing = subcommands.add_parser(
        "eval-score-routing-calibration",
        help="Score sealed profiles from authenticated calibration lineage",
    )
    eval_score_routing.add_argument("--dataset", type=Path, required=True)
    eval_score_routing.add_argument("--plan", type=Path, required=True)
    eval_score_routing.add_argument("--batch", type=Path, required=True)
    eval_score_routing.add_argument("--mapping", type=Path, required=True)
    eval_score_routing.add_argument("--raw-results", type=Path, required=True)
    eval_score_routing.add_argument("--grading-batch", type=Path, required=True)
    eval_score_routing.add_argument(
        "--dual-grading-resolution", type=Path, required=True
    )
    eval_score_routing.add_argument(
        "--dual-graded-observations", type=Path, required=True
    )
    eval_score_routing.add_argument("--grading-trust-policy", type=Path, required=True)
    eval_score_routing.add_argument(
        "--resolution-trust-policy", type=Path, required=True
    )
    eval_score_routing.add_argument("--feature-manifest", type=Path, required=True)
    eval_score_routing.add_argument("--sealed-study", type=Path, required=True)
    eval_score_routing.add_argument("--output", type=Path, required=True)
    eval_freeze_routing = subcommands.add_parser(
        "eval-freeze-routing-policy",
        help="Freeze a non-activating candidate policy from calibration evidence",
    )
    for option in (
        "dataset",
        "plan",
        "batch",
        "mapping",
        "raw-results",
        "grading-batch",
        "dual-grading-resolution",
        "dual-graded-observations",
        "grading-trust-policy",
        "resolution-trust-policy",
        "feature-manifest",
        "sealed-study",
        "calibration-report",
        "output",
    ):
        eval_freeze_routing.add_argument(f"--{option}", type=Path, required=True)
    eval_holdout_routing = subcommands.add_parser(
        "eval-evaluate-routing-holdout",
        help="Consume a local claim and evaluate a frozen policy on holdout",
    )
    for option in (
        "dataset",
        "plan",
        "feature-manifest",
        "sealed-study",
        "calibration-report",
        "candidate-policy",
        "promotion-policy",
        "holdout-use-directory",
        "output",
    ):
        eval_holdout_routing.add_argument(f"--{option}", type=Path, required=True)
    for prefix in ("calibration", "holdout"):
        for option in (
            "batch",
            "mapping",
            "raw-results",
            "grading-batch",
            "dual-grading-resolution",
            "dual-graded-observations",
            "grading-trust-policy",
            "resolution-trust-policy",
        ):
            eval_holdout_routing.add_argument(
                f"--{prefix}-{option}", type=Path, required=True
            )
    eval_derive_promotion = subcommands.add_parser(
        "eval-derive-routing-promotion",
        help="Apply pre-pinned promotion thresholds without authorizing promotion",
    )
    eval_derive_promotion.add_argument("--promotion-policy", type=Path, required=True)
    eval_derive_promotion.add_argument("--holdout-report", type=Path, required=True)
    eval_derive_promotion.add_argument("--output", type=Path, required=True)
    eval_authenticate_promotion = subcommands.add_parser(
        "eval-authenticate-routing-promotion",
        help="Reverify holdout lineage and authenticate an independent promotion",
    )
    for option in (
        "dataset",
        "plan",
        "feature-manifest",
        "sealed-study",
        "calibration-report",
        "candidate-policy",
        "promotion-policy",
        "holdout-use-claim",
        "holdout-report",
        "signed-promotion",
        "authority-policy",
        "output",
    ):
        eval_authenticate_promotion.add_argument(
            f"--{option}", type=Path, required=True
        )
    for prefix in ("calibration", "holdout"):
        for option in (
            "batch",
            "mapping",
            "raw-results",
            "grading-batch",
            "dual-grading-resolution",
            "dual-graded-observations",
            "grading-trust-policy",
            "resolution-trust-policy",
        ):
            eval_authenticate_promotion.add_argument(
                f"--{prefix}-{option}", type=Path, required=True
            )
    eval_activation = subcommands.add_parser(
        "eval-issue-routing-activation-eligibility",
        help="Issue short-lived eligibility from fresh signed operational evidence",
    )
    for option in (
        "dataset",
        "plan",
        "feature-manifest",
        "sealed-study",
        "calibration-report",
        "candidate-policy",
        "promotion-policy",
        "holdout-use-claim",
        "holdout-report",
        "promotion-receipt",
        "promotion-authority-policy",
        "signed-activation-policy",
        "signed-operational-snapshot",
        "signed-control-state",
        "activation-authority-policy",
        "output",
    ):
        eval_activation.add_argument(f"--{option}", type=Path, required=True)
    for prefix in ("calibration", "holdout"):
        for option in (
            "batch",
            "mapping",
            "raw-results",
            "grading-batch",
            "dual-grading-resolution",
            "dual-graded-observations",
            "grading-trust-policy",
            "resolution-trust-policy",
        ):
            eval_activation.add_argument(
                f"--{prefix}-{option}", type=Path, required=True
            )
    runtime_preflight = subcommands.add_parser(
        "eval-routing-runtime-preflight",
        help="Reverify eligibility against the latest anchored control state",
    )
    for option in (
        "dataset",
        "plan",
        "feature-manifest",
        "sealed-study",
        "calibration-report",
        "candidate-policy",
        "promotion-policy",
        "holdout-use-claim",
        "holdout-report",
        "promotion-receipt",
        "promotion-authority-policy",
        "signed-activation-policy",
        "signed-operational-snapshot",
        "signed-control-state",
        "activation-authority-policy",
        "activation-eligibility",
        "control-anchor",
        "output",
    ):
        runtime_preflight.add_argument(f"--{option}", type=Path, required=True)
    for prefix in ("calibration", "holdout"):
        for option in (
            "batch",
            "mapping",
            "raw-results",
            "grading-batch",
            "dual-grading-resolution",
            "dual-graded-observations",
            "grading-trust-policy",
            "resolution-trust-policy",
        ):
            runtime_preflight.add_argument(
                f"--{prefix}-{option}", type=Path, required=True
            )
    skills = subcommands.add_parser(
        "skills", help="Discover and inspect inert prompt-only skill packages"
    )
    skill_commands = skills.add_subparsers(dest="skill_command", required=True)
    for name, help_text in (
        ("list", "List validated discovery metadata without loading bodies"),
        ("validate", "Validate prompt-only skill packages; grants no trust"),
    ):
        skill_command = skill_commands.add_parser(name, help=help_text)
        skill_command.add_argument(
            "--user-root", type=Path, action="append", default=[]
        )
        skill_command.add_argument(
            "--project-root", type=Path, action="append", default=[]
        )
        skill_command.add_argument("--json", action="store_true")
    skill_show = skill_commands.add_parser(
        "show", help="Activate one exact source-qualified skill snapshot"
    )
    skill_show.add_argument("reference")
    skill_show.add_argument("--user-root", type=Path, action="append", default=[])
    skill_show.add_argument("--project-root", type=Path, action="append", default=[])
    skill_show.add_argument("--allow-project", action="store_true")
    skill_show.add_argument("--json", action="store_true")
    skill_archive = skill_commands.add_parser(
        "archive", help="Retain one exact validated package without installing it"
    )
    skill_archive.add_argument("reference")
    skill_archive.add_argument("--user-root", type=Path, action="append", default=[])
    skill_archive.add_argument("--project-root", type=Path, action="append", default=[])
    skill_archive.add_argument("--allow-project", action="store_true")
    skill_archive.add_argument("--output", type=Path, required=True)
    skill_verify_archive = skill_commands.add_parser(
        "verify-archive", help="Revalidate retained package bytes without extraction"
    )
    skill_verify_archive.add_argument("archive", type=Path)
    subcommands.add_parser("models", help="Print the configured model registry")
    return command


def _utf8_file(path: Path, limit: int) -> str:
    try:
        value = read_bounded(path, limit).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("input file must be UTF-8") from error
    if not value:
        raise ValueError("input file must not be empty")
    return value


def _write_contract(path: Path, value: Contract) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_write(path, canonical_bytes(value))


def _paths_overlap(left: Path, right: Path) -> bool:
    left_resolved = left.resolve()
    right_resolved = right.resolve()
    return (
        left_resolved == right_resolved
        or left_resolved.is_relative_to(right_resolved)
        or right_resolved.is_relative_to(left_resolved)
    )


def _openai_api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY")


async def _openai_run(
    config: AgentConfig,
    api_key: str,
    journal: Journal,
    spend_policy: SpendPolicy,
    directory: Path,
    ledger: SpendLedger,
) -> AgentResult:
    async with AsyncOpenAI(
        api_key=api_key,
        timeout=config.request_timeout_seconds,
        max_retries=0,
        base_url="https://api.openai.com/v1",
        http_client=BoundedOpenAIHttpClient(trust_env=False, follow_redirects=False),
    ) as sdk:
        return await run_agent(
            config,
            openai_registry(),
            OpenAIResponsesClient(
                BudgetedOpenAITransport(
                    SDKOpenAITransport(sdk), spend_policy, directory, ledger
                )
            ),
            NoToolsDispatcher(),
            journal,
        )


def _authenticate_adjudication_command(args: argparse.Namespace) -> int:
    grading = GradingBatch.model_validate_json(
        read_bounded(cast(Path, args.grading_batch), 16_000_000)
    )
    signed = SignedAdjudication.model_validate_json(
        read_bounded(cast(Path, args.signed_adjudication), 16_000_000)
    )
    trust_policy = GradingTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.trust_policy), 64_000)
    )
    authenticated = authenticate_adjudication(grading, signed, trust_policy)
    output = cast(Path, args.output)
    _write_contract(output, authenticated)
    print(
        json.dumps(
            {
                "type": "evaluation.adjudication.authenticated",
                "path": str(output),
                "authenticated_adjudication_sha256": (
                    authenticated.authenticated_adjudication_sha256
                ),
                "grading_batch_sha256": authenticated.grading_batch_sha256,
                "trust_policy_sha256": authenticated.trust_policy_sha256,
                "adjudicator_id": (
                    authenticated.signed_adjudication.signature.signer_id
                ),
            }
        )
    )
    return 0


def _resolve_adjudications_command(args: argparse.Namespace) -> int:
    grading = GradingBatch.model_validate_json(
        read_bounded(cast(Path, args.grading_batch), 16_000_000)
    )
    left = AuthenticatedAdjudication.model_validate_json(
        read_bounded(cast(Path, args.left_authenticated), 16_000_000)
    )
    right = AuthenticatedAdjudication.model_validate_json(
        read_bounded(cast(Path, args.right_authenticated), 16_000_000)
    )
    grading_policy = GradingTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.grading_trust_policy), 64_000)
    )
    resolution_policy = ResolutionTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.resolution_trust_policy), 64_000)
    )
    resolution_path = cast(Path | None, args.signed_resolution)
    signed_resolution = (
        SignedResolutionSet.model_validate_json(
            read_bounded(resolution_path, 16_000_000)
        )
        if resolution_path is not None
        else None
    )
    artifact = resolve_authenticated_adjudications(
        grading,
        left,
        right,
        grading_policy,
        resolution_policy,
        signed_resolution,
    )
    output = cast(Path, args.output)
    _write_contract(output, artifact)
    print(
        json.dumps(
            {
                "type": "evaluation.dual_grading.resolved",
                "path": str(output),
                "dual_grading_resolution_sha256": (
                    artifact.dual_grading_resolution_sha256
                ),
                "grading_batch_sha256": artifact.grading_batch_sha256,
                "left_adjudicator_id": left.signed_adjudication.signature.signer_id,
                "right_adjudicator_id": right.signed_adjudication.signature.signer_id,
                "resolver_id": (
                    signed_resolution.signature.signer_id
                    if signed_resolution is not None
                    else None
                ),
                "conflicts": len(artifact.agreement.conflicts),
                "promotion_eligible": artifact.promotion_eligible,
            }
        )
    )
    return 0


def _compile_dual_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    batch = ExecutionBatch.model_validate_json(
        read_bounded(cast(Path, args.batch), 16_000_000)
    )
    mapping = BlindingMap.model_validate_json(
        read_bounded(cast(Path, args.mapping), 16_000_000)
    )
    raw_results = RawResultSet.model_validate_json(
        read_bounded(cast(Path, args.raw_results), 16_000_000)
    )
    grading_batch = GradingBatch.model_validate_json(
        read_bounded(cast(Path, args.grading_batch), 16_000_000)
    )
    dual_grading = DualGradingResolution.model_validate_json(
        read_bounded(cast(Path, args.dual_grading_resolution), 16_000_000)
    )
    grading_policy = GradingTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.grading_trust_policy), 64_000)
    )
    resolution_policy = ResolutionTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.resolution_trust_policy), 64_000)
    )
    observations = compile_dual_graded_observations(
        dataset,
        plan,
        batch,
        mapping,
        raw_results,
        grading_batch,
        dual_grading,
        grading_policy,
        resolution_policy,
    )
    output = cast(Path, args.output)
    _write_contract(output, observations)
    print(
        json.dumps(
            {
                "type": "evaluation.dual_graded_observations.compiled",
                "path": str(output),
                "dual_graded_observations_sha256": (
                    observations.dual_graded_observations_sha256
                ),
                "dual_grading_resolution_sha256": (
                    observations.dual_grading_resolution_sha256
                ),
                "observations": len(observations.observations),
                "promotion_eligible": observations.promotion_eligible,
            }
        )
    )
    return 0


def _score_dual_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    batch = ExecutionBatch.model_validate_json(
        read_bounded(cast(Path, args.batch), 16_000_000)
    )
    mapping = BlindingMap.model_validate_json(
        read_bounded(cast(Path, args.mapping), 16_000_000)
    )
    raw_results = RawResultSet.model_validate_json(
        read_bounded(cast(Path, args.raw_results), 16_000_000)
    )
    grading_batch = GradingBatch.model_validate_json(
        read_bounded(cast(Path, args.grading_batch), 16_000_000)
    )
    dual_grading = DualGradingResolution.model_validate_json(
        read_bounded(cast(Path, args.dual_grading_resolution), 16_000_000)
    )
    observations = DualGradedObservationSet.model_validate_json(
        read_bounded(cast(Path, args.dual_graded_observations), 16_000_000)
    )
    grading_policy = GradingTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.grading_trust_policy), 64_000)
    )
    resolution_policy = ResolutionTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.resolution_trust_policy), 64_000)
    )
    split = cast(Split, args.split)
    report = score_dual_graded_observations(
        dataset,
        plan,
        batch,
        mapping,
        raw_results,
        grading_batch,
        dual_grading,
        grading_policy,
        resolution_policy,
        observations,
        split,
    )
    output = cast(Path, args.output)
    _write_contract(output, report)
    print(
        json.dumps(
            {
                "type": "evaluation.dual_lineage_score.created",
                "path": str(output),
                "dual_lineage_report_sha256": report.dual_lineage_report_sha256,
                "dual_graded_observations_sha256": (
                    report.dual_graded_observations_sha256
                ),
                "split": report.split,
                "eligible": sum(item.eligible for item in report.scores),
                "promotion_ready": report.promotion_ready,
            }
        )
    )
    return 0


def _seal_skill_comparison_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    protocol = SkillComparisonProtocol.model_validate_json(
        read_bounded(cast(Path, args.protocol), 1_000_000)
    )
    artifact = seal_skill_comparison(dataset, plan, protocol)
    output = cast(Path, args.output)
    _write_contract(output, artifact)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_comparison.sealed",
                "path": str(output),
                "sealed_comparison_sha256": artifact.sealed_comparison_sha256,
                "protocol_sha256": artifact.protocol.protocol_sha256,
                "activation_authorized": artifact.activation_authorized,
            }
        )
    )
    return 0


def _score_skill_comparison_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    batch = ExecutionBatch.model_validate_json(
        read_bounded(cast(Path, args.batch), 16_000_000)
    )
    mapping = BlindingMap.model_validate_json(
        read_bounded(cast(Path, args.mapping), 16_000_000)
    )
    raw_results = RawResultSet.model_validate_json(
        read_bounded(cast(Path, args.raw_results), 16_000_000)
    )
    grading_batch = GradingBatch.model_validate_json(
        read_bounded(cast(Path, args.grading_batch), 16_000_000)
    )
    dual_grading = DualGradingResolution.model_validate_json(
        read_bounded(cast(Path, args.dual_grading_resolution), 16_000_000)
    )
    observations = DualGradedObservationSet.model_validate_json(
        read_bounded(cast(Path, args.dual_graded_observations), 16_000_000)
    )
    grading_policy = GradingTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.grading_trust_policy), 64_000)
    )
    resolution_policy = ResolutionTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.resolution_trust_policy), 64_000)
    )
    sealed = SealedSkillComparison.model_validate_json(
        read_bounded(cast(Path, args.sealed_comparison), 2_000_000)
    )
    split = cast(Split, args.split)
    output = cast(Path, args.output)
    claim = None
    claim_path = None
    if split == "holdout":
        if args.holdout_use_directory is None:
            raise ValueError("holdout scoring requires --holdout-use-directory")
        use_directory = cast(Path, args.holdout_use_directory)
        if output.exists():
            raise ValueError("skill comparison report output already exists")
        if not use_directory.is_dir():
            raise ValueError("holdout use directory must already exist")
        if _paths_overlap(output, use_directory):
            raise ValueError("skill report and holdout use directory must not overlap")
        claim = make_skill_holdout_use_claim(
            sealed,
            batch,
            mapping,
            raw_results,
            grading_batch,
            dual_grading,
            grading_policy,
            resolution_policy,
            observations,
        )
        claim_path = claim_skill_holdout_use(use_directory, claim)
    elif args.holdout_use_directory is not None:
        raise ValueError("calibration scoring does not accept --holdout-use-directory")
    report = score_authenticated_skill_comparison(
        dataset,
        plan,
        batch,
        mapping,
        raw_results,
        grading_batch,
        dual_grading,
        grading_policy,
        resolution_policy,
        observations,
        sealed,
        split,
        claim,
    )
    _write_contract(output, report)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_comparison.scored",
                "path": str(output),
                "claim_path": str(claim_path) if claim_path is not None else None,
                "skill_comparison_report_sha256": (
                    report.skill_comparison_report_sha256
                ),
                "split": report.split,
                "passes_registered_gate": report.passes_registered_gate,
                "promotion_ready": report.promotion_ready,
                "activation_authorized": report.activation_authorized,
            }
        )
    )
    return 0


def _derive_skill_promotion_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    sealed = SealedSkillComparison.model_validate_json(
        read_bounded(cast(Path, args.sealed_comparison), 2_000_000)
    )
    calibration_report = SkillComparisonReport.model_validate_json(
        read_bounded(cast(Path, args.calibration_report), 2_000_000)
    )
    holdout_report = SkillComparisonReport.model_validate_json(
        read_bounded(cast(Path, args.holdout_report), 2_000_000)
    )
    authority_policy = SkillPromotionAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.authority_policy), 64_000)
    )
    decision = make_skill_promotion_decision(
        dataset,
        plan,
        sealed,
        calibration_report,
        holdout_report,
        authority_policy,
        cast(datetime, args.issued_at),
        cast(datetime, args.valid_until),
    )
    output = cast(Path, args.output)
    _write_contract(output, decision)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_promotion.derived",
                "path": str(output),
                "decision_sha256": decision.decision_sha256,
                "criteria_satisfied": decision.criteria_satisfied,
                "valid_until": decision.valid_until.isoformat(),
                "authenticated": False,
                "activation_authorized": decision.activation_authorized,
                "configuration_mutation_authorized": (
                    decision.configuration_mutation_authorized
                ),
            }
        )
    )
    return 0


def _authenticate_skill_promotion_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    calibration = _load_routing_lineage(args, "calibration")
    holdout = _load_routing_lineage(args, "holdout")
    sealed = SealedSkillComparison.model_validate_json(
        read_bounded(cast(Path, args.sealed_comparison), 2_000_000)
    )
    claim = SkillHoldoutUseClaim.model_validate_json(
        read_bounded(cast(Path, args.holdout_use_claim), 64_000)
    )
    calibration_report = SkillComparisonReport.model_validate_json(
        read_bounded(cast(Path, args.calibration_report), 2_000_000)
    )
    holdout_report = SkillComparisonReport.model_validate_json(
        read_bounded(cast(Path, args.holdout_report), 2_000_000)
    )
    signed = SignedSkillPromotionDecision.model_validate_json(
        read_bounded(cast(Path, args.signed_promotion), 128_000)
    )
    authority_policy = SkillPromotionAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.authority_policy), 64_000)
    )
    authenticated = authenticate_skill_promotion(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        signed,
        authority_policy,
        datetime.now(UTC),
    )
    output = cast(Path, args.output)
    _write_contract(output, authenticated)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_promotion.authenticated",
                "path": str(output),
                "promotion_receipt_sha256": (authenticated.promotion_receipt_sha256),
                "signer_id": signed.signature.signer_id,
                "promotion_ready": authenticated.promotion_ready,
                "valid_until": authenticated.valid_until.isoformat(),
                "activation_authorized": authenticated.activation_authorized,
                "configuration_mutation_authorized": (
                    authenticated.configuration_mutation_authorized
                ),
            }
        )
    )
    return 0


def _bind_skill_release_evidence_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    calibration = _load_routing_lineage(args, "calibration")
    holdout = _load_routing_lineage(args, "holdout")
    sealed = SealedSkillComparison.model_validate_json(
        read_bounded(cast(Path, args.sealed_comparison), 2_000_000)
    )
    claim = SkillHoldoutUseClaim.model_validate_json(
        read_bounded(cast(Path, args.holdout_use_claim), 64_000)
    )
    calibration_report = SkillComparisonReport.model_validate_json(
        read_bounded(cast(Path, args.calibration_report), 2_000_000)
    )
    holdout_report = SkillComparisonReport.model_validate_json(
        read_bounded(cast(Path, args.holdout_report), 2_000_000)
    )
    promotion = AuthenticatedSkillPromotion.model_validate_json(
        read_bounded(cast(Path, args.promotion_receipt), 128_000)
    )
    authority_policy = SkillPromotionAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.authority_policy), 64_000)
    )
    archive = SkillPackageArchive.model_validate_json(
        read_bounded(cast(Path, args.archive), 6_000_000)
    )
    evidence = bind_skill_release_evidence(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        authority_policy,
        archive,
        datetime.now(UTC),
    )
    output = cast(Path, args.output)
    _write_contract(output, evidence)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_release_evidence.bound",
                "path": str(output),
                "release_evidence_sha256": evidence.release_evidence_sha256,
                "archive_sha256": evidence.archive_sha256,
                "promotion_receipt_sha256": evidence.promotion_receipt_sha256,
                "valid_until": evidence.valid_until.isoformat(),
                "package_retained": evidence.package_retained,
                "promotion_ready": evidence.promotion_ready,
                "installation_authorized": evidence.installation_authorized,
                "activation_authorized": evidence.activation_authorized,
                "configuration_mutation_authorized": (
                    evidence.configuration_mutation_authorized
                ),
            }
        )
    )
    return 0


def _derive_skill_release_control_command(args: argparse.Namespace) -> int:
    (
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control_authorities,
        rollback_archive,
    ) = _load_skill_release_control_sources(args)
    decision = make_skill_release_control_decision(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control_authorities,
        cast(int, args.sequence),
        cast(Literal["allowed", "revoked"], args.disposition),
        rollback_archive,
        cast(datetime, args.issued_at),
        cast(datetime, args.valid_until),
    )
    output = cast(Path, args.output)
    _write_contract(output, decision)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_release_control.derived",
                "path": str(output),
                "decision_sha256": decision.decision_sha256,
                "release_evidence_sha256": decision.release_evidence_sha256,
                "sequence": decision.sequence,
                "disposition": decision.disposition,
                "rollback_nominated": decision.rollback is not None,
                "authenticated": False,
                "installation_authorized": decision.installation_authorized,
                "activation_authorized": decision.activation_authorized,
                "configuration_mutation_authorized": (
                    decision.configuration_mutation_authorized
                ),
            }
        )
    )
    return 0


def _authenticate_skill_release_control_command(args: argparse.Namespace) -> int:
    (
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control_authorities,
        rollback_archive,
    ) = _load_skill_release_control_sources(args)
    signed = SignedSkillReleaseControl.model_validate_json(
        read_bounded(cast(Path, args.signed_control), 256_000)
    )
    receipt = authenticate_skill_release_control(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        signed,
        control_authorities,
        rollback_archive,
        datetime.now(UTC),
    )
    output = cast(Path, args.output)
    _write_contract(output, receipt)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_release_control.authenticated",
                "path": str(output),
                "control_receipt_sha256": receipt.control_receipt_sha256,
                "release_evidence_sha256": receipt.release_evidence_sha256,
                "sequence": signed.decision.sequence,
                "signer_id": signed.signature.signer_id,
                "release_allowed": receipt.release_allowed,
                "release_revoked": receipt.release_revoked,
                "rollback_nominated": receipt.rollback_archive is not None,
                "installation_authorized": receipt.installation_authorized,
                "activation_authorized": receipt.activation_authorized,
                "configuration_mutation_authorized": (
                    receipt.configuration_mutation_authorized
                ),
            }
        )
    )
    return 0


def _skill_release_control_anchor_create_command(args: argparse.Namespace) -> int:
    control_authorities = SkillReleaseControlAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.control_authority_policy), 64_000)
    )
    policy = SkillReleaseControlAnchorPolicy.model_validate_json(
        read_bounded(cast(Path, args.anchor_policy), 64_000)
    )
    anchor = SkillReleaseControlAnchor.create(
        cast(Path, args.path),
        policy,
        control_authorities,
    )
    snapshot = anchor.snapshot(control_authorities)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_release_control.anchor_created",
                "path": str(anchor.path),
                "anchor_id": snapshot.policy.anchor_id,
                "anchor_policy_sha256": snapshot.policy.policy_sha256,
                "release_evidence_sha256": (snapshot.policy.release_evidence_sha256),
                "entries": snapshot.entries,
            }
        )
    )
    return 0


def _skill_release_control_anchor_advance_command(args: argparse.Namespace) -> int:
    control_authorities = SkillReleaseControlAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.control_authority_policy), 64_000)
    )
    signed = SignedSkillReleaseControl.model_validate_json(
        read_bounded(cast(Path, args.signed_control), 256_000)
    )
    anchor = SkillReleaseControlAnchor(cast(Path, args.anchor))
    snapshot = anchor.advance(signed, control_authorities, datetime.now(UTC))
    latest = snapshot.latest
    if latest is None:
        raise ValueError("skill release control anchor advance produced no state")
    print(
        json.dumps(
            {
                "type": "evaluation.skill_release_control.anchor_advanced",
                "path": str(anchor.path),
                "anchor_id": snapshot.policy.anchor_id,
                "anchor_entry_sha256": latest.anchor_entry_sha256,
                "sequence": latest.signed_control.decision.sequence,
                "disposition": latest.signed_control.decision.disposition,
                "entries": snapshot.entries,
                "installation_authorized": False,
                "activation_authorized": False,
                "configuration_mutation_authorized": False,
            }
        )
    )
    return 0


def _skill_release_control_anchor_status_command(args: argparse.Namespace) -> int:
    control_authorities = SkillReleaseControlAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.control_authority_policy), 64_000)
    )
    anchor = SkillReleaseControlAnchor(cast(Path, args.anchor))
    snapshot = anchor.snapshot(control_authorities)
    latest = snapshot.latest
    print(
        json.dumps(
            {
                "type": "evaluation.skill_release_control.anchor_status",
                "path": str(anchor.path),
                "anchor_id": snapshot.policy.anchor_id,
                "anchor_policy_sha256": snapshot.policy.policy_sha256,
                "release_evidence_sha256": (snapshot.policy.release_evidence_sha256),
                "entries": snapshot.entries,
                "latest_entry_sha256": (
                    latest.anchor_entry_sha256 if latest is not None else None
                ),
                "latest_sequence": (
                    latest.signed_control.decision.sequence
                    if latest is not None
                    else None
                ),
                "latest_disposition": (
                    latest.signed_control.decision.disposition
                    if latest is not None
                    else None
                ),
                "installation_authorized": False,
                "activation_authorized": False,
                "configuration_mutation_authorized": False,
            }
        )
    )
    return 0


def _skill_staging_store_create_command(args: argparse.Namespace) -> int:
    policy = SkillStagingStorePolicy.model_validate_json(
        read_bounded(cast(Path, args.store_policy), 64_000)
    )
    anchor_policy = SkillReleaseControlAnchorPolicy.model_validate_json(
        read_bounded(cast(Path, args.anchor_policy), 64_000)
    )
    store = SkillStagingStore.create(
        cast(Path, args.path),
        policy,
        anchor_policy,
    )
    snapshot = store.snapshot()
    print(
        json.dumps(
            {
                "type": "evaluation.skill_staging.store_created",
                "path": str(store.root),
                "store_id": snapshot.policy.store_id,
                "store_policy_sha256": snapshot.policy.policy_sha256,
                "control_anchor_policy_sha256": (
                    snapshot.policy.control_anchor_policy_sha256
                ),
                "packages": len(snapshot.packages),
                "incomplete_transactions": len(snapshot.incomplete),
                "installation_authorized": False,
                "activation_authorized": False,
                "configuration_mutation_authorized": False,
            }
        )
    )
    return 0


def _skill_staging_store_status_command(args: argparse.Namespace) -> int:
    store = SkillStagingStore(cast(Path, args.store))
    snapshot = store.snapshot()
    print(
        json.dumps(
            {
                "type": "evaluation.skill_staging.store_status",
                "path": str(store.root),
                "store_id": snapshot.policy.store_id,
                "store_policy_sha256": snapshot.policy.policy_sha256,
                "snapshot_sha256": snapshot.snapshot_sha256,
                "packages": list(snapshot.packages),
                "incomplete_transactions": [
                    item.model_dump(mode="json") for item in snapshot.incomplete
                ],
                "installation_authorized": False,
                "activation_authorized": False,
                "configuration_mutation_authorized": False,
            }
        )
    )
    return 0


def _stage_skill_release_command(args: argparse.Namespace) -> int:
    (
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control_authorities,
        _rollback_archive,
    ) = _load_skill_release_control_sources(args)
    authenticated_control = AuthenticatedSkillReleaseControl.model_validate_json(
        read_bounded(cast(Path, args.authenticated_control), 8_000_000)
    )
    control_anchor = SkillReleaseControlAnchor(cast(Path, args.control_anchor))
    staging_store = SkillStagingStore(cast(Path, args.staging_store))
    result = stage_authenticated_skill_release(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        authenticated_control,
        control_authorities,
        control_anchor,
        staging_store,
        cast(Literal["candidate", "rollback"], args.action),
        datetime.now(UTC),
    )
    output = cast(Path, args.output)
    _write_contract(output, result)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_staging.completed",
                "path": str(output),
                "package_path": result.package_path,
                "manifest_sha256": result.manifest.manifest_sha256,
                "archive_sha256": result.manifest.intent.archive_sha256,
                "action": result.manifest.intent.action,
                "already_present": result.already_present,
                "quarantine_staged": result.manifest.quarantine_staged,
                "installation_authorized": result.installation_authorized,
                "activation_authorized": result.activation_authorized,
                "configuration_mutation_authorized": (
                    result.configuration_mutation_authorized
                ),
            }
        )
    )
    return 0


def _load_skill_installation_runtime(
    args: argparse.Namespace,
) -> tuple[
    AuthenticatedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillStagingStore,
    SkillInstallationAuthorityPolicy,
]:
    authenticated_control = AuthenticatedSkillReleaseControl.model_validate_json(
        read_bounded(cast(Path, args.authenticated_control), 8_000_000)
    )
    anchor = SkillReleaseControlAnchor(cast(Path, args.control_anchor))
    staging_store = SkillStagingStore(cast(Path, args.staging_store))
    installation_policy = SkillInstallationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.installation_authority_policy), 64_000)
    )
    return authenticated_control, anchor, staging_store, installation_policy


def _derive_skill_installation_command(args: argparse.Namespace) -> int:
    (
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control_authorities,
        _rollback_archive,
    ) = _load_skill_release_control_sources(args)
    control, anchor, staging_store, installation_policy = (
        _load_skill_installation_runtime(args)
    )
    decision = make_skill_installation_decision(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control,
        control_authorities,
        anchor,
        staging_store,
        installation_policy,
        cast(Literal["candidate", "rollback"], args.action),
        cast(datetime, args.issued_at),
        cast(datetime, args.valid_until),
    )
    output = cast(Path, args.output)
    _write_contract(output, decision)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_installation.derived",
                "path": str(output),
                "decision_sha256": decision.decision_sha256,
                "staging_manifest_sha256": decision.staging_manifest_sha256,
                "archive_sha256": decision.archive_sha256,
                "action": decision.action,
                "valid_until": decision.valid_until.isoformat(),
                "one_use_required": decision.one_use_required,
                "authenticated": False,
                "installation_authorized": decision.installation_authorized,
                "activation_authorized": decision.activation_authorized,
                "configuration_mutation_authorized": (
                    decision.configuration_mutation_authorized
                ),
            }
        )
    )
    return 0


def _authenticate_skill_installation_command(args: argparse.Namespace) -> int:
    (
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control_authorities,
        _rollback_archive,
    ) = _load_skill_release_control_sources(args)
    control, anchor, staging_store, installation_policy = (
        _load_skill_installation_runtime(args)
    )
    signed = SignedSkillInstallationDecision.model_validate_json(
        read_bounded(cast(Path, args.signed_installation), 256_000)
    )
    authorization = authenticate_skill_installation(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control,
        control_authorities,
        anchor,
        staging_store,
        signed,
        installation_policy,
        cast(Literal["candidate", "rollback"], args.action),
        datetime.now(UTC),
    )
    output = cast(Path, args.output)
    _write_contract(output, authorization)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_installation.authenticated",
                "path": str(output),
                "authorization_sha256": authorization.authorization_sha256,
                "decision_sha256": signed.decision.decision_sha256,
                "signer_id": signed.signature.signer_id,
                "archive_sha256": authorization.archive_sha256,
                "valid_until": authorization.valid_until.isoformat(),
                "one_use_required": authorization.one_use_required,
                "installation_authorized": authorization.installation_authorized,
                "installation_performed": authorization.installation_performed,
                "activation_authorized": authorization.activation_authorized,
                "configuration_mutation_authorized": (
                    authorization.configuration_mutation_authorized
                ),
            }
        )
    )
    return 0


def _skill_installation_claim_store_create_command(args: argparse.Namespace) -> int:
    store_policy = SkillInstallationClaimStorePolicy.model_validate_json(
        read_bounded(cast(Path, args.store_policy), 64_000)
    )
    authority_policy = SkillInstallationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.installation_authority_policy), 64_000)
    )
    store = SkillInstallationClaimStore.create(
        cast(Path, args.path), store_policy, authority_policy
    )
    snapshot = store.snapshot(authority_policy)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_installation.claim_store_created",
                "path": str(store.path),
                "store_id": snapshot.policy.store_id,
                "store_policy_sha256": snapshot.policy.policy_sha256,
                "claims": len(snapshot.claims),
                "installation_performed": False,
                "activation_authorized": False,
                "configuration_mutation_authorized": False,
            }
        )
    )
    return 0


def _skill_installation_claim_store_status_command(args: argparse.Namespace) -> int:
    authority_policy = SkillInstallationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.installation_authority_policy), 64_000)
    )
    store = SkillInstallationClaimStore(cast(Path, args.store))
    snapshot = store.snapshot(authority_policy)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_installation.claim_store_status",
                "path": str(store.path),
                "store_id": snapshot.policy.store_id,
                "snapshot_sha256": snapshot.snapshot_sha256,
                "claims": [item.model_dump(mode="json") for item in snapshot.claims],
                "installation_performed": False,
                "activation_authorized": False,
                "configuration_mutation_authorized": False,
            }
        )
    )
    return 0


def _skill_installed_store_create_command(args: argparse.Namespace) -> int:
    store_policy = SkillInstalledStorePolicy.model_validate_json(
        read_bounded(cast(Path, args.store_policy), 64_000)
    )
    installation_policy = SkillInstallationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.installation_authority_policy), 64_000)
    )
    staging_store = SkillStagingStore(cast(Path, args.staging_store))
    claim_store_policy = SkillInstallationClaimStorePolicy.model_validate_json(
        read_bounded(cast(Path, args.claim_store_policy), 64_000)
    )
    store = SkillInstalledStore.create(
        cast(Path, args.path),
        store_policy,
        installation_policy,
        staging_store,
        claim_store_policy,
    )
    snapshot = store.snapshot(installation_policy)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_installation.store_created",
                "path": str(store.root),
                "store_id": snapshot.policy.store_id,
                "store_policy_sha256": snapshot.policy.policy_sha256,
                "packages": len(snapshot.packages),
                "incomplete_transactions": len(snapshot.incomplete),
                "default_changed": False,
                "configuration_mutation_authorized": False,
                "activation_authorized": False,
                "runtime_lookup_authorized": False,
            }
        )
    )
    return 0


def _skill_installed_store_status_command(args: argparse.Namespace) -> int:
    installation_policy = SkillInstallationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.installation_authority_policy), 64_000)
    )
    store = SkillInstalledStore(cast(Path, args.store))
    snapshot = store.snapshot(installation_policy)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_installation.store_status",
                "path": str(store.root),
                "store_id": snapshot.policy.store_id,
                "snapshot_sha256": snapshot.snapshot_sha256,
                "packages": list(snapshot.packages),
                "incomplete_transactions": [
                    item.model_dump(mode="json") for item in snapshot.incomplete
                ],
                "default_changed": False,
                "configuration_mutation_authorized": False,
                "activation_authorized": False,
                "runtime_lookup_authorized": False,
            }
        )
    )
    return 0


def _skill_install_recovery_status_command(args: argparse.Namespace) -> int:
    installation_policy = SkillInstallationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.installation_authority_policy), 64_000)
    )
    installed_store = SkillInstalledStore(cast(Path, args.installed_store))
    claim_store = SkillInstallationClaimStore(cast(Path, args.claim_store))
    snapshot = inspect_skill_install_recovery(
        installed_store,
        installation_policy,
        claim_store,
    )
    print(
        json.dumps(
            {
                "type": "evaluation.skill_installation.recovery_status",
                "installed_store": str(installed_store.root),
                "claim_store": str(claim_store.path),
                "snapshot_sha256": snapshot.snapshot_sha256,
                "entries": [item.model_dump(mode="json") for item in snapshot.entries],
                "unbound_transactions": list(snapshot.unbound_transactions),
                "automatic_recovery_authorized": (
                    snapshot.automatic_recovery_authorized
                ),
                "cleanup_authorized": snapshot.cleanup_authorized,
                "default_mutation_authorized": (snapshot.default_mutation_authorized),
                "configuration_mutation_authorized": (
                    snapshot.configuration_mutation_authorized
                ),
                "runtime_lookup_authorized": snapshot.runtime_lookup_authorized,
            }
        )
    )
    return 0


def _install_skill_release_command(args: argparse.Namespace) -> int:
    (
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control_authorities,
        _rollback_archive,
    ) = _load_skill_release_control_sources(args)
    control, anchor, staging_store, installation_policy = (
        _load_skill_installation_runtime(args)
    )
    authorization = AuthenticatedSkillInstallation.model_validate_json(
        read_bounded(cast(Path, args.authenticated_installation), 256_000)
    )
    claim_store = SkillInstallationClaimStore(cast(Path, args.claim_store))
    installed_store = SkillInstalledStore(cast(Path, args.installed_store))
    result = install_authenticated_skill_release(
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control,
        control_authorities,
        anchor,
        staging_store,
        authorization,
        installation_policy,
        claim_store,
        installed_store,
        cast(Literal["candidate", "rollback"], args.action),
        datetime.now(UTC),
    )
    output = cast(Path, args.output)
    _write_contract(output, result)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_installation.completed",
                "path": str(output),
                "package_path": result.package_path,
                "manifest_sha256": result.manifest.manifest_sha256,
                "archive_sha256": result.manifest.intent.archive_sha256,
                "decision_sha256": result.claim.decision_sha256,
                "installation_performed": result.installation_performed,
                "default_changed": result.default_changed,
                "configuration_mutation_authorized": (
                    result.configuration_mutation_authorized
                ),
                "activation_authorized": result.activation_authorized,
                "runtime_lookup_authorized": result.runtime_lookup_authorized,
            }
        )
    )
    return 0


def _load_skill_default_runtime(
    args: argparse.Namespace,
) -> tuple[
    AuthenticatedSkillReleaseControl,
    SkillReleaseControlAnchor,
    SkillInstalledStore,
    SkillInstallationAuthorityPolicy,
    SkillDefaultStore,
    SkillDefaultAuthorityPolicy,
]:
    control = AuthenticatedSkillReleaseControl.model_validate_json(
        read_bounded(cast(Path, args.authenticated_control), 8_000_000)
    )
    anchor = SkillReleaseControlAnchor(cast(Path, args.control_anchor))
    installed_store = SkillInstalledStore(cast(Path, args.installed_store))
    installation_policy = SkillInstallationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.installation_authority_policy), 64_000)
    )
    default_store = SkillDefaultStore(cast(Path, args.default_store))
    default_policy = SkillDefaultAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.default_authority_policy), 64_000)
    )
    return (
        control,
        anchor,
        installed_store,
        installation_policy,
        default_store,
        default_policy,
    )


type SkillDefaultSources = tuple[
    EvaluationDataset,
    SweepPlan,
    SkillEvaluationLineage,
    SkillEvaluationLineage,
    SealedSkillComparison,
    SkillHoldoutUseClaim,
    SkillComparisonReport,
    SkillComparisonReport,
    AuthenticatedSkillPromotion,
    SkillPromotionAuthorityPolicy,
    SkillPackageArchive,
    SkillReleaseEvidence,
    AuthenticatedSkillReleaseControl,
    SkillReleaseControlAuthorityPolicy,
    SkillReleaseControlAnchor,
    SkillInstalledStore,
    SkillInstallationAuthorityPolicy,
]
type SkillDefaultRuntime = tuple[SkillDefaultStore, SkillDefaultAuthorityPolicy]


def _skill_default_sources(
    args: argparse.Namespace,
) -> tuple[SkillDefaultSources, SkillDefaultRuntime]:
    (
        dataset,
        plan,
        calibration,
        holdout,
        sealed,
        claim,
        calibration_report,
        holdout_report,
        promotion,
        promotion_authorities,
        archive,
        evidence,
        control_authorities,
        _rollback_archive,
    ) = _load_skill_release_control_sources(args)
    (
        control,
        anchor,
        installed_store,
        installation_policy,
        default_store,
        default_policy,
    ) = _load_skill_default_runtime(args)
    return (
        (
            dataset,
            plan,
            calibration,
            holdout,
            sealed,
            claim,
            calibration_report,
            holdout_report,
            promotion,
            promotion_authorities,
            archive,
            evidence,
            control,
            control_authorities,
            anchor,
            installed_store,
            installation_policy,
        ),
        (default_store, default_policy),
    )


def _derive_skill_default_command(args: argparse.Namespace) -> int:
    sources, (default_store, default_policy) = _skill_default_sources(args)
    decision = make_skill_default_decision(  # type: ignore[arg-type]
        *sources,
        default_store,
        default_policy,
        cast(Literal["candidate", "rollback"], args.action),
        cast(datetime, args.issued_at),
        cast(datetime, args.valid_until),
    )
    output = cast(Path, args.output)
    _write_contract(output, decision)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_default.derived",
                "path": str(output),
                "decision_sha256": decision.decision_sha256,
                "sequence": decision.sequence,
                "expected_previous_pointer_sha256": (
                    decision.expected_previous_pointer_sha256
                ),
                "installed_manifest_sha256": decision.installed_manifest_sha256,
                "archive_sha256": decision.archive_sha256,
                "action": decision.action,
                "valid_until": decision.valid_until.isoformat(),
                "one_use_required": decision.one_use_required,
                "default_pointer_mutation_authorized": (
                    decision.default_pointer_mutation_authorized
                ),
                "default_changed": False,
                "other_configuration_mutation_authorized": (
                    decision.other_configuration_mutation_authorized
                ),
                "activation_authorized": decision.activation_authorized,
                "runtime_lookup_authorized": decision.runtime_lookup_authorized,
            }
        )
    )
    return 0


def _authenticate_skill_default_command(args: argparse.Namespace) -> int:
    sources, (default_store, default_policy) = _skill_default_sources(args)
    signed = SignedSkillDefaultDecision.model_validate_json(
        read_bounded(cast(Path, args.signed_default), 256_000)
    )
    authorization = authenticate_skill_default(  # type: ignore[arg-type]
        *sources,
        default_store,
        signed,
        default_policy,
        cast(Literal["candidate", "rollback"], args.action),
        datetime.now(UTC),
    )
    output = cast(Path, args.output)
    _write_contract(output, authorization)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_default.authenticated",
                "path": str(output),
                "authorization_sha256": authorization.authorization_sha256,
                "decision_sha256": signed.decision.decision_sha256,
                "signer_id": signed.signature.signer_id,
                "sequence": signed.decision.sequence,
                "archive_sha256": authorization.archive_sha256,
                "valid_until": authorization.valid_until.isoformat(),
                "one_use_required": authorization.one_use_required,
                "default_pointer_mutation_authorized": (
                    authorization.default_pointer_mutation_authorized
                ),
                "default_changed": authorization.default_changed,
                "other_configuration_mutation_authorized": (
                    authorization.other_configuration_mutation_authorized
                ),
                "activation_authorized": authorization.activation_authorized,
                "runtime_lookup_authorized": authorization.runtime_lookup_authorized,
            }
        )
    )
    return 0


def _skill_default_store_create_command(args: argparse.Namespace) -> int:
    store_policy = SkillDefaultStorePolicy.model_validate_json(
        read_bounded(cast(Path, args.store_policy), 64_000)
    )
    default_policy = SkillDefaultAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.default_authority_policy), 64_000)
    )
    installed_store = SkillInstalledStore(cast(Path, args.installed_store))
    store = SkillDefaultStore.create(
        cast(Path, args.path), store_policy, default_policy, installed_store
    )
    print(
        json.dumps(
            {
                "type": "evaluation.skill_default.store_created",
                "path": str(store.path),
                "store_id": store.policy.store_id,
                "store_policy_sha256": store.policy.policy_sha256,
                "revisions": 0,
                "current": None,
                "atomic_commit": True,
                "default_changed": False,
                "other_configuration_mutation_authorized": False,
                "runtime_lookup_authorized": False,
                "activation_authorized": False,
            }
        )
    )
    return 0


def _skill_default_store_status_command(args: argparse.Namespace) -> int:
    default_policy = SkillDefaultAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.default_authority_policy), 64_000)
    )
    installation_policy = SkillInstallationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.installation_authority_policy), 64_000)
    )
    installed_store = SkillInstalledStore(cast(Path, args.installed_store))
    store = SkillDefaultStore(cast(Path, args.store))
    snapshot = store.snapshot(default_policy, installed_store, installation_policy)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_default.store_status",
                "path": str(store.path),
                "store_id": store.policy.store_id,
                "snapshot_sha256": snapshot.snapshot_sha256,
                "revisions": snapshot.revisions,
                "current": (
                    snapshot.current.model_dump(mode="json")
                    if snapshot.current is not None
                    else None
                ),
                "atomic_commit": snapshot.atomic_commit,
                "automatic_recovery_required": (snapshot.automatic_recovery_required),
                "default_changed": snapshot.default_changed,
                "other_configuration_mutation_authorized": (
                    snapshot.other_configuration_mutation_authorized
                ),
                "runtime_lookup_authorized": snapshot.runtime_lookup_authorized,
                "activation_authorized": snapshot.activation_authorized,
            }
        )
    )
    return 0


def _select_skill_default_command(args: argparse.Namespace) -> int:
    sources, (default_store, default_policy) = _skill_default_sources(args)
    authorization = AuthenticatedSkillDefault.model_validate_json(
        read_bounded(cast(Path, args.authenticated_default), 256_000)
    )
    result = select_authenticated_skill_default(  # type: ignore[arg-type]
        *sources,
        default_store,
        authorization,
        default_policy,
        cast(Literal["candidate", "rollback"], args.action),
        datetime.now(UTC),
    )
    output = cast(Path, args.output)
    _write_contract(output, result)
    print(
        json.dumps(
            {
                "type": "evaluation.skill_default.selected",
                "path": str(output),
                "pointer_sha256": result.pointer.pointer_sha256,
                "sequence": result.pointer.sequence,
                "previous_pointer_sha256": result.pointer.previous_pointer_sha256,
                "archive_sha256": result.pointer.archive_sha256,
                "skill": result.pointer.skill.model_dump(mode="json"),
                "authorization_consumed": result.authorization_consumed,
                "default_changed": result.default_changed,
                "atomic_commit": result.atomic_commit,
                "other_configuration_mutation_authorized": (
                    result.other_configuration_mutation_authorized
                ),
                "activation_authorized": result.activation_authorized,
                "runtime_lookup_authorized": result.runtime_lookup_authorized,
            }
        )
    )
    return 0


def _seal_routing_study_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    manifest = PromptFeatureManifest.model_validate_json(
        read_bounded(cast(Path, args.feature_manifest), 16_000_000)
    )
    protocol = RoutingStudyProtocol.model_validate_json(
        read_bounded(cast(Path, args.protocol), 1_000_000)
    )
    artifact = seal_routing_study(dataset, plan, manifest, protocol)
    output = cast(Path, args.output)
    _write_contract(output, artifact)
    print(
        json.dumps(
            {
                "type": "evaluation.routing_study.sealed",
                "path": str(output),
                "sealed_study_sha256": artifact.sealed_study_sha256,
                "protocol_sha256": artifact.protocol_sha256,
                "profiles": len(artifact.profile_ids),
                "activation_authorized": artifact.activation_authorized,
            }
        )
    )
    return 0


def _score_routing_calibration_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    batch = ExecutionBatch.model_validate_json(
        read_bounded(cast(Path, args.batch), 16_000_000)
    )
    mapping = BlindingMap.model_validate_json(
        read_bounded(cast(Path, args.mapping), 16_000_000)
    )
    raw_results = RawResultSet.model_validate_json(
        read_bounded(cast(Path, args.raw_results), 16_000_000)
    )
    grading_batch = GradingBatch.model_validate_json(
        read_bounded(cast(Path, args.grading_batch), 16_000_000)
    )
    dual_grading = DualGradingResolution.model_validate_json(
        read_bounded(cast(Path, args.dual_grading_resolution), 16_000_000)
    )
    observations = DualGradedObservationSet.model_validate_json(
        read_bounded(cast(Path, args.dual_graded_observations), 16_000_000)
    )
    grading_policy = GradingTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.grading_trust_policy), 64_000)
    )
    resolution_policy = ResolutionTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.resolution_trust_policy), 64_000)
    )
    manifest = PromptFeatureManifest.model_validate_json(
        read_bounded(cast(Path, args.feature_manifest), 16_000_000)
    )
    sealed_study = SealedRoutingStudy.model_validate_json(
        read_bounded(cast(Path, args.sealed_study), 2_000_000)
    )
    report = score_routing_calibration(
        dataset,
        plan,
        batch,
        mapping,
        raw_results,
        grading_batch,
        dual_grading,
        grading_policy,
        resolution_policy,
        observations,
        manifest,
        sealed_study,
    )
    output = cast(Path, args.output)
    _write_contract(output, report)
    print(
        json.dumps(
            {
                "type": "evaluation.routing_calibration.scored",
                "path": str(output),
                "calibration_report_sha256": report.calibration_report_sha256,
                "profiles": len(report.profiles),
                "eligible_profile_routes": sum(
                    score.eligible
                    for profile in report.profiles
                    for score in profile.scores
                ),
                "promotion_ready": report.promotion_ready,
                "activation_authorized": report.activation_authorized,
            }
        )
    )
    return 0


def _freeze_routing_policy_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    batch = ExecutionBatch.model_validate_json(
        read_bounded(cast(Path, args.batch), 16_000_000)
    )
    mapping = BlindingMap.model_validate_json(
        read_bounded(cast(Path, args.mapping), 16_000_000)
    )
    raw_results = RawResultSet.model_validate_json(
        read_bounded(cast(Path, args.raw_results), 16_000_000)
    )
    grading_batch = GradingBatch.model_validate_json(
        read_bounded(cast(Path, args.grading_batch), 16_000_000)
    )
    dual_grading = DualGradingResolution.model_validate_json(
        read_bounded(cast(Path, args.dual_grading_resolution), 16_000_000)
    )
    observations = DualGradedObservationSet.model_validate_json(
        read_bounded(cast(Path, args.dual_graded_observations), 16_000_000)
    )
    grading_policy = GradingTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.grading_trust_policy), 64_000)
    )
    resolution_policy = ResolutionTrustPolicy.model_validate_json(
        read_bounded(cast(Path, args.resolution_trust_policy), 64_000)
    )
    manifest = PromptFeatureManifest.model_validate_json(
        read_bounded(cast(Path, args.feature_manifest), 16_000_000)
    )
    sealed_study = SealedRoutingStudy.model_validate_json(
        read_bounded(cast(Path, args.sealed_study), 2_000_000)
    )
    calibration_report = RoutingCalibrationReport.model_validate_json(
        read_bounded(cast(Path, args.calibration_report), 16_000_000)
    )
    policy = freeze_candidate_routing_policy(
        dataset,
        plan,
        batch,
        mapping,
        raw_results,
        grading_batch,
        dual_grading,
        grading_policy,
        resolution_policy,
        observations,
        manifest,
        sealed_study,
        calibration_report,
    )
    output = cast(Path, args.output)
    _write_contract(output, policy)
    print(
        json.dumps(
            {
                "type": "evaluation.routing_policy.frozen",
                "path": str(output),
                "candidate_policy_sha256": policy.candidate_policy_sha256,
                "profiles": len(policy.decisions),
                "calibrated_routes": sum(
                    item.action == "calibrated_route" for item in policy.decisions
                ),
                "fallbacks": sum(
                    item.action == "role_fallback" for item in policy.decisions
                ),
                "fail_closed": sum(
                    item.action == "fail_closed" for item in policy.decisions
                ),
                "holdout_status": policy.holdout_status,
                "promotion_ready": policy.promotion_ready,
                "activation_authorized": policy.activation_authorized,
            }
        )
    )
    return 0


type RoutingLineage = tuple[
    ExecutionBatch,
    BlindingMap,
    RawResultSet,
    GradingBatch,
    DualGradingResolution,
    GradingTrustPolicy,
    ResolutionTrustPolicy,
    DualGradedObservationSet,
]


def _load_routing_lineage(args: argparse.Namespace, prefix: str) -> RoutingLineage:
    def path(name: str) -> Path:
        return cast(Path, getattr(args, f"{prefix}_{name}"))

    return (
        ExecutionBatch.model_validate_json(read_bounded(path("batch"), 16_000_000)),
        BlindingMap.model_validate_json(read_bounded(path("mapping"), 16_000_000)),
        RawResultSet.model_validate_json(read_bounded(path("raw_results"), 16_000_000)),
        GradingBatch.model_validate_json(
            read_bounded(path("grading_batch"), 16_000_000)
        ),
        DualGradingResolution.model_validate_json(
            read_bounded(path("dual_grading_resolution"), 16_000_000)
        ),
        GradingTrustPolicy.model_validate_json(
            read_bounded(path("grading_trust_policy"), 64_000)
        ),
        ResolutionTrustPolicy.model_validate_json(
            read_bounded(path("resolution_trust_policy"), 64_000)
        ),
        DualGradedObservationSet.model_validate_json(
            read_bounded(path("dual_graded_observations"), 16_000_000)
        ),
    )


type SkillReleaseControlSources = tuple[
    EvaluationDataset,
    SweepPlan,
    SkillEvaluationLineage,
    SkillEvaluationLineage,
    SealedSkillComparison,
    SkillHoldoutUseClaim,
    SkillComparisonReport,
    SkillComparisonReport,
    AuthenticatedSkillPromotion,
    SkillPromotionAuthorityPolicy,
    SkillPackageArchive,
    SkillReleaseEvidence,
    SkillReleaseControlAuthorityPolicy,
    SkillPackageArchive | None,
]


def _load_skill_release_control_sources(
    args: argparse.Namespace,
) -> SkillReleaseControlSources:
    def load(path_name: str, limit: int) -> bytes:
        return read_bounded(cast(Path, getattr(args, path_name)), limit)

    rollback_path = cast(Path | None, args.rollback_archive)
    return (
        EvaluationDataset.model_validate_json(load("dataset", 16_000_000)),
        SweepPlan.model_validate_json(load("plan", 16_000_000)),
        _load_routing_lineage(args, "calibration"),
        _load_routing_lineage(args, "holdout"),
        SealedSkillComparison.model_validate_json(load("sealed_comparison", 2_000_000)),
        SkillHoldoutUseClaim.model_validate_json(load("holdout_use_claim", 64_000)),
        SkillComparisonReport.model_validate_json(
            load("calibration_report", 2_000_000)
        ),
        SkillComparisonReport.model_validate_json(load("holdout_report", 2_000_000)),
        AuthenticatedSkillPromotion.model_validate_json(
            load("promotion_receipt", 128_000)
        ),
        SkillPromotionAuthorityPolicy.model_validate_json(
            load("promotion_authority_policy", 64_000)
        ),
        SkillPackageArchive.model_validate_json(load("archive", 6_000_000)),
        SkillReleaseEvidence.model_validate_json(load("release_evidence", 8_000_000)),
        SkillReleaseControlAuthorityPolicy.model_validate_json(
            load("control_authority_policy", 64_000)
        ),
        (
            SkillPackageArchive.model_validate_json(
                read_bounded(rollback_path, 6_000_000)
            )
            if rollback_path is not None
            else None
        ),
    )


def _evaluate_routing_holdout_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    calibration = _load_routing_lineage(args, "calibration")
    holdout = _load_routing_lineage(args, "holdout")
    manifest = PromptFeatureManifest.model_validate_json(
        read_bounded(cast(Path, args.feature_manifest), 16_000_000)
    )
    sealed_study = SealedRoutingStudy.model_validate_json(
        read_bounded(cast(Path, args.sealed_study), 2_000_000)
    )
    calibration_report = RoutingCalibrationReport.model_validate_json(
        read_bounded(cast(Path, args.calibration_report), 16_000_000)
    )
    policy = FrozenCandidateRoutingPolicy.model_validate_json(
        read_bounded(cast(Path, args.candidate_policy), 16_000_000)
    )
    promotion_policy = RoutingPromotionPolicy.model_validate_json(
        read_bounded(cast(Path, args.promotion_policy), 64_000)
    )
    output = cast(Path, args.output)
    use_directory = cast(Path, args.holdout_use_directory)
    if output.exists():
        raise ValueError("holdout report output already exists")
    if not use_directory.is_dir():
        raise ValueError("holdout use directory must already exist")
    if _paths_overlap(output, use_directory):
        raise ValueError("holdout report and use directory must not overlap")

    claim = make_holdout_use_claim(policy, promotion_policy, *holdout)
    claim_path = claim_holdout_use(use_directory, claim)
    report = evaluate_frozen_routing_policy(
        dataset,
        plan,
        *calibration,
        *holdout,
        manifest,
        sealed_study,
        calibration_report,
        policy,
        promotion_policy,
        claim,
    )
    _write_contract(output, report)
    print(
        json.dumps(
            {
                "type": "evaluation.routing_holdout.evaluated",
                "path": str(output),
                "claim_path": str(claim_path),
                "holdout_report_sha256": report.holdout_report_sha256,
                **report.summary.model_dump(mode="json"),
                "holdout_status": report.holdout_status,
                "promotion_ready": report.promotion_ready,
                "activation_authorized": report.activation_authorized,
            }
        )
    )
    return 0


def _derive_routing_promotion_command(args: argparse.Namespace) -> int:
    promotion_policy = RoutingPromotionPolicy.model_validate_json(
        read_bounded(cast(Path, args.promotion_policy), 64_000)
    )
    report = FrozenPolicyHoldoutReport.model_validate_json(
        read_bounded(cast(Path, args.holdout_report), 32_000_000)
    )
    decision = make_routing_promotion_decision(report, promotion_policy)
    output = cast(Path, args.output)
    _write_contract(output, decision)
    print(
        json.dumps(
            {
                "type": "evaluation.routing_promotion.derived",
                "path": str(output),
                "decision_sha256": decision.decision_sha256,
                "threshold_result": decision.threshold_result,
                "criteria_satisfied": decision.criteria_satisfied,
                "authenticated": False,
                "activation_authorized": decision.activation_authorized,
            }
        )
    )
    return 0


def _authenticate_routing_promotion_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    calibration = _load_routing_lineage(args, "calibration")
    holdout = _load_routing_lineage(args, "holdout")
    manifest = PromptFeatureManifest.model_validate_json(
        read_bounded(cast(Path, args.feature_manifest), 16_000_000)
    )
    sealed_study = SealedRoutingStudy.model_validate_json(
        read_bounded(cast(Path, args.sealed_study), 2_000_000)
    )
    calibration_report = RoutingCalibrationReport.model_validate_json(
        read_bounded(cast(Path, args.calibration_report), 16_000_000)
    )
    policy = FrozenCandidateRoutingPolicy.model_validate_json(
        read_bounded(cast(Path, args.candidate_policy), 16_000_000)
    )
    promotion_policy = RoutingPromotionPolicy.model_validate_json(
        read_bounded(cast(Path, args.promotion_policy), 64_000)
    )
    claim = HoldoutUseClaim.model_validate_json(
        read_bounded(cast(Path, args.holdout_use_claim), 64_000)
    )
    report = FrozenPolicyHoldoutReport.model_validate_json(
        read_bounded(cast(Path, args.holdout_report), 32_000_000)
    )
    signed = SignedRoutingPromotionDecision.model_validate_json(
        read_bounded(cast(Path, args.signed_promotion), 64_000)
    )
    authority_policy = RoutingPromotionAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.authority_policy), 64_000)
    )
    authenticated = authenticate_routing_promotion(
        dataset,
        plan,
        calibration,
        holdout,
        manifest,
        sealed_study,
        calibration_report,
        policy,
        claim,
        report,
        promotion_policy,
        signed,
        authority_policy,
    )
    output = cast(Path, args.output)
    _write_contract(output, authenticated)
    print(
        json.dumps(
            {
                "type": "evaluation.routing_promotion.authenticated",
                "path": str(output),
                "promotion_receipt_sha256": authenticated.promotion_receipt_sha256,
                "signer_id": signed.signature.signer_id,
                "promotion_ready": authenticated.promotion_ready,
                "activation_authorized": authenticated.activation_authorized,
            }
        )
    )
    return 0


def _issue_routing_activation_eligibility_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    calibration = _load_routing_lineage(args, "calibration")
    holdout = _load_routing_lineage(args, "holdout")
    manifest = PromptFeatureManifest.model_validate_json(
        read_bounded(cast(Path, args.feature_manifest), 16_000_000)
    )
    sealed_study = SealedRoutingStudy.model_validate_json(
        read_bounded(cast(Path, args.sealed_study), 2_000_000)
    )
    calibration_report = RoutingCalibrationReport.model_validate_json(
        read_bounded(cast(Path, args.calibration_report), 16_000_000)
    )
    candidate_policy = FrozenCandidateRoutingPolicy.model_validate_json(
        read_bounded(cast(Path, args.candidate_policy), 16_000_000)
    )
    promotion_policy = RoutingPromotionPolicy.model_validate_json(
        read_bounded(cast(Path, args.promotion_policy), 64_000)
    )
    claim = HoldoutUseClaim.model_validate_json(
        read_bounded(cast(Path, args.holdout_use_claim), 64_000)
    )
    holdout_report = FrozenPolicyHoldoutReport.model_validate_json(
        read_bounded(cast(Path, args.holdout_report), 32_000_000)
    )
    promotion = AuthenticatedRoutingPromotion.model_validate_json(
        read_bounded(cast(Path, args.promotion_receipt), 128_000)
    )
    promotion_authorities = RoutingPromotionAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.promotion_authority_policy), 64_000)
    )
    signed_activation_policy = SignedRoutingActivationPolicy.model_validate_json(
        read_bounded(cast(Path, args.signed_activation_policy), 1_000_000)
    )
    signed_snapshot = SignedRoutingOperationalSnapshot.model_validate_json(
        read_bounded(cast(Path, args.signed_operational_snapshot), 2_000_000)
    )
    signed_control = SignedRoutingActivationControl.model_validate_json(
        read_bounded(cast(Path, args.signed_control_state), 2_000_000)
    )
    activation_authorities = RoutingActivationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.activation_authority_policy), 64_000)
    )
    eligibility = issue_routing_activation_eligibility(
        dataset,
        plan,
        calibration,
        holdout,
        manifest,
        sealed_study,
        calibration_report,
        candidate_policy,
        promotion_policy,
        claim,
        holdout_report,
        promotion,
        promotion_authorities,
        signed_activation_policy,
        signed_snapshot,
        signed_control,
        activation_authorities,
        datetime.now(UTC),
    )
    output = cast(Path, args.output)
    _write_contract(output, eligibility)
    print(
        json.dumps(
            {
                "type": "evaluation.routing_activation.eligibility_issued",
                "path": str(output),
                "eligibility_sha256": eligibility.eligibility_sha256,
                "issued_at": eligibility.issued_at.isoformat(),
                "valid_until": eligibility.valid_until.isoformat(),
                "eligible_routes": len(eligibility.eligible_candidate_ids),
                "unavailable_action": eligibility.unavailable_action,
                "allow_model_substitution": eligibility.allow_model_substitution,
                "activation_eligible": eligibility.activation_eligible,
                "runtime_activation_authorized": (
                    eligibility.runtime_activation_authorized
                ),
                "configuration_mutation_authorized": (
                    eligibility.configuration_mutation_authorized
                ),
            }
        )
    )
    return 0


def _routing_control_anchor_create_command(args: argparse.Namespace) -> int:
    activation_authorities = RoutingActivationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.activation_authority_policy), 64_000)
    )
    policy = RoutingControlAnchorPolicy.model_validate_json(
        read_bounded(cast(Path, args.anchor_policy), 64_000)
    )
    anchor = RoutingControlAnchor.create(
        cast(Path, args.path),
        policy,
        activation_authorities,
    )
    snapshot = anchor.snapshot(activation_authorities)
    print(
        json.dumps(
            {
                "type": "evaluation.routing_control.anchor_created",
                "path": str(anchor.path),
                "anchor_id": snapshot.policy.anchor_id,
                "anchor_policy_sha256": snapshot.policy.policy_sha256,
                "entries": snapshot.entries,
            }
        )
    )
    return 0


def _routing_control_anchor_advance_command(args: argparse.Namespace) -> int:
    activation_authorities = RoutingActivationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.activation_authority_policy), 64_000)
    )
    signed_control = SignedRoutingActivationControl.model_validate_json(
        read_bounded(cast(Path, args.signed_control_state), 2_000_000)
    )
    anchor = RoutingControlAnchor(cast(Path, args.anchor))
    snapshot = anchor.advance(
        signed_control,
        activation_authorities,
        datetime.now(UTC),
    )
    latest = snapshot.latest
    if latest is None:
        raise ValueError("routing control anchor advance produced no state")
    print(
        json.dumps(
            {
                "type": "evaluation.routing_control.anchor_advanced",
                "path": str(anchor.path),
                "anchor_id": snapshot.policy.anchor_id,
                "anchor_entry_sha256": latest.anchor_entry_sha256,
                "sequence": latest.signed_control.control.sequence,
                "emergency_stop": latest.signed_control.control.emergency_stop,
                "valid_until": latest.signed_control.control.valid_until.isoformat(),
                "entries": snapshot.entries,
            }
        )
    )
    return 0


def _routing_control_anchor_status_command(args: argparse.Namespace) -> int:
    activation_authorities = RoutingActivationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.activation_authority_policy), 64_000)
    )
    anchor = RoutingControlAnchor(cast(Path, args.anchor))
    snapshot = anchor.snapshot(activation_authorities)
    latest = snapshot.latest
    print(
        json.dumps(
            {
                "type": "evaluation.routing_control.anchor_status",
                "path": str(anchor.path),
                "anchor_id": snapshot.policy.anchor_id,
                "anchor_policy_sha256": snapshot.policy.policy_sha256,
                "entries": snapshot.entries,
                "latest_entry_sha256": (
                    latest.anchor_entry_sha256 if latest is not None else None
                ),
                "latest_sequence": (
                    latest.signed_control.control.sequence
                    if latest is not None
                    else None
                ),
                "emergency_stop": (
                    latest.signed_control.control.emergency_stop
                    if latest is not None
                    else None
                ),
                "valid_until": (
                    latest.signed_control.control.valid_until.isoformat()
                    if latest is not None
                    else None
                ),
            }
        )
    )
    return 0


def _routing_runtime_preflight_command(args: argparse.Namespace) -> int:
    dataset = EvaluationDataset.model_validate_json(
        read_bounded(cast(Path, args.dataset), 16_000_000)
    )
    plan = SweepPlan.model_validate_json(
        read_bounded(cast(Path, args.plan), 16_000_000)
    )
    calibration = _load_routing_lineage(args, "calibration")
    holdout = _load_routing_lineage(args, "holdout")
    manifest = PromptFeatureManifest.model_validate_json(
        read_bounded(cast(Path, args.feature_manifest), 16_000_000)
    )
    sealed_study = SealedRoutingStudy.model_validate_json(
        read_bounded(cast(Path, args.sealed_study), 2_000_000)
    )
    calibration_report = RoutingCalibrationReport.model_validate_json(
        read_bounded(cast(Path, args.calibration_report), 16_000_000)
    )
    candidate_policy = FrozenCandidateRoutingPolicy.model_validate_json(
        read_bounded(cast(Path, args.candidate_policy), 16_000_000)
    )
    promotion_policy = RoutingPromotionPolicy.model_validate_json(
        read_bounded(cast(Path, args.promotion_policy), 64_000)
    )
    claim = HoldoutUseClaim.model_validate_json(
        read_bounded(cast(Path, args.holdout_use_claim), 64_000)
    )
    holdout_report = FrozenPolicyHoldoutReport.model_validate_json(
        read_bounded(cast(Path, args.holdout_report), 32_000_000)
    )
    promotion = AuthenticatedRoutingPromotion.model_validate_json(
        read_bounded(cast(Path, args.promotion_receipt), 128_000)
    )
    promotion_authorities = RoutingPromotionAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.promotion_authority_policy), 64_000)
    )
    signed_activation_policy = SignedRoutingActivationPolicy.model_validate_json(
        read_bounded(cast(Path, args.signed_activation_policy), 1_000_000)
    )
    signed_snapshot = SignedRoutingOperationalSnapshot.model_validate_json(
        read_bounded(cast(Path, args.signed_operational_snapshot), 2_000_000)
    )
    signed_control = SignedRoutingActivationControl.model_validate_json(
        read_bounded(cast(Path, args.signed_control_state), 2_000_000)
    )
    activation_authorities = RoutingActivationAuthorityPolicy.model_validate_json(
        read_bounded(cast(Path, args.activation_authority_policy), 64_000)
    )
    eligibility = RoutingActivationEligibility.model_validate_json(
        read_bounded(cast(Path, args.activation_eligibility), 1_000_000)
    )
    anchor = RoutingControlAnchor(cast(Path, args.control_anchor))
    preflight = perform_routing_runtime_preflight(
        dataset,
        plan,
        calibration,
        holdout,
        manifest,
        sealed_study,
        calibration_report,
        candidate_policy,
        promotion_policy,
        claim,
        holdout_report,
        promotion,
        promotion_authorities,
        signed_activation_policy,
        signed_snapshot,
        signed_control,
        activation_authorities,
        eligibility,
        anchor,
        datetime.now(UTC),
    )
    output = cast(Path, args.output)
    _write_contract(output, preflight)
    print(
        json.dumps(
            {
                "type": "evaluation.routing_runtime.preflight_passed",
                "path": str(output),
                "preflight_sha256": preflight.preflight_sha256,
                "checked_at": preflight.checked_at.isoformat(),
                "valid_until": preflight.valid_until.isoformat(),
                "eligible_routes": len(preflight.eligible_candidate_ids),
                "allow_model_substitution": preflight.allow_model_substitution,
                "dispatch_authorized": preflight.dispatch_authorized,
                "runtime_activation_authorized": (
                    preflight.runtime_activation_authorized
                ),
                "configuration_mutation_authorized": (
                    preflight.configuration_mutation_authorized
                ),
            }
        )
    )
    return 0


def _specialized_evaluation_command(args: argparse.Namespace) -> int | None:
    handlers = {
        "eval-authenticate-adjudication": _authenticate_adjudication_command,
        "eval-resolve-adjudications": _resolve_adjudications_command,
        "eval-compile-dual": _compile_dual_command,
        "eval-score-dual": _score_dual_command,
        "eval-seal-skill-comparison": _seal_skill_comparison_command,
        "eval-score-skill-comparison": _score_skill_comparison_command,
        "eval-derive-skill-promotion": _derive_skill_promotion_command,
        "eval-authenticate-skill-promotion": (_authenticate_skill_promotion_command),
        "eval-bind-skill-release-evidence": (_bind_skill_release_evidence_command),
        "eval-derive-skill-release-control": (_derive_skill_release_control_command),
        "eval-authenticate-skill-release-control": (
            _authenticate_skill_release_control_command
        ),
        "skill-release-control-anchor-create": (
            _skill_release_control_anchor_create_command
        ),
        "skill-release-control-anchor-advance": (
            _skill_release_control_anchor_advance_command
        ),
        "skill-release-control-anchor-status": (
            _skill_release_control_anchor_status_command
        ),
        "skill-staging-store-create": _skill_staging_store_create_command,
        "skill-staging-store-status": _skill_staging_store_status_command,
        "eval-stage-skill-release": _stage_skill_release_command,
        "eval-derive-skill-installation": _derive_skill_installation_command,
        "eval-authenticate-skill-installation": (
            _authenticate_skill_installation_command
        ),
        "skill-installation-claim-store-create": (
            _skill_installation_claim_store_create_command
        ),
        "skill-installation-claim-store-status": (
            _skill_installation_claim_store_status_command
        ),
        "skill-installed-store-create": _skill_installed_store_create_command,
        "skill-installed-store-status": _skill_installed_store_status_command,
        "skill-install-recovery-status": _skill_install_recovery_status_command,
        "eval-install-skill-release": _install_skill_release_command,
        "eval-derive-skill-default": _derive_skill_default_command,
        "eval-authenticate-skill-default": _authenticate_skill_default_command,
        "skill-default-store-create": _skill_default_store_create_command,
        "skill-default-store-status": _skill_default_store_status_command,
        "eval-select-skill-default": _select_skill_default_command,
        "eval-seal-routing-study": _seal_routing_study_command,
        "eval-score-routing-calibration": _score_routing_calibration_command,
        "eval-freeze-routing-policy": _freeze_routing_policy_command,
        "eval-evaluate-routing-holdout": _evaluate_routing_holdout_command,
        "eval-derive-routing-promotion": _derive_routing_promotion_command,
        "eval-authenticate-routing-promotion": (
            _authenticate_routing_promotion_command
        ),
        "eval-issue-routing-activation-eligibility": (
            _issue_routing_activation_eligibility_command
        ),
        "routing-control-anchor-create": _routing_control_anchor_create_command,
        "routing-control-anchor-advance": _routing_control_anchor_advance_command,
        "routing-control-anchor-status": _routing_control_anchor_status_command,
        "eval-routing-runtime-preflight": _routing_runtime_preflight_command,
    }
    handler = handlers.get(args.command)
    return handler(args) if handler is not None else None


def _skills_command(args: argparse.Namespace) -> int:
    if args.skill_command == "verify-archive":
        archive = SkillPackageArchive.model_validate_json(
            read_bounded(cast(Path, args.archive), 6_000_000)
        )
        verify_skill_archive(archive)
        print(
            json.dumps(
                {
                    "type": "skill.archive_verified",
                    "path": str(cast(Path, args.archive)),
                    "archive_sha256": archive.archive_sha256,
                    "package_sha256": archive.descriptor.identity.package_sha256,
                    "activation_authorized": archive.activation_authorized,
                    "installation_authorized": archive.installation_authorized,
                    "configuration_mutation_authorized": (
                        archive.configuration_mutation_authorized
                    ),
                },
                sort_keys=True,
            )
        )
        return 0
    catalog = discover_skills(
        user_roots=tuple(cast(list[Path], args.user_root)),
        project_roots=tuple(cast(list[Path], args.project_root)),
    )
    if args.skill_command == "archive":
        archive = catalog.archive(
            cast(str, args.reference),
            allow_project=cast(bool, args.allow_project),
        )
        output = cast(Path, args.output)
        _write_contract(output, archive)
        print(
            json.dumps(
                {
                    "type": "skill.archived",
                    "path": str(output),
                    "archive_sha256": archive.archive_sha256,
                    "package_sha256": archive.descriptor.identity.package_sha256,
                    "activation_authorized": archive.activation_authorized,
                    "installation_authorized": archive.installation_authorized,
                    "configuration_mutation_authorized": (
                        archive.configuration_mutation_authorized
                    ),
                },
                sort_keys=True,
            )
        )
        return 0
    if args.skill_command == "show":
        activated = catalog.activate(
            cast(str, args.reference),
            allow_project=cast(bool, args.allow_project),
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "type": "skill.activated",
                        "descriptor": activated.descriptor.model_dump(mode="json"),
                        "instructions": activated.instructions,
                        "authority_granted": False,
                    },
                    sort_keys=True,
                )
            )
        else:
            print(activated.instructions)
        return 0
    event = {
        "type": (
            "skills.validated"
            if args.skill_command == "validate"
            else "skills.discovered"
        ),
        "skills": [item.model_dump(mode="json") for item in catalog.descriptors],
        "shadowed_names": list(catalog.shadowed_names),
        "authority_granted": False,
    }
    if args.json:
        print(json.dumps(event, sort_keys=True))
    else:
        for descriptor in catalog.descriptors:
            identity = descriptor.identity
            print(
                f"{identity.qualified_reference} {identity.kind} "
                f"{descriptor.package_bytes} bytes"
            )
        if catalog.shadowed_names:
            print("shadowed names: " + ", ".join(catalog.shadowed_names))
        if args.skill_command == "validate":
            print("structurally valid; no trust or authority granted")
    return 0


def _recorded_review_command(args: argparse.Namespace) -> int:
    if args.command == "replay":
        brief, cassette, policy, expected = load_run(cast(Path, args.run))
        actual = asyncio.run(
            review(
                brief,
                tuple(r.critic for r in cassette.critics),
                RecordedReviewer(cassette),
                policy,
            )
        )
        if actual != expected:
            raise ValueError("recorded replay differs from stored result")
        print(
            json.dumps(
                {
                    "type": "replay.verified",
                    "brief_id": brief.brief_id,
                    "decision": actual.verdict.decision,
                }
            )
        )
        return 0
    skill_manifest = None
    if args.command == "demo":
        brief, cassette = demo_inputs()
    else:
        brief = Brief.model_validate_json(read_bounded(cast(Path, args.brief)))
        cassette = Cassette.model_validate_json(
            read_bounded(cast(Path, args.cassette), 16_000_000)
        )
        roster_path = cast(Path | None, args.skill_roster)
        user_skill_roots = tuple(cast(list[Path], args.user_skill_root))
        project_skill_roots = tuple(cast(list[Path], args.project_skill_root))
        allow_project_skills = cast(bool, args.allow_project_skills)
        if roster_path is None and (
            user_skill_roots or project_skill_roots or allow_project_skills
        ):
            raise ValueError("skill options require --skill-roster")
        if roster_path is not None:
            roster = SkillRoster.model_validate_json(read_bounded(roster_path, 64_000))
            catalog = discover_skills(
                user_roots=user_skill_roots,
                project_roots=project_skill_roots,
            )
            skill_manifest = bind_skill_roster(
                cassette,
                roster,
                catalog,
                allow_project=allow_project_skills,
            )
    if brief.brief_id != cassette.brief_id:
        raise ValueError("cassette does not match the supplied brief")
    policy = ReviewPolicy()
    result = asyncio.run(
        review(
            brief,
            tuple(r.critic for r in cassette.critics),
            RecordedReviewer(cassette),
            policy,
        )
    )
    root = cast(Path, args.output)
    path = save_run(
        root,
        brief,
        cassette,
        policy,
        result,
        skill_manifest=skill_manifest,
    )
    try:
        index_run(root, path, result)
    except (OSError, sqlite3.Error):
        print(
            "Index unavailable; complete run artifacts were preserved.",
            file=sys.stderr,
        )
    if args.json:
        print(json.dumps({"type": "run.saved", "mode": "recorded", "path": str(path)}))
        print(json.dumps({"type": "verdict", **result.verdict.model_dump(mode="json")}))
    else:
        print(
            f"Recorded review: {result.verdict.decision} "
            f"({len(result.verdict.findings)} findings)"
        )
        print(f"Artifacts: {path}")
    return EXIT_CODES[result.verdict.decision]


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        specialized_result = _specialized_evaluation_command(args)
        if specialized_result is not None:
            return specialized_result
        if args.command == "skills":
            return _skills_command(args)
        if args.command in {"demo", "review", "replay"}:
            return _recorded_review_command(args)
        if args.command == "openai-conformance":
            if not cast(bool, args.allow_data_transfer):
                raise ValueError("OpenAI data transfer was not acknowledged")
            batch = ExecutionBatch.model_validate_json(
                read_bounded(cast(Path, args.batch), 16_000_000)
            )
            spend_policy = SpendPolicy.model_validate_json(
                read_bounded(cast(Path, args.spend_policy), 64_000)
            )
            spend_policy.check_current()
            ledger = SpendLedger(cast(Path, args.spend_ledger))
            if ledger.snapshot().blocked:
                raise ValueError("shared spending ledger is blocked")
            sample_id = cast(str, args.sample_id)
            payload = build_openai_conformance_payload(batch, sample_id, spend_policy)
            timeout = cast(float, args.timeout)
            container = OfflineContainer(
                cast(Path, args.docker),
                cast(str, args.image),
                cast(Path, args.lifecycle_root),
            )
            # Broker construction independently enforces this bound, but preflight
            # it before credential access or any output is created.
            if not 0 < timeout <= 60:
                raise ValueError("conformance timeout must be between zero and 60")
            audit_directory = cast(Path, args.audit_dir)
            authorization_output = cast(Path, args.authorization_output)
            artifact_output = cast(Path, args.artifact_output)
            if (
                audit_directory.exists()
                or authorization_output.exists()
                or artifact_output.exists()
            ):
                raise ValueError("conformance output already exists")
            if not audit_directory.parent.is_dir():
                raise ValueError("trusted audit parent must already exist")
            if any(
                _paths_overlap(left, right)
                for left, right in (
                    (audit_directory, authorization_output),
                    (audit_directory, artifact_output),
                    (authorization_output, artifact_output),
                )
            ):
                raise ValueError("conformance output paths must not overlap")
            api_key = _openai_api_key()
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not configured")
            budgeted = BudgetedOpenAITransport(
                EphemeralOpenAITransport(api_key, timeout),
                spend_policy,
                audit_directory,
                ledger,
            )
            authorization = authorize_assignment(batch, sample_id, payload, budgeted)
            # This trusted copy is outside the broker-created audit directory and
            # exists before the worker can redeem its single-use capability.
            _write_contract(authorization_output, authorization)
            broker = make_assignment_broker(
                batch,
                sample_id,
                payload,
                budgeted,
                audit_directory,
                lifetime_seconds=timeout,
            )
            reply = run_isolated_broker(broker, container, timeout=timeout)
            artifact = compile_brokered_evaluation(
                reply, authorization, audit_directory, ledger
            )
            _write_contract(artifact_output, artifact)
            print(
                json.dumps(
                    {
                        "type": "openai.conformance.completed",
                        "mode": artifact.mode,
                        "authorization_path": str(authorization_output),
                        "audit_path": str(audit_directory),
                        "artifact_path": str(artifact_output),
                        "lifecycle_path": (
                            str(container.lifecycle_path)
                            if container.lifecycle_path is not None
                            else None
                        ),
                        "artifact_sha256": artifact.artifact_sha256,
                        "provider_request_id": artifact.provider_request_id,
                        "input_tokens": artifact.usage.input,
                        "output_tokens": artifact.usage.output,
                        "latency_ms": artifact.latency_ms,
                        "cost_microusd": artifact.cost_microusd,
                        "promotion_eligible": artifact.promotion_eligible,
                    }
                )
            )
            return 0
        if args.command == "broker-audit-status":
            audit_directory = cast(Path, args.audit_dir)
            expected_path = cast(Path, args.expected_authorization)
            if (
                expected_path.resolve()
                == (audit_directory / "authorization.json").resolve()
            ):
                raise ValueError(
                    "expected authorization must be independently supplied"
                )
            expected = AssignmentAuthorization.model_validate_json(
                read_bounded(expected_path, 4096)
            )
            state = inspect_broker_recovery(
                audit_directory,
                expected,
                SpendLedger(cast(Path, args.spend_ledger)),
            )
            print(
                json.dumps(
                    {
                        "type": "broker.audit.status",
                        **state.model_dump(mode="json"),
                    }
                )
            )
            return 0
        if args.command in ("spend-ledger-create", "spend-ledger-status"):
            ledger = (
                SpendLedger.create(
                    cast(Path, args.path), cast(int, args.ceiling_microusd)
                )
                if args.command == "spend-ledger-create"
                else SpendLedger(cast(Path, args.path))
            )
            print(ledger.snapshot().model_dump_json())
            return 0
        if args.command == "eval-agreement":
            grading = GradingBatch.model_validate_json(
                read_bounded(cast(Path, args.grading_batch), 16_000_000)
            )
            left = AdjudicationSet.model_validate_json(
                read_bounded(cast(Path, args.left), 16_000_000)
            )
            right = AdjudicationSet.model_validate_json(
                read_bounded(cast(Path, args.right), 16_000_000)
            )
            agreement = compare_adjudications(grading, left, right)
            output = cast(Path, args.output)
            _write_contract(output, agreement)
            print(
                json.dumps(
                    {
                        "type": "evaluation.agreement.completed",
                        "path": str(output),
                        "report_sha256": agreement.report_sha256,
                        "compared_findings": agreement.compared_findings,
                        "conflicts": len(agreement.conflicts),
                        "promotion_ready": agreement.promotion_ready,
                    }
                )
            )
            return 0
        if args.command == "eval-blind":
            dataset = EvaluationDataset.model_validate_json(
                read_bounded(cast(Path, args.dataset), 16_000_000)
            )
            plan = SweepPlan.model_validate_json(
                read_bounded(cast(Path, args.plan), 16_000_000)
            )
            split = cast(Split, args.split)
            batch, mapping = make_execution_batch(
                plan, dataset, split, secrets.token_bytes(32)
            )
            batch_output = cast(Path, args.batch_output)
            mapping_output = cast(Path, args.mapping_output)
            if batch_output == mapping_output:
                raise ValueError("batch and mapping outputs must be different files")
            if batch_output.exists() or mapping_output.exists():
                raise ValueError("evaluation output already exists")
            _write_contract(batch_output, batch)
            _write_contract(mapping_output, mapping)
            print(
                json.dumps(
                    {
                        "type": "evaluation.batch.created",
                        "batch_path": str(batch_output),
                        "mapping_path": str(mapping_output),
                        "batch_sha256": batch.batch_sha256,
                        "mapping_sha256": mapping.mapping_sha256,
                        "requests": len(batch.requests),
                    }
                )
            )
            return 0
        if args.command in ("eval-run-recorded", "eval-run-isolated"):
            batch = ExecutionBatch.model_validate_json(
                read_bounded(cast(Path, args.batch), 16_000_000)
            )
            cassette = EvaluationCassette.model_validate_json(
                read_bounded(cast(Path, args.cassette), 16_000_000)
            )
            container: OfflineContainer | None = None
            if args.command == "eval-run-isolated":
                container = OfflineContainer(
                    cast(Path, args.docker),
                    cast(str, args.image),
                    cast(Path, args.lifecycle_root),
                )
                raw_results = run_isolated_recorded(batch, cassette, container)
            else:
                raw_results = run_recorded_evaluation(batch, cassette)
            output = cast(Path, args.output)
            _write_contract(output, raw_results)
            print(
                json.dumps(
                    {
                        "type": "evaluation.execution.completed",
                        "execution_boundary": (
                            "offline_container"
                            if args.command == "eval-run-isolated"
                            else "in_process"
                        ),
                        "image_id": args.image
                        if args.command == "eval-run-isolated"
                        else None,
                        "path": str(output),
                        "lifecycle_path": str(container.lifecycle_path)
                        if container
                        else None,
                        "raw_results_sha256": raw_results.raw_results_sha256,
                        "completed": sum(
                            result.status == "completed"
                            for result in raw_results.results
                        ),
                        "errors": sum(
                            result.status == "error" for result in raw_results.results
                        ),
                    }
                )
            )
            return 0
        if args.command == "eval-grade-packet":
            dataset = EvaluationDataset.model_validate_json(
                read_bounded(cast(Path, args.dataset), 16_000_000)
            )
            plan = SweepPlan.model_validate_json(
                read_bounded(cast(Path, args.plan), 16_000_000)
            )
            batch = ExecutionBatch.model_validate_json(
                read_bounded(cast(Path, args.batch), 16_000_000)
            )
            mapping = BlindingMap.model_validate_json(
                read_bounded(cast(Path, args.mapping), 16_000_000)
            )
            raw_results = RawResultSet.model_validate_json(
                read_bounded(cast(Path, args.raw_results), 16_000_000)
            )
            grading_batch = make_grading_batch(
                dataset, plan, batch, mapping, raw_results
            )
            output = cast(Path, args.output)
            _write_contract(output, grading_batch)
            print(
                json.dumps(
                    {
                        "type": "evaluation.grading_batch.created",
                        "path": str(output),
                        "grading_batch_sha256": grading_batch.grading_batch_sha256,
                        "items": len(grading_batch.items),
                    }
                )
            )
            return 0
        if args.command == "eval-compile":
            dataset = EvaluationDataset.model_validate_json(
                read_bounded(cast(Path, args.dataset), 16_000_000)
            )
            plan = SweepPlan.model_validate_json(
                read_bounded(cast(Path, args.plan), 16_000_000)
            )
            batch = ExecutionBatch.model_validate_json(
                read_bounded(cast(Path, args.batch), 16_000_000)
            )
            mapping = BlindingMap.model_validate_json(
                read_bounded(cast(Path, args.mapping), 16_000_000)
            )
            raw_results = RawResultSet.model_validate_json(
                read_bounded(cast(Path, args.raw_results), 16_000_000)
            )
            grading_batch = GradingBatch.model_validate_json(
                read_bounded(cast(Path, args.grading_batch), 16_000_000)
            )
            adjudication = AdjudicationSet.model_validate_json(
                read_bounded(cast(Path, args.adjudication), 16_000_000)
            )
            observations = compile_observations(
                dataset,
                plan,
                batch,
                mapping,
                raw_results,
                grading_batch,
                adjudication,
            )
            output = cast(Path, args.output)
            _write_contract(output, observations)
            print(
                json.dumps(
                    {
                        "type": "evaluation.observations.compiled",
                        "path": str(output),
                        "observations_sha256": observations.observations_sha256,
                        "observations": len(observations.observations),
                    }
                )
            )
            return 0
        if args.command == "eval-plan":
            dataset = EvaluationDataset.model_validate_json(
                read_bounded(cast(Path, args.dataset), 16_000_000)
            )
            candidates = CandidateGrid.model_validate_json(
                read_bounded(cast(Path, args.candidates))
            )
            gate = EvaluationGate.model_validate_json(
                read_bounded(cast(Path, args.gate))
            )
            plan = make_plan(
                dataset,
                candidates,
                cast(int, args.repetitions),
                cast(int, args.seed),
                gate,
            )
            output = cast(Path, args.output)
            _write_contract(output, plan)
            print(
                json.dumps(
                    {
                        "type": "evaluation.plan.created",
                        "path": str(output),
                        "plan_sha256": plan.plan_sha256,
                        "assignments": len(plan.assignments),
                    }
                )
            )
            return 0
        if args.command == "eval-score":
            dataset = EvaluationDataset.model_validate_json(
                read_bounded(cast(Path, args.dataset), 16_000_000)
            )
            plan = SweepPlan.model_validate_json(
                read_bounded(cast(Path, args.plan), 16_000_000)
            )
            observations = ObservationSet.model_validate_json(
                read_bounded(cast(Path, args.observations), 16_000_000)
            )
            split = cast(Split, args.split)
            report = score(plan, dataset, observations, split)
            output = cast(Path, args.output)
            _write_contract(output, report)
            print(
                json.dumps(
                    {
                        "type": "evaluation.score.created",
                        "path": str(output),
                        "split": split,
                        "eligible": sum(item.eligible for item in report.scores),
                        "promotion_ready": report.promotion_ready,
                    }
                )
            )
            return 0
        if args.command == "models":
            for model in default_registry().models:
                print(model.model_dump_json())
            return 0
        if args.command == "openai-run":
            if not cast(bool, args.allow_data_transfer):
                raise ValueError("OpenAI data transfer was not acknowledged")
            api_key = _openai_api_key()
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not configured")
            policy_path = cast(Path | None, args.spend_policy)
            if policy_path is None:
                raise ValueError("an explicit spending policy is required")
            spend_policy = SpendPolicy.model_validate_json(read_bounded(policy_path))
            spend_policy.check_current()
            if spend_policy.model != args.model:
                raise ValueError("spending policy model mismatch")
            ledger_path = cast(Path | None, args.spend_ledger)
            if ledger_path is None:
                raise ValueError("an explicit shared spending ledger is required")
            ledger = SpendLedger(ledger_path)
            if ledger.snapshot().blocked:
                raise ValueError("shared spending ledger is blocked")
            prompt = _utf8_file(cast(Path, args.prompt), 64_000)
            instructions_path = cast(Path | None, args.instructions)
            instructions = (
                _utf8_file(instructions_path, 64_000)
                if instructions_path is not None
                else ""
            )
            config = AgentConfig(
                provider="openai",
                model=cast(str, args.model),
                effort=cast(Effort, args.effort),
                system=instructions,
                initial_turns=(
                    Turn(
                        role="user",
                        blocks=tuple(
                            TextBlock(text=prompt[index : index + 8000])
                            for index in range(0, len(prompt), 8000)
                        ),
                    ),
                ),
                max_iterations=1,
                max_tool_calls=0,
                budget=BudgetPolicy(max_output_tokens=spend_policy.max_output_tokens),
            )
            session = begin_live_run(cast(Path, args.output), config, spend_policy)
            try:
                result = asyncio.run(
                    _openai_run(
                        config,
                        api_key,
                        session.journal,
                        spend_policy,
                        session.path,
                        ledger,
                    )
                )
                session.complete(result)
            except BaseException:
                session.abort()
                raise
            event = {
                "type": "openai.completed",
                "path": str(session.path),
                "model": result.resolved_model.spec.id,
                "input_tokens": result.usage.billed_input,
                "output_tokens": result.usage.billed_output,
                "cost_upper_bound_microusd": spend_policy.cost(
                    result.usage.billed_input, result.usage.billed_output
                ),
                "spend_policy_sha256": spend_policy.policy_sha256,
                "spend_ledger_id": ledger.policy.ledger_id,
                "text": result.final_text,
            }
            if args.json:
                print(json.dumps(event))
            else:
                print(result.final_text)
                print(f"Artifacts: {session.path}")
            return 0
        if args.command == "agent-replay":
            config, fixtures, cassette, expected_events, expected_result = (
                load_agent_run(cast(Path, args.run))
            )
            client = RecordedAgentClient(cassette)
            journal = MemoryJournal()
            actual = asyncio.run(
                run_agent(
                    config,
                    fixture_registry(),
                    client,
                    FixtureDispatcher(fixtures),
                    journal,
                )
            )
            comparable_actual = (
                actual
                if expected_result.responses
                else actual.model_copy(update={"responses": ()})
            )
            if (
                comparable_actual != expected_result
                or tuple(journal.events) != expected_events
                or not client.exhausted
            ):
                raise ValueError("recorded agent replay differs from stored run")
            print(
                json.dumps(
                    {
                        "type": "agent.replay.verified",
                        "requests": actual.usage.requests,
                        "tools": actual.usage.tools,
                    }
                )
            )
            return 0
        if args.command == "agent-demo":
            config, fixtures, cassette = agent_demo_inputs()
            session = begin_agent_run(
                cast(Path, args.output), config, fixtures, cassette
            )
            try:
                client = RecordedAgentClient(cassette)
                result = asyncio.run(
                    run_agent(
                        config,
                        fixture_registry(),
                        client,
                        FixtureDispatcher(fixtures),
                        session.journal,
                    )
                )
                if not client.exhausted:
                    raise ValueError("recorded agent left unused exchanges")
                session.complete(result)
            except BaseException:
                session.abort()
                raise
            event = {
                "type": "agent.completed",
                "mode": "recorded_agent",
                "path": str(session.path),
                "requests": result.usage.requests,
                "tools": result.usage.tools,
                "text": result.final_text,
            }
            if args.json:
                print(json.dumps(event))
            else:
                print(result.final_text)
                print(f"Artifacts: {session.path}")
            return 0
        raise ValueError("unhandled command")
    except ValidationError:
        # Pydantic diagnostics include raw rejected values; do not echo inputs.
        print("mos-eisley: invalid input schema", file=sys.stderr)
        return 2
    except (AgentFailure, OSError, ProviderError, ValueError) as error:
        print(
            f"mos-eisley: {type(error).__name__}: input or artifact validation failed",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
