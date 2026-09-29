"""Offline CLI for freezing and replay-verifying blind reviewer-test packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_test_package import (
    FROZEN_PACKAGE_BYTES,
    MANIFEST_BYTES,
    decode_frozen_reviewer_test_package,
    decode_reviewer_test_manifest,
    freeze_reviewer_test_package,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import private_write


def add_arguments(command: argparse.ArgumentParser, name: str) -> None:
    if name == "g4-freeze-reviewer-test-package":
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--package-root", type=Path, required=True)
        command.add_argument(
            "--reference",
            type=Path,
            action="append",
            required=True,
            help="Approved derivation reference, repeated in manifest order",
        )
        command.add_argument("--output", type=Path, required=True)
    else:
        command.add_argument("--package", type=Path, required=True)


def _overlaps(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _write_private_contract(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_write(path, payload)


def run_command(args: argparse.Namespace) -> int:
    if args.command == "g4-verify-reviewer-test-package":
        package = decode_frozen_reviewer_test_package(
            read_bounded(cast(Path, args.package), FROZEN_PACKAGE_BYTES)
        )
        print(
            json.dumps(
                {
                    "type": "g4.reviewer_test_package.verified",
                    "path": str(cast(Path, args.package)),
                    "frozen_package_sha256": package.frozen_package_sha256,
                    "payload_sha256": package.payload_sha256,
                    "files": len(package.payload.files),
                    "test_execution_authorized": package.test_execution_authorized,
                    "implementation_binding_authorized": (
                        package.implementation_binding_authorized
                    ),
                    "repository_write_authorized": (
                        package.repository_write_authorized
                    ),
                }
            )
        )
        return 0

    manifest_path = cast(Path, args.manifest)
    package_root = cast(Path, args.package_root)
    reference_paths = tuple(cast(list[Path], args.reference))
    output = cast(Path, args.output)
    protected = (manifest_path, *reference_paths)
    if any(_overlaps(package_root, path) for path in (*protected, output)):
        raise ValueError("package root must be separate from references and output")
    if any(_overlaps(output, path) for path in protected):
        raise ValueError("output must be separate from every input")
    manifest = decode_reviewer_test_manifest(
        read_bounded(manifest_path, MANIFEST_BYTES)
    )
    package = freeze_reviewer_test_package(manifest, package_root, reference_paths)
    _write_private_contract(output, canonical_bytes(package))
    print(
        json.dumps(
            {
                "type": "g4.reviewer_test_package.frozen",
                "path": str(output),
                "manifest_sha256": manifest.manifest_sha256,
                "payload_sha256": package.payload_sha256,
                "frozen_package_sha256": package.frozen_package_sha256,
                "files": len(package.payload.files),
                "declared_markers": len(manifest.declared_markers),
                "test_execution_authorized": package.test_execution_authorized,
                "implementation_binding_authorized": (
                    package.implementation_binding_authorized
                ),
                "repository_write_authorized": package.repository_write_authorized,
                "vcs_authorized": package.vcs_authorized,
                "network_authorized": package.network_authorized,
                "credential_access_authorized": package.credential_access_authorized,
                "provider_dispatch_authorized": package.provider_dispatch_authorized,
            }
        )
    )
    return 0
