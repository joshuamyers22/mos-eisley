"""Offline challenges to signed discovery admission and redacted harness failures."""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qualify_rc16_discovery as subject
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley import app_release
from mos_eisley.app_release import canonical


class SignedDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.key = Ed25519PrivateKey.generate()
        trust = patch.object(
            app_release,
            "PUBLISHER_PUBLIC_KEY",
            self.key.public_key().public_bytes_raw().hex(),
        )
        trust.start()
        self.addCleanup(trust.stop)
        self.target = app_release.platform_id()

    def bundle(
        self, version: str = subject.VERSION, source: str = subject.SOURCE
    ) -> Path:
        directory = self.root / version
        directory.mkdir(exist_ok=True)
        raw = b"signed archive fixture"
        payload = {
            "schema": 1,
            "version": version,
            "channel": "preview",
            "source_commit": source,
            "notes": "Synthetic release.",
            "storage_epoch": 2,
            "withdrawn": False,
            "artifacts": [
                {
                    "platform": self.target,
                    "url": (
                        f"{app_release.RELEASE_ORIGIN}v{version}/"
                        f"mos-{version}-{self.target}.tar.gz"
                    ),
                    "sha256": subject.sha(raw),
                    "size": len(raw),
                }
            ],
        }
        envelope = {
            "payload": payload,
            "signature": base64.b64encode(self.key.sign(canonical(payload))).decode(),
        }
        (directory / "release.json").write_bytes(canonical(envelope))
        (directory / f"mos-{version}-{self.target}.tar.gz").write_bytes(raw)
        bootstrap = directory / f"mos-install-{self.target}"
        bootstrap.write_bytes(b"synthetic bootstrap")
        (directory / "BOOTSTRAP_SHA256SUMS").write_text(
            f"{subject.sha(bootstrap.read_bytes())}  {bootstrap.name}\n"
        )
        return directory

    def test_real_signature_archive_and_bootstrap_hash_admission(self) -> None:
        for version, source in (
            (subject.VERSION, subject.SOURCE),
            (subject.PREVIOUS_VERSION, subject.PREVIOUS_SOURCE),
        ):
            with self.subTest(version=version):
                release, bootstrap = subject.admitted(
                    self.bundle(version, source), source, version
                )
                self.assertEqual(release.version, version)
                self.assertTrue(bootstrap.is_file())

    def test_wrong_signed_identity_and_archive_substitution_refuse(self) -> None:
        directory = self.bundle()
        for source, version in (
            ("0" * 40, subject.VERSION),
            (subject.SOURCE, subject.PREVIOUS_VERSION),
        ):
            with (
                self.subTest(source=source, version=version),
                self.assertRaises(ValueError),
            ):
                subject.admitted(directory, source, version)
        (directory / f"mos-{subject.VERSION}-{self.target}.tar.gz").write_bytes(
            b"tampered"
        )
        with self.assertRaises(ValueError):
            subject.admitted(directory, subject.SOURCE, subject.VERSION)

    def test_tampered_signature_bootstrap_and_duplicate_manifest_refuse(self) -> None:
        for fault in ("metadata", "bootstrap", "duplicate", "symlink"):
            with self.subTest(fault=fault):
                directory = self.bundle()
                bootstrap = directory / f"mos-install-{self.target}"
                if fault == "metadata":
                    p = directory / "release.json"
                    p.write_bytes(p.read_bytes().replace(b"Synthetic", b"Corrupted"))
                elif fault == "bootstrap":
                    bootstrap.write_bytes(b"tampered bootstrap")
                elif fault == "duplicate":
                    p = directory / "BOOTSTRAP_SHA256SUMS"
                    p.write_text(p.read_text() * 2)
                else:
                    bootstrap.unlink()
                    bootstrap.symlink_to(directory / "release.json")
                with self.assertRaises(ValueError):
                    subject.admitted(directory, subject.SOURCE, subject.VERSION)
                if bootstrap.is_symlink():
                    bootstrap.unlink()

    def test_platform_and_harness_mismatch_never_download_or_execute(self) -> None:
        with (
            patch.object(subject, "download") as fetch,
            patch.object(subject, "command") as native,
        ):
            with self.assertRaisesRegex(ValueError, "host platform"):
                subject.qualify(self.root, self.root, "unsupported", "a" * 40)
            with (
                patch.object(subject.subprocess, "check_output", return_value="b" * 40),
                self.assertRaisesRegex(ValueError, "harness source"),
            ):
                subject.qualify(self.root, self.root, self.target, "a" * 40)
            fetch.assert_not_called()
            native.assert_not_called()

    def test_native_command_has_isolated_environment_finite_deadline_and_no_retry(
        self,
    ) -> None:
        with patch.object(
            subject.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, '{"status":"ok"}', ""),
        ) as execute:
            self.assertEqual(
                subject.command(self.root / "native", ["update"], self.root),
                {"status": "ok"},
            )
            env = execute.call_args.kwargs["env"]
            self.assertEqual(set(env), {"HOME", "PATH", "TMPDIR", "LANG", "LC_ALL"})
            self.assertFalse(Path(env["PATH"]).exists())
            self.assertEqual(execute.call_args.kwargs["timeout"], 180)
        for code, output in ((1, "{}"), (0, "[]"), (0, "x" * (128 * 1024 + 1))):
            with (
                self.subTest(code=code, size=len(output)),
                patch.object(
                    subject.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], code, output, ""),
                ) as execute,
            ):
                with self.assertRaises(ValueError):
                    subject.command(self.root / "native", [], self.root)
                self.assertEqual(execute.call_count, 1)

    def test_failure_receipt_retains_fixed_reason_without_external_details(
        self,
    ) -> None:
        for error in (
            subject.QualificationError("bootstrap checksum mismatch or duplicate"),
            OSError("sensitive synthetic detail"),
        ):
            report = self.root / "report.json"
            with (
                patch(
                    "sys.argv",
                    [
                        "qualify",
                        "--candidate",
                        str(self.root),
                        "--predecessor",
                        str(self.root),
                        "--platform",
                        self.target,
                        "--harness-source",
                        "a" * 40,
                        "--evidence",
                        str(report),
                    ],
                ),
                patch.object(subject, "qualify", side_effect=error),
            ):
                self.assertEqual(subject.main(), 1)
            text = report.read_text()
            self.assertNotIn("sensitive synthetic detail", text)
            result = json.loads(text)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(
                result["error_code"],
                str(error)
                if isinstance(error, subject.QualificationError)
                else "external_boundary_failure",
            )


if __name__ == "__main__":
    unittest.main()
