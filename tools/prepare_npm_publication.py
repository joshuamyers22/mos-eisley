"""Verify the signed four-platform release before preparing registry packages."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from mos_eisley.app_release import (
    MAX_ARCHIVE,
    MAX_METADATA,
    RELEASE_ORIGIN,
    Release,
    ReleaseError,
    download,
    parse_release,
    verify_archive,
)

PLATFORMS = {"linux-aarch64", "linux-x86_64", "macos-aarch64", "macos-x86_64"}


def bounded_read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ReleaseError("publication artifact exceeds its size limit")
    return raw


def validate_lineage(raw: bytes, tag: str, commit: str) -> Release:
    release = parse_release(raw)
    if tag != f"v{release.version}" or release.source_commit != commit:
        raise ReleaseError("publication tag/commit differs from signed release")
    if {item.platform for item in release.artifacts} != PLATFORMS:
        raise ReleaseError("publication requires all four native platforms")
    return release


def acquire_publication(assets: Path, tag: str, commit: str) -> None:
    # Validate the tag before building an endpoint or contacting the publisher.
    from mos_eisley.app_release import version_key

    if not tag.startswith("v"):
        raise ReleaseError("publication requires a version tag")
    version_key(tag[1:])
    raw = download(f"{RELEASE_ORIGIN}{tag}/release.json", MAX_METADATA)
    release = validate_lineage(raw, tag, commit)
    assets.mkdir(parents=True, exist_ok=False)
    (assets / "release.json").write_bytes(raw)
    for item in release.artifacts:
        raw_archive = download(item.url, min(MAX_ARCHIVE, item.size))
        verify_archive(raw_archive, item)
        archive = assets / f"mos-{release.version}-{item.platform}.tar.gz"
        archive.write_bytes(raw_archive)


def verify_publication(assets: Path, tag: str, commit: str) -> Release:
    release = validate_lineage(
        bounded_read(assets / "release.json", MAX_METADATA), tag, commit
    )
    for item in release.artifacts:
        archive = assets / f"mos-{release.version}-{item.platform}.tar.gz"
        verify_archive(bounded_read(archive, min(MAX_ARCHIVE, item.size)), item)
    return release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        acquire_publication(args.artifacts, args.tag, args.commit)
    release = verify_publication(args.artifacts, args.tag, args.commit)
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("package_app_managers.py")),
            "--artifacts",
            str(args.artifacts),
            "--output",
            str(args.output),
        ],
        check=True,
    )
    print(
        f"Verified {release.version} at {release.source_commit}; "
        "packages prepared for owner-reviewed staging."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
