"""Interactive operator-owned Anthropic critic/judge review under a fixed cap."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance_review import (
    REVIEW_GUIDANCE_BYTES,
    decode_prepared_review,
)
from mos_eisley.project_guidance_role_admission import RoleContextAdmissionStore
from mos_eisley.review_approval_terminal import TerminalReviewApproval
from mos_eisley.run.anthropic_probe import load_anthropic_key
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.operator_review_probe import (
    OperatorReviewIdentity,
    OperatorReviewProbe,
)
from mos_eisley.run.review_campaign import (
    CAMPAIGN_BYTES,
    CampaignEvidenceSubmission,
    ReviewCampaignBundle,
    decode_campaign_submission,
    read_campaign_seal,
    review_campaign_evidence,
    write_campaign_export,
)
from mos_eisley.run.review_campaign_dispatch import ReviewCampaignBinding
from mos_eisley.run.review_campaign_runner import CampaignProbeCompletion
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
    ReviewConformanceScope,
    SignedReviewConformanceAuthorization,
)
from mos_eisley.run.review_conformance_probe import BrokeredReviewConformanceProbe
from mos_eisley.run.review_controller_inspection import inspect_review_controller
from mos_eisley.run.review_launch import (
    CONFIGURATION_BYTES,
    decode_launch_configuration,
    prepare_review_launch_components,
)
from mos_eisley.run.spend_ledger import SpendLedger


def add_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--config", type=Path, required=True)
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
    command.add_argument("--image-id", required=True)
    command.add_argument("--docker", type=Path)
    command.add_argument("--campaign-dir", type=Path)
    command.add_argument("--expected-seal-sha256")
    command.add_argument("--campaign-slot", type=int, choices=(0, 1, 2))
    command.add_argument("--authority-policy", type=Path)
    command.add_argument("--completion-output", type=Path)
    command.add_argument("--previous-evidence", type=Path)
    command.add_argument("--expected-previous-evidence-sha256")


async def _read_line(prompt: str) -> str:
    """Wait on terminal input without leaving a blocked reader on cancellation."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()
    sys.stdout.write(prompt)
    sys.stdout.flush()

    def readable() -> None:
        if future.done():
            return
        try:
            line = sys.stdin.readline()
        except OSError as error:
            future.set_exception(error)
            return
        if line:
            future.set_result(line.rstrip("\r\n"))
        else:
            future.set_exception(EOFError())

    fd = sys.stdin.fileno()
    loop.add_reader(fd, readable)
    try:
        return await future
    finally:
        loop.remove_reader(fd)


def verify_operator_campaign_prefix_ledgers(
    bundle: ReviewCampaignBundle,
    prior: CampaignEvidenceSubmission,
    slot: int,
) -> None:
    """Reject unexplained spending or a used future slot before another dispatch."""
    expected: dict[Path, tuple[set[str], int]] = {}
    for attempt, supplied in zip(
        bundle.attempts[:slot], prior.attempts[:slot], strict=True
    ):
        if supplied is None:
            raise ValueError("previous campaign slot is missing")
        path = Path(attempt.ledger_path).resolve()
        ledger = SpendLedger(path)
        inventory = inspect_review_controller(
            Path(attempt.preview.envelope.artifact_directory),
            supplied.start,
            ledger,
            expected_judge_preview_sha256=supplied.judge.sha256,
        )
        if not inventory.spending_inventory_complete or inventory.judge is None:
            raise ValueError("previous campaign spending inventory is incomplete")
        entries, cost = expected.setdefault(path, (set(), 0))
        statuses = (
            *(item.ledger for item in inventory.critics),
            inventory.judge_allowance,
            inventory.judge.ledger,
        )
        if any(item is None or item.entry_id in entries for item in statuses):
            raise ValueError("previous campaign ledger entries are missing or repeated")
        entries.update(item.entry_id for item in statuses if item is not None)
        expected[path] = (entries, cost + inventory.identified_charged_microusd)
    for path in {Path(attempt.ledger_path).resolve() for attempt in bundle.attempts}:
        ledger = SpendLedger(path)
        entries, cost = expected.get(path, (set(), 0))
        snapshot = ledger.snapshot()
        if (
            snapshot.blocked
            or snapshot.unresolved_entries
            or snapshot.entries != len(entries)
            or snapshot.charged_microusd != cost
        ):
            raise ValueError("campaign ledger contains unexplained prior exposure")


