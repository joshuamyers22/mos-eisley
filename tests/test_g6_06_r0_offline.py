"""R0 metadata-only runner denial and output-shape tests."""

from __future__ import annotations

import unittest
from unittest import TestCase

from tools.g6_06_r0_offline import (
    PROJECT_ROOT,
    R0SuiteResult,
    assess_suite,
    bound_source_files,
    verify_bound_module_origins,
)


class R0OfflineRunnerTests(TestCase):
    def test_suite_counts_pass_without_granting_review(self) -> None:
        class SyntheticPass(TestCase):
            def test_pass(self) -> None:
                self.assertTrue(True)

        result = assess_suite(
            "synthetic", unittest.TestSuite((SyntheticPass("test_pass"),))
        )
        self.assertEqual(result.status, "synthetic_pass")
        self.assertEqual((result.expected_case_count, result.ran_count), (1, 1))
        self.assertEqual(result.failure_count, 0)
        self.assertNotIn("assessment_authorized", R0SuiteResult.model_fields)

    def test_empty_failure_and_skip_are_blocked_without_failure_text(self) -> None:
        class SyntheticFailure(TestCase):
            def test_failure(self) -> None:
                raise AssertionError("synthetic private failure detail")

        class SyntheticSkip(TestCase):
            def test_skip(self) -> None:
                self.skipTest("synthetic private skip detail")

        for suite in (
            unittest.TestSuite(),
            unittest.TestSuite((SyntheticFailure("test_failure"),)),
            unittest.TestSuite((SyntheticSkip("test_skip"),)),
        ):
            with self.subTest(suite=suite):
                result = assess_suite("synthetic", suite)
                self.assertEqual(result.status, "blocked")
                raw = result.model_dump_json()
                self.assertNotIn("synthetic private failure detail", raw)
                self.assertNotIn("synthetic private skip detail", raw)

    def test_bound_source_index_contains_only_paths_and_digests(self) -> None:
        verify_bound_module_origins(PROJECT_ROOT)
        with self.assertRaisesRegex(ValueError, "origin mismatch"):
            verify_bound_module_origins(PROJECT_ROOT.parent)
        sources = bound_source_files(PROJECT_ROOT)
        self.assertTrue(sources)
        self.assertTrue(all(item.sha256 for item in sources))
        self.assertIn(
            "tools/g6_06_r0_offline.py", {item.relative_path for item in sources}
        )
