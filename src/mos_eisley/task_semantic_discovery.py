"""Validated, inert semantic selection of one frozen author task profile."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.project_guidance_role_admission import RoleContextAdmissionStore
from mos_eisley.run.files import read_bounded
from mos_eisley.task_profile import (
    RuntimeTaskProfile,
    TaskCategory,
    TaskProfileAcquirer,
    TaskSemanticDiscoveryEvidence,
    validate_task_profile_scope,
)
from mos_eisley.task_profile_acquisition import (
    TASK_PROFILE_SELECTION_BYTES,
    FrozenRoleTaskProfileAcquirer,
    FrozenRoleTaskProfileSelection,
    materialize_role_task_profile,
)
from mos_eisley.task_state import WorkUnitReference

TASK_DISCOVERY_BYTES = 128 * 1024


class SemanticTaskSignal(Contract):
    """Exact character range supporting a private semantic decision."""

    start: Annotated[int, Field(ge=0, le=8000)]
    end: Annotated[int, Field(gt=0, le=8000)]
    quote: Annotated[str, Field(min_length=1, max_length=2000)]

    @model_validator(mode="after")
    def ordered_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError("semantic task signal range must be ordered")
        return self


class OmittedTaskProfile(Contract):
    profile_id: Identifier
    reason: Annotated[str, Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def nonblank_reason(self) -> Self:
        if not self.reason.strip():
            raise ValueError("semantic profile omission needs a reason")
        self.reason.encode("utf-8")
        return self


class SemanticTaskDecision(Contract):
    """One supplied semantic decision for an exact queued author message."""

    decision_id: Identifier
    task_text_sha256: Digest
    work_unit: WorkUnitReference
    category: TaskCategory
    objective: Annotated[str, Field(min_length=1, max_length=2000)]
    signals: Annotated[
        tuple[SemanticTaskSignal, ...], Field(min_length=1, max_length=16)
    ]
    selected_profile_id: Identifier
    selection_reason: Annotated[str, Field(min_length=1, max_length=1000)]
    omitted_profiles: Annotated[
        tuple[OmittedTaskProfile, ...], Field(max_length=15)
    ] = ()
    ambiguous: Literal[False] = False
    grants_authority: Literal[False] = False

    @model_validator(mode="after")
    def nonblank_semantics(self) -> Self:
        for value in (self.objective, self.selection_reason):
            if not value.strip():
                raise ValueError("semantic decision text cannot be blank")
            value.encode("utf-8")
        ranges = tuple((item.start, item.end) for item in self.signals)
        if len(set(ranges)) != len(ranges):
            raise ValueError("semantic task signal ranges must be unique")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class SemanticTaskProfileDiscovery(Contract):
    """Bounded private decisions over an exact frozen author-profile inventory."""

    schema_version: Literal[1] = 1
    kind: Literal["semantic_task_profile_discovery"] = "semantic_task_profile_discovery"
    project_id: Identifier
    candidates: Annotated[
        tuple[FrozenRoleTaskProfileSelection, ...], Field(min_length=1, max_length=16)
    ]
    decisions: Annotated[
        tuple[SemanticTaskDecision, ...], Field(min_length=1, max_length=64)
    ]
    offline_only: Literal[True] = True
    grants_authority: Literal[False] = False
    selects_tools: Literal[False] = False
    starts_servers: Literal[False] = False

    @model_validator(mode="after")
    def complete_inventory(self) -> Self:
        profile_ids = tuple(item.profile_id for item in self.candidates)
        if len(set(profile_ids)) != len(profile_ids):
            raise ValueError("semantic discovery candidate profile IDs must be unique")
        if any(item.project_id != self.project_id for item in self.candidates):
            raise ValueError("semantic discovery candidates must share one project")
        if len({item.expected_policy_sha256 for item in self.candidates}) != 1:
            raise ValueError(
                "semantic discovery candidates must share one owner policy"
            )
        if len({item.decision_id for item in self.decisions}) != len(self.decisions):
            raise ValueError("semantic discovery decision IDs must be unique")
        if len({item.task_text_sha256 for item in self.decisions}) != len(
            self.decisions
        ):
            raise ValueError("semantic discovery task-message digests must be unique")
        by_id = {item.profile_id: item for item in self.candidates}
        for decision in self.decisions:
            selected = by_id.get(decision.selected_profile_id)
            if selected is None:
                raise ValueError("semantic discovery selected an unknown profile")
            if selected.work_unit != decision.work_unit:
                raise ValueError(
                    "semantic discovery work unit differs from its profile"
                )
            expected_omissions = tuple(
                item for item in profile_ids if item != decision.selected_profile_id
            )
            actual_omissions = tuple(
                item.profile_id for item in decision.omitted_profiles
            )
            if actual_omissions != expected_omissions:
                raise ValueError(
                    "semantic discovery omissions must cover every unselected profile"
                )
        if len(canonical_bytes(self)) > TASK_DISCOVERY_BYTES:
            raise ValueError("semantic task discovery exceeds 128 KiB")
        return self


def decode_semantic_task_discovery(payload: bytes) -> SemanticTaskProfileDiscovery:
    if len(payload) > TASK_DISCOVERY_BYTES:
        raise ValueError("Semantic task discovery exceeds 128 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return SemanticTaskProfileDiscovery.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid semantic task discovery.") from None


def _validate_signals(decision: SemanticTaskDecision, task_text: str) -> None:
    for signal in decision.signals:
        if signal.end > len(task_text) or task_text[signal.start : signal.end] != (
            signal.quote
        ):
            raise ValueError(
                "semantic task discovery signal does not match author text"
            )


@dataclass(frozen=True)
class ValidatedSemanticTaskProfileAcquirer:
    """Select and revalidate one frozen profile for an exact queued author task."""

    guidance_storage: Path
    policy_path: Path
    discovery_payload: bytes

    def __post_init__(self) -> None:
        decode_semantic_task_discovery(self.discovery_payload)

    @classmethod
    def from_paths(
        cls, guidance_storage: Path, discovery_path: Path, policy_path: Path
    ) -> Self:
        return cls(
            guidance_storage=guidance_storage,
            policy_path=policy_path,
            discovery_payload=read_bounded(discovery_path, TASK_DISCOVERY_BYTES),
        )

    def acquire(
        self, *, owner_uid: int, workspace: str, task_text: str | None = None
    ) -> RuntimeTaskProfile:
        if owner_uid != os.getuid():
            raise ValueError("semantic task discovery belongs to another owner")
        if task_text is None:
            raise ValueError("semantic task discovery requires queued author text")
        plan = decode_semantic_task_discovery(self.discovery_payload)
        task_sha = digest(task_text.encode("utf-8"))
        decision = next(
            (item for item in plan.decisions if item.task_text_sha256 == task_sha),
            None,
        )
        if decision is None:
            raise ValueError(
                "semantic task discovery has no exact queued-task decision"
            )
        _validate_signals(decision, task_text)
        selection = next(
            item
            for item in plan.candidates
            if item.profile_id == decision.selected_profile_id
        )
        store = RoleContextAdmissionStore(self.guidance_storage)
        with store.guard_context(
            Path(workspace),
            selection.guidance,
            self.policy_path,
            selection.expected_policy_sha256,
        ) as context:
            profile = materialize_role_task_profile(
                selection,
                context,
                owner_uid=owner_uid,
                workspace=workspace,
                selection_source_sha256=digest(self.discovery_payload),
            )
        acquisition = profile.acquisition
        assert acquisition is not None
        evidence = TaskSemanticDiscoveryEvidence(
            discovery_source_sha256=digest(self.discovery_payload),
            decision_sha256=decision.sha256,
            task_text_sha256=task_sha,
            category=decision.category,
            selected_profile_id=selection.profile_id,
            candidate_profile_ids=tuple(item.profile_id for item in plan.candidates),
            omitted_profile_ids=tuple(
                item.profile_id for item in decision.omitted_profiles
            ),
        )
        profile = RuntimeTaskProfile.model_validate(
            profile.model_copy(
                update={
                    "acquisition": acquisition.model_copy(
                        update={"semantic_discovery": evidence}
                    )
                }
            ).model_dump()
        )
        validate_task_profile_scope(profile, owner_uid=owner_uid, workspace=workspace)
        return profile


def task_profile_acquirer_from_paths(
    guidance_storage: Path, selection_path: Path, policy_path: Path
) -> TaskProfileAcquirer:
    """Load either the legacy frozen selection or a semantic discovery plan."""
    payload = read_bounded(selection_path, TASK_DISCOVERY_BYTES)
    try:
        decoded = cast(object, json.loads(payload, object_pairs_hook=unique_object))
        kind = (
            cast(dict[str, object], decoded).get("kind")
            if isinstance(decoded, dict)
            else None
        )
    except (ValueError, RecursionError, UnicodeDecodeError):
        raise ValueError("Invalid automatic task-profile selection.") from None
    if kind == "frozen_role_task_profile":
        if len(payload) > TASK_PROFILE_SELECTION_BYTES:
            raise ValueError("Automatic task-profile selection exceeds 32 KiB.")
        return FrozenRoleTaskProfileAcquirer(
            guidance_storage=guidance_storage,
            policy_path=policy_path,
            selection_payload=payload,
        )
    if kind == "semantic_task_profile_discovery":
        return ValidatedSemanticTaskProfileAcquirer(
            guidance_storage=guidance_storage,
            policy_path=policy_path,
            discovery_payload=payload,
        )
    raise ValueError("Invalid automatic task-profile selection.")
