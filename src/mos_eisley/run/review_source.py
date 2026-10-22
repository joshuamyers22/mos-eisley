"""Exact, inert Git-source admission shared by preview and paid launch."""

import os
from pathlib import Path

from mos_eisley.core.models import Brief, canonical_bytes, digest
from mos_eisley.git_review import MAX_SCOPE_BYTES, GitReviewScope, revalidate_git_scope
from mos_eisley.run.files import read_bounded


def check_review_source(scope: GitReviewScope, workspace: Path, brief: Brief) -> None:
    if (
        scope.owner_uid != os.getuid()
        or scope.workspace != str(workspace.resolve())
        or not scope.complete
        or scope.brief() != brief
    ):
        raise ValueError("Live review requires this owner's exact complete Git brief.")
    revalidate_git_scope(scope)


def read_review_source(
    path: Path | None, expected_sha256: str | None, workspace: Path, brief: Brief
) -> GitReviewScope | None:
    if (path is None) != (expected_sha256 is None):
        raise ValueError(
            "Review scope and its expected hash must be selected together."
        )
    if path is None:
        return None
    raw = read_bounded(path, MAX_SCOPE_BYTES)
    if digest(raw) != expected_sha256:
        raise ValueError("Selected review scope changed.")
    try:
        scope = GitReviewScope.model_validate_json(raw)
    except ValueError:
        raise ValueError("Invalid frozen review scope.") from None
    if raw != canonical_bytes(scope):
        raise ValueError("Review scope requires canonical artifact bytes.")
    check_review_source(scope, workspace, brief)
    return scope
