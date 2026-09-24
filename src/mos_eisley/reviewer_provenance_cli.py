"""CLI for authenticated G4 custody and read-only VCS/E2 provenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.reviewer_provenance import (
    PROVENANCE_ARTIFACT_BYTES,
    AuthenticatedG4ProvenanceRecord,
    G4ProvenanceTrustPolicy,
    SignedG4ChildAssignment,
    SignedG4ChildResult,
    SignedG4CreatorApproval,
    SignedG4ReviewerCustody,
    SignedTrustedGitProvenance,
    assemble_authenticated_provenance,
    decode_provenance_artifact,
    record_trusted_git_provenance,
    verify_authenticated_provenance,
    verify_custody_chain,
)
from mos_eisley.reviewer_test_execution import (
    CONTROL_RECORD_BYTES,
    decode_control_record,
    load_binding,
)
from mos_eisley.reviewer_test_package import (
    FROZEN_PACKAGE_BYTES,
    FrozenReviewerTestPackage,
    decode_frozen_reviewer_test_package,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.store import private_write


def add_arguments(command: argparse.ArgumentParser, name: str) -> None:
    if name == "g4-record-reviewer-git-provenance":
        _add_custody_inputs(command)
        _add_git_inputs(command)
        command.add_argument("--output", type=Path, required=True)
    elif name == "g4-assemble-reviewer-provenance":
        _add_custody_inputs(command)
        command.add_argument("--git-provenance", type=Path, required=True)
        command.add_argument("--controls", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    else:
        command.add_argument("--record", type=Path, required=True)
        command.add_argument("--binding", type=Path, required=True)
        command.add_argument("--reviewer-package", type=Path, required=True)
        command.add_argument("--controls", type=Path, required=True)
        _add_git_location(command)


def _add_custody_inputs(command: argparse.ArgumentParser) -> None:
    command.add_argument("--policy", type=Path, required=True)
    command.add_argument("--creator-approval", type=Path, required=True)
    command.add_argument("--reviewer-custody", type=Path, required=True)
    command.add_argument("--child-assignment", type=Path, required=True)
    command.add_argument("--child-result", type=Path, required=True)
    command.add_argument("--binding", type=Path, required=True)
    command.add_argument("--reviewer-package", type=Path, required=True)


def _add_git_location(command: argparse.ArgumentParser) -> None:
    command.add_argument("--repository-root", type=Path, required=True)
    command.add_argument("--implementation-root", type=Path, required=True)
    command.add_argument("--git", type=Path, required=True)


def _add_git_inputs(command: argparse.ArgumentParser) -> None:
    _add_git_location(command)
    command.add_argument("--repository-id", required=True)


def _load[T: Contract](path: Path, model: type[T]) -> T:
    return decode_provenance_artifact(
        read_bounded(path, PROVENANCE_ARTIFACT_BYTES), model
    )


def _load_custody(
    args: argparse.Namespace,
) -> tuple[
    G4ProvenanceTrustPolicy,
    SignedG4CreatorApproval,
    SignedG4ReviewerCustody,
    SignedG4ChildAssignment,
    SignedG4ChildResult,
]:
    return (
        _load(cast(Path, args.policy), G4ProvenanceTrustPolicy),
        _load(cast(Path, args.creator_approval), SignedG4CreatorApproval),
        _load(cast(Path, args.reviewer_custody), SignedG4ReviewerCustody),
        _load(cast(Path, args.child_assignment), SignedG4ChildAssignment),
        _load(cast(Path, args.child_result), SignedG4ChildResult),
    )


def _load_package(path: Path) -> FrozenReviewerTestPackage:
    return decode_frozen_reviewer_test_package(read_bounded(path, FROZEN_PACKAGE_BYTES))


def _overlaps(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _protect_repository(repository_root: Path, paths: tuple[Path, ...]) -> None:
    if any(path.resolve().is_relative_to(repository_root.resolve()) for path in paths):
        raise ValueError(
            "G4 provenance inputs and output must remain outside repository"
        )


def _write_private(path: Path, value: Contract) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_write(path, canonical_bytes(value))


def _event(kind: str, path: Path, sha256: str) -> str:
    return json.dumps(
        {
            "type": kind,
            "path": str(path),
            "sha256": sha256,
            "child_dispatch_authorized": False,
            "repository_write_authorized": False,
            "vcs_write_authorized": False,
            "network_authorized": False,
            "credential_access_authorized": False,
            "provider_dispatch_authorized": False,
            "correction_authorized": False,
            "acceptance_authorized": False,
        },
        sort_keys=True,
    )


def _record(args: argparse.Namespace) -> int:
    policy, creator, reviewer, assignment, result = _load_custody(args)
    package_path = cast(Path, args.reviewer_package)
    binding_path = cast(Path, args.binding)
    root = cast(Path, args.repository_root)
    implementation = cast(Path, args.implementation_root)
    output = cast(Path, args.output)
    protected = tuple(
        cast(Path, getattr(args, name))
        for name in (
            "policy",
            "creator_approval",
            "reviewer_custody",
            "child_assignment",
            "child_result",
            "binding",
            "reviewer_package",
        )
    ) + (output,)
    _protect_repository(root, protected)
    if any(_overlaps(output, path) for path in protected[:-1]):
        raise ValueError("G4 Git provenance output must be separate from its inputs")
    package = _load_package(package_path)
    verify_custody_chain(policy, creator, reviewer, assignment, result, package)
    provenance = record_trusted_git_provenance(
        repository_id=cast(str, args.repository_id),
        repository_root=root,
        implementation_root=implementation,
        git_executable=cast(Path, args.git),
        binding=load_binding(binding_path),
        reviewer_package_path=package_path,
        assignment=assignment,
        result=result,
    )
    _write_private(output, provenance)
    print(_event("g4.git_provenance.recorded", output, provenance.provenance_sha256))
    return 0


def _assemble(args: argparse.Namespace) -> int:
    policy, creator, reviewer, assignment, result = _load_custody(args)
    package_path = cast(Path, args.reviewer_package)
    output = cast(Path, args.output)
    inputs = tuple(
        cast(Path, getattr(args, name))
        for name in (
            "policy",
            "creator_approval",
            "reviewer_custody",
            "child_assignment",
            "child_result",
            "binding",
            "reviewer_package",
            "git_provenance",
            "controls",
        )
    )
    if any(_overlaps(output, path) for path in inputs):
        raise ValueError("authenticated provenance output must be separate from inputs")
    record = assemble_authenticated_provenance(
        policy=policy,
        creator=creator,
        reviewer=reviewer,
        assignment=assignment,
        result=result,
        git_provenance=_load(
            cast(Path, args.git_provenance), SignedTrustedGitProvenance
        ),
        package=_load_package(package_path),
        binding=load_binding(cast(Path, args.binding)),
        controls=decode_control_record(
            read_bounded(cast(Path, args.controls), CONTROL_RECORD_BYTES)
        ),
    )
    _write_private(output, record)
    print(_event("g4.authenticated_provenance.assembled", output, record.record_sha256))
    return 0


def _verify(args: argparse.Namespace) -> int:
    record_path = cast(Path, args.record)
    package_path = cast(Path, args.reviewer_package)
    binding_path = cast(Path, args.binding)
    controls_path = cast(Path, args.controls)
    root = cast(Path, args.repository_root)
    _protect_repository(root, (record_path, package_path, binding_path, controls_path))
    record = _load(record_path, AuthenticatedG4ProvenanceRecord)
    package = _load_package(package_path)
    binding = load_binding(binding_path)
    controls = decode_control_record(read_bounded(controls_path, CONTROL_RECORD_BYTES))
    verify_authenticated_provenance(
        record, package=package, binding=binding, controls=controls
    )
    replayed = record_trusted_git_provenance(
        repository_id=record.git_provenance.provenance.repository_id,
        repository_root=root,
        implementation_root=cast(Path, args.implementation_root),
        git_executable=cast(Path, args.git),
        binding=binding,
        reviewer_package_path=package_path,
        assignment=record.child_assignment,
        result=record.child_result,
    )
    if replayed != record.git_provenance.provenance:
        raise ValueError("current Git provenance differs from authenticated record")
    print(
        _event(
            "g4.authenticated_provenance.verified", record_path, record.record_sha256
        )
    )
    return 0


def run_command(args: argparse.Namespace) -> int:
    if args.command == "g4-record-reviewer-git-provenance":
        return _record(args)
    if args.command == "g4-assemble-reviewer-provenance":
        return _assemble(args)
    return _verify(args)
