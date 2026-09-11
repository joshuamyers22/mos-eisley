"""Explicit directory handoff without carrying project conversation inputs."""

import argparse
from dataclasses import dataclass
from pathlib import Path

from mos_eisley.conversation_directory import (
    DirectorySelection,
    DirectorySelectionError,
    valid_path_text,
)

SWITCH_COMMAND = "/directory switch"


def is_directory_switch(text: str) -> bool:
    return text == SWITCH_COMMAND or text.startswith(SWITCH_COMMAND + " ")


def switch_target(text: str, workspace: Path) -> DirectorySelection | None:
    if text == SWITCH_COMMAND:
        return None
    value = text.removeprefix(SWITCH_COMMAND + " ")
    if not is_directory_switch(text) or not valid_path_text(value):
        raise DirectorySelectionError(
            "Use /directory switch or /directory switch PATH."
        )
    try:
        path = Path(value).expanduser()
    except RuntimeError:
        raise DirectorySelectionError("That directory is unavailable.") from None
    return DirectorySelection.inspect(path if path.is_absolute() else workspace / path)


@dataclass(frozen=True)
class DirectoryHandoff:
    target: DirectorySelection


def fresh_directory_arguments(
    previous: argparse.Namespace, target: DirectorySelection
) -> argparse.Namespace:
    """Retain invocation options; clear session/project-specific launch inputs."""
    values = vars(previous).copy()
    values.update(
        command="chat",
        workspace=target.path,
        directory_selection=target,
        choose_directory=False,
        name=None,
        prompt=None,
        cassette=None,
        review_packet=None,
        session_id=None,
        last=False,
        inspect=False,
        refresh_memory=False,
        refresh_cassette=None,
        catalog_max_bytes=None,
        memory_project_root=None,
    )
    return argparse.Namespace(**values)
