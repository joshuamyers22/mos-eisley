"""CLI for creating and replay-verifying immutable implementation bindings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_implementation_binding import (
    BINDING_MANIFEST_BYTES,
    BINDING_RECORD_BYTES,
    ImmutableImplementationBindingRecord,
    create_implementation_binding_record,
    decode_implementation_binding_manifest,
    decode_implementation_binding_record,
    verify_implementation_binding_record,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import private_write


def add_arguments(command: argparse.ArgumentParser, name: str) -> None:
    if name == "g4-bind-reviewer-implementation":
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--reviewer-package", type=Path, required=True)
        command.add_argument("--implementation-root", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    else:
        command.add_argument("--binding", type=Path, required=True)
        command.add_argument("--reviewer-package", type=Path, required=True)
        command.add_argument("--implementation-root", type=Path, required=True)


def _overlaps(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _binding_event(
    binding: ImmutableImplementationBindingRecord, *, event_type: str, path: Path
) -> str:
    return json.dumps(
        {
            "type": event_type,
            "path": str(path),
            "binding_record_sha256": binding.binding_record_sha256,
            "frozen_reviewer_test_package_sha256": (
                binding.payload.frozen_reviewer_test_package_sha256
            ),
            "implementation_tree_sha256": (binding.payload.implementation_tree_sha256),
            "adapter_sha256": binding.payload.adapter_sha256,
            "source_revision": binding.payload.manifest.source_revision,
            "implementation_binding_authorized": (
                binding.implementation_binding_authorized
            ),
            "test_execution_authorized": binding.test_execution_authorized,
            "repository_write_authorized": binding.repository_write_authorized,
            "vcs_authorized": binding.vcs_authorized,
            "network_authorized": binding.network_authorized,
            "credential_access_authorized": binding.credential_access_authorized,
            "provider_dispatch_authorized": binding.provider_dispatch_authorized,
            "correction_authorized": binding.correction_authorized,
            "acceptance_authorized": binding.acceptance_authorized,
        }
    )


def run_command(args: argparse.Namespace) -> int:
    package_path = cast(Path, args.reviewer_package)
    implementation_root = cast(Path, args.implementation_root)
    if args.command == "g4-verify-reviewer-implementation-binding":
        binding_path = cast(Path, args.binding)
        if _overlaps(implementation_root, binding_path) or _overlaps(
            implementation_root, package_path
        ):
            raise ValueError("implementation root must be separate from binding inputs")
        record = decode_implementation_binding_record(
            read_bounded(binding_path, BINDING_RECORD_BYTES)
        )
        verify_implementation_binding_record(record, package_path, implementation_root)
        print(
            _binding_event(
                record,
                event_type="g4.reviewer_implementation_binding.verified",
                path=binding_path,
            )
        )
        return 0

    manifest_path = cast(Path, args.manifest)
    output = cast(Path, args.output)
    protected = (manifest_path, package_path)
    if any(_overlaps(implementation_root, path) for path in (*protected, output)):
        raise ValueError("implementation root must be separate from inputs and output")
    if any(_overlaps(output, path) for path in protected):
        raise ValueError("output must be separate from every input")
    manifest = decode_implementation_binding_manifest(
        read_bounded(manifest_path, BINDING_MANIFEST_BYTES)
    )
    record = create_implementation_binding_record(
        manifest, package_path, implementation_root
    )
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_write(output, canonical_bytes(record))
    print(
        _binding_event(
            record,
            event_type="g4.reviewer_implementation_binding.created",
            path=output,
        )
    )
    return 0
