"""Fixed R0–R6 runner coverage, source binding and metadata-only denial tests."""

from __future__ import annotations

import io
import stat
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

from mos_eisley.core.models import digest
from tools.g6_06_full_offline import (
    BOUND_SOURCE_PATHS,
    PROJECT_ROOT,
    SUITES,
    bound_source_files,
    discover_local_source_modules,
    main,
    make_index,
    verify_bound_module_origins,
)
from tools.g6_06_r0_offline import R0SuiteResult, assess_suite


def _passing_results() -> tuple[R0SuiteResult, ...]:
    return tuple(
        R0SuiteResult(
            suite_id=suite_id,
            case_ids_sha256=digest(suite_id.encode()),
            expected_case_count=1,
            ran_count=1,
            failure_count=0,
            error_count=0,
            skipped_count=0,
            expected_failure_count=0,
            unexpected_success_count=0,
            status="synthetic_pass",
        )
        for suite_id, _ in SUITES
    )


class FullOfflineRunnerTests(TestCase):
    def test_fixed_suites_and_sources_cover_r0_through_r6(self) -> None:
        ids = tuple(suite_id for suite_id, _ in SUITES)
        self.assertEqual(len(ids), len(set(ids)))
        for phase in range(1, 7):
            self.assertIn(f"g6_06_r{phase}_", " ".join(ids))
        self.assertIn("g6_06_cohort", ids)
        self.assertIn("g6_05_host_drills", ids)
        for relative in (
            "tools/g6_06_full_offline.py",
            "src/mos_eisley/run/routing_decision_readiness.py",
            "src/mos_eisley/run/routing_owner_decision.py",
            "src/mos_eisley/run/cohort_entry.py",
            "src/mos_eisley/run/cohort_shadow.py",
            "src/mos_eisley/run/activation_control.py",
            "src/mos_eisley/evaluation/routing_policy.py",
            "src/mos_eisley/evaluation/routing_protocol.py",
            "src/mos_eisley/run/cohort_surveillance.py",
            "src/mos_eisley/run/cohort_close_handoff.py",
            "src/mos_eisley/run/cohort_assessment_handoff.py",
            "tests/test_cohort_r6_assessment_handoff.py",
        ):
            self.assertIn(relative, BOUND_SOURCE_PATHS)
        verify_bound_module_origins(PROJECT_ROOT)
        with self.assertRaisesRegex(ValueError, "origin mismatch"):
            verify_bound_module_origins(PROJECT_ROOT.parent)

    def test_local_source_closure_follows_transitive_imports(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "tests"
            package.mkdir()
            (package / "entry.py").write_text("from tests import dependency\n")
            (package / "dependency.py").write_text("from tests import leaf\n")
            (package / "leaf.py").write_text("VALUE = 1\n")
            seeds = ("tests.entry",)
            self.assertEqual(
                discover_local_source_modules(root, seeds),
                ("tests.dependency", "tests.entry", "tests.leaf"),
            )
            (package / "new_leaf.py").write_text("VALUE = 2\n")
            (package / "dependency.py").write_text(
                "from tests import leaf, new_leaf\n"
            )
            self.assertIn(
                "tests.new_leaf", discover_local_source_modules(root, seeds)
            )

    def test_dynamic_local_import_outside_closure_is_rejected(self) -> None:
        module = ModuleType("tools.synthetic_unbound")
        module.__file__ = str(PROJECT_ROOT / "tools" / "synthetic_unbound.py")
        with (
            patch.dict(sys.modules, {module.__name__: module}),
            self.assertRaisesRegex(ValueError, "imported module is unbound"),
        ):
            verify_bound_module_origins(PROJECT_ROOT)

    def test_missing_suite_or_changed_source_blocks_index(self) -> None:
        files = bound_source_files(PROJECT_ROOT)
        results = _passing_results()
        passed = make_index(files=files, results=results, source_stable=True)
        self.assertEqual(passed.status, "synthetic_pass")
        self.assertFalse(passed.target_build_verified)
        self.assertFalse(passed.independent_reviewed)
        self.assertFalse(passed.g6_05_qualified)
        self.assertFalse(passed.cohort_release_authorized)
        self.assertFalse(passed.dispatch_authorized)
        self.assertFalse(passed.assessment_authorized)
        changed = make_index(files=files, results=results, source_stable=False)
        self.assertEqual(changed.status, "blocked")
        with self.assertRaises(ValidationError):
            make_index(files=files, results=results[:-1], source_stable=True)
        with self.assertRaises(ValidationError):
            make_index(files=files[:-1], results=results, source_stable=True)
        with self.assertRaises(ValidationError):
            type(passed).model_validate_json(
                passed.model_copy(update={"status": "blocked"}).model_dump_json()
            )
        falsely_passing = results[0].model_copy(update={"failure_count": 1})
        with self.assertRaises(ValidationError):
            make_index(
                files=files,
                results=(falsely_passing, *results[1:]),
                source_stable=True,
            )

    def test_failure_text_never_enters_private_index(self) -> None:
        class SyntheticFailure(TestCase):
            def test_failure(self) -> None:
                raise AssertionError("synthetic private failure detail")

        failed = assess_suite(
            SUITES[0][0], unittest.TestSuite((SyntheticFailure("test_failure"),))
        )
        results = (failed, *_passing_results()[1:])
        index = make_index(
            files=bound_source_files(PROJECT_ROOT),
            results=results,
            source_stable=True,
        )
        self.assertEqual(index.status, "blocked")
        self.assertEqual(index.suites[0].failure_count, 1)
        self.assertNotIn("synthetic private failure detail", index.model_dump_json())

    def test_cli_writes_exclusive_private_metadata_file(self) -> None:
        index = make_index(
            files=bound_source_files(PROJECT_ROOT),
            results=_passing_results(),
            source_stable=True,
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "full-index.json"
            with (
                patch("tools.g6_06_full_offline.run_offline_full", return_value=index),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main([str(path)]), 0)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertIn('"synthetic_pass"', path.read_text())
            self.assertNotIn("synthetic private failure detail", path.read_text())
            with (
                patch("tools.g6_06_full_offline.run_offline_full", return_value=index),
                redirect_stdout(io.StringIO()),
                self.assertRaises(FileExistsError),
            ):
                main([str(path)])

    def test_cli_returns_blocked_without_failure_detail(self) -> None:
        class SyntheticFailure(TestCase):
            def test_failure(self) -> None:
                raise AssertionError("synthetic private failure detail")

        failed = assess_suite(
            SUITES[0][0], unittest.TestSuite((SyntheticFailure("test_failure"),))
        )
        index = make_index(
            files=bound_source_files(PROJECT_ROOT),
            results=(failed, *_passing_results()[1:]),
            source_stable=True,
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "blocked-index.json"
            with (
                patch("tools.g6_06_full_offline.run_offline_full", return_value=index),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main([str(path)]), 1)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertIn('"blocked"', path.read_text())
            self.assertNotIn("synthetic private failure detail", path.read_text())
