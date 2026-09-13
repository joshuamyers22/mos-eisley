"""Reviewed override publication beside private project bindings."""

import difflib
import json
import os
from pathlib import Path

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance_binding import (
    GuidanceBindingStore,
    project_name,
    snapshot_name,
)
from mos_eisley.project_guidance_overrides import (
    OVERRIDE_INPUT_BYTES,
    SavedOverrides,
    decode_profile,
    effective_rules,
)
from mos_eisley.project_guidance_storage import GuidanceFile, publish_file, read_file
from mos_eisley.run.files import read_bounded


def override_name(workspace: MappedDirectory) -> str:
    return "overrides-" + project_name(workspace)


def history_name(sha256: str) -> str:
    return "overrides-" + snapshot_name(sha256)


class GuidanceOverrideStore(GuidanceBindingStore):
    def _decode(self, file: GuidanceFile, workspace: MappedDirectory) -> SavedOverrides:
        saved = SavedOverrides.model_validate_json(file.payload)
        if (
            canonical_bytes(saved) != file.payload
            or saved.basis.owner_uid != os.getuid()
            or saved.basis.workspace != workspace
        ):
            raise ValueError("Saved overrides require canonical owner/project data.")
        return saved

    def _history(
        self, root: int | None, workspace: MappedDirectory, sha256: str
    ) -> SavedOverrides:
        file = read_file(root, history_name(sha256))
        if file is None:
            raise ValueError("Pinned override snapshot is missing.")
        saved = self._decode(file, workspace)
        if saved.sha256 != sha256:
            raise ValueError("Pinned override snapshot integrity changed.")
        return saved

    def _overrides(
        self, root: int | None, workspace: MappedDirectory
    ) -> tuple[GuidanceFile | None, SavedOverrides | None]:
        file = read_file(root, override_name(workspace))
        if file is None:
            return None, None
        saved = self._decode(file, workspace)
        if self._history(root, workspace, saved.sha256) != saved:
            raise ValueError("Current overrides differ from their pinned snapshot.")
        return file, saved

    def show_overrides(
        self,
        workspace: Path,
        *,
        snapshot_sha256: str | None = None,
        effective: bool = False,
    ) -> dict[str, object]:
        if snapshot_sha256 is not None and effective:
            raise ValueError("Effective inspection uses current bindings only.")
        if effective:
            from mos_eisley.project_guidance_conflict_store import GuidanceConflictStore

            return GuidanceConflictStore(self.root).show_conflicts(
                workspace, effective=True
            )
        selected = MappedDirectory.inspect(workspace)
        with self._lock_handles() as handles:
            root = None if handles is None else handles[0]
            _, bindings = self._record(root, selected)
            self._snapshots(root, bindings)
            if snapshot_sha256 is None:
                _, saved = self._overrides(root, selected)
            else:
                saved = self._history(root, selected, snapshot_sha256)
            stale = (
                saved is not None
                and saved.profile is not None
                and saved.basis != bindings
            )
            result: dict[str, object] = {
                "storage": str(self.root.resolve()),
                "bindings": bindings.model_dump(mode="json"),
                "overrides": None if saved is None else saved.model_dump(mode="json"),
                "override_snapshot_sha256": None if saved is None else saved.sha256,
                "stale": stale,
                "historical_snapshot": snapshot_sha256 is not None,
                "context_materialized": False,
            }
            selected.selection()
            self._storage_identity(handles)
            return result

    def change_overrides(
        self,
        workspace: Path,
        input_path: Path | None,
        *,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        preview = None
        if expected_sha256 is not None:
            preview = self.change_overrides(workspace, input_path)
            if expected_sha256 != preview["preview_sha256"]:
                raise ValueError("Overrides changed; review again.")
        selected = MappedDirectory.inspect(workspace)
        payload = (
            None
            if input_path is None
            else read_bounded(input_path, OVERRIDE_INPUT_BYTES)
        )
        profile = None if payload is None else decode_profile(payload)
        with self._lock_handles(write=expected_sha256 is not None) as handles:
            root = None if handles is None else handles[0]
            binding_file, bindings = self._record(root, selected)
            snapshots = self._snapshots(root, bindings)
            before_file, before = self._overrides(root, selected)
            if profile is None and (before is None or before.profile is None):
                raise ValueError("No saved override profile to clear.")
            after = SavedOverrides(
                revision=1 if before is None else before.revision + 1,
                basis=bindings,
                profile=profile,
                source_json=None if payload is None else payload.decode("utf-8"),
            )
            rules = effective_rules(bindings, snapshots, after)
            previous_basis = (
                bindings if before is None or before.profile is None else before.basis
            )
            previous_snapshots = self._snapshots(root, previous_basis)
            previous_rules = effective_rules(previous_basis, previous_snapshots, before)
            if (
                before is not None
                and before.basis == bindings
                and before.source_json == after.source_json
            ):
                raise ValueError("Override profile has no changes.")
            old = None if before is None else before.model_dump(mode="json")
            new = after.model_dump(mode="json")
            body: dict[str, object] = {
                "storage": str(self.root.resolve()),
                "storage_identity": None
                if handles is None
                or (preview is not None and preview["storage_identity"] is None)
                else self._storage_identity(handles),
                "action": "clear" if input_path is None else "set",
                "input_path": None
                if input_path is None
                else str(input_path.absolute()),
                "binding_file": None if binding_file is None else binding_file.identity,
                "before_file": None if before_file is None else before_file.identity,
                "before": old,
                "after": new,
                "effective_rules": rules,
                "previous_effective_rules": previous_rules,
                "previous_profile_stale": previous_basis != bindings,
                "diff": "".join(
                    difflib.unified_diff(
                        (json.dumps(old, sort_keys=True, indent=2) + "\n").splitlines(
                            keepends=True
                        ),
                        (json.dumps(new, sort_keys=True, indent=2) + "\n").splitlines(
                            keepends=True
                        ),
                        fromfile="previous",
                        tofile="proposed",
                    )
                ),
            }
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            )
            if expected_sha256 is not None and expected_sha256 != preview_hash:
                raise ValueError("Overrides changed; review again.")

            def verify() -> None:
                self._storage_identity(handles)
                selected.selection()
                if (
                    read_file(root, project_name(selected)) != binding_file
                    or self._snapshots(root, bindings) != snapshots
                    or self._overrides(root, selected) != (before_file, before)
                    or self._snapshots(root, previous_basis) != previous_snapshots
                ):
                    raise ValueError(
                        "Bindings or overrides changed before publication."
                    )
                if (
                    input_path is not None
                    and read_bounded(input_path, OVERRIDE_INPUT_BYTES) != payload
                ):
                    raise ValueError("Override input changed before publication.")

            verify()
            if expected_sha256 is not None:
                assert root is not None
                publish_file(
                    root,
                    history_name(after.sha256),
                    canonical_bytes(after),
                    verify,
                    immutable=True,
                )

                def verify_current() -> None:
                    verify()
                    if self._history(root, selected, after.sha256) != after:
                        raise ValueError(
                            "New override snapshot changed before publication."
                        )

                publish_file(
                    root,
                    override_name(selected),
                    canonical_bytes(after),
                    verify_current,
                )
            return {
                **body,
                "preview_sha256": preview_hash,
                "applied": expected_sha256 is not None,
            }
