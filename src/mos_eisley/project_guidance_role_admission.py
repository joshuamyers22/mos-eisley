"""Current role-context checks and a guarded local consumption boundary."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.project_guidance import Detail
from mos_eisley.project_guidance_role import Role, RoleContext
from mos_eisley.project_guidance_role_store import RoleGuidanceStore, role_snapshot_name
from mos_eisley.project_guidance_storage import read_file


class RoleContextSelection(Contract):
    snapshot_sha256: Digest
    context_sha256: Digest
    role: Role
    scope: Detail


class RoleContextAdmissionStore(RoleGuidanceStore):
    @contextmanager
    def guard_context(
        self,
        workspace: Path,
        selection: RoleContextSelection,
        policy_path: Path,
        expected_policy_sha256: str,
    ) -> Generator[RoleContext]:
        """Validate before yielding; hold the guidance lock through local use.

        Consumers must not dispatch, await user input, or acquire a guidance write
        lock here. Exit validation detects external edits but cannot undo
        caller side effects. This is no provider/tool/spend authorization grant.
        """
        selected = MappedDirectory.inspect(workspace)
        with self._lock_handles() as handles:
            root = None if handles is None else handles[0]
            identity = self._storage_identity(handles)
            name = role_snapshot_name(selection.snapshot_sha256)
            before = read_file(root, name)
            snapshot = self._context_snapshot(root, selected, selection.snapshot_sha256)
            context = snapshot.context
            if (
                context.role != selection.role
                or context.scope != selection.scope
                or digest(canonical_bytes(context)) != selection.context_sha256
                or context.policy_source_sha256 != expected_policy_sha256
            ):
                raise ValueError("Role context selection or selected policy changed.")
            check = self._check_policy_locked(
                selected, policy_path, expected_policy_sha256, handles
            )
            guidance = cast(dict[str, object], check["guidance"])
            if (
                check["guidance_selection_allowed"] is not True
                or guidance["conflict_snapshot_sha256"]
                != context.assessment_snapshot_sha256
            ):
                raise ValueError(
                    "Role context is no longer current; review and freeze again."
                )

            def verify() -> None:
                selected.selection()
                if (
                    self._storage_identity(handles) != identity
                    or read_file(root, name) != before
                    or self._context_snapshot(root, selected, selection.snapshot_sha256)
                    != snapshot
                    or self._check_policy_locked(
                        selected, policy_path, expected_policy_sha256, handles
                    )
                    != check
                ):
                    raise ValueError("Role context sources changed during local use.")

            verify()
            yield context
            verify()

    def check_context(
        self,
        workspace: Path,
        selection: RoleContextSelection,
        policy_path: Path,
        expected_policy_sha256: str,
    ) -> dict[str, object]:
        """Read-only diagnostic; never a reusable admission token."""
        with self.guard_context(
            workspace, selection, policy_path, expected_policy_sha256
        ) as context:
            receipt: dict[str, object] = {
                "selection": selection.model_dump(mode="json"),
                "assessment_snapshot_sha256": context.assessment_snapshot_sha256,
                "policy_source_sha256": context.policy_source_sha256,
                "context_bytes": len(canonical_bytes(context)),
                "current_at_check": True,
                "reusable_authority": False,
                "provider_context_loaded": False,
                "execution_authorized": False,
            }
        return receipt
