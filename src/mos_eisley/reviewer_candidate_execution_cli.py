"""CLI for separately approved, one-use G4 candidate test dispatch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TypedDict, cast

from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_candidate_execution import (
    CANDIDATE_ARTIFACT_BYTES,
    G4CandidateAdmissionRecord,
    G4CandidateDispatchReceipt,
    SignedG4CandidateExecutionApproval,
    admit_candidate_execution,
    decode_candidate_artifact,
    dispatch_candidate_execution,
    verify_candidate_dispatch_receipt,
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


class _Inputs(TypedDict):
    provenance: AuthenticatedG4ProvenanceRecord
    controls: KnownControlValidationRecord
    binding: ImmutableImplementationBindingRecord
    package: FrozenReviewerTestPackage
    reviewer_package_path: Path
    repository_root: Path
    implementation_root: Path
    git_executable: Path


def add_arguments(command: argparse.ArgumentParser, name: str) -> None:
    if name == "g4-check-candidate-execution":
        command.add_argument("--approval", type=Path, required=True)
        command.add_argument("--request", type=Path, required=True)
    elif name == "g4-dispatch-candidate-execution":
        command.add_argument("--admission", type=Path, required=True)
        command.add_argument("--docker", type=Path, required=True)
        command.add_argument("--dispatch-store", type=Path, required=True)
        command.add_argument("--lifecycle-root", type=Path, required=True)
    else:
        command.add_argument("--receipt", type=Path, required=True)
        command.add_argument("--dispatch-store", type=Path, required=True)
    command.add_argument("--provenance", type=Path, required=True)
    command.add_argument("--controls", type=Path, required=True)
    command.add_argument("--binding", type=Path, required=True)
    command.add_argument("--reviewer-package", type=Path, required=True)
    command.add_argument("--repository-root", type=Path, required=True)
    command.add_argument("--implementation-root", type=Path, required=True)
    command.add_argument("--git", type=Path, required=True)
    if name != "g4-verify-candidate-execution":
        command.add_argument("--output", type=Path, required=True)


def _inputs(
    args: argparse.Namespace,
) -> tuple[
    AuthenticatedG4ProvenanceRecord,
    KnownControlValidationRecord,
    ImmutableImplementationBindingRecord,
    FrozenReviewerTestPackage,
]:
    provenance = decode_provenance_artifact(
        read_bounded(cast(Path, args.provenance), PROVENANCE_ARTIFACT_BYTES),
        AuthenticatedG4ProvenanceRecord,
    )
    controls = decode_control_record(
        read_bounded(cast(Path, args.controls), CONTROL_RECORD_BYTES)
    )
    binding = load_binding(cast(Path, args.binding))
    package = decode_frozen_reviewer_test_package(
        read_bounded(cast(Path, args.reviewer_package), FROZEN_PACKAGE_BYTES)
    )
    return provenance, controls, binding, package


def _check_paths(args: argparse.Namespace) -> None:
    root = cast(Path, args.repository_root).resolve()
    implementation = cast(Path, args.implementation_root).resolve()
    if not implementation.is_relative_to(root):
        raise ValueError("candidate implementation root must be inside repository")
    protected = [
        cast(Path, getattr(args, name))
        for name in ("provenance", "controls", "binding", "reviewer_package")
    ]
    for name in (
        "approval",
        "request",
        "admission",
        "receipt",
        "dispatch_store",
        "lifecycle_root",
    ):
        value = getattr(args, name, None)
        if value is not None:
            protected.append(cast(Path, value))
    output_value = getattr(args, "output", None)
    all_paths = protected + (
        [cast(Path, output_value)] if output_value is not None else []
    )
    if any(path.resolve().is_relative_to(root) for path in all_paths):
        raise ValueError("G4 candidate artifacts and state must remain outside Git")
    if output_value is not None:
        output = cast(Path, output_value).resolve()
        if any(output == path.resolve() for path in protected):
            raise ValueError("candidate output must not overwrite an input")
    if (
        getattr(args, "dispatch_store", None) is not None
        and getattr(args, "lifecycle_root", None) is not None
    ):
        store = cast(Path, args.dispatch_store).resolve()
        lifecycle = cast(Path, args.lifecycle_root).resolve()
        if (
            store == lifecycle
            or store.is_relative_to(lifecycle)
            or lifecycle.is_relative_to(store)
        ):
            raise ValueError("dispatch store and lifecycle root must be separate")


def _common(args: argparse.Namespace) -> _Inputs:
    provenance, controls, binding, package = _inputs(args)
    return {
        "provenance": provenance,
        "controls": controls,
        "binding": binding,
        "package": package,
        "reviewer_package_path": cast(Path, args.reviewer_package),
        "repository_root": cast(Path, args.repository_root),
        "implementation_root": cast(Path, args.implementation_root),
        "git_executable": cast(Path, args.git),
    }


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_write(path, payload)


def run_command(args: argparse.Namespace) -> int:
    _check_paths(args)
    inputs = _common(args)
    if args.command == "g4-check-candidate-execution":
        approval = decode_candidate_artifact(
            read_bounded(cast(Path, args.approval), CANDIDATE_ARTIFACT_BYTES),
            SignedG4CandidateExecutionApproval,
        )
        request = decode_execution_request(
            read_bounded(cast(Path, args.request), EXECUTION_REQUEST_BYTES)
        )
        admission = admit_candidate_execution(
            approval=approval, request=request, **inputs
        )
        output = cast(Path, args.output)
        _write(output, canonical_bytes(admission))
        print(
            json.dumps(
                {
                    "type": "g4.candidate_execution.admitted",
                    "path": str(output),
                    "admission_sha256": admission.admission_sha256,
                    "execution_id": request.execution_id,
                    "candidate_execution_completed": False,
                    "correction_authorized": False,
                    "acceptance_authorized": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "g4-dispatch-candidate-execution":
        admission = decode_candidate_artifact(
            read_bounded(cast(Path, args.admission), CANDIDATE_ARTIFACT_BYTES),
            G4CandidateAdmissionRecord,
        )
        container = OfflineContainer(
            cast(Path, args.docker),
            admission.request.container_image_id,
            cast(Path, args.lifecycle_root),
        )
        receipt = dispatch_candidate_execution(
            admission,
            container=container,
            dispatch_store=cast(Path, args.dispatch_store),
            **inputs,
        )
        output = cast(Path, args.output)
        _write(output, canonical_bytes(receipt))
        print(
            json.dumps(
                {
                    "type": "g4.candidate_execution.completed",
                    "path": str(output),
                    "receipt_sha256": receipt.receipt_sha256,
                    "execution_id": receipt.execution.request.execution_id,
                    "candidate_tests_passed": receipt.candidate_tests_passed,
                    "correction_authorized": False,
                    "acceptance_authorized": False,
                },
                sort_keys=True,
            )
        )
        return 0 if receipt.candidate_tests_passed else 1
    receipt = decode_candidate_artifact(
        read_bounded(cast(Path, args.receipt), CANDIDATE_ARTIFACT_BYTES),
        G4CandidateDispatchReceipt,
    )
    verify_candidate_dispatch_receipt(
        receipt, dispatch_store=cast(Path, args.dispatch_store), **inputs
    )
    print(
        json.dumps(
            {
                "type": "g4.candidate_execution.verified",
                "path": str(args.receipt),
                "receipt_sha256": receipt.receipt_sha256,
                "candidate_tests_passed": receipt.candidate_tests_passed,
                "correction_authorized": False,
                "acceptance_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0
