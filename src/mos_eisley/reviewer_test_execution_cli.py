"""CLI for isolated G4 reviewer-test execution and count evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_test_execution import (
    CONTROL_RECORD_BYTES,
    EXECUTION_RECEIPT_BYTES,
    EXECUTION_REQUEST_BYTES,
    ImmutableReviewerTestExecutionReceipt,
    decode_control_record,
    decode_execution_receipt,
    decode_execution_request,
    load_binding,
    run_isolated_reviewer_tests,
    validate_known_controls,
    verify_execution_receipt,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.store import private_write


def add_arguments(command: argparse.ArgumentParser, name: str) -> None:
    if name == "g4-run-reviewer-tests-isolated":
        command.add_argument("--request", type=Path, required=True)
        command.add_argument("--binding", type=Path, required=True)
        command.add_argument("--reviewer-package", type=Path, required=True)
        command.add_argument("--implementation-root", type=Path, required=True)
        command.add_argument("--docker", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument(
            "--lifecycle-root",
            type=Path,
            required=True,
            help="Private container cleanup records outside the implementation root",
        )
    elif name == "g4-verify-reviewer-test-execution":
        command.add_argument("--receipt", type=Path, required=True)
        command.add_argument("--request", type=Path, required=True)
        command.add_argument("--binding", type=Path, required=True)
        command.add_argument("--reviewer-package", type=Path, required=True)
        command.add_argument("--implementation-root", type=Path, required=True)
    elif name == "g4-validate-reviewer-test-controls":
        command.add_argument("--known-good", type=Path, required=True)
        command.add_argument("--known-bad", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    else:
        command.add_argument("--control-record", type=Path, required=True)


def _overlaps(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _write_private(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_write(path, payload)


def _receipt_event(
    receipt: ImmutableReviewerTestExecutionReceipt, path: Path, event_type: str
) -> str:
    return json.dumps(
        {
            "type": event_type,
            "path": str(path),
            "receipt_sha256": receipt.receipt_sha256,
            "execution_id": receipt.request.execution_id,
            "role": receipt.request.role,
            "container_image_id": receipt.request.container_image_id,
            "binding_record_sha256": receipt.binding_record_sha256,
            "job_sha256": receipt.job_sha256,
            "collected_tests": receipt.observation.collected_tests,
            "executed_tests": receipt.observation.executed_tests,
            "skipped_tests": receipt.observation.skipped_tests,
            "failures": receipt.observation.failures,
            "errors": receipt.observation.errors,
            "collection_contract_satisfied": (receipt.collection_contract_satisfied),
            "role_expectation_satisfied": receipt.role_expectation_satisfied,
            "repository_write_authorized": receipt.repository_write_authorized,
            "vcs_authorized": receipt.vcs_authorized,
            "network_authorized": receipt.network_authorized,
            "credential_access_authorized": (receipt.credential_access_authorized),
            "provider_dispatch_authorized": receipt.provider_dispatch_authorized,
            "correction_authorized": receipt.correction_authorized,
            "acceptance_authorized": receipt.acceptance_authorized,
        },
        sort_keys=True,
    )


def _run_execution(args: argparse.Namespace) -> int:
    request_path = cast(Path, args.request)
    binding_path = cast(Path, args.binding)
    package_path = cast(Path, args.reviewer_package)
    implementation_root = cast(Path, args.implementation_root)
    output = cast(Path, args.output)
    lifecycle_root = cast(Path, args.lifecycle_root)
    protected = (request_path, binding_path, package_path)
    if any(
        _overlaps(implementation_root, path)
        for path in (*protected, output, lifecycle_root)
    ):
        raise ValueError(
            "implementation root must be separate from inputs, output and lifecycle"
        )
    if any(_overlaps(output, path) for path in (*protected, lifecycle_root)) or any(
        _overlaps(lifecycle_root, path) for path in protected
    ):
        raise ValueError("execution inputs, output and lifecycle root must be separate")
    request = decode_execution_request(
        read_bounded(request_path, EXECUTION_REQUEST_BYTES)
    )
    binding = load_binding(binding_path)
    container = OfflineContainer(
        cast(Path, args.docker),
        request.container_image_id,
        lifecycle_root,
    )
    receipt = run_isolated_reviewer_tests(
        request, binding, package_path, implementation_root, container
    )
    _write_private(output, canonical_bytes(receipt))
    print(_receipt_event(receipt, output, "g4.reviewer_test_execution.completed"))
    return 0 if receipt.role_expectation_satisfied else 1


def _verify_execution(args: argparse.Namespace) -> int:
    receipt_path = cast(Path, args.receipt)
    request_path = cast(Path, args.request)
    binding_path = cast(Path, args.binding)
    package_path = cast(Path, args.reviewer_package)
    implementation_root = cast(Path, args.implementation_root)
    protected = (receipt_path, request_path, binding_path, package_path)
    if any(_overlaps(implementation_root, path) for path in protected):
        raise ValueError("implementation root must be separate from execution inputs")
    receipt = decode_execution_receipt(
        read_bounded(receipt_path, EXECUTION_RECEIPT_BYTES)
    )
    request = decode_execution_request(
        read_bounded(request_path, EXECUTION_REQUEST_BYTES)
    )
    verify_execution_receipt(
        receipt,
        request,
        load_binding(binding_path),
        package_path,
        implementation_root,
    )
    print(_receipt_event(receipt, receipt_path, "g4.reviewer_test_execution.verified"))
    return 0


def _validate_controls(args: argparse.Namespace) -> int:
    known_good_path = cast(Path, args.known_good)
    known_bad_path = cast(Path, args.known_bad)
    output = cast(Path, args.output)
    if _overlaps(known_good_path, known_bad_path) or any(
        _overlaps(output, path) for path in (known_good_path, known_bad_path)
    ):
        raise ValueError("control inputs and output must be separate")
    known_good = decode_execution_receipt(
        read_bounded(known_good_path, EXECUTION_RECEIPT_BYTES)
    )
    known_bad = decode_execution_receipt(
        read_bounded(known_bad_path, EXECUTION_RECEIPT_BYTES)
    )
    record = validate_known_controls(known_good, known_bad)
    _write_private(output, canonical_bytes(record))
    print(
        json.dumps(
            {
                "type": "g4.reviewer_test_controls.validated",
                "path": str(output),
                "control_record_sha256": record.control_record_sha256,
                "known_good_receipt_sha256": known_good.receipt_sha256,
                "known_bad_receipt_sha256": known_bad.receipt_sha256,
                "controls_validated": record.controls_validated,
                "candidate_execution_authorized": (
                    record.candidate_execution_authorized
                ),
                "repository_write_authorized": record.repository_write_authorized,
                "correction_authorized": record.correction_authorized,
                "acceptance_authorized": record.acceptance_authorized,
            },
            sort_keys=True,
        )
    )
    return 0


def run_command(args: argparse.Namespace) -> int:
    if args.command == "g4-run-reviewer-tests-isolated":
        return _run_execution(args)
    if args.command == "g4-verify-reviewer-test-execution":
        return _verify_execution(args)
    if args.command == "g4-validate-reviewer-test-controls":
        return _validate_controls(args)
    path = cast(Path, args.control_record)
    record = decode_control_record(read_bounded(path, CONTROL_RECORD_BYTES))
    print(
        json.dumps(
            {
                "type": "g4.reviewer_test_controls.verified",
                "path": str(path),
                "control_record_sha256": record.control_record_sha256,
                "controls_validated": record.controls_validated,
                "candidate_execution_authorized": (
                    record.candidate_execution_authorized
                ),
                "correction_authorized": record.correction_authorized,
                "acceptance_authorized": record.acceptance_authorized,
            },
            sort_keys=True,
        )
    )
    return 0
