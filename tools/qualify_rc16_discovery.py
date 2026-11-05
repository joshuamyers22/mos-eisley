"""Qualify frozen rc.16 discovery with actual signed native installers, no inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import cast

from mos_eisley.app_release import (
    FEEDS,
    MAX_METADATA,
    MAX_PREVIEW_INVENTORY,
    Release,
    download,
    parse_release,
    platform_id,
)
from tools.qualify_published_upgrade import artifact

SOURCE = "14eb79d52950f340aba159815222e04e6ea864e3"
VERSION = "0.1.0-rc.16"
PREVIOUS_SOURCE = "21fc2b02db5611d806626ad8c70698b3c7181577"
PREVIOUS_VERSION = "0.1.0-rc.15"
PUBLIC_METADATA_SHA256 = (
    "a7dc636d2dc1c6078694393dd27388b5fea53cbe9bb3d2bbe61d9a18e646915b"
)


class QualificationError(ValueError):
    """Fixed, content-free refusal reason owned by this harness."""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def admitted(directory: Path, source: str, version: str) -> tuple[Release, Path]:
    release, _, bootstrap = artifact(directory, source)
    if (
        release.version != version
        or release.channel != "preview"
        or release.storage_epoch != 2
    ):
        raise QualificationError("wrong signed version/channel/epoch")
    lines = (directory / "BOOTSTRAP_SHA256SUMS").read_text().splitlines()
    matches = [
        line.split()[0]
        for line in lines
        if len(line.split()) == 2 and line.split()[1] == bootstrap.name
    ]
    if matches != [sha(bootstrap.read_bytes())]:
        raise QualificationError("bootstrap checksum mismatch or duplicate")
    return release, bootstrap


def command(binary: Path, args: list[str], home: Path) -> dict[str, object]:
    result = subprocess.run(
        [str(binary), *args],
        cwd=home,
        env={
            "HOME": str(home),
            "PATH": str(home / "no-host-tools"),
            "TMPDIR": str(home / "tmp"),
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
        },
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if (
        result.returncode
        or len(result.stdout.encode()) > 128 * 1024
        or len(result.stderr.encode()) > 128 * 1024
    ):
        raise QualificationError("native command failed or exceeded output bound")
    value: object = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise QualificationError("native result is not an object")
    return cast(dict[str, object], value)


def install(
    directory: Path, release: Release, bootstrap: Path, home: Path, root: Path
) -> None:
    command(
        bootstrap,
        [
            "--metadata",
            str(directory / "release.json"),
            "--archive",
            str(directory / f"mos-{release.version}-{platform_id()}.tar.gz"),
            "--version",
            release.version,
            "--channel",
            "preview",
            "--root",
            str(root),
            "--bin-dir",
            str(home / "bin"),
        ],
        home,
    )


def qualify(
    candidate: Path, previous: Path, target: str, harness: str
) -> dict[str, object]:
    if target != platform_id():
        raise QualificationError("host platform differs from target")
    actual_harness = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    if harness != actual_harness:
        raise QualificationError("harness source differs from checkout")
    current, current_bootstrap = admitted(candidate, SOURCE, VERSION)
    old, old_bootstrap = admitted(previous, PREVIOUS_SOURCE, PREVIOUS_VERSION)
    feed = download(FEEDS["preview"], MAX_PREVIEW_INVENTORY)
    if len(feed) <= MAX_METADATA:
        raise QualificationError(
            "public feed no longer reproduces the original size boundary"
        )
    result: dict[str, object] = {
        "schema": "rc16-signed-discovery/v1",
        "status": "running",
        "platform": target,
        "source": SOURCE,
        "version": VERSION,
        "harness_source": harness,
        "harness_sha256": sha(Path(__file__).read_bytes()),
        "candidate_metadata_sha256": sha(current.raw),
        "candidate_archive_sha256": current.artifact(target).sha256,
        "candidate_bootstrap_sha256": sha(current_bootstrap.read_bytes()),
        "predecessor_source": old.source_commit,
        "predecessor_metadata_sha256": sha(old.raw),
        "predecessor_archive_sha256": old.artifact(target).sha256,
        "predecessor_bootstrap_sha256": sha(old_bootstrap.read_bytes()),
        "public_feed_bytes": len(feed),
        "public_feed_sha256": sha(feed),
        "provider_calls": 0,
        "inventory_byte_limit": MAX_PREVIEW_INVENTORY,
        "metadata_byte_limit": MAX_METADATA,
        "host_tools_on_native_path": False,
    }
    with tempfile.TemporaryDirectory(prefix="mos-rc16-discovery-") as temporary:
        base = Path(temporary).resolve()
        home = base / "home"
        home.mkdir(mode=0o700)
        (home / "tmp").mkdir(mode=0o700)
        root = home / "app"
        install(previous, old, old_bootstrap, home, root)
        sentinel = root / "synthetic-private-state"
        sentinel.write_bytes(b"preserve synthetic uncertainty")
        native = root / "current" / "mos"
        command(native, ["update", "preview", "--root", str(root), "--json"], home)
        before = command(
            native, ["update", "check", "--root", str(root), "--json"], home
        )
        if (
            before.get("status") != "unable_to_check"
            or before.get("installed") != PREVIOUS_VERSION
        ):
            raise QualificationError("old native refusal did not reproduce")
        cache = root / "update-cache-preview.json"
        failed_cache = cache.read_bytes()
        sentinel_hash = sha(sentinel.read_bytes())
        install(candidate, current, current_bootstrap, home, root)
        if (
            cache.read_bytes() != failed_cache
            or sha(sentinel.read_bytes()) != sentinel_hash
        ):
            raise QualificationError(
                "explicit upgrade changed preserved synthetic state/cache"
            )
        pointer = (root / "current").resolve()
        binary_sha = sha(native.read_bytes())
        after = command(
            native, ["update", "check", "--root", str(root), "--json"], home
        )
        if (
            after.get("status") != "up_to_date"
            or after.get("installed") != VERSION
            or after.get("latest") != PREVIOUS_VERSION
            or after.get("available") is not False
            or after.get("notify", False) is not False
        ):
            raise QualificationError("new signed native public discovery failed")
        cached = json.loads(cache.read_text())
        if cached["failed"] is not False:
            raise QualificationError("new native retained a failed discovery result")
        public = parse_release(cached["release"].encode())
        if (
            public.version != PREVIOUS_VERSION
            or public.source_commit != PREVIOUS_SOURCE
            or sha(public.raw) != PUBLIC_METADATA_SHA256
        ):
            raise QualificationError(
                "public enrolled metadata differs from the selected profile"
            )
        if (
            pointer != (root / "current").resolve()
            or sha(sentinel.read_bytes()) != sentinel_hash
        ):
            raise QualificationError(
                "read-only discovery changed runtime pointer or synthetic state"
            )
        result.update(
            {
                "status": "passed",
                "old_native_refusal_reproduced": True,
                "explicit_signed_rc15_to_rc16_upgrade": True,
                "old_failed_cache_preserved_during_upgrade": True,
                "new_native_public_discovery": True,
                "public_metadata_enrolled": True,
                "public_version": public.version,
                "public_metadata_sha256": sha(public.raw),
                "native_sha256": binary_sha,
                "synthetic_state_unchanged": True,
                "runtime_pointer_unchanged_by_discovery": True,
            }
        )
    result["private_root_removed"] = not base.exists()
    if not result["private_root_removed"]:
        raise QualificationError("qualification cleanup failed")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--predecessor", type=Path, required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--harness-source", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = qualify(
            args.candidate.resolve(),
            args.predecessor.resolve(),
            args.platform,
            args.harness_source,
        )
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result = {
            "schema": "rc16-signed-discovery/v1",
            "status": "failed",
            "error_type": type(error).__name__,
            "error_code": str(error)
            if isinstance(error, QualificationError)
            else "external_boundary_failure",
            "source": SOURCE,
            "platform": args.platform,
            "provider_calls": 0,
        }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(
        json.dumps(
            {"status": result["status"], "platform": args.platform, "provider_calls": 0}
        )
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
