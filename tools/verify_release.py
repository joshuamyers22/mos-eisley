"""Reject a release tag that does not match metadata or the mainline commit."""

from __future__ import annotations

import argparse
import subprocess
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import cast


def project_version(manifest: Path) -> str:
    document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    project_value: object = document.get("project")
    if not isinstance(project_value, dict):
        raise ValueError(f"{manifest} has no [project] table")
    project = cast(dict[str, object], project_value)
    version: object = project.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{manifest} has no valid project version")
    return version


def git_revision(repo: Path, ref: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--end-of-options", ref],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def verify_release(
    manifest: Path, tag: str, *, repo: Path | None = None, main_ref: str | None = None
) -> None:
    expected = f"v{project_version(manifest)}"
    if tag != expected:
        raise ValueError(f"release tag {tag!r} does not match {expected!r}")
    if main_ref is None:
        return
    if repo is None:
        raise ValueError("repository path is required for mainline verification")
    tag_commit = git_revision(repo, f"refs/tags/{tag}^{{commit}}")
    head_commit = git_revision(repo, "HEAD")
    if tag_commit != head_commit:
        raise ValueError("release checkout does not match the exact tag commit")
    main_commit = git_revision(repo, main_ref)
    ancestry = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "merge-base",
            "--is-ancestor",
            tag_commit,
            main_commit,
        ],
        capture_output=True,
        check=False,
    )
    if ancestry.returncode != 0:
        raise ValueError("release tag commit is not reachable from main")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--tag", required=True)
    command.add_argument("--manifest", type=Path, default=Path("pyproject.toml"))
    command.add_argument(
        "--main-ref", help="require tag commit to be reachable from this ref"
    )
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    verify_release(
        cast(Path, args.manifest),
        cast(str, args.tag),
        repo=Path.cwd(),
        main_ref=cast(str | None, args.main_ref),
    )
    print(f"release tag {args.tag} matches project metadata and requested ancestry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
