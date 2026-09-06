"""Exclusive local claims for one-attempt frozen-policy holdout evaluation."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from mos_eisley.core.models import canonical_bytes
from mos_eisley.evaluation.routing_holdout import HoldoutUseClaim
from mos_eisley.evaluation.skill_comparison import SkillHoldoutUseClaim


def _claim(directory: Path, filename: str, payload: bytes) -> Path:
    """Atomically consume one namespaced claim in a trusted private directory."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(directory, flags)
    try:
        metadata = os.fstat(directory_fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("holdout use path must be a directory")
        if metadata.st_uid != os.getuid():
            raise ValueError("holdout use directory must be owned by the current user")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError(
                "holdout use directory must not grant group or other access"
            )
        fd = os.open(
            filename,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return directory / filename


def claim_holdout_use(directory: Path, claim: HoldoutUseClaim) -> Path:
    """Atomically consume a policy-keyed claim in a trusted private directory."""
    filename = f"{claim.candidate_policy_sha256}.json"
    return _claim(directory, filename, canonical_bytes(claim))


def claim_skill_holdout_use(directory: Path, claim: SkillHoldoutUseClaim) -> Path:
    """Atomically consume a sealed-comparison claim before skill holdout scoring."""
    filename = f"skill-{claim.sealed_comparison_sha256}.json"
    return _claim(directory, filename, canonical_bytes(claim))
