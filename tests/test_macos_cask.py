"""Refuse substituted or untrusted cask artifacts before package generation."""

from __future__ import annotations

import hashlib
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_macos_cask import validate_bundle, verify_signature
from tools.package_macos_cask import Identity, generate, load_package


class CaskTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()

    def test_workflow_module_entry_points_are_executable(self) -> None:
        repository = Path(__file__).resolve().parent.parent
        for module in ("build_macos_cask", "package_macos_cask", "smoke_macos_cask"):
            result = subprocess.run(
                [sys.executable, "-m", f"tools.{module}", "--help"],
                cwd=repository,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout)

    def package(
        self,
        target: str,
        *,
        development: bool = True,
        version: str = "0.1.0-rc.4",
        source: str = "a" * 40,
        team: str = "ABCDE12345",
    ) -> Path:
        suffix = "-development" if development else ""
        image = self.base / f"mos-{version}-{target}-cask{suffix}.dmg"
        image.write_bytes(b"inert disk-image fixture")
        receipt = image.with_suffix(".json")
        receipt.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "version": version,
                    "source_commit": source,
                    "platform": target,
                    "file": image.name,
                    "size": image.stat().st_size,
                    "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                    "development": development,
                    "team_id": team if not development else None,
                    "apple_trust_verified": not development,
                    "notarization": {"status": "Accepted"} if not development else None,
                }
            )
        )
        return receipt

    def test_development_cask_is_disabled_and_keeps_full_runtime(self) -> None:
        for target in ("macos-aarch64", "macos-x86_64"):
            self.package(target)
        content = generate(self.base, development=True)
        self.assertIn("disable! date:", content)
        self.assertIn('arch arm: "aarch64", intel: "x86_64"', content)
        self.assertIn('binary "Mos Eisley/mos"', content)
        self.assertIn(self.base.as_uri(), content)
        self.assertNotIn("zap", content)
        self.assertNotIn("preflight", content)

    def test_development_artifacts_cannot_be_promoted(self) -> None:
        receipt = self.package("macos-aarch64")
        with self.assertRaisesRegex(ValueError, "development mode mismatch"):
            load_package(receipt, development=False, expected_team="ABCDE12345")

    def test_one_architecture_is_insufficient(self) -> None:
        self.package("macos-aarch64")
        with self.assertRaisesRegex(ValueError, "both unique"):
            generate(self.base, development=True)

    def test_mixed_source_or_version_is_refused(self) -> None:
        self.package("macos-aarch64")
        receipt = self.package("macos-x86_64", source="b" * 40)
        with self.assertRaisesRegex(ValueError, "mixed cask"):
            generate(self.base, development=True)
        receipt.unlink()
        self.package("macos-x86_64", version="0.1.0-rc.5")
        with self.assertRaisesRegex(ValueError, "mixed cask"):
            generate(self.base, development=True)

    def test_duplicate_architecture_is_refused(self) -> None:
        receipt = self.package("macos-aarch64")
        (self.base / "duplicate.json").write_bytes(receipt.read_bytes())
        with self.assertRaisesRegex(ValueError, "both unique"):
            generate(self.base, development=True)

    def test_tampered_image_is_refused(self) -> None:
        receipt = self.package("macos-aarch64")
        image = receipt.with_suffix(".dmg")
        image.write_bytes(b"X" * image.stat().st_size)
        with self.assertRaisesRegex(ValueError, "image identity"):
            load_package(receipt, development=True)

    def test_linked_image_is_refused(self) -> None:
        receipt = self.package("macos-aarch64")
        image = receipt.with_suffix(".dmg")
        original = image.rename(self.base / "original.dmg")
        image.symlink_to(original)
        with self.assertRaisesRegex(ValueError, "image identity"):
            load_package(receipt, development=True)

    def test_declined_notarization_is_refused_before_execution(self) -> None:
        receipt = self.package("macos-aarch64", development=False)
        raw = json.loads(receipt.read_text())
        raw["notarization"]["status"] = "Invalid"
        receipt.write_text(json.dumps(raw))
        with (
            patch("tools.package_macos_cask.verify_image") as verify,
            self.assertRaisesRegex(ValueError, "accepted notarization"),
        ):
            load_package(receipt, development=False, expected_team="ABCDE12345")
        verify.assert_not_called()

    def test_forged_json_cannot_replace_actual_apple_assessment(self) -> None:
        receipt = self.package("macos-aarch64", development=False)
        error = subprocess.CalledProcessError(1, ["spctl", "--assess"])
        with (
            patch("tools.package_macos_cask.verify_image", side_effect=error) as verify,
            self.assertRaises(subprocess.CalledProcessError),
        ):
            load_package(receipt, development=False, expected_team="ABCDE12345")
        verify.assert_called_once_with(receipt.with_suffix(".dmg"), "ABCDE12345")

    def test_production_generation_reassesses_both_actual_images(self) -> None:
        for target in ("macos-aarch64", "macos-x86_64"):
            self.package(target, development=False)
        with patch("tools.package_macos_cask.verify_image") as verify:
            content = generate(
                self.base,
                development=False,
                identity=Identity("0.1.0-rc.4", "a" * 40, "ABCDE12345"),
            )
        self.assertEqual(verify.call_count, 2)
        self.assertIn("releases/download/v0.1.0-rc.4/", content)
        self.assertNotIn("disable!", content)
        self.assertNotIn("file://", content)

    def test_mixed_apple_teams_are_refused(self) -> None:
        self.package("macos-aarch64", development=False)
        self.package("macos-x86_64", development=False, team="FGHIJ67890")
        with (
            patch("tools.package_macos_cask.verify_image"),
            self.assertRaisesRegex(ValueError, "trusted publisher selection"),
        ):
            generate(
                self.base,
                development=False,
                identity=Identity("0.1.0-rc.4", "a" * 40, "ABCDE12345"),
            )

    def test_foreign_team_cannot_self_enroll_through_receipts(self) -> None:
        for target in ("macos-aarch64", "macos-x86_64"):
            self.package(target, development=False, team="FGHIJ67890")
        with patch("tools.package_macos_cask.verify_image") as verify:
            with self.assertRaisesRegex(ValueError, "trusted publisher selection"):
                generate(
                    self.base,
                    development=False,
                    identity=Identity("0.1.0-rc.4", "a" * 40, "ABCDE12345"),
                )
        verify.assert_not_called()

    def test_source_claim_cannot_replace_selected_release(self) -> None:
        for target in ("macos-aarch64", "macos-x86_64"):
            self.package(target, development=False)
        with (
            patch("tools.package_macos_cask.verify_image"),
            self.assertRaisesRegex(ValueError, "selected version, source"),
        ):
            generate(
                self.base,
                development=False,
                identity=Identity("0.1.0-rc.4", "b" * 40, "ABCDE12345"),
            )

    def test_external_payload_link_is_refused(self) -> None:
        bundle = self.base / "bundle"
        bundle.mkdir()
        (bundle / "mos").write_bytes(bytes.fromhex("cffaedfe") + b"inert fixture")
        (bundle / "escape").symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, "symlink escapes"):
            validate_bundle(bundle)

    def test_ad_hoc_or_wrong_team_or_missing_runtime_is_refused(self) -> None:
        for details in (
            "Signature=adhoc\nTeamIdentifier=not set\n",
            "Authority=Developer ID Application: Fixture\nTeamIdentifier=WRONG12345\n"
            "Timestamp=fixture\nflags=0x10000(runtime)\n",
            "Authority=Developer ID Application: Fixture\nTeamIdentifier=ABCDE12345\n"
            "Timestamp=fixture\nExecutable=/path/containing/runtime\nflags=0x0(none)\n",
        ):
            with (
                self.subTest(details=details),
                patch(
                    "tools.build_macos_cask.run",
                    return_value=subprocess.CompletedProcess([], 0, "", details),
                ),
                self.assertRaisesRegex(ValueError, "Developer ID"),
            ):
                verify_signature(self.base / "mos", "ABCDE12345", runtime=True)

    def test_debug_entitlement_is_refused(self) -> None:
        details = (
            "Authority=Developer ID Application: Fixture\nTeamIdentifier=ABCDE12345\n"
            "Timestamp=fixture\nflags=0x10000(runtime)\n"
        )
        results = [
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "", details),
            subprocess.CompletedProcess(
                [],
                0,
                plistlib.dumps(
                    {
                        "com.apple.security.get-task-allow": True,
                    }
                ).decode(),
                "",
            ),
        ]
        with (
            patch("tools.build_macos_cask.run", side_effect=results),
            self.assertRaisesRegex(ValueError, "development task entitlement"),
        ):
            verify_signature(self.base / "mos", "ABCDE12345", runtime=True)
