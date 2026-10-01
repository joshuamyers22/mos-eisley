"""Bind one explicit conversation review to the existing signed live-launch CLI."""

from __future__ import annotations

import asyncio
import json
import signal
import sys
from contextlib import suppress
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.conversation_review import ConversationLiveReviewPacket
from mos_eisley.core.models import (
    Contract,
    Digest,
    ReviewResult,
    canonical_bytes,
    digest,
)
from mos_eisley.project_guidance_review import (
    REVIEW_GUIDANCE_BYTES,
    decode_prepared_review,
)
from mos_eisley.review_live_cli import ReviewLiveCompletion
from mos_eisley.run.files import read_bounded
from mos_eisley.run.operator_review_probe import OperatorReviewIdentity
from mos_eisley.run.process import MAX_WIRE_BYTES
from mos_eisley.run.review_campaign import CAMPAIGN_BYTES, read_campaign_seal
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
)
from mos_eisley.run.review_launch import (
    CONFIGURATION_BYTES,
    decode_launch_configuration,
)
from mos_eisley.run.review_launch_authorization import (
    ReviewLaunchAuthorityPolicy,
    SignedReviewLaunchDecision,
    verify_review_launch_decision,
)
from mos_eisley.run.review_verdict import RetainedReviewResult

MAX_LIVE_SELECTION_BYTES = 32_000


class LiveReviewSelection(Contract):
    """Operating paths stay out of saved conversation state."""

    schema_version: Literal[1] = 1
    mode: Literal["conversation_live_review_selection"] = (
        "conversation_live_review_selection"
    )
    config: Path
    expected_config_sha256: Digest
    identity: Path
    workspace: Path
    guidance_storage: Path
    prepared: Path
    expected_prepared_sha256: Digest
    guidance_policy: Path
    expected_guidance_policy_sha256: Digest
    spend_ledger: Path
    review_dir: Path
    key_file: Path
    openai_key_file: Path | None = None
    image_id: str
    docker: Path | None = None
    campaign_dir: Path
    expected_seal_sha256: Digest
    evidence: Path
    expected_evidence_sha256: Digest
    authority_policy: Path
    launch_authority_policy: Path
    completion_output: Path

    @model_validator(mode="after")
    def absolute_paths(self) -> Self:
        for name, value in self.model_dump().items():
            if isinstance(value, Path) and not value.is_absolute():
                raise ValueError(f"live review {name} requires an absolute path")
        if (
            self.review_dir == self.campaign_dir
            or self.completion_output == self.evidence
        ):
            raise ValueError("live review output paths must be distinct")
        return self

    def command(self, selection_sha256: Digest | None = None) -> list[str]:
        args = [
            sys.executable,
            "-c",
            "from mos_eisley.cli import main; raise SystemExit(main())",
            "review-live",
        ]
        for name in type(self).model_fields:
            if name in {"schema_version", "mode"}:
                continue
            value = getattr(self, name)
            if value is not None:
                args.extend(("--" + name.replace("_", "-"), str(value)))
        if selection_sha256 is not None:
            args.extend(("--selection-sha256", selection_sha256))
        return args


def read_selection(path: Path, workspace: Path) -> tuple[LiveReviewSelection, Digest]:
    raw = read_bounded(path, MAX_LIVE_SELECTION_BYTES)
    try:
        json.loads(raw, object_pairs_hook=unique_object)
        selection = LiveReviewSelection.model_validate_json(raw)
    except (ValueError, RecursionError):
        raise ValueError("invalid live review selection") from None
    if selection.workspace.resolve() != workspace.resolve():
        raise ValueError("live review selection differs from conversation workspace")
    config_raw = read_bounded(selection.config, CONFIGURATION_BYTES)
    prepared_raw = read_bounded(selection.prepared, REVIEW_GUIDANCE_BYTES)
    evidence_raw = read_bounded(selection.evidence, CAMPAIGN_BYTES)
    if (
        digest(config_raw) != selection.expected_config_sha256
        or digest(prepared_raw) != selection.expected_prepared_sha256
        or digest(evidence_raw) != selection.expected_evidence_sha256
    ):
        raise ValueError("selected live review inputs changed")
    decode_launch_configuration(config_raw)
    prepared = decode_prepared_review(prepared_raw)
    if prepared.sha256 != selection.expected_prepared_sha256:
        raise ValueError("selected guidance review differs from its hash")
    read_campaign_seal(selection.campaign_dir, selection.expected_seal_sha256)
    return selection, digest(raw)


def select_live_review(path: Path, workspace: Path) -> ConversationLiveReviewPacket:
    selection, manifest_sha256 = read_selection(path, workspace)
    return packet_for_selection(selection, manifest_sha256)


def packet_for_selection(
    selection: LiveReviewSelection, manifest_sha256: Digest
) -> ConversationLiveReviewPacket:
    prepared = decode_prepared_review(
        read_bounded(selection.prepared, REVIEW_GUIDANCE_BYTES)
    )
    return ConversationLiveReviewPacket(
        brief=prepared.brief,
        prepared_sha256=selection.expected_prepared_sha256,
        configuration_sha256=selection.expected_config_sha256,
        campaign_seal_sha256=selection.expected_seal_sha256,
        campaign_evidence_sha256=selection.expected_evidence_sha256,
        manifest_sha256=manifest_sha256,
        guidance_review=prepared,
    )


