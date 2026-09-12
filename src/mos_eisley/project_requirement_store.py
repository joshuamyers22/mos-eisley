"""Private project requirement acceptance with review-bound atomic publication."""

import difflib
import json
import os
from pathlib import Path

from mos_eisley.conversation_memory import MemoryStorage
from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance_binding import project_name, snapshot_name
from mos_eisley.project_guidance_storage import GuidanceFile, publish_file, read_file
from mos_eisley.project_requirements import SavedRequirements, inspect_requirements


def requirement_name(workspace: MappedDirectory) -> str:
    return "requirements-" + project_name(workspace)


def requirement_history_name(sha256: str) -> str:
    return "requirements-" + snapshot_name(sha256)


class RequirementStore(MemoryStorage):
    def _decode(
        self, file: GuidanceFile, workspace: MappedDirectory
    ) -> SavedRequirements:
        saved = SavedRequirements.model_validate_json(file.payload)
        if (
            canonical_bytes(saved) != file.payload
            or saved.owner_uid != os.getuid()
            or saved.workspace != workspace
        ):
            raise ValueError("Saved requirements require canonical owner/project data.")
        return saved

    def _history(
        self, root: int | None, workspace: MappedDirectory, sha256: str
    ) -> SavedRequirements:
        file = read_file(root, requirement_history_name(sha256))
        if file is None:
            raise ValueError("Pinned requirement snapshot is missing.")
        saved = self._decode(file, workspace)
        if saved.sha256 != sha256:
            raise ValueError("Pinned requirement snapshot integrity changed.")
        return saved

    def _current(
        self, root: int | None, workspace: MappedDirectory
    ) -> tuple[GuidanceFile | None, SavedRequirements | None]:
        file = read_file(root, requirement_name(workspace))
        if file is None:
            return None, None
        saved = self._decode(file, workspace)
        if self._history(root, workspace, saved.sha256) != saved:
            raise ValueError("Current requirements differ from their pinned snapshot.")
        return file, saved

    def show(
        self, workspace: Path, *, snapshot_sha256: str | None = None
    ) -> dict[str, object]:
        selected = MappedDirectory.inspect(workspace)
        with self._lock_handles() as handles:
            root = None if handles is None else handles[0]
            if snapshot_sha256 is None:
                _, saved = self._current(root, selected)
            else:
                saved = self._history(root, selected, snapshot_sha256)
            selected.selection()
            self._storage_identity(handles)
            return {
                "storage": str(self.root.resolve()),
                "workspace": selected.model_dump(mode="json"),
                "requirements": None
                if saved is None
                else saved.model_dump(mode="json"),
                "snapshot_sha256": None if saved is None else saved.sha256,
                "historical_snapshot": snapshot_sha256 is not None,
                "accepted_current": snapshot_sha256 is None
                and saved is not None
                and saved.proposal is not None,
                "context_materialized": False,
            }

    def change(
        self,
        workspace: Path,
        input_path: Path | None,
        source_paths: tuple[Path, ...] = (),
        *,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        if input_path is None and source_paths:
            raise ValueError("Clear accepts no source paths.")
        preview = None
        if expected_sha256 is not None:
            preview = self.change(workspace, input_path, source_paths)
            if expected_sha256 != preview["preview_sha256"]:
                raise ValueError("Requirements changed; review again.")
        selected = MappedDirectory.inspect(workspace)
        proposal = (
            None
            if input_path is None
            else inspect_requirements(input_path, source_paths)
        )
        with self._lock_handles(write=expected_sha256 is not None) as handles:
            root = None if handles is None else handles[0]
            before_file, before = self._current(root, selected)
            if proposal is None and (before is None or before.proposal is None):
                raise ValueError("No accepted requirements to clear.")
            if before is not None and before.proposal == proposal:
                raise ValueError("Requirement selection has no changes.")
            after = SavedRequirements(
                owner_uid=os.getuid(),
                workspace=selected,
                revision=1 if before is None else before.revision + 1,
                proposal=proposal,
            )
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
                "before_file": None if before_file is None else before_file.identity,
                "before": old,
                "after": new,
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
                raise ValueError("Requirements changed; review again.")

            def verify() -> None:
                self._storage_identity(handles)
                selected.selection()
                if self._current(root, selected) != (before_file, before):
                    raise ValueError(
                        "Accepted requirements changed before publication."
                    )
                if (
                    input_path is not None
                    and inspect_requirements(input_path, source_paths) != proposal
                ):
                    raise ValueError("Requirement inputs changed before publication.")

            verify()
            if expected_sha256 is not None:
                assert root is not None
                publish_file(
                    root,
                    requirement_history_name(after.sha256),
                    canonical_bytes(after),
                    verify,
                    immutable=True,
                )

                def verify_current() -> None:
                    verify()
                    if self._history(root, selected, after.sha256) != after:
                        raise ValueError(
                            "New requirement snapshot changed before publication."
                        )

                publish_file(
                    root,
                    requirement_name(selected),
                    canonical_bytes(after),
                    verify_current,
                )
            return {
                **body,
                "preview_sha256": preview_hash,
                "snapshot_sha256": after.sha256,
                "applied": expected_sha256 is not None,
            }
