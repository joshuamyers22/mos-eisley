"""Run fixed G6-06 R0–R6 synthetic suites into a metadata-only index."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import importlib.util
import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from mos_eisley.core.models import Contract, Digest, digest
from mos_eisley.run.store import private_write
from tools.g6_06_r0_offline import (
    BOUND_MODULES as R0_BOUND_MODULES,
)
from tools.g6_06_r0_offline import (
    BOUND_SOURCE_PATHS as R0_BOUND_SOURCE_PATHS,
)
from tools.g6_06_r0_offline import (
    PROJECT_ROOT,
    R0SourceFile,
    R0SuiteResult,
    assess_suite,
)
from tools.g6_06_r0_offline import SUITES as R0_SUITES

SUITES: tuple[tuple[str, tuple[str, ...]], ...] = (
    *R0_SUITES,
    ("g6_05_host_drills", ("tests.test_routing_host_drills",)),
    ("g6_06_r1_shadow", ("tests.test_cohort_r1_shadow",)),
    ("g6_06_r2_entry", ("tests.test_cohort_r2_entry",)),
    ("g6_06_r3_attempt", ("tests.test_cohort_r3_attempt",)),
    ("g6_06_r4_surveillance", ("tests.test_cohort_r4_surveillance",)),
    ("g6_06_r5_close", ("tests.test_cohort_r5_close_followup",)),
    ("g6_06_r6_assessment", ("tests.test_cohort_r6_assessment_handoff",)),
    ("g6_06_handoff_evidence", ("tests.test_cohort_handoff_evidence",)),
    ("g6_06_reproduction_handoff", ("tests.test_g6_06_reproduction_handoff",)),
    ("g6_06_operating_gate", ("tests.test_g6_06_operating_gate",)),
    ("g6_06_assessment_sources", ("tests.test_g6_06_assessment_sources",)),
    ("g6_06_full_runner", ("tests.test_g6_06_full_offline",)),
)

EXTRA_BOUND_MODULES: tuple[str, ...] = (
    "mos_eisley.core.models",
    "mos_eisley.run.store",
    "mos_eisley.evaluation.routing_holdout",
    "mos_eisley.evaluation.routing_promotion",
    "mos_eisley.evaluation.routing_activation",
    "tests.test_routing_holdout",
    "mos_eisley.run.routing_preflight",
    "mos_eisley.run.routing_host_drills",
    "mos_eisley.run.routing_source_handoff",
    "mos_eisley.run.routing_decision_readiness",
    "mos_eisley.run.routing_owner_decision",
    "mos_eisley.run.cohort_entry",
    "mos_eisley.run.cohort_surveillance",
    "mos_eisley.run.cohort_close_handoff",
    "mos_eisley.run.cohort_assessment_handoff",
    "tools.g6_06_full_offline",
    *(name for _, names in SUITES for name in names),
)
BOUND_MODULES = tuple(dict.fromkeys((*R0_BOUND_MODULES, *EXTRA_BOUND_MODULES)))

_LOCAL_ROOTS = ("mos_eisley", "tests", "tools")
_PROTECTED_SOURCE_STEMS = frozenset(
    {"sampling_registry", "custodian_mapping", "label_store", "outcome_store"}
)


def _local_module_path(root: Path, name: str) -> str | None:
    if name.split(".")[0] not in _LOCAL_ROOTS:
        return None
    stem = "src/" if name.startswith("mos_eisley") else ""
    base = stem + name.replace(".", "/")
    for relative in (base + ".py", base + "/__init__.py"):
        if (root / relative).is_file():
            return relative
    return None


def _required_local_module_path(root: Path, name: str) -> str:
    relative = _local_module_path(root, name)
    if relative is None:
        raise ValueError(f"full offline local source missing: {name}")
    return relative


def discover_local_source_modules(
    root: Path, seeds: tuple[str, ...]
) -> tuple[str, ...]:
    """Bind local Python sources reachable through static imports and packages."""
    pending = list(seeds)
    found: dict[str, str] = {}
    while pending:
        name = pending.pop()
        if name in found:
            continue
        relative = _local_module_path(root, name)
        if relative is None:
            if name in {"tests", "tools"}:
                continue
            raise ValueError(f"full offline local source missing: {name}")
        if Path(relative).stem in _PROTECTED_SOURCE_STEMS:
            raise ValueError("full offline protected source requires audited workflow")
        found[name] = relative
        parts = name.split(".")
        pending.extend(".".join(parts[:depth]) for depth in range(1, len(parts)))
        tree = ast.parse((root / relative).read_text(), filename=relative)
        package = name if relative.endswith("/__init__.py") else name.rpartition(".")[0]
        for node in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    base = importlib.util.resolve_name("." * node.level + base, package)
                if base:
                    candidates.append(base)
                    candidates.extend(
                        base + "." + alias.name
                        for alias in node.names
                        if alias.name != "*"
                    )
            for candidate in candidates:
                if _local_module_path(root, candidate) is not None:
                    pending.append(candidate)
    return tuple(sorted(found))


SOURCE_MODULES = discover_local_source_modules(PROJECT_ROOT, BOUND_MODULES)
BOUND_SOURCE_PATHS = tuple(
    dict.fromkeys(
        (
            *R0_BOUND_SOURCE_PATHS,
            *(
                _required_local_module_path(PROJECT_ROOT, name)
                for name in SOURCE_MODULES
            ),
        )
    )
)


class FullOfflineResultIndex(Contract):
    schema_version: Literal[1] = 1
    generated_at: datetime
    source_files: tuple[R0SourceFile, ...]
    bound_source_set_sha256: Digest
    suites: tuple[R0SuiteResult, ...]
    source_stable: bool
    status: Literal["synthetic_pass", "blocked"]
    target_build_verified: Literal[False] = False
    independent_reviewed: Literal[False] = False
    g6_05_qualified: Literal[False] = False
    cohort_release_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False
    assessment_authorized: Literal[False] = False

    @model_validator(mode="after")
    def fixed_coverage_and_status(self) -> Self:
        paths = tuple(item.relative_path for item in self.source_files)
        ids = tuple(item.suite_id for item in self.suites)
        expected_ids = tuple(suite_id for suite_id, _ in SUITES)
        expected_set = digest(
            json.dumps(
                [(item.relative_path, item.sha256) for item in self.source_files],
                separators=(",", ":"),
            ).encode("utf-8")
        )
        passing = self.source_stable and all(
            item.status == "synthetic_pass" for item in self.suites
        )
        inconsistent_pass = any(
            item.status == "synthetic_pass"
            and (
                item.expected_case_count == 0
                or item.ran_count != item.expected_case_count
                or item.failure_count
                or item.error_count
                or item.skipped_count
                or item.expected_failure_count
                or item.unexpected_success_count
            )
            for item in self.suites
        )
        if (
            paths != BOUND_SOURCE_PATHS
            or ids != expected_ids
            or self.bound_source_set_sha256 != expected_set
            or inconsistent_pass
            or self.status != ("synthetic_pass" if passing else "blocked")
        ):
            raise ValueError("full offline index coverage or status is inconsistent")
        return self


def verify_bound_module_origins(root: Path) -> None:
    """Reject imported code outside the fixed source tree."""
    for name in BOUND_MODULES:
        relative = _local_module_path(root, name)
        if relative is None:
            raise ValueError(f"full offline imported module origin mismatch: {name}")
        expected = (root / relative).resolve()
        module = importlib.import_module(name)
        if module.__file__ is None or Path(module.__file__).resolve() != expected:
            raise ValueError(f"full offline imported module origin mismatch: {name}")
    for name, module in tuple(sys.modules.items()):
        if name.split(".")[0] not in _LOCAL_ROOTS:
            continue
        path = getattr(module, "__file__", None)
        if path is None:
            continue
        relative = _local_module_path(root, name)
        if relative is None or name not in SOURCE_MODULES:
            raise ValueError(f"full offline imported module is unbound: {name}")
        if Path(path).resolve() != (root / relative).resolve():
            raise ValueError(f"full offline imported module origin mismatch: {name}")


def bound_source_files(root: Path) -> tuple[R0SourceFile, ...]:
    if discover_local_source_modules(root, BOUND_MODULES) != SOURCE_MODULES:
        raise ValueError("full offline source import closure changed")
    return tuple(
        R0SourceFile(
            relative_path=relative,
            sha256=hashlib.sha256((root / relative).read_bytes()).hexdigest(),
        )
        for relative in BOUND_SOURCE_PATHS
    )


def make_index(
    *,
    files: tuple[R0SourceFile, ...],
    results: tuple[R0SuiteResult, ...],
    source_stable: bool,
) -> FullOfflineResultIndex:
    passing = source_stable and all(item.status == "synthetic_pass" for item in results)
    return FullOfflineResultIndex(
        generated_at=datetime.now(UTC),
        source_files=files,
        bound_source_set_sha256=digest(
            json.dumps(
                [(item.relative_path, item.sha256) for item in files],
                separators=(",", ":"),
            ).encode("utf-8")
        ),
        suites=results,
        source_stable=source_stable,
        status="synthetic_pass" if passing else "blocked",
    )


def run_offline_full(*, root: Path = PROJECT_ROOT) -> FullOfflineResultIndex:
    """Run only fixed offline suites; retain counts and digests, not test output."""
    verify_bound_module_origins(root)
    before = bound_source_files(root)
    results = tuple(
        assess_suite(suite_id, unittest.defaultTestLoader.loadTestsFromNames(names))
        for suite_id, names in SUITES
    )
    try:
        verify_bound_module_origins(root)
        source_stable = before == bound_source_files(root)
    except (OSError, ValueError):
        source_stable = False
    return make_index(files=before, results=results, source_stable=source_stable)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new private metadata-only JSON path")
    args = parser.parse_args(argv)
    index = run_offline_full()
    private_write(args.output, (index.model_dump_json(indent=2) + "\n").encode())
    print(
        f"{index.status}: {sum(item.ran_count for item in index.suites)} "
        f"synthetic tests across {len(index.suites)} suites"
    )
    return 0 if index.status == "synthetic_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
