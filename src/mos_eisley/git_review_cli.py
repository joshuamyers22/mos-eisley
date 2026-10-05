"""Explicit no-provider Git review scope preflight and shared target parsing."""

import argparse
import json
import shlex
from pathlib import Path
from typing import NoReturn

from mos_eisley.core.models import canonical_bytes
from mos_eisley.git_review import (
    DEFAULT_CRITERIA,
    GitReviewSelection,
    GitReviewTarget,
    freeze_git_scope,
)
from mos_eisley.run.store import private_write


class ScopeParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(
            "Select --uncommitted, --base REF or --commit REF; "
            "or use --file PATH / --range PATH:START-END without a diff basis. "
            "--parent N is only valid with --commit."
        )


def add_options(parser: argparse.ArgumentParser) -> None:
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--uncommitted", action="store_true")
    target.add_argument("--base")
    target.add_argument("--commit")
    parser.add_argument("--parent", type=int)
    parser.add_argument("--criteria", default=DEFAULT_CRITERIA)
    parser.add_argument("--file", action="append", default=[], dest="files")
    parser.add_argument("--range", action="append", default=[], dest="ranges")


def selection(args: argparse.Namespace) -> GitReviewSelection:
    targets = [GitReviewTarget(path=path) for path in args.files]
    for value in args.ranges:
        path, separator, interval = value.rpartition(":")
        start, dash, end = interval.partition("-")
        if (
            not separator
            or not dash
            or not start.isascii()
            or not end.isascii()
            or not start.isdecimal()
            or not end.isdecimal()
        ):
            raise ValueError(
                "Use --range PATH:START-END with one-based inclusive lines."
            )
        targets.append(GitReviewTarget(path=path, start=int(start), end=int(end)))
    if not (args.uncommitted or args.base or args.commit or targets):
        raise ValueError(
            "Select --uncommitted, --base REF, --commit REF, --file or --range."
        )
    return GitReviewSelection(
        kind="uncommitted"
        if args.uncommitted
        else "base"
        if args.base
        else "commit"
        if args.commit
        else "files",
        reference=args.base or args.commit,
        parent=args.parent,
        criteria=args.criteria,
        targets=tuple(targets),
    )


def parse_review_selection(text: str) -> GitReviewSelection:
    parser = ScopeParser(add_help=False, allow_abbrev=False)
    add_options(parser)
    if not text.startswith("/review ") or "\n" in text or len(text) > 8000:
        raise ValueError("Use one bounded /review scope command.")
    return selection(parser.parse_args(shlex.split(text)[1:]))


def add_command(parser: argparse.ArgumentParser) -> None:
    add_options(parser)
    parser.add_argument("--workspace", "-C", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)


def run_command(args: argparse.Namespace) -> int:
    scope = freeze_git_scope(args.workspace, selection(args))
    artifact = {
        "scope": scope.model_dump(mode="json"),
        "preview": scope.preview(),
        "brief": scope.brief().model_dump(mode="json")
        if any(file.patch for file in scope.files)
        else None,
    }
    if args.output is not None:
        private_write(args.output, canonical_bytes(scope))
    print(json.dumps(artifact, ensure_ascii=False))
    return 0
