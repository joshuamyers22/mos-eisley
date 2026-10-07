"""Frozen credential-free installer; does not require an installed Python."""

from __future__ import annotations

import argparse
from pathlib import Path

from mos_eisley.app_install import default_root, install
from mos_eisley.app_release import (
    MAX_ARCHIVE,
    MAX_METADATA,
    RELEASE_ORIGIN,
    ReleaseError,
    download,
    parse_release,
    platform_id,
    release_metadata,
)


def bounded_file(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ReleaseError("offline artifact exceeds its size limit")
    return raw


def main() -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--root", type=Path, default=default_root())
    command.add_argument("--bin-dir", type=Path, default=Path.home() / ".local/bin")
    command.add_argument(
        "--metadata",
        type=Path,
        help="previously acquired signed release.json for offline installation",
    )
    command.add_argument(
        "--archive", type=Path, help="previously acquired platform archive"
    )
    command.add_argument("--version", help="require this exact release version")
    command.add_argument("--channel", choices=("stable", "preview"), default="stable")
    args = command.parse_args()
    if (args.metadata is None) != (args.archive is None):
        command.error("offline installation requires both --metadata and --archive")
    raw = (
        bounded_file(args.metadata, MAX_METADATA)
        if args.metadata
        else download(f"{RELEASE_ORIGIN}v{args.version}/release.json", MAX_METADATA)
        if args.version
        else release_metadata(args.channel)
    )
    release = parse_release(raw)
    if release.channel != args.channel or (
        args.version and release.version != args.version
    ):
        command.error("release channel/version differs from selected installation")
    artifact = release.artifact(platform_id())
    archive = (
        bounded_file(args.archive, min(MAX_ARCHIVE, artifact.size))
        if args.archive
        else download(artifact.url, min(MAX_ARCHIVE, artifact.size))
    )
    install(args.root, args.bin_dir, release, archive)
    print(
        f"Installed Mos Eisley {release.version}. Add {args.bin_dir} "
        "to PATH, then run mos setup and mos in your project. "
        "Existing sessions, credentials and spending records are preserved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
