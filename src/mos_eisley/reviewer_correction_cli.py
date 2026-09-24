"""Offline G4 correction-cycle admission and renewed-chain completion commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from mos_eisley.core.models import canonical_bytes
from mos_eisley.reviewer_candidate_execution import (
    CANDIDATE_ARTIFACT_BYTES,
    G4CandidateDispatchReceipt,
    decode_candidate_artifact,
)
from mos_eisley.reviewer_correction import (
    MAX_RECORD_BYTES,
    G4CorrectionCycleAdmission,
    G4CorrectionCycleCompletion,
    G4CorrectionReviewPolicy,
    SignedG4CorrectionCycleApproval,
    SignedG4CorrectionTriage,
    admit_correction_cycle,
    complete_correction_cycle,
    decode_correction_artifact,
)
from mos_eisley.reviewer_provenance import (
    PROVENANCE_ARTIFACT_BYTES,
    AuthenticatedG4ProvenanceRecord,
    decode_provenance_artifact,
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
    if name == "g4-admit-correction-cycle":
        for flag in (
            "first-receipt",
            "reproduction-receipt",
            "triage",
            "approval",
            "review-policy",
            "provenance",
            "controls",
            "binding",
            "reviewer-package",
            "dispatch-store",
        ):
            command.add_argument(f"--{flag}", type=Path, required=True)
        command.add_argument("--previous-completion", type=Path)
    else:
        for flag in (
            "admission",
            "prior-provenance",
            "prior-package",
            "prior-binding",
            "next-receipt",
            "next-provenance",
            "next-controls",
            "next-binding",
            "next-reviewer-package",
            "next-dispatch-store",
        ):
            command.add_argument(f"--{flag}", type=Path, required=True)
    command.add_argument("--correction-store", type=Path, required=True)
    command.add_argument("--repository-root", type=Path, required=True)
    command.add_argument("--implementation-root", type=Path, required=True)
    command.add_argument("--git", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)


def _load_provenance(path: Path) -> AuthenticatedG4ProvenanceRecord:
    return decode_provenance_artifact(
        read_bounded(path, PROVENANCE_ARTIFACT_BYTES),
        AuthenticatedG4ProvenanceRecord,
    )


def _load_package(path: Path) -> FrozenReviewerTestPackage:
    return decode_frozen_reviewer_test_package(read_bounded(path, FROZEN_PACKAGE_BYTES))


def _load_receipt(path: Path) -> G4CandidateDispatchReceipt:
    return decode_candidate_artifact(
        read_bounded(path, CANDIDATE_ARTIFACT_BYTES), G4CandidateDispatchReceipt
    )


def _check_paths(args: argparse.Namespace) -> None:
    root = cast(Path, args.repository_root).resolve()
    if not cast(Path, args.implementation_root).resolve().is_relative_to(root):
        raise ValueError("correction implementation root must be inside repository")
    named_paths = {
        key: value
        for key, value in vars(args).items()
        if isinstance(value, Path)
        and key not in {"repository_root", "implementation_root", "git"}
    }
    if any(path.resolve().is_relative_to(root) for path in named_paths.values()):
        raise ValueError("G4 correction artifacts and state must remain outside Git")
    output = cast(Path, args.output).resolve()
    if any(
        output == path.resolve() for key, path in named_paths.items() if key != "output"
    ):
        raise ValueError("correction output must not overwrite an input")
    if cast(Path, args.output).exists():
        raise FileExistsError("correction output already exists")


def run_command(args: argparse.Namespace) -> int:
    _check_paths(args)
    root = cast(Path, args.repository_root)
    implementation = cast(Path, args.implementation_root)
    git = cast(Path, args.git)
    store = cast(Path, args.correction_store)
    output = cast(Path, args.output)
    if args.command == "g4-admit-correction-cycle":
        first = _load_receipt(cast(Path, args.first_receipt))
        reproduction = _load_receipt(cast(Path, args.reproduction_receipt))
        triage = decode_correction_artifact(
            read_bounded(cast(Path, args.triage), MAX_RECORD_BYTES),
            SignedG4CorrectionTriage,
        )
        approval = decode_correction_artifact(
            read_bounded(cast(Path, args.approval), MAX_RECORD_BYTES),
            SignedG4CorrectionCycleApproval,
        )
        policy = decode_correction_artifact(
            read_bounded(cast(Path, args.review_policy), MAX_RECORD_BYTES),
            G4CorrectionReviewPolicy,
        )
        previous_path = cast(Path | None, args.previous_completion)
        previous: G4CorrectionCycleCompletion | None = None
        if previous_path is not None:
            previous = decode_correction_artifact(
                read_bounded(previous_path, MAX_RECORD_BYTES),
                G4CorrectionCycleCompletion,
            )
        admission = admit_correction_cycle(
            first=first,
            reproduction=reproduction,
            triage=triage,
            approval=approval,
            review_policy=policy,
            provenance=_load_provenance(cast(Path, args.provenance)),
            controls=decode_control_record(
                read_bounded(cast(Path, args.controls), CONTROL_RECORD_BYTES)
            ),
            binding=load_binding(cast(Path, args.binding)),
            package=_load_package(cast(Path, args.reviewer_package)),
            reviewer_package_path=cast(Path, args.reviewer_package),
            repository_root=root,
            implementation_root=implementation,
            git_executable=git,
            dispatch_store=cast(Path, args.dispatch_store),
            correction_store=store,
            previous=previous,
        )
        artifact = admission
        result_type = "g4.correction_cycle.admitted"
        result_hash = admission.admission_sha256
        candidate_passed: bool | None = None
    else:
        admission = decode_correction_artifact(
            read_bounded(cast(Path, args.admission), MAX_RECORD_BYTES),
            G4CorrectionCycleAdmission,
        )
        completion = complete_correction_cycle(
            admission,
            correction_store=store,
            next_candidate=_load_receipt(cast(Path, args.next_receipt)),
            next_provenance=_load_provenance(cast(Path, args.next_provenance)),
            next_controls=decode_control_record(
                read_bounded(cast(Path, args.next_controls), CONTROL_RECORD_BYTES)
            ),
            next_binding=load_binding(cast(Path, args.next_binding)),
            next_package=_load_package(cast(Path, args.next_reviewer_package)),
            next_reviewer_package_path=cast(Path, args.next_reviewer_package),
            next_dispatch_store=cast(Path, args.next_dispatch_store),
            repository_root=root,
            implementation_root=implementation,
            git_executable=git,
            prior_provenance=_load_provenance(cast(Path, args.prior_provenance)),
            prior_package=_load_package(cast(Path, args.prior_package)),
            prior_binding=load_binding(cast(Path, args.prior_binding)),
        )
        artifact = completion
        result_type = "g4.correction_cycle.completed"
        result_hash = completion.completion_sha256
        candidate_passed = completion.candidate_tests_passed
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_write(output, canonical_bytes(artifact))
    print(
        json.dumps(
            {
                "type": result_type,
                "path": str(output),
                "artifact_sha256": result_hash,
                "cycle": admission.approval.approval.cycle,
                "candidate_tests_passed": candidate_passed,
                "child_dispatch_authorized": False,
                "acceptance_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0