def run_command(args: argparse.Namespace) -> int:
    try:
        signed_options = (
            args.campaign_dir,
            args.expected_seal_sha256,
            args.campaign_slot,
            args.authority_policy,
            args.completion_output,
        )
        signed = any(item is not None for item in signed_options)
        if signed and any(item is None for item in signed_options):
            raise ValueError(
                "signed campaign requires all campaign and authority options"
            )
        if not signed and (
            args.previous_evidence is not None
            or args.expected_previous_evidence_sha256 is not None
        ):
            raise ValueError("previous evidence requires a signed campaign slot")
        prior_raw: bytes | None = None
        if signed:
            slot = cast(int, args.campaign_slot)
            campaign_dir = cast(Path, args.campaign_dir)
            output = cast(Path, args.completion_output)
            bundle, _ = read_campaign_seal(
                campaign_dir, cast(str, args.expected_seal_sha256)
            )
            protected = (
                campaign_dir,
                *(
                    Path(attempt.preview.envelope.artifact_directory)
                    for attempt in bundle.attempts
                ),
            )
            if (
                not output.is_absolute()
                or not output.parent.is_dir()
                or output.exists()
                or output.is_symlink()
                or any(
                    output.resolve().is_relative_to(path.resolve())
                    for path in protected
                )
            ):
                raise ValueError(
                    "campaign completion output must be a fresh external file"
                )
            has_prior = args.previous_evidence is not None
            if has_prior != (args.expected_previous_evidence_sha256 is not None):
                raise ValueError("previous evidence requires an exact file hash")
            if has_prior != (slot > 0):
                raise ValueError("later campaign slots require prior verified evidence")
            if slot == 0:
                verify_operator_campaign_prefix_ledgers(
                    bundle,
                    CampaignEvidenceSubmission(
                        seal_sha256=cast(str, args.expected_seal_sha256),
                        attempts=(None, None, None),
                    ),
                    0,
                )
            if has_prior:
                prior_raw = read_bounded(
                    cast(Path, args.previous_evidence), CAMPAIGN_BYTES
                )
                if digest(prior_raw) != args.expected_previous_evidence_sha256:
                    raise ValueError("previous campaign evidence changed")
                prior = decode_campaign_submission(prior_raw)
                if any(item is None for item in prior.attempts[:slot]) or any(
                    item is not None for item in prior.attempts[slot:]
                ):
                    raise ValueError(
                        "previous campaign evidence is not an exact prefix"
                    )
                accepted = review_campaign_evidence(
                    cast(Path, args.campaign_dir),
                    cast(str, args.expected_seal_sha256),
                    prior,
                    now=datetime.now(UTC),
                )
                if accepted.qualifying_attempts != slot:
                    raise ValueError("previous campaign slots are not all accepted")
                verify_operator_campaign_prefix_ledgers(bundle, prior, slot)

        def current_authority() -> ReviewConformanceAuthorityPolicy:
            if prior_raw is not None:
                current = read_bounded(
                    cast(Path, args.previous_evidence), CAMPAIGN_BYTES
                )
                if current != prior_raw:
                    raise ValueError(
                        "previous campaign evidence changed during dispatch"
                    )
            return ReviewConformanceAuthorityPolicy.model_validate_json(
                read_bounded(cast(Path, args.authority_policy), 65_536)
            )

        async def load_authorization(
            scope: ReviewConformanceScope,
        ) -> SignedReviewConformanceAuthorization | None:
            print(
                json.dumps(
                    {
                        "type": "review.campaign.signature.request",
                        "scope": scope.model_dump(mode="json"),
                    },
                    ensure_ascii=True,
                ),
                flush=True,
            )
            try:
                answer = await _read_line(
                    "Signed phase authorization file (or cancel): "
                )
            except EOFError:
                return None
            if answer == "cancel":
                return None
            if not answer or not Path(answer).is_absolute():
                raise ValueError("signed authorization requires an absolute file path")
            return SignedReviewConformanceAuthorization.model_validate_json(
                read_bounded(Path(answer), 16_384)
            )

        identity = OperatorReviewIdentity.model_validate_json(
            read_bounded(cast(Path, args.identity), 4096)
        )
        configuration = decode_launch_configuration(
            read_bounded(cast(Path, args.config), CONFIGURATION_BYTES)
        )
        prepared = decode_prepared_review(
            read_bounded(cast(Path, args.prepared), REVIEW_GUIDANCE_BYTES)
        )
        ledger = SpendLedger(cast(Path, args.spend_ledger))
        if ledger.policy.ceiling_microusd > identity.max_total_microusd:
            raise ValueError("operator ledger ceiling exceeds the selected cap")
        review_dir = cast(Path, args.review_dir)
        envelope, reviewer, _ = prepare_review_launch_components(
            configuration,
            prepared=prepared,
            expected_prepared_sha256=cast(str, args.expected_prepared_sha256),
            workspace=cast(Path, args.workspace),
            guidance_store=RoleContextAdmissionStore(cast(Path, args.guidance_storage)),
            guidance_policy_path=cast(Path, args.guidance_policy),
            expected_guidance_policy_sha256=cast(
                str, args.expected_guidance_policy_sha256
            ),
            ledger=ledger,
            review_directory=review_dir,
        )
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
        key_path = cast(Path, args.key_file)
        if signed:
            campaign = ReviewCampaignBinding(
                campaign_directory=str(cast(Path, args.campaign_dir).resolve()),
                expected_seal_sha256=cast(str, args.expected_seal_sha256),
                attempt_index=cast(int, args.campaign_slot),
            )
            probe = BrokeredReviewConformanceProbe(
                envelope,
                reviewer,
                configuration.policy,
                TerminalReviewApproval(_read_line, sys.stdout),
                critic_containers=containers,
                judge_container=judge_container,
                authority_policy=current_authority,
                load_authorization=load_authorization,
                load_api_key=lambda: load_anthropic_key(key_path),
                total_seconds=configuration.total_seconds,
                campaign=campaign,
                operator_identity=identity,
            )
        else:
            probe = OperatorReviewProbe(
                identity,
                envelope,
                reviewer,
                configuration.policy,
                TerminalReviewApproval(_read_line, sys.stdout),
                critic_containers=containers,
                judge_container=judge_container,
                load_api_key=lambda: load_anthropic_key(key_path),
                total_seconds=configuration.total_seconds,
            )
        result = asyncio.run(probe.run())
        completion_sha256 = None
        if signed and result is not None:
            assert isinstance(probe, BrokeredReviewConformanceProbe)
            start, judge = probe.controller.start, probe.judge_preview
            authorizations, paths = (
                probe.approval_ui.authorizations,
                probe.lifecycle_paths,
            )
            if (
                start is None
                or judge is None
                or len(authorizations) != 2
                or any(path is None for path in paths)
            ):
                raise ValueError(
                    "signed campaign probe lacks complete handoff evidence"
                )
            completion = CampaignProbeCompletion(
                seal_sha256=cast(str, args.expected_seal_sha256),
                attempt_index=cast(int, args.campaign_slot),
                start=start,
                judge=judge,
                authorizations=(authorizations[0], authorizations[1]),
                expected_result_sha256=digest(canonical_bytes(result)),
                lifecycle_directories=tuple(str(path) for path in paths),
            )
            raw = canonical_bytes(completion)
            write_campaign_export(
                cast(Path, args.campaign_dir),
                cast(str, args.expected_seal_sha256),
                cast(Path, args.completion_output),
                raw,
            )
            completion_sha256 = digest(raw)
        print(
            json.dumps(
                {
                    "type": "operator.review.completed",
                    "status": "cancelled" if result is None else "completed",
                    "review_dir": str(review_dir.resolve()),
                    "author_artifact_sha256": identity.author_artifact_sha256,
                    "result_sha256": None
                    if result is None
                    else digest(canonical_bytes(result)),
                    "charged_microusd": ledger.snapshot().charged_microusd,
                    "unresolved_entries": ledger.snapshot().unresolved_entries,
                    "campaign_slot": args.campaign_slot if signed else None,
                    "completion_sha256": completion_sha256,
                    "independent_conformance_claimed": False,
                },
                ensure_ascii=True,
            )
        )
        return 0 if result is not None else 1
    except sqlite3.Error:
        raise ValueError("operator review spending ledger is unavailable") from None
