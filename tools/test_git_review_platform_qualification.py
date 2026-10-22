"""Faults in native qualification evidence fail closed without running providers."""

import json
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from qualify_git_review_platform import (
    quality_counts,
    read_json,
    validate_host,
    verify_wheel,
    write_json,
)


class QualificationEvidenceTests(TestCase):
    def test_wsl_requires_matching_host_side_distro_and_candidate(self) -> None:
        commit = "a" * 40
        host: dict[str, object] = {
            "schema_version": 1,
            "host_os": "Windows",
            "candidate_commit": commit,
            "distribution": "Ubuntu-24.04",
            "distribution_version": 2,
            "windows_build": "26100",
            "wsl_version": "WSL version: 3.0.3.0",
            "distribution_listing": "  NAME STATE VERSION\n* Ubuntu-24.04 Running 2\n",
        }
        validate_host(host, commit)
        for key, value in (
            ("candidate_commit", "b" * 40),
            ("host_os", "Linux"),
            ("distribution_version", 1),
            ("distribution_listing", "Ubuntu-24.04 Running 1"),
            ("windows_build", None),
            ("wsl_version", ""),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_host({**host, key: value}, commit)

    def test_quality_requires_both_actual_success_summaries(self) -> None:
        passed = (
            "Ran 3853 tests in 3010.803s\n\nOK (skipped=17)\n"
            "Ran 2831 tests in 2072.095s\n\nOK (skipped=13)\n"
        )
        results = quality_counts(passed)
        self.assertEqual(results[0]["tests_run"], 3853)
        self.assertEqual(results[1]["skipped"], 13)
        for text in (
            passed.replace("OK", "FAILED", 1),
            passed.split("Ran 2831")[0],
            "Ran 1 tests in 1.0s\nOK\n" * 2,
        ):
            with self.subTest(text=text[:30]), self.assertRaises(ValueError):
                quality_counts(text)

    def test_evidence_exclusive_write_and_size_bound(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            write_json(path, {"status": "failed", "execution_authorized": False})
            self.assertFalse(read_json(path)["execution_authorized"])
            with self.assertRaises(FileExistsError):
                write_json(path, {"status": "passed"})
            path.write_text(json.dumps(["not an object"]))
            with self.assertRaises(ValueError):
                read_json(path)
            path.write_bytes(b"x" * 1_000_001)
            with self.assertRaisesRegex(ValueError, "too_large"):
                read_json(path)

    def test_wheel_must_contain_exact_source_bytes_and_module_set(self) -> None:
        with TemporaryDirectory() as directory:
            repo = Path(directory)
            source = repo / "src/mos_eisley"
            source.mkdir(parents=True)
            (source / "__init__.py").write_bytes(b"# exact\n")
            wheel = repo / "candidate.whl"
            for data, extra in (
                (b"# exact\n", False),
                (b"# altered\n", False),
                (b"# exact\n", True),
            ):
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr("mos_eisley/__init__.py", data)
                    if extra:
                        archive.writestr("mos_eisley/unexpected.py", b"")
                if data == b"# exact\n" and not extra:
                    self.assertEqual(verify_wheel(repo, wheel), 1)
                else:
                    with self.assertRaisesRegex(ValueError, "exact_source"):
                        verify_wheel(repo, wheel)
