"""Adversarial cases for retained qualification ZIP custody."""

import hashlib
import io
import json
import tempfile
import unittest
import warnings
import zipfile
from collections.abc import Sequence
from pathlib import Path

import rc17_continuation_custody as subject


class CustodyTests(unittest.TestCase):
    def bundle(self, paths: Sequence[tuple[str, bytes]]) -> bytes:
        stream = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(stream, "w") as archive:
                for name, data in paths:
                    archive.writestr(name, data)
        return stream.getvalue()

    def verify(self, paths: Sequence[tuple[str, bytes]]) -> dict[str, str]:
        raw = self.bundle(paths)
        return subject.verify_zip(raw, hashlib.sha256(raw).hexdigest(), {"report.json"})

    def test_exact_bytes_have_content_hash_without_extraction(self) -> None:
        self.assertEqual(
            self.verify([("dist/standalone/report.json", b"{}")]),
            {
                "report.json": hashlib.sha256(b"{}").hexdigest(),
            },
        )

    def test_changed_archive_refused(self) -> None:
        raw = self.bundle([("dist/standalone/report.json", b"{}")])
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            subject.verify_zip(raw, "0" * 64, {"report.json"})

    def test_missing_extra_duplicate_or_traversal_report_refused(self) -> None:
        good = ("dist/standalone/report.json", b"{}")
        for paths in (
            [],
            [good, good],
            [good, ("extra.json", b"{}")],
            [("../report.json", b"{}")],
        ):
            with (
                self.subTest(paths=[p[0] for p in paths]),
                self.assertRaises(ValueError),
            ):
                self.verify(paths)

    def test_oversized_member_and_archive_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "Oversized report"):
            self.verify([("dist/standalone/report.json", b"x" * 100_001)])
        with self.assertRaisesRegex(ValueError, "Oversized report archive"):
            subject.verify_zip(b"x" * 1_000_001, "0" * 64, set())

    def test_wrong_or_incomplete_run_refused_before_reading_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for run in (
                {},
                {"id": subject.RUN, "head_sha": "0" * 40},
                {"id": subject.RUN, "status": "in_progress"},
            ):
                (root / "run.json").write_text(json.dumps(run))
                with self.assertRaisesRegex(ValueError, "Wrong continuation run"):
                    subject.review(root)


if __name__ == "__main__":
    unittest.main()
