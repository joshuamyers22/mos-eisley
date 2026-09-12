"""Private reviewed conflict assessments over pinned advisory guidance."""

import difflib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance_binding import (
    PinnedGuidance,
    project_name,
    snapshot_name,
)
from mos_eisley.project_guidance_conflicts import (
    ASSESSMENT_BYTES,
    GuidanceBasis,
    SavedConflictAssessment,
    decode_assessment,
    resolution_report,
)
from mos_eisley.project_guidance_override_store import GuidanceOverrideStore
from mos_eisley.project_guidance_storage import GuidanceFile, publish_file, read_file
from mos_eisley.run.files import read_bounded


def conflict_name(workspace: MappedDirectory) -> str:
    return "conflicts-" + project_name(workspace)


def conflict_history_name(sha256: str) -> str:
    return "conflicts-" + snapshot_name(sha256)


@dataclass(frozen=True)
class CapturedGuidance:
    binding_file: GuidanceFile | None
    override_file: GuidanceFile | None
    basis: GuidanceBasis
    snapshots: tuple[PinnedGuidance, ...]


class GuidanceConflictStore(GuidanceOverrideStore):
    def _capture(
        self, root: int | None, workspace: MappedDirectory
    ) -> CapturedGuidance:
        binding_file, bindings = self._record(root, workspace)
        snapshots = self._snapshots(root, bindings)
        override_file, overrides = self._overrides(root, workspace)
        return CapturedGuidance(
            binding_file,
            override_file,
            GuidanceBasis(bindings=bindings, overrides=overrides),
            snapshots,
        )

    def _decode_conflicts(
        self, file: GuidanceFile, workspace: MappedDirectory
    ) -> SavedConflictAssessment:
        saved = SavedConflictAssessment.model_validate_json(file.payload)
        if (
            canonical_bytes(saved) != file.payload
            or saved.basis.bindings.owner_uid != os.getuid()
            or saved.basis.bindings.workspace != workspace
        ):
            raise ValueError(
                "Saved conflict assessment requires canonical owner/project data."
            )
        return saved

    def _conflict_history(
        self, root: int | None, workspace: MappedDirectory, sha256: str
    ) -> SavedConflictAssessment:
        file = read_file(root, conflict_history_name(sha256))
        if file is None:
            raise ValueError("Pinned conflict assessment is missing.")
        saved = self._decode_conflicts(file, workspace)
        if saved.sha256 != sha256:
            raise ValueError("Pinned conflict assessment integrity changed.")
        return saved

    def _read_conflicts(
        self, root: int | None, workspace: MappedDirectory
    ) -> tuple[GuidanceFile | None, SavedConflictAssessment | None]:
        file = read_file(root, conflict_name(workspace))
        if file is None:
            return None, None
        saved = self._decode_conflicts(file, workspace)
        if self._conflict_history(root, workspace, saved.sha256) != saved:
            raise ValueError(
                "Current conflict assessment differs from its pinned snapshot."
            )
        return file, saved

    def _pinned_report(
        self, root: int | None, saved: SavedConflictAssessment
    ) -> dict[str, object]:
        return resolution_report(
            saved.basis, self._snapshots(root, saved.basis.bindings), saved.assessment
        )

    def _inspection(
        self, captured: CapturedGuidance, saved: SavedConflictAssessment | None
    ) -> dict[str, object]:
        basis = captured.basis
        assessed = saved is not None and saved.assessment is not None
        stale = (
            saved is not None
            and assessed
            and (saved.basis != basis or basis.overrides_stale)
        )
        report = resolution_report(
            basis,
            captured.snapshots,
            None if saved is None or stale else saved.assessment,
        )
        return {
            "storage": str(self.root.resolve()),
            "bindings": basis.bindings.model_dump(mode="json"),
            "overrides": None
            if basis.overrides is None
            else basis.overrides.model_dump(mode="json"),
            "override_snapshot_sha256": None
            if basis.overrides is None
            else basis.overrides.sha256,
            "stale": basis.overrides_stale,
            "context_materialized": False,
            "precedence": ["approved_project_override", "advisory_default"],
            "basis_sha256": basis.sha256,
            "conflict_assessment": None
            if saved is None
            else saved.model_dump(mode="json"),
            "conflict_snapshot_sha256": None if saved is None else saved.sha256,
            "assessment_status": "stale"
            if stale
            else "current"
            if assessed
            else "unassessed",
            "stale_conflict_ids": []
            if not stale or saved is None or saved.assessment is None
            else [item.id for item in saved.assessment.conflicts],
            **report,
        }

    def show_conflicts(
        self,
        workspace: Path,
        *,
        snapshot_sha256: str | None = None,
        effective: bool = False,
    ) -> dict[str, object]:
        if snapshot_sha256 is not None and effective:
            raise ValueError(
                "Effective conflict inspection uses current guidance only."
            )
        selected = MappedDirectory.inspect(workspace)
        with self._lock_handles() as handles:
            root = None if handles is None else handles[0]
            captured = self._capture(root, selected)
            if effective and captured.basis.overrides_stale:
                raise ValueError(
                    "Review project overrides before effective inspection."
                )
            if snapshot_sha256 is None:
                _, saved = self._read_conflicts(root, selected)
            else:
                saved = self._conflict_history(root, selected, snapshot_sha256)
            result = self._inspection(captured, saved)
            result["historical_snapshot"] = snapshot_sha256 is not None
            if snapshot_sha256 is not None:
                result["assessment_status"] = "historical"
                result["advisory_resolution_complete"] = False
                result["rules"] = None
            result["pinned_report"] = (
                None if saved is None else self._pinned_report(root, saved)
            )
            selected.selection()
            self._storage_identity(handles)
            return result

    def change_assessment(
        self,
        workspace: Path,
        input_path: Path | None,
        *,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        preview = None
        if expected_sha256 is not None:
            preview = self.change_assessment(workspace, input_path)
            if expected_sha256 != preview["preview_sha256"]:
                raise ValueError("Conflict review changed; preview again.")
        selected = MappedDirectory.inspect(workspace)
        payload = (
            None if input_path is None else read_bounded(input_path, ASSESSMENT_BYTES)
        )
        assessment = None if payload is None else decode_assessment(payload)
        with self._lock_handles(write=expected_sha256 is not None) as handles:
            root = None if handles is None else handles[0]
            captured = self._capture(root, selected)
            before_file, before = self._read_conflicts(root, selected)
            if assessment is None and (before is None or before.assessment is None):
                raise ValueError("No conflict assessment to clear.")
            if assessment is not None and not captured.basis.bindings.templates:
                raise ValueError("Attach guidance before assessing its conflicts.")
            after = SavedConflictAssessment(
                revision=1 if before is None else before.revision + 1,
                basis=captured.basis,
                assessment=assessment,
                source_json=None if payload is None else payload.decode("utf-8"),
            )
            report = resolution_report(after.basis, captured.snapshots, assessment)
            previous_report = (
                None if before is None else self._pinned_report(root, before)
            )
            if (
                before is not None
                and before.basis == after.basis
                and before.source_json == after.source_json
            ):
                raise ValueError("Conflict assessment has no changes.")
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
                "binding_file": None
                if captured.binding_file is None
                else captured.binding_file.identity,
                "override_file": None
                if captured.override_file is None
                else captured.override_file.identity,
                "before_file": None if before_file is None else before_file.identity,
                "before": old,
                "after": new,
                "previous_report": previous_report,
                "proposed_report": report,
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
                raise ValueError("Conflict review changed; preview again.")

            def verify() -> None:
                self._storage_identity(handles)
                selected.selection()
                if self._capture(root, selected) != captured or self._read_conflicts(
                    root, selected
                ) != (before_file, before):
                    raise ValueError(
                        "Guidance or conflict assessment changed before publication."
                    )
                if (
                    before is not None
                    and self._pinned_report(root, before) != previous_report
                ):
                    raise ValueError(
                        "Previous conflict basis changed before publication."
                    )
                if (
                    input_path is not None
                    and read_bounded(input_path, ASSESSMENT_BYTES) != payload
                ):
                    raise ValueError("Conflict input changed before publication.")

            verify()
            if expected_sha256 is not None:
                assert root is not None
                publish_file(
                    root,
                    conflict_history_name(after.sha256),
                    canonical_bytes(after),
                    verify,
                    immutable=True,
                )

                def verify_current() -> None:
                    verify()
                    if self._conflict_history(root, selected, after.sha256) != after:
                        raise ValueError(
                            "New conflict snapshot changed before publication."
                        )

                publish_file(
                    root,
                    conflict_name(selected),
                    canonical_bytes(after),
                    verify_current,
                )
            return {
                **body,
                "preview_sha256": preview_hash,
                "applied": expected_sha256 is not None,
            }
