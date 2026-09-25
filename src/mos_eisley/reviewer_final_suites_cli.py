"""CLI for separately approved G4 final creator/reviewer whole suites."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TypedDict, cast

from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_candidate_execution import (
    CANDIDATE_ARTIFACT_BYTES,
    G4CandidateDispatchReceipt,
    decode_candidate_artifact,
)
from mos_eisley.reviewer_final_suites import (
    FINAL_SUITE_ARTIFACT_BYTES,
    G4FinalWholeSuiteReceipt,
    SignedG4FinalWholeSuiteApproval,
    decode_final_suite_artifact,
    run_final_whole_suites,
    verify_final_whole_suite_receipt,
)
from mos_eisley.reviewer_implementation_binding import (
    ImmutableImplementationBindingRecord,
)
from mos_eisley.reviewer_provenance import (
    PROVENANCE_ARTIFACT_BYTES,
    AuthenticatedG4ProvenanceRecord,
    decode_provenance_artifact,
)
from mos_eisley.reviewer_test_execution import (
    CONTROL_RECORD_BYTES,
    EXECUTION_REQUEST_BYTES,
    KnownControlValidationRecord,
    decode_control_record,
    decode_execution_request,
    load_binding,
)
from mos_eisley.reviewer_test_package import (
    FROZEN_PACKAGE_BYTES,
    FrozenReviewerTestPackage,
    decode_frozen_reviewer_test_package,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.store import private_write


class _Common(TypedDict):
    candidate: G4CandidateDispatchReceipt
    provenance: AuthenticatedG4ProvenanceRecord
    controls: KnownControlValidationRecord
    reviewer_binding: ImmutableImplementationBindingRecord
    creator_package: FrozenReviewerTestPackage
    reviewer_package: FrozenReviewerTestPackage
    creator_package_path: Path
    reviewer_package_path: Path
    repository_root: Path
    implementation_root: Path
    git_executable: Path
    candidate_dispatch_store: Path
    final_dispatch_store: Path


def add_arguments(command: argparse.ArgumentParser, name: str) -> None:
    if name == "g4-run-final-whole-suites":
        command.add_argument("--approval", type=Path, required=True)
        command.add_argument("--creator-request", type=Path, required=True)
        command.add_argument("--reviewer-request", type=Path, required=True)
        command.add_argument("--docker", type=Path, required=True)
        command.add_argument("--lifecycle-root", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    else:
        command.add_argument("--receipt", type=Path, required=True)
    command.add_argument("--candidate", type=Path, required=True)
    command.add_argument("--provenance", type=Path, required=True)
    command.add_argument("--controls", type=Path, required=True)
    command.add_argument("--binding", type=Path, required=True)
    command.add_argument("--creator-package", type=Path, required=True)
    command.add_argument("--reviewer-package", type=Path, required=True)
    command.add_argument("--repository-root", type=Path, required=True)
    command.add_argument("--implementation-root", type=Path, required=True)
    command.add_argument("--git", type=Path, required=True)
    command.add_argument("--candidate-dispatch-store", type=Path, required=True)
    command.add_argument("--final-dispatch-store", type=Path, required=True)


def _check_paths(args: argparse.Namespace) -> None:
    root = cast(Path, args.repository_root).resolve()
    implementation = cast(Path, args.implementation_root).resolve()
    if not implementation.is_relative_to(root):
        raise ValueError("final-suite implementation root must be inside repository")
    artifact_names = (
        "candidate",
        "provenance",
        "controls",
        "binding",
        "creator_package",
        "reviewer_package",
        "candidate_dispatch_store",
        "final_dispatch_store",
        "approval",
        "creator_request",
        "reviewer_request",
        "lifecycle_root",
        "output",
        "receipt",
    )
    artifacts = [
        cast(Path, value).resolve()
        for name in artifact_names
        if (value := getattr(args, name, None)) is not None
    ]
    if any(path.is_relative_to(root) for path in artifacts):
        raise ValueError("final-suite artifacts and state must remain outside Git")
    output = getattr(args, "output", None)
    if output is not None and artifacts.count(cast(Path, output).resolve()) != 1:
        raise ValueError("final-suite output must not overwrite an input")
    candidate_store = cast(Path, args.candidate_dispatch_store).resolve()
    final_store = cast(Path, args.final_dispatch_store).resolve()
    if candidate_store.is_relative_to(final_store) or final_store.is_relative_to(
        candidate_store
    ):
        raise ValueError("candidate and final-suite stores must be separate")
    lifecycle = getattr(args, "lifecycle_root", None)
    if lifecycle is not None:
        lifecycle = cast(Path, lifecycle).resolve()
        if any(
            store.is_relative_to(lifecycle) or lifecycle.is_relative_to(store)
            for store in (candidate_store, final_store)
        ):
            raise ValueError("final-suite lifecycle and claim stores must be separate")


def _common(args: argparse.Namespace) -> _Common:
    return {
        "candidate": decode_candidate_artifact(
            read_bounded(cast(Path, args.candidate), CANDIDATE_ARTIFACT_BYTES),
            G4CandidateDispatchReceipt,
        ),
        "provenance": decode_provenance_artifact(
            read_bounded(cast(Path, args.provenance), PROVENANCE_ARTIFACT_BYTES),
            AuthenticatedG4ProvenanceRecord,
        ),
        "controls": decode_control_record(
            read_bounded(cast(Path, args.controls), CONTROL_RECORD_BYTES)
        ),
        "reviewer_binding": load_binding(cast(Path, args.binding)),
        "creator_package": decode_frozen_reviewer_test_package(
            read_bounded(cast(Path, args.creator_package), FROZEN_PACKAGE_BYTES)
        ),
        "reviewer_package": decode_frozen_reviewer_test_package(
            read_bounded(cast(Path, args.reviewer_package), FROZEN_PACKAGE_BYTES)
        ),
        "creator_package_path": cast(Path, args.creator_package),
        "reviewer_package_path": cast(Path, args.reviewer_package),
        "repository_root": cast(Path, args.repository_root),
        "implementation_root": cast(Path, args.implementation_root),
        "git_executable": cast(Path, args.git),
        "candidate_dispatch_store": cast(Path, args.candidate_dispatch_store),
        "final_dispatch_store": cast(Path, args.final_dispatch_store),
    }


def run_command(args: argparse.Namespace) -> int:
    _check_paths(args)
    common = _common(args)
    if args.command == "g4-run-final-whole-suites":
        approval = decode_final_suite_artifact(
            read_bounded(cast(Path, args.approval), FINAL_SUITE_ARTIFACT_BYTES),
            SignedG4FinalWholeSuiteApproval,
        )
        creator_request = decode_execution_request(
            read_bounded(cast(Path, args.creator_request), EXECUTION_REQUEST_BYTES)
        )
        reviewer_request = decode_execution_request(
            read_bounded(cast(Path, args.reviewer_request), EXECUTION_REQUEST_BYTES)
        )
        container = OfflineContainer(
            cast(Path, args.docker),
            approval.approval.container_image_id,
            cast(Path, args.lifecycle_root),
        )
        receipt = run_final_whole_suites(
            approval=approval,
            creator_request=creator_request,
            reviewer_request=reviewer_request,
            container=container,
            **common,
        )
        output = cast(Path, args.output)
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_write(output, canonical_bytes(receipt))
        event = "g4.final_whole_suites.completed"
        path = output
    else:
        receipt = decode_final_suite_artifact(
            read_bounded(cast(Path, args.receipt), FINAL_SUITE_ARTIFACT_BYTES),
            G4FinalWholeSuiteReceipt,
        )
        verify_final_whole_suite_receipt(receipt, **common)
        event = "g4.final_whole_suites.verified"
        path = cast(Path, args.receipt)
    print(
        json.dumps(
            {
                "type": event,
                "path": str(path),
                "receipt_sha256": receipt.receipt_sha256,
                "creator_tests_passed": (
                    receipt.creator_execution.role_expectation_satisfied
                ),
                "reviewer_tests_passed": (
                    receipt.reviewer_execution.role_expectation_satisfied
                ),
                "final_suites_passed": receipt.final_suites_passed,
                "independent_review_passed": False,
                "acceptance_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt.final_suites_passed else 1
