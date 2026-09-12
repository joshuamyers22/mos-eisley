"""Reviewed immutable role contexts pinned to accepted guidance and owner policy."""

import json
import os
from pathlib import Path
from typing import cast

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance_binding import snapshot_name
from mos_eisley.project_guidance_policy import (
    GuidancePolicyCheckStore,
    decode_policy,
    policy_decisions,
)
from mos_eisley.project_guidance_role import (
    SELECTION_BYTES,
    FrozenRoleContext,
    decode_role_selection,
    project_role_context,
)
from mos_eisley.project_guidance_storage import publish_file, read_file
from mos_eisley.run.files import read_bounded


def role_snapshot_name(sha256: str) -> str:
    return "role-" + snapshot_name(sha256)


class RoleGuidanceStore(GuidancePolicyCheckStore):
    def _context_snapshot(
        self, root: int | None, workspace: MappedDirectory, sha256: str
    ) -> FrozenRoleContext:
        file = read_file(root, role_snapshot_name(sha256))
        if file is None:
            raise ValueError("Frozen role context is missing.")
        snapshot = FrozenRoleContext.model_validate_json(file.payload)
        if (
            canonical_bytes(snapshot) != file.payload
            or snapshot.sha256 != sha256
            or snapshot.owner_uid != os.getuid()
            or snapshot.workspace != workspace
        ):
            raise ValueError("Frozen role context identity or integrity changed.")
        assessment = self._conflict_history(
            root, workspace, snapshot.context.assessment_snapshot_sha256
        )
        report = self._pinned_report(root, assessment)
        if report["project_resolution_complete"] is not True:
            raise ValueError(
                "Frozen role context requires a complete pinned assessment."
            )
        rules = cast(list[dict[str, object]], report["rules"])
        policy = decode_policy(snapshot.policy_source_json.encode("utf-8"))
        if any(
            item["status"] == "prohibited" for item in policy_decisions(policy, rules)
        ):
            raise ValueError("Frozen role context violates its selected owner policy.")
        expected = project_role_context(
            snapshot.selection,
            rules,
            assessment.sha256,
            snapshot.context.policy_source_sha256,
        )
        if expected != snapshot.context:
            raise ValueError("Frozen role context differs from its pinned projection.")
        return snapshot

    def show_context(self, workspace: Path, snapshot_sha256: str) -> dict[str, object]:
        selected = MappedDirectory.inspect(workspace)
        with self._lock_handles() as handles:
            root = None if handles is None else handles[0]
            snapshot = self._context_snapshot(root, selected, snapshot_sha256)
            selected.selection()
            self._storage_identity(handles)
            return {
                "snapshot_sha256": snapshot.sha256,
                "snapshot": snapshot.model_dump(mode="json"),
                "historical_snapshot": True,
                "current_authority": False,
                "provider_context_loaded": False,
            }

    def freeze_context(
        self,
        workspace: Path,
        input_path: Path,
        policy_path: Path,
        expected_policy_sha256: str,
        *,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        if expected_sha256 is not None:
            preview = self.freeze_context(
                workspace, input_path, policy_path, expected_policy_sha256
            )
            if preview["preview_sha256"] != expected_sha256:
                raise ValueError("Role context review changed; preview again.")
        selected = MappedDirectory.inspect(workspace)
        payload = read_bounded(input_path, SELECTION_BYTES)
        selection = decode_role_selection(payload)
        with self._lock_handles(write=expected_sha256 is not None) as handles:
            root = None if handles is None else handles[0]
            check = self._check_policy_locked(
                selected, policy_path, expected_policy_sha256, handles
            )
            if check["guidance_selection_allowed"] is not True:
                raise ValueError(
                    "Complete current guidance and satisfy owner policy "
                    "before freezing a role context."
                )
            guidance = cast(dict[str, object], check["guidance"])
            assessment_sha = cast(str, guidance["conflict_snapshot_sha256"])
            context = project_role_context(
                selection,
                cast(list[dict[str, object]], guidance["rules"]),
                assessment_sha,
                expected_policy_sha256,
            )
            snapshot = FrozenRoleContext(
                owner_uid=os.getuid(),
                workspace=selected,
                selection_json=payload.decode("utf-8"),
                selection=selection,
                policy_source_json=cast(str, check["policy_source_json"]),
                context=context,
            )
            name = role_snapshot_name(snapshot.sha256)
            existing = read_file(root, name)
            if existing is not None and existing.payload != canonical_bytes(snapshot):
                raise ValueError("Existing frozen role context is corrupt.")
            body: dict[str, object] = {
                "storage_identity": self._storage_identity(handles),
                "input_path": str(input_path.absolute()),
                "policy_check": check,
                "snapshot": snapshot.model_dump(mode="json"),
                "snapshot_sha256": snapshot.sha256,
                "context_sha256": digest(canonical_bytes(context)),
                "context_bytes": len(canonical_bytes(context)),
                "existing_file": None if existing is None else existing.identity,
                "provider_context_loaded": False,
            }
            preview_sha = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            )
            if expected_sha256 is not None and preview_sha != expected_sha256:
                raise ValueError("Role context review changed; preview again.")

            def verify() -> None:
                selected.selection()
                self._storage_identity(handles)
                if (
                    read_bounded(input_path, SELECTION_BYTES) != payload
                    or read_file(root, name) != existing
                ):
                    raise ValueError(
                        "Role selection or snapshot changed before publication."
                    )
                current = self._check_policy_locked(
                    selected, policy_path, expected_policy_sha256, handles
                )
                if current != check:
                    raise ValueError(
                        "Guidance or owner policy changed before role publication."
                    )

            verify()
            if expected_sha256 is not None:
                assert root is not None
                publish_file(
                    root, name, canonical_bytes(snapshot), verify, immutable=True
                )
                if self._context_snapshot(root, selected, snapshot.sha256) != snapshot:
                    raise ValueError("Published role snapshot integrity changed.")
            return {
                **body,
                "preview_sha256": preview_sha,
                "applied": expected_sha256 is not None,
            }
