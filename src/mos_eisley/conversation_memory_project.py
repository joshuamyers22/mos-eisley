"""Explicit ancestor memory identities; Git discovery never selects one."""

import json
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from mos_eisley.core.models import digest

if TYPE_CHECKING:
    from mos_eisley.conversation_directory import DirectorySelection


def memory_workspace(workspace: str, project_root: str | None) -> str:
    if project_root is None:
        return workspace
    root = PurePosixPath(project_root)
    working = PurePosixPath(workspace)
    if (
        not root.is_absolute()
        or str(root) != project_root
        or str(working) != workspace
        or ".." in root.parts
        or ".." in working.parts
        or not working.is_relative_to(root)
        or not project_root.isprintable()
        or len(project_root.encode("utf-8")) > 4096
    ):
        raise ValueError("Memory project root must be a canonical workspace ancestor.")
    return project_root


def select_memory_project(workspace: Path, root: Path) -> "DirectorySelection":
    from mos_eisley.conversation_directory import DirectorySelection

    working = DirectorySelection.inspect(workspace)
    selected = DirectorySelection.inspect(root)
    memory_workspace(str(working.path), str(selected.path))
    return selected


def preview_memory_project(
    storage: Path, workspace: Path, root: Path
) -> dict[str, object]:
    from mos_eisley.conversation_directory import DirectorySelection
    from mos_eisley.conversation_memory import MemoryStore

    selected_source = DirectorySelection.inspect(workspace)
    selected = select_memory_project(selected_source.path, root)
    source = MemoryStore(storage, selected_source.path)
    target = MemoryStore(storage, selected.path)
    before, after = source.project_pair(target)
    selected.verify()
    selected_source.verify()
    status = (
        "same-identity"
        if source.workspace == target.workspace
        else "collision"
        if before is not None and after is not None
        else "source-only"
        if before is not None
        else "target-only"
        if after is not None
        else "empty"
    )
    body: dict[str, object] = {
        "workspace": source.workspace,
        "memory_project_root": target.workspace,
        "status": status,
        "source_path": str(source.path("project")),
        "target_path": str(target.path("project")),
        "source": before.model_dump(mode="json") if before else None,
        "target": after.model_dump(mode="json") if after else None,
        "applied": False,
    }
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**body, "preview_sha256": digest(payload)}
