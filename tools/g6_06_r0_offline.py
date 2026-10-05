"""Run the fixed G6-06 R0 synthetic suites and write a metadata-only index."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.core.models import Contract, Digest, digest
from mos_eisley.run.store import private_write

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUITES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("g6_02_exact_route", ("tests.test_exact_route",)),
    ("g6_03_one_use", ("tests.test_routing_transaction",)),
    (
        "g6_04_witness_budget",
        ("tests.test_routing_runtime_preflight", "tests.test_witnessed_admission"),
    ),
    (
        "g6_05_qualification",
        (
            "tests.test_routing_promotion",
            "tests.test_routing_activation",
            "tests.test_routing_qualification",
        ),
    ),
    (
        "g6_06_cohort",
        (
            "tests.test_cohort_controller",
            "tests.test_cohort_closeout",
            "tests.test_cohort_audit_outage",
            "tests.test_cohort_route_change",
            "tests.test_cohort_stop_reentry",
            "tests.test_cohort_early_close_followup",
            "tests.test_cohort_combined_rollback",
            "tests.test_cohort_assessment_freeze",
            "tests.test_cohort_r0_integrated",
            "tests.test_g6_06_r0_offline",
        ),
    ),
)
BOUND_MODULES: tuple[str, ...] = (
    "mos_eisley.run.exact_route",
    "mos_eisley.run.routing_transaction",
    "mos_eisley.run.witnessed_admission",
    "mos_eisley.run.routing_qualification",
    "mos_eisley.run.cohort_controller",
    "mos_eisley.run.cohort_closeout",
    "mos_eisley.run.cohort_stop",
    *(name for _, names in SUITES for name in names),
)
BOUND_SOURCE_PATHS: tuple[str, ...] = (
    "pyproject.toml",
    "uv.lock",
    "tools/g6_06_r0_offline.py",
    "src/mos_eisley/run/exact_route.py",
    "src/mos_eisley/run/routing_transaction.py",
    "src/mos_eisley/run/witnessed_admission.py",
    "src/mos_eisley/run/routing_qualification.py",
    "src/mos_eisley/run/cohort_controller.py",
    "src/mos_eisley/run/cohort_closeout.py",
    "src/mos_eisley/run/cohort_stop.py",
    *(name.replace(".", "/") + ".py" for _, names in SUITES for name in names),
)


class R0SourceFile(Contract):
    relative_path: Annotated[str, Field(min_length=1, max_length=200)]
    sha256: Digest


class R0SuiteResult(Contract):
    suite_id: Annotated[str, Field(min_length=1, max_length=80)]
    case_ids_sha256: Digest
    expected_case_count: Annotated[int, Field(ge=0)]
    ran_count: Annotated[int, Field(ge=0)]
    failure_count: Annotated[int, Field(ge=0)]
    error_count: Annotated[int, Field(ge=0)]
    skipped_count: Annotated[int, Field(ge=0)]
    expected_failure_count: Annotated[int, Field(ge=0)]
    unexpected_success_count: Annotated[int, Field(ge=0)]
    status: Literal["synthetic_pass", "blocked"]


class R0OfflineResultIndex(Contract):
    schema_version: Literal[1] = 1
    generated_at: datetime
    source_files: tuple[R0SourceFile, ...]
    bound_source_set_sha256: Digest
    suites: tuple[R0SuiteResult, ...]
    status: Literal["synthetic_pass", "blocked"]
    target_build_verified: Literal[False] = False
    independent_reviewed: Literal[False] = False
    g6_05_qualified: Literal[False] = False
    cohort_release_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False
    assessment_authorized: Literal[False] = False


def _case_ids(suite: unittest.TestSuite) -> tuple[str, ...]:
    result: list[str] = []
    for case in suite:
        if isinstance(case, unittest.TestSuite):
            result.extend(_case_ids(case))
        elif isinstance(case, unittest.TestCase):
            result.append(case.id())
        else:
            raise ValueError("R0 suite contains an unknown test case")
    return tuple(result)


def assess_suite(suite_id: str, suite: unittest.TestSuite) -> R0SuiteResult:
    """Keep only case identities and counts; discard traceback and output text."""
    case_ids = _case_ids(suite)
    result = unittest.TestResult()
    suite.run(result)
    blocked = (
        not case_ids
        or result.testsRun != len(case_ids)
        or bool(result.failures)
        or bool(result.errors)
        or bool(result.skipped)
        or bool(result.expectedFailures)
        or bool(result.unexpectedSuccesses)
    )
    return R0SuiteResult(
        suite_id=suite_id,
        case_ids_sha256=digest(
            json.dumps(case_ids, separators=(",", ":")).encode("utf-8")
        ),
        expected_case_count=len(case_ids),
        ran_count=result.testsRun,
        failure_count=len(result.failures),
        error_count=len(result.errors),
        skipped_count=len(result.skipped),
        expected_failure_count=len(result.expectedFailures),
        unexpected_success_count=len(result.unexpectedSuccesses),
        status="blocked" if blocked else "synthetic_pass",
    )


def bound_source_files(root: Path) -> tuple[R0SourceFile, ...]:
    return tuple(
        R0SourceFile(
            relative_path=relative,
            sha256=hashlib.sha256((root / relative).read_bytes()).hexdigest(),
        )
        for relative in BOUND_SOURCE_PATHS
    )


def verify_bound_module_origins(root: Path) -> None:
    """Refuse an index if imported modules differ from the hashed source files."""
    for name in BOUND_MODULES:
        expected = (
            root
            / ("src" if name.startswith("mos_eisley.") else "")
            / (name.replace(".", "/") + ".py")
        ).resolve()
        module = importlib.import_module(name)
        if module.__file__ is None or Path(module.__file__).resolve() != expected:
            raise ValueError(f"R0 imported module origin mismatch: {name}")


def run_offline_r0(*, root: Path = PROJECT_ROOT) -> R0OfflineResultIndex:
    """Run only the fixed synthetic suite list; never inspect outcome sources."""
    verify_bound_module_origins(root)
    files = bound_source_files(root)
    results = tuple(
        assess_suite(suite_id, unittest.defaultTestLoader.loadTestsFromNames(names))
        for suite_id, names in SUITES
    )
    return R0OfflineResultIndex(
        generated_at=datetime.now(UTC),
        source_files=files,
        bound_source_set_sha256=digest(
            json.dumps(
                [(item.relative_path, item.sha256) for item in files],
                separators=(",", ":"),
            ).encode("utf-8")
        ),
        suites=results,
        status=(
            "synthetic_pass"
            if all(item.status == "synthetic_pass" for item in results)
            else "blocked"
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new private metadata-only JSON path")
    args = parser.parse_args()
    index = run_offline_r0()
    private_write(args.output, (index.model_dump_json(indent=2) + "\n").encode())
    print(
        f"{index.status}: {sum(item.ran_count for item in index.suites)} "
        f"synthetic tests across {len(index.suites)} suites"
    )
    return 0 if index.status == "synthetic_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
