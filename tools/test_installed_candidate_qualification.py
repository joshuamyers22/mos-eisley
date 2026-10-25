"""Challenge evidence/identity refusal before any native side effect."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qualify_installed_candidate as subject

SOURCE = "a" * 40
VERSION = "0.1.0-rc.9"


class InstalledQualificationTests(unittest.TestCase):
    def test_missing_duplicate_out_of_order_or_wrong_schema_result_refuses(
        self,
    ) -> None:
        good = {"sequence": 1, "schema_version": 1, "type": "exec.result"}
        for events in (
            [],
            [good, {**good, "sequence": 2}],
            [{**good, "sequence": 2}],
            [{**good, "schema_version": 2}],
            [good, {"sequence": 2, "schema_version": 1, "type": "later"}],
        ):
            with self.subTest(events=events), self.assertRaises(ValueError):
                subject.result("\n".join(json.dumps(e) for e in events))

    def test_wrong_source_version_or_epoch_never_installs_or_writes_evidence(
        self,
    ) -> None:
        for field, wrong in (
            ("source_commit", "0" * 40),
            ("version", "0.1.0-rc.7"),
            ("storage_epoch", 1),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                payload = {
                    "source_commit": SOURCE,
                    "version": VERSION,
                    "storage_epoch": 2,
                }
                payload[field] = wrong
                (root / "release.json").write_text(json.dumps({"payload": payload}))
                output = root / "report.json"
                with (
                    patch.object(subject, "run") as execute,
                    self.assertRaisesRegex(ValueError, "source/version/epoch"),
                ):
                    subject.qualify(root, output, SOURCE, VERSION)
                execute.assert_not_called()
                self.assertFalse(output.exists())

    def test_archive_substitution_never_reaches_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / f"mos-{VERSION}-linux-x86_64.tar.gz").write_bytes(b"substituted")
            payload = {
                "source_commit": SOURCE,
                "version": VERSION,
                "storage_epoch": 2,
                "artifacts": [
                    {"platform": "linux-x86_64", "sha256": "0" * 64, "size": 11}
                ],
            }
            (root / "release.json").write_text(json.dumps({"payload": payload}))
            with (
                patch.object(subject.platform, "machine", return_value="x86_64"),
                patch.object(subject.platform, "system", return_value="Linux"),
                patch.object(subject, "run") as execute,
                self.assertRaisesRegex(ValueError, "archive mismatch"),
            ):
                subject.qualify(root, root / "report.json", SOURCE, VERSION)
            execute.assert_not_called()
            self.assertFalse((root / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