async def run_selected_live_review(
    packet: ConversationLiveReviewPacket,
    selection_path: Path,
    workspace: Path,
) -> ReviewResult:
    selection, manifest_sha256 = read_selection(selection_path, workspace)
    if (
        manifest_sha256 != packet.manifest_sha256
        or selection.expected_prepared_sha256 != packet.prepared_sha256
        or selection.expected_config_sha256 != packet.configuration_sha256
        or selection.expected_seal_sha256 != packet.campaign_seal_sha256
        or selection.expected_evidence_sha256 != packet.campaign_evidence_sha256
    ):
        raise ValueError("queued live review selection changed")
    prepared = decode_prepared_review(
        read_bounded(selection.prepared, REVIEW_GUIDANCE_BYTES)
    )
    if prepared.brief != packet.brief:
        raise ValueError("queued live review brief changed")
    for output in (selection.review_dir, selection.completion_output):
        if output.exists() or output.is_symlink():
            raise ValueError("live review output path was already used")

    process = await asyncio.create_subprocess_exec(*selection.command(manifest_sha256))
    try:
        status = await process.wait()
    except asyncio.CancelledError:
        await stop_and_reap_live_review(process)
        raise
    if status != 0:
        raise ValueError("operator-approved live review did not complete")
    return load_live_result(selection, packet)


async def stop_and_reap_live_review(process: asyncio.subprocess.Process) -> None:
    """Keep child ownership through repeated caller cancellation."""
    if process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        process.send_signal(signal.SIGINT)
    waiter = asyncio.create_task(process.wait())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 120
    stage = 0
    while not waiter.done():
        remaining = deadline - loop.time()
        if remaining <= 0:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    if stage == 0:
                        process.terminate()
                    else:
                        process.kill()
            stage += 1
            deadline = loop.time() + 30
            continue
        try:
            await asyncio.wait_for(asyncio.shield(waiter), remaining)
        except (asyncio.CancelledError, TimeoutError):
            continue
    await waiter


def load_live_result(
    selection: LiveReviewSelection,
    packet: ConversationLiveReviewPacket,
) -> ReviewResult:
    """Read only the exact successful child receipt and its retained result."""
    completion_raw = read_bounded(selection.completion_output, 4096)
    completion = ReviewLiveCompletion.model_validate_json(completion_raw)
    raw = read_bounded(selection.review_dir / "review-result.json", MAX_WIRE_BYTES)
    if (
        completion_raw != canonical_bytes(completion)
        or completion.review_dir != str(selection.review_dir.resolve())
        or completion.result_sha256 != digest(raw)
        or completion.brief_id != packet.brief.brief_id
        or completion.prepared_sha256 != packet.prepared_sha256
        or completion.selection_sha256 != packet.manifest_sha256
        or selection.expected_config_sha256 != packet.configuration_sha256
        or selection.expected_prepared_sha256 != packet.prepared_sha256
        or selection.expected_seal_sha256 != packet.campaign_seal_sha256
        or selection.expected_evidence_sha256 != packet.campaign_evidence_sha256
    ):
        raise ValueError("live review completion differs from frozen selection")
    config_raw = read_bounded(selection.config, CONFIGURATION_BYTES)
    prepared_raw = read_bounded(selection.prepared, REVIEW_GUIDANCE_BYTES)
    evidence_raw = read_bounded(selection.evidence, CAMPAIGN_BYTES)
    prepared = decode_prepared_review(prepared_raw)
    if (
        digest(config_raw) != packet.configuration_sha256
        or digest(prepared_raw) != packet.prepared_sha256
        or digest(evidence_raw) != packet.campaign_evidence_sha256
        or prepared.brief != packet.brief
    ):
        raise ValueError("live review inputs differ from frozen selection")
    signed_raw = read_bounded(selection.review_dir / "launch-admission.json", 16_384)
    signed = SignedReviewLaunchDecision.model_validate_json(signed_raw)
    launch_policy = ReviewLaunchAuthorityPolicy.model_validate_json(
        read_bounded(selection.launch_authority_policy, 65_536)
    )
    phase_policy = ReviewConformanceAuthorityPolicy.model_validate_json(
        read_bounded(selection.authority_policy, 65_536)
    )
    identity = OperatorReviewIdentity.model_validate_json(
        read_bounded(selection.identity, 4096)
    )
    scope = signed.decision.scope
    if (
        signed_raw != canonical_bytes(signed)
        or digest(signed_raw) != completion.launch_decision_sha256
        or scope.configuration_sha256
        != digest(canonical_bytes(decode_launch_configuration(config_raw)))
        or scope.phase_authority_policy_sha256 != phase_policy.sha256
        or scope.seal_sha256 != packet.campaign_seal_sha256
        or scope.evidence_file_sha256 != packet.campaign_evidence_sha256
        or scope.runtime.image_id != selection.image_id
        or scope.ledger_path != str(selection.spend_ledger.resolve())
        or scope.artifact_directory != str(selection.review_dir.resolve())
        or scope.owner_total_cap_microusd != identity.max_total_microusd
    ):
        raise ValueError("live review launch differs from frozen selection")
    verify_review_launch_decision(
        signed, launch_policy, scope, signed.decision.issued_at
    )
    retained = RetainedReviewResult.model_validate_json(raw)
    if (
        raw != canonical_bytes(retained)
        or retained.result.verdict.brief_id != packet.brief.brief_id
        or retained.result.judge_request is None
        or retained.result.judge_request.brief != packet.brief
    ):
        raise ValueError("retained live review differs from frozen brief")
    return retained.result
