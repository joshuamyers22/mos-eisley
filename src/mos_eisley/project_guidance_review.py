"""Deterministic shared guidance in an explicit recorded-review brief."""

import json
import os
from contextlib import ExitStack
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Brief, Contract, canonical_bytes, digest
from mos_eisley.project_guidance_role import RoleContext
from mos_eisley.project_guidance_role_admission import (
    RoleContextAdmissionStore,
    RoleContextSelection,
)

REVIEW_GUIDANCE_BYTES = 512 * 1024


class ReviewGuidanceSelection(Contract):
    critic: RoleContextSelection
    judge: RoleContextSelection

    @model_validator(mode="after")
    def paired_roles(self) -> Self:
        if (
            self.critic.role != "critic"
            or self.judge.role != "judge"
            or self.critic.scope != self.judge.scope
        ):
            raise ValueError(
                "Review requires critic/judge packets for the same exact scope."
            )
        return self


def guided_brief(source: Brief, critic: RoleContext, judge: RoleContext) -> Brief:
    shared = critic.model_dump(mode="json", exclude={"role"})
    if (
        critic.role != "critic"
        or judge.role != "judge"
        or shared != judge.model_dump(mode="json", exclude={"role"})
    ):
        raise ValueError(
            "Critic and judge must use identical frozen guidance and rubric."
        )
    block = json.dumps(
        {"kind": "project_guidance_review_constraints", **shared},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return Brief(
        spec=source.spec,
        diff=source.diff,
        constraints=source.constraints
        + "\n\nProject guidance (declarative):\n"
        + block,
    )


class PreparedGuidanceReview(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["prepared_guidance_review"] = "prepared_guidance_review"
    owner_uid: int
    workspace: MappedDirectory
    selection: ReviewGuidanceSelection
    source_brief: Brief
    critic_context: RoleContext
    judge_context: RoleContext
    brief: Brief
    provider_request_sent: Literal[False] = False
    execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exact_projection(self) -> Self:
        if self.owner_uid < 0:
            raise ValueError("Invalid prepared review owner.")
        for selection, context in (
            (self.selection.critic, self.critic_context),
            (self.selection.judge, self.judge_context),
        ):
            if (
                selection.role != context.role
                or selection.scope != context.scope
                or selection.context_sha256 != digest(canonical_bytes(context))
            ):
                raise ValueError("Prepared review context differs from its selection.")
        if self.brief != guided_brief(
            self.source_brief, self.critic_context, self.judge_context
        ):
            raise ValueError("Prepared review brief differs from its exact projection.")
        if len(canonical_bytes(self)) > REVIEW_GUIDANCE_BYTES:
            raise ValueError("Prepared guidance review exceeds 512 KiB.")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


def decode_prepared_review(payload: bytes) -> PreparedGuidanceReview:
    if len(payload) > REVIEW_GUIDANCE_BYTES:
        raise ValueError("Prepared guidance review exceeds 512 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return PreparedGuidanceReview.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid prepared guidance review.") from None


def prepare_guidance_review(
    store: RoleContextAdmissionStore,
    workspace: Path,
    selection: ReviewGuidanceSelection,
    brief: Brief,
    policy_path: Path,
    expected_policy_sha256: str,
) -> PreparedGuidanceReview:
    selected = MappedDirectory.inspect(workspace)
    # Both shared read locks remain held during the short synchronous projection.
    with ExitStack() as stack:
        contexts = tuple(
            stack.enter_context(
                store.guard_context(
                    workspace, role, policy_path, expected_policy_sha256
                )
            )
            for role in (selection.critic, selection.judge)
        )
        result = PreparedGuidanceReview(
            owner_uid=os.getuid(),
            workspace=selected,
            selection=selection,
            source_brief=brief,
            critic_context=contexts[0],
            judge_context=contexts[1],
            brief=guided_brief(brief, *contexts),
        )
        selected.selection()
    return result


def verify_current_review(
    store: RoleContextAdmissionStore,
    workspace: Path,
    prepared: PreparedGuidanceReview,
    policy_path: Path,
    expected_policy_sha256: str,
) -> None:
    current = prepare_guidance_review(
        store,
        workspace,
        prepared.selection,
        prepared.source_brief,
        policy_path,
        expected_policy_sha256,
    )
    if current != prepared:
        raise ValueError("Prepared review no longer matches current guidance.")
