"""Prepare explicit guidance-bearing briefs and run only recorded reviews."""

import argparse
import asyncio
import json
from pathlib import Path

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Brief, ReviewPolicy
from mos_eisley.project_guidance_review import (
    REVIEW_GUIDANCE_BYTES,
    ReviewGuidanceSelection,
    decode_prepared_review,
    prepare_guidance_review,
    verify_current_review,
)
from mos_eisley.project_guidance_role_admission import RoleContextAdmissionStore
from mos_eisley.providers.recorded import Cassette, RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import save_run


def add_command(command: argparse.ArgumentParser) -> None:
    command.add_argument("action", choices=("prepare", "run"))
    command.add_argument("-C", "--workspace", type=Path, default=Path.cwd())
    command.add_argument("--brief", type=Path)
    command.add_argument("--selection", type=Path)
    command.add_argument("--prepared", type=Path)
    command.add_argument("--expected-prepared-sha256")
    command.add_argument("--cassette", type=Path)
    command.add_argument("--policy", type=Path, required=True)
    command.add_argument("--expected-policy-sha256", required=True)
    command.add_argument("--output", type=Path)
    command.add_argument(
        "--guidance-storage", type=Path, default=Path.home() / ".mos-eisley-guidance"
    )
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    store = RoleContextAdmissionStore(args.guidance_storage)
    if args.action == "prepare":
        if (
            args.brief is None
            or args.selection is None
            or any(
                value is not None
                for value in (
                    args.prepared,
                    args.expected_prepared_sha256,
                    args.cassette,
                    args.output,
                )
            )
        ):
            raise ValueError(
                "Prepare requires only brief, paired selection and policy inputs."
            )
        payload = read_bounded(args.selection, 16 * 1024)
        try:
            payload.decode("utf-8")
            json.loads(payload, object_pairs_hook=unique_object)
            selection = ReviewGuidanceSelection.model_validate_json(payload)
        except (ValueError, RecursionError):
            raise ValueError("Invalid paired review guidance selection.") from None
        source = Brief.model_validate_json(
            read_bounded(args.brief, REVIEW_GUIDANCE_BYTES)
        )
        prepared = prepare_guidance_review(
            store,
            args.workspace,
            selection,
            source,
            args.policy,
            args.expected_policy_sha256,
        )
        print(
            json.dumps(
                {
                    "type": "guidance.review.prepared",
                    "prepared_sha256": prepared.sha256,
                    "prepared": prepared.model_dump(mode="json"),
                },
                ensure_ascii=True,
                indent=None if args.json else 2,
            )
        )
        return 0
    if (
        any(
            value is None
            for value in (
                args.prepared,
                args.expected_prepared_sha256,
                args.cassette,
                args.output,
            )
        )
        or args.brief is not None
        or args.selection is not None
    ):
        raise ValueError(
            "Run requires prepared input/hash, cassette, output and policy inputs."
        )
    prepared = decode_prepared_review(
        read_bounded(args.prepared, REVIEW_GUIDANCE_BYTES)
    )
    if prepared.sha256 != args.expected_prepared_sha256:
        raise ValueError("Prepared review changed; review and select its exact hash.")
    cassette = Cassette.model_validate_json(read_bounded(args.cassette, 16_000_000))
    if cassette.brief_id != prepared.brief.brief_id:
        raise ValueError("Cassette must match the guidance-bearing brief.")
    verify_current_review(
        store, args.workspace, prepared, args.policy, args.expected_policy_sha256
    )
    policy = ReviewPolicy()
    result = asyncio.run(
        review(
            prepared.brief,
            tuple(item.critic for item in cassette.critics),
            RecordedReviewer(cassette),
            policy,
        )
    )
    # Revalidate after offline execution; never hold guidance locks across awaits.
    verify_current_review(
        store, args.workspace, prepared, args.policy, args.expected_policy_sha256
    )
    path = save_run(
        args.output, prepared.brief, cassette, policy, result, guidance_review=prepared
    )
    print(
        json.dumps(
            {
                "type": "guidance.review.saved",
                "mode": "recorded",
                "path": str(path),
                "prepared_sha256": prepared.sha256,
                "brief_id": prepared.brief.brief_id,
                "decision": result.verdict.decision,
                "provider_request_sent": False,
            },
            ensure_ascii=True,
            indent=None if args.json else 2,
        )
    )
    return {"accept": 0, "revise": 1, "reject": 1, "infrastructure_error": 2}[
        result.verdict.decision
    ]
