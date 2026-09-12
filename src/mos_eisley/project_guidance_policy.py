"""Explicit owner-policy prohibitions for guidance selection, never runtime grants."""

import json
import os
from pathlib import Path
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.conversation_memory_replace import unique_object
from mos_eisley.core.models import Contract, Identifier, canonical_bytes, digest
from mos_eisley.project_guidance import Detail
from mos_eisley.project_guidance_precedence import ProjectRuleReference
from mos_eisley.project_guidance_precedence_store import ProjectAssessmentStore
from mos_eisley.project_guidance_storage import GuidanceFile, read_file

POLICY_BYTES = 64 * 1024


class GuidanceProhibition(Contract):
    id: Identifier
    reference: ProjectRuleReference
    reason: Detail

    @model_validator(mode="after")
    def valid_reason(self) -> Self:
        if not self.reason.strip():
            raise ValueError("An owner-policy prohibition needs a reason.")
        self.reason.encode("utf-8")
        return self


class OwnerGuidancePolicy(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["owner_guidance_prohibitions"] = "owner_guidance_prohibitions"
    policy_id: Identifier
    revision: Identifier
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: MappedDirectory
    prohibitions: Annotated[
        tuple[GuidanceProhibition, ...], Field(min_length=1, max_length=64)
    ]

    @model_validator(mode="after")
    def unique_prohibitions(self) -> Self:
        if len({item.id for item in self.prohibitions}) != len(
            self.prohibitions
        ) or len({item.reference.key for item in self.prohibitions}) != len(
            self.prohibitions
        ):
            raise ValueError("Policy prohibition IDs and references must be unique.")
        if len(canonical_bytes(self)) > POLICY_BYTES:
            raise ValueError("Owner guidance policy exceeds 64 KiB.")
        return self


def decode_policy(payload: bytes) -> OwnerGuidancePolicy:
    if len(payload) > POLICY_BYTES:
        raise ValueError("Owner guidance policy exceeds 64 KiB.")
    try:
        payload.decode("utf-8")
        json.loads(payload, object_pairs_hook=unique_object)
        return OwnerGuidancePolicy.model_validate_json(payload)
    except (ValueError, RecursionError):
        raise ValueError("Invalid owner guidance policy.") from None


def read_policy(path: Path) -> tuple[GuidanceFile, tuple[int, int]]:
    """Require an explicitly chosen owner-private file and parent directory."""
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(parent)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Owner policy requires a private owner-held directory.")
        file = read_file(parent, path.name)
        if file is None:
            raise ValueError("Owner policy file is missing.")
        named = path.parent.stat(follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("Owner policy directory changed.")
        return file, (info.st_dev, info.st_ino)
    finally:
        os.close(parent)


def policy_decisions(
    policy: OwnerGuidancePolicy, rules: list[dict[str, object]] | None
) -> list[dict[str, object]]:
    inventory = (
        {}
        if rules is None
        else {
            ProjectRuleReference.model_validate(rule["reference"]).key: rule
            for rule in rules
        }
    )
    decisions: list[dict[str, object]] = []
    for prohibition in policy.prohibitions:
        rule = inventory.get(prohibition.reference.key)
        status = (
            "unavailable"
            if rules is None
            else "not_present"
            if rule is None
            else ("prohibited" if rule["selected"] else "not_selected")
        )
        decisions.append({**prohibition.model_dump(mode="json"), "status": status})
    return decisions


class GuidancePolicyCheckStore(ProjectAssessmentStore):
    def check_policy(
        self, workspace: Path, policy_path: Path, expected_policy_sha256: str
    ) -> dict[str, object]:
        selected = MappedDirectory.inspect(workspace)
        with self._lock_handles() as handles:
            return self._check_policy_locked(
                selected, policy_path, expected_policy_sha256, handles
            )

    def _check_policy_locked(
        self,
        selected: MappedDirectory,
        policy_path: Path,
        expected_policy_sha256: str,
        handles: tuple[int, int] | None,
    ) -> dict[str, object]:
        policy_path = policy_path.absolute()
        if policy_path.resolve().is_relative_to(Path(selected.path)):
            raise ValueError("Owner policy must be outside the selected project.")
        source = read_policy(policy_path)
        file, parent_identity = source
        source_sha256 = digest(file.payload)
        if source_sha256 != expected_policy_sha256:
            raise ValueError(
                "Owner policy changed; inspect and select its current hash."
            )
        policy = decode_policy(file.payload)
        if policy.owner_uid != os.getuid() or policy.workspace != selected:
            raise ValueError(
                "Owner policy belongs to another user or project identity."
            )
        root = None if handles is None else handles[0]
        captured = self._capture(root, selected)
        before_file, assessment = self._read_conflicts(root, selected)
        report = self._inspection(captured, assessment)
        # Also validate retained sources for a stale/current prior assessment.
        if assessment is not None:
            self._pinned_report(root, assessment)
        rules = cast(list[dict[str, object]] | None, report["rules"])
        decisions = policy_decisions(policy, rules)
        policy_satisfied = rules is not None and all(
            decision["status"] != "prohibited" for decision in decisions
        )
        allowed = policy_satisfied and report["project_resolution_complete"] is True
        body: dict[str, object] = {
            "scope": "owner_prohibitions_on_guidance_selection",
            "policy_path": str(policy_path),
            "policy_parent_identity": parent_identity,
            "policy_file_identity": file.identity,
            "policy_source_sha256": source_sha256,
            "policy_source_json": file.payload.decode("utf-8"),
            "policy": policy.model_dump(mode="json"),
            "guidance": report,
            "guidance_file_identities": {
                "binding": None
                if captured.binding_file is None
                else captured.binding_file.identity,
                "override": None
                if captured.override_file is None
                else captured.override_file.identity,
                "requirements": None
                if captured.requirement_file is None
                else captured.requirement_file.identity,
                "assessment": None if before_file is None else before_file.identity,
            },
            "decisions": decisions,
            "policy_satisfied": policy_satisfied,
            "guidance_selection_allowed": allowed,
            "status": "allowed"
            if allowed
            else "blocked"
            if any(decision["status"] == "prohibited" for decision in decisions)
            else "incomplete",
            "runtime_authorization_evaluated": False,
            "execution_authorized": False,
            "context_materialized": False,
        }
        selected.selection()
        self._storage_identity(handles)
        if self._capture(root, selected) != captured or self._read_conflicts(
            root, selected
        ) != (before_file, assessment):
            raise ValueError("Guidance changed during owner-policy inspection.")
        if read_policy(policy_path) != source:
            raise ValueError("Owner policy changed during inspection.")
        return {
            **body,
            "check_sha256": digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            ),
        }
