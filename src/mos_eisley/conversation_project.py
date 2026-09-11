"""Bounded Git-marker discovery for display, separate from persisted identity."""

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

MAX_PROJECT_ANCESTORS = 64
Detection = Literal["git-directory", "git-file", "none", "unavailable", "limit"]


@dataclass(frozen=True)
class ProjectLocation:
    workspace: str
    root: str | None
    detection: Detection

    @classmethod
    def inspect(cls, workspace: Path) -> "ProjectLocation":
        # This result supplies display metadata only. Never use it to select
        # memory, session storage, tool permissions or repository configuration.
        try:
            current = workspace.resolve(strict=True)
            if not current.is_dir():
                raise ValueError("workspace is not a directory")
        except (OSError, ValueError, RuntimeError):
            return cls(str(workspace), None, "unavailable")
        canonical = str(current)
        for _ in range(MAX_PROJECT_ANCESTORS):
            try:
                mode = (current / ".git").lstat().st_mode
            except FileNotFoundError:
                pass
            except OSError:
                return cls(canonical, None, "unavailable")
            else:
                if stat.S_ISDIR(mode):
                    return cls(canonical, str(current), "git-directory")
                if stat.S_ISREG(mode):
                    return cls(canonical, str(current), "git-file")
                # A suspicious nearer marker must not select an outer project.
                return cls(canonical, None, "unavailable")
            if current.parent == current:
                return cls(canonical, None, "none")
            current = current.parent
        return cls(canonical, None, "limit")

    def root_label(self) -> str:
        if self.root is not None:
            return self.root
        return {
            "none": "none detected",
            "limit": "unknown (ancestor scan limit)",
        }.get(self.detection, "unknown (discovery unavailable)")

    def fields(self, memory_workspace: str | None = None) -> dict[str, object]:
        return {
            "workspace": self.workspace,
            "project_root": self.root,
            "project_detection": self.detection,
            "memory_workspace": memory_workspace or self.workspace,
        }

    def describe(self, memory_workspace: str | None = None) -> str:
        return (
            f"Working directory\n{self.workspace}\n\n"
            f"Project root (Git marker at startup)\n{self.root_label()}\n"
            f"Detection: {self.detection}\n\n"
            f"Project memory identity\n{memory_workspace or self.workspace}"
        )
