"""One independently admitted, operator-approved live review."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import cast

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.operator_review_cli import read_line
from mos_eisley.project_guidance_review import (
    REVIEW_GUIDANCE_BYTES,
    decode_prepared_review,
)
from mos_eisley.project_guidance_role_admission import RoleContextAdmissionStore
from mos_eisley.review_approval_terminal import TerminalReviewApproval
from mos_eisley.run.anthropic_probe import load_anthropic_key
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.operator_review_probe import OperatorReviewIdentity
from mos_eisley.run.review_campaign import (
    CAMPAIGN_BYTES,
    read_campaign_seal,
    write_campaign_export,
)
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
    ReviewConformanceScope,
    SignedReviewConformanceAuthorization,
)
from mos_eisley.run.review_conformance_probe import BrokeredReviewConformanceProbe
from mos_eisley.run.review_credentials import load_review_key
from mos_eisley.run.review_launch import (
    CONFIGURATION_BYTES,
    decode_launch_configuration,
    prepare_review_launch_components,
)
from mos_eisley.run.review_launch_admission import (
    ReviewLaunchAdmissionInputs,
    ReviewLaunchBinding,
    campaign_charged_microusd,
)
from mos_eisley.run.review_launch_authorization import (
    ReviewLaunchAuthorityPolicy,
    SignedReviewLaunchDecision,
)
from mos_eisley.run.spend_ledger import SpendLedger


def add_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--config", type=Path, required=True)
    command.add_argument("--expected-config-sha256", required=True)
    command.add_argument("--identity", type=Path, required=True)
    command.add_argument("-C", "--workspace", type=Path, required=True)
    command.add_argument("--guidance-storage", type=Path, required=True)
    command.add_argument("--prepared", type=Path, required=True)
    command.add_argument("--expected-prepared-sha256", required=True)
    command.add_argument("--guidance-policy", type=Path, required=True)
    command.add_argument("--expected-guidance-policy-sha256", required=True)
    command.add_argument("--spend-ledger", type=Path, required=True)
    command.add_argument("--review-dir", type=Path, required=True)
    command.add_argument("--key-file", type=Path, required=True)
    command.add_argument("--openai-key-file", type=Path)
    command.add_argument("--image-id", required=True)
    command.add_argument("--docker", type=Path)
    command.add_argument("--campaign-dir", type=Path, required=True)
    command.add_argument("--expected-seal-sha256", required=True)
    command.add_argument("--evidence", type=Path, required=True)
    command.add_argument("--expected-evidence-sha256", required=True)
    command.add_argument("--authority-policy", type=Path, required=True)
    command.add_argument("--launch-authority-policy", type=Path, required=True)
    command.add_argument("--launch-scope-output", type=Path)
    command.add_argument("--phase-scope-dir", type=Path)


def _campaign_charge(args: argparse.Namespace) -> int:
    bundle, _ = read_campaign_seal(
        cast(Path, args.campaign_dir), cast(str, args.expected_seal_sha256)
    )
    return campaign_charged_microusd(bundle)


def check_owner_total_cap(
    args: argparse.Namespace, launch_reserved_microusd: int, cap_microusd: int
) -> None:
    if _campaign_charge(args) + launch_reserved_microusd > cap_microusd:
        raise ValueError("campaign plus launch exceeds the selected total cap")


async def _run(args: argparse.Namespace) -> int:
    config_raw = read_bounded(cast(Path, args.config), CONFIGURATION_BYTES)
    evidence_raw = read_bounded(cast(Path, args.evidence), CAMPAIGN_BYTES)
    if (
        digest(config_raw) != args.expected_config_sha256
        or digest(evidence_raw) != args.expected_evidence_sha256
    ):
        raise ValueError("selected live review input changed")
    configuration = decode_launch_configuration(config_raw)
    providers = {
        *(critic.critic.provider for critic in configuration.critics),
        configuration.judge_provider,
    }
    openai_key_path = cast(Path | None, args.openai_key_file)
    if "openai" in providers and openai_key_path is None:
        raise ValueError("signed OpenAI review requires --openai-key-file")
    key_path = cast(Path, args.key_file)
    key_loaders = {"anthropic": lambda: load_review_key(key_path, "anthropic")}
    if openai_key_path is not None:
        key_loaders["openai"] = lambda: load_review_key(openai_key_path, "openai")
    prepared = decode_prepared_review(
        read_bounded(cast(Path, args.prepared), REVIEW_GUIDANCE_BYTES)
    )
    identity = OperatorReviewIdentity.model_validate_json(
        read_bounded(cast(Path, args.identity), 4096)
    )
    ledger = SpendLedger(cast(Path, args.spend_ledger))
    review_dir = cast(Path, args.review_dir)
    envelope, reviewer, _ = prepare_review_launch_components(
        configuration,
        prepared=prepared,
        expected_prepared_sha256=cast(str, args.expected_prepared_sha256),
        workspace=cast(Path, args.workspace),
        guidance_store=RoleContextAdmissionStore(cast(Path, args.guidance_storage)),
        guidance_policy_path=cast(Path, args.guidance_policy),
        expected_guidance_policy_sha256=cast(str, args.expected_guidance_policy_sha256),
        ledger=ledger,
        review_directory=review_dir,
    )

    def check_total_cap() -> None:
        check_owner_total_cap(
            args,
            envelope.envelope.total_reserved_microusd,
            identity.max_total_microusd,
        )

    check_total_cap()
    executable = cast(Path | None, args.docker)
    if executable is None:
        found = shutil.which("docker")
        if found is None:
            raise ValueError("Docker executable is unavailable")
        executable = Path(found)
    executable = executable.resolve()
    lifecycle_root = review_dir.parent / "container-lifecycles"
    containers = tuple(
        OfflineContainer(executable, cast(str, args.image_id), lifecycle_root)
        for _ in envelope.critics
    )
    judge_container = OfflineContainer(
        executable, cast(str, args.image_id), lifecycle_root
    )

    def phase_policy() -> ReviewConformanceAuthorityPolicy:
        check_total_cap()
        return ReviewConformanceAuthorityPolicy.model_validate_json(
            read_bounded(cast(Path, args.authority_policy), 65_536)
        )

    def launch_policy() -> ReviewLaunchAuthorityPolicy:
        return ReviewLaunchAuthorityPolicy.model_validate_json(
            read_bounded(cast(Path, args.launch_authority_policy), 65_536)
        )

    decision_path: Path | None = None

    def load_decision() -> SignedReviewLaunchDecision | None:
        if decision_path is None:
            return None
        return SignedReviewLaunchDecision.model_validate_json(
            read_bounded(decision_path, 16_384)
        )

    async def load_authorization(
        scope: ReviewConformanceScope,
    ) -> SignedReviewConformanceAuthorization | None:
        if args.phase_scope_dir is not None:
            write_campaign_export(
                cast(Path, args.campaign_dir),
                cast(str, args.expected_seal_sha256),
                cast(Path, args.phase_scope_dir) / f"launch-{scope.phase}-scope.json",
                canonical_bytes(scope),
            )
        print(
            json.dumps(
                {
                    "type": "review.live.phase_signature.request",
                    "scope": scope.model_dump(mode="json"),
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        try:
            answer = await read_line("Signed phase authorization file (or cancel): ")
        except EOFError:
            return None
        if answer == "cancel":
            return None
        if not answer or not Path(answer).is_absolute():
            raise ValueError("signed authorization requires an absolute file path")
        return SignedReviewConformanceAuthorization.model_validate_json(
            read_bounded(Path(answer), 16_384)
        )

    probe = BrokeredReviewConformanceProbe(
        envelope,
        reviewer,
        configuration.policy,
        TerminalReviewApproval(read_line, sys.stdout),
        critic_containers=containers,
        judge_container=judge_container,
        authority_policy=phase_policy,
        load_authorization=load_authorization,
        load_api_key=lambda: load_anthropic_key(cast(Path, args.key_file)),
        load_api_keys=key_loaders,
        total_seconds=configuration.total_seconds,
        launch=ReviewLaunchAdmissionInputs(
            binding=ReviewLaunchBinding(
                campaign_directory=str(cast(Path, args.campaign_dir).resolve()),
                expected_seal_sha256=cast(str, args.expected_seal_sha256),
                evidence_path=str(cast(Path, args.evidence).resolve()),
                expected_evidence_sha256=cast(str, args.expected_evidence_sha256),
            ),
            configuration=configuration,
            authority_policy=launch_policy,
            load_decision=load_decision,
            owner_total_cap_microusd=identity.max_total_microusd,
        ),
        operator_identity=identity,
    )
    scope = probe.launch_scope
    if scope is None:
        raise ValueError("live launch admission did not produce an exact scope")
    if args.launch_scope_output is not None:
        write_campaign_export(
            cast(Path, args.campaign_dir),
            cast(str, args.expected_seal_sha256),
            cast(Path, args.launch_scope_output),
            canonical_bytes(scope),
        )
    print(
        json.dumps(
            {
                "type": "review.live.launch_decision.request",
                "scope": scope.model_dump(mode="json"),
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    try:
        answer = await read_line("Signed launch decision file (or cancel): ")
    except EOFError:
        return 1
    if answer == "cancel":
        return 1
    if not answer or not Path(answer).is_absolute():
        raise ValueError("signed launch decision requires an absolute file path")
    decision_path = Path(answer)
    result = await probe.run()
    snapshot = ledger.snapshot()
    print(
        json.dumps(
            {
                "type": "review.live.completed",
                "status": "cancelled" if result is None else "completed",
                "review_dir": str(review_dir.resolve()),
                "result_sha256": (
                    None if result is None else digest(canonical_bytes(result))
                ),
                "charged_microusd": snapshot.charged_microusd,
                "unresolved_entries": snapshot.unresolved_entries,
                "launch_decision_sha256": None
                if probe.launch_decision is None
                else digest(canonical_bytes(probe.launch_decision)),
                "global_activation_authorized": False,
            },
            ensure_ascii=True,
        )
    )
    return 0 if result is not None else 1


def run_command(args: argparse.Namespace) -> int:
    try:
        return asyncio.run(_run(args))
    except sqlite3.Error:
        raise ValueError(
            "selected live review spending ledger is unavailable"
        ) from None
