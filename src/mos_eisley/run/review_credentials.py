"""Read one selected provider key only after signed and local review approval."""

import stat
from pathlib import Path

from mos_eisley.run.files import read_bounded


def load_review_key(path: Path, provider: str) -> str:
    if provider not in {"openai", "anthropic"}:
        raise ValueError("review credential provider is unsupported")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError("review key must be a private regular file")
    value = read_bounded(path, 4096).decode("utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise ValueError("review key file must contain one nonempty line")
    return value
