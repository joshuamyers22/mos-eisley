"""Reviewed project bindings; no conversation context is materialized here."""

import difflib
import json
import os
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_memory import MemoryStorage
from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.project_guidance import GuidanceSnapshot, inspect_guidance
from mos_eisley.project_guidance_storage import (
    GUIDANCE_FILE_BYTES,
    GuidanceFile,
    publish_file,
    read_file,
)

BindingAction = Literal["attach", "update", "detach"]
MAX_TEMPLATES = 8


class PinnedGuidance(Contract):
    schema_version: Literal[1] = 1
    workspace: MappedDirectory
    inspection: GuidanceSnapshot

    @model_validator(mode="after")
    def matching_identity(self) -> Self:
        if self.workspace.path != self.inspection.workspace:
            raise ValueError("Pinned guidance project identity does not match.")
        if len(canonical_bytes(self)) > GUIDANCE_FILE_BYTES:
            raise ValueError("Pinned guidance snapshot exceeds 512 KiB.")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class TemplateBinding(Contract):
    template_id: Identifier
    snapshot_sha256: Digest


class ProjectGuidanceBindings(Contract):
    schema_version: Literal[1] = 1
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: MappedDirectory
    revision: Annotated[int, Field(ge=0)] = 0
    templates: Annotated[
        tuple[TemplateBinding, ...], Field(max_length=MAX_TEMPLATES)
    ] = ()
    context_materialized: Literal[False] = False

    @model_validator(mode="after")
    def unique_templates(self) -> Self:
        ids = tuple(item.template_id for item in self.templates)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("Guidance bindings require unique sorted template IDs.")
        return self


def project_name(workspace: MappedDirectory) -> str:
    return "project-" + digest(workspace.path.encode("utf-8")) + ".json"


def snapshot_name(sha256: str) -> str:
    # A user-supplied historical digest must never become an arbitrary path.
    if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
        raise ValueError("Use a complete lowercase snapshot SHA-256.")
    return "snapshot-" + sha256 + ".json"


