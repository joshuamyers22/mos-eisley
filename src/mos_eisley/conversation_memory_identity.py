"""Exact historical project identities for explicitly reviewed memory relocation."""

import stat
from dataclasses import dataclass
from pathlib import Path

from mos_eisley.conversation_directory import DirectorySelection, valid_path_text


@dataclass(frozen=True)
class RelocationSource:
    path: Path
    exists: bool
    anchor: DirectorySelection

    @classmethod
    def inspect(cls, identity: str) -> "RelocationSource":
        """Never normalize an old identity into a different memory document key."""
        path = Path(identity)
        if (
            not valid_path_text(identity)
            or not path.is_absolute()
            or str(path) != identity
            or identity.startswith("//")
            or ".." in path.parts
        ):
            raise ValueError("Use the exact canonical absolute source workspace.")
        try:
            if path.resolve(strict=False) != path:
                raise ValueError("Source identity must not traverse a symlink.")
            anchor = path
            while True:
                try:
                    info = anchor.lstat()
                except FileNotFoundError:
                    anchor = anchor.parent
                    continue
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError(
                        "Source identity must name a directory or be absent."
                    )
                break
            selection = DirectorySelection.inspect(anchor)
            if selection.path != anchor:
                raise ValueError("Source identity must not traverse a symlink.")
        except (OSError, RuntimeError):
            raise ValueError(
                "Source identity is inaccessible; inspect its path."
            ) from None
        return cls(path, anchor == path, selection)

    def verify(self) -> None:
        if self.inspect(str(self.path)) != self:
            raise ValueError("Source identity changed; preview relocation again.")

    def receipt(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "anchor": {
                "path": str(self.anchor.path),
                "device": self.anchor.device,
                "inode": self.anchor.inode,
            },
        }