class GuidanceBindingStore(MemoryStorage):
    def _record(
        self, root: int | None, workspace: MappedDirectory
    ) -> tuple[GuidanceFile | None, ProjectGuidanceBindings]:
        saved = read_file(root, project_name(workspace))
        if saved is None:
            return None, ProjectGuidanceBindings(
                owner_uid=os.getuid(), workspace=workspace
            )
        record = ProjectGuidanceBindings.model_validate_json(saved.payload)
        if (
            canonical_bytes(record) != saved.payload
            or record.owner_uid != os.getuid()
            or record.workspace != workspace
        ):
            raise ValueError(
                "Saved guidance belongs to another user or project identity."
            )
        return saved, record

    def _snapshot(
        self, root: int | None, workspace: MappedDirectory, sha256: str
    ) -> PinnedGuidance:
        saved = read_file(root, snapshot_name(sha256))
        if saved is None:
            raise ValueError("Pinned guidance snapshot is missing.")
        snapshot = PinnedGuidance.model_validate_json(saved.payload)
        if (
            canonical_bytes(snapshot) != saved.payload
            or snapshot.sha256 != sha256
            or snapshot.inspection.owner_uid != os.getuid()
            or snapshot.workspace != workspace
        ):
            raise ValueError("Pinned guidance snapshot identity or integrity changed.")
        return snapshot

    def _snapshots(
        self, root: int | None, record: ProjectGuidanceBindings
    ) -> tuple[PinnedGuidance, ...]:
        snapshots = tuple(
            self._snapshot(root, record.workspace, item.snapshot_sha256)
            for item in record.templates
        )
        if any(
            snapshot.inspection.descriptor.template_id != item.template_id
            for item, snapshot in zip(record.templates, snapshots, strict=True)
        ):
            raise ValueError("Pinned guidance template ID does not match its binding.")
        return snapshots

    def show(
        self, workspace: Path, *, snapshot_sha256: str | None = None
    ) -> dict[str, object]:
        selected = MappedDirectory.inspect(workspace)
        with self._lock_handles() as handles:
            root = None if handles is None else handles[0]
            _, record = self._record(root, selected)
            snapshots = (
                self._snapshots(root, record)
                if snapshot_sha256 is None
                else (self._snapshot(root, selected, snapshot_sha256),)
            )
            selected.selection()
            self._storage_identity(handles)
            return {
                "storage": str(self.root.resolve()),
                "bindings": record.model_dump(mode="json"),
                "snapshots": [item.model_dump(mode="json") for item in snapshots],
                "historical_snapshot": snapshot_sha256 is not None,
            }

    def change(
        self,
        workspace: Path,
        action: BindingAction,
        template_id: str,
        *,
        descriptor_path: Path | None = None,
        markdown_path: Path | None = None,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        if action not in {"attach", "update", "detach"}:
            raise ValueError("Unknown guidance binding action.")
        if (
            action == "detach"
            and (descriptor_path is not None or markdown_path is not None)
        ) or (
            action != "detach" and (descriptor_path is None or markdown_path is None)
        ):
            raise ValueError(
                "Attach/update require descriptor and Markdown; detach accepts neither."
            )
        # Reject a stale review without bootstrapping private storage.
        preview = None
        if expected_sha256 is not None:
            preview = self.change(
                workspace,
                action,
                template_id,
                descriptor_path=descriptor_path,
                markdown_path=markdown_path,
            )
            if preview["preview_sha256"] != expected_sha256:
                raise ValueError("Guidance changed; review the operation again.")
        selected = MappedDirectory.inspect(workspace)
        candidate = None
        if descriptor_path is not None and markdown_path is not None:
            candidate = PinnedGuidance(
                workspace=selected,
                inspection=inspect_guidance(
                    Path(selected.path), descriptor_path, markdown_path
                ),
            )
            if candidate.inspection.descriptor.template_id != template_id:
                raise ValueError(
                    "Selected descriptor must match the requested template ID."
                )
        with self._lock_handles(write=expected_sha256 is not None) as handles:
            root = None if handles is None else handles[0]
            before_file, before = self._record(root, selected)
            snapshots = self._snapshots(root, before)
            previous = next(
                (
                    item
                    for item in snapshots
                    if item.inspection.descriptor.template_id == template_id
                ),
                None,
            )
            if (action == "attach") == (previous is not None):
                raise ValueError(
                    "Attach requires an absent binding; "
                    "update/detach require an existing one."
                )
            if candidate == previous:
                raise ValueError("Guidance update has no changes.")
            entries = [
                item for item in before.templates if item.template_id != template_id
            ]
            if candidate is not None:
                entries.append(
                    TemplateBinding(
                        template_id=template_id, snapshot_sha256=candidate.sha256
                    )
                )
            after = ProjectGuidanceBindings(
                owner_uid=os.getuid(),
                workspace=selected,
                revision=before.revision + 1,
                templates=tuple(sorted(entries, key=lambda item: item.template_id)),
            )
            old = None if previous is None else previous.model_dump(mode="json")
            new = None if candidate is None else candidate.model_dump(mode="json")
            body: dict[str, object] = {
                "storage": str(self.root.resolve()),
                "storage_identity": (
                    None
                    if handles is None
                    or (preview is not None and preview["storage_identity"] is None)
                    else self._storage_identity(handles)
                ),
                "action": action,
                "template_id": template_id,
                "before_file": None if before_file is None else before_file.identity,
                "before": before.model_dump(mode="json"),
                "after": after.model_dump(mode="json"),
                "previous_snapshot": old,
                "proposed_snapshot": new,
                "diff": "".join(
                    difflib.unified_diff(
                        (
                            json.dumps(old, ensure_ascii=True, sort_keys=True, indent=2)
                            + "\n"
                        ).splitlines(keepends=True),
                        (
                            json.dumps(new, ensure_ascii=True, sort_keys=True, indent=2)
                            + "\n"
                        ).splitlines(keepends=True),
                        fromfile="previous",
                        tofile="proposed",
                    )
                ),
            }
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            )
            if expected_sha256 is not None and preview_hash != expected_sha256:
                raise ValueError("Guidance changed; review the operation again.")

            def verify() -> None:
                self._storage_identity(handles)
                selected.selection()
                if read_file(root, project_name(selected)) != before_file:
                    raise ValueError("Project guidance changed before publication.")
                if self._snapshots(root, before) != snapshots:
                    raise ValueError("Pinned guidance changed before publication.")
                if candidate is not None:
                    assert descriptor_path is not None and markdown_path is not None
                    if (
                        inspect_guidance(
                            Path(selected.path), descriptor_path, markdown_path
                        )
                        != candidate.inspection
                    ):
                        raise ValueError("Guidance sources changed; review again.")

            verify()
            if expected_sha256 is not None:
                assert root is not None
                if candidate is not None:
                    publish_file(
                        root,
                        snapshot_name(candidate.sha256),
                        canonical_bytes(candidate),
                        verify,
                        immutable=True,
                    )

                def verify_binding() -> None:
                    verify()
                    if (
                        candidate is not None
                        and self._snapshot(root, selected, candidate.sha256)
                        != candidate
                    ):
                        raise ValueError(
                            "New guidance snapshot changed before binding."
                        )

                publish_file(
                    root, project_name(selected), canonical_bytes(after), verify_binding
                )
            return {
                **body,
                "preview_sha256": preview_hash,
                "applied": expected_sha256 is not None,
            }
