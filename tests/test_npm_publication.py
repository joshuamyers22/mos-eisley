"""Publication rejects mismatched lineage and incomplete/tampered native sets."""

from __future__ import annotations

import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley import app_release
from mos_eisley.app_release import ReleaseError, canonical
from tools.prepare_npm_publication import (
    PLATFORMS,
    acquire_publication,
    verify_publication,
)


class NpmPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.assets = Path(temporary.name)
        self.key = Ed25519PrivateKey.generate()
        self.commit = "a" * 40
        self.trust = patch.object(
            app_release,
            "PUBLISHER_PUBLIC_KEY",
            self.key.public_key().public_bytes_raw().hex(),
        )
        self.trust.start()
        self.addCleanup(self.trust.stop)

    def manifest(self, platforms: set[str] | None = None) -> None:
        artifacts: list[dict[str, object]] = []
        for target in sorted(PLATFORMS if platforms is None else platforms):
            raw = target.encode()
            name = f"mos-0.1.0-{target}.tar.gz"
            (self.assets / name).write_bytes(raw)
            artifacts.append(
                {
                    "platform": target,
                    "url": f"{app_release.RELEASE_ORIGIN}v0.1.0/{name}",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size": len(raw),
                }
            )
        payload = {
            "schema": 1,
            "version": "0.1.0",
            "channel": "stable",
            "source_commit": self.commit,
            "notes": "Synthetic test inventory",
            "storage_epoch": 1,
            "withdrawn": False,
            "artifacts": artifacts,
        }
        envelope = {
            "payload": payload,
            "signature": base64.b64encode(self.key.sign(canonical(payload))).decode(),
        }
        (self.assets / "release.json").write_bytes(canonical(envelope))

    def test_complete_signed_inventory(self) -> None:
        self.manifest()
        release = verify_publication(self.assets, "v0.1.0", self.commit)
        self.assertEqual(len(release.artifacts), 4)

    def test_mismatched_tag_or_commit(self) -> None:
        self.manifest()
        for tag, commit in [("v0.1.1", self.commit), ("v0.1.0", "b" * 40)]:
            with self.subTest(tag=tag, commit=commit), self.assertRaises(ReleaseError):
                verify_publication(self.assets, tag, commit)

    def test_incomplete_inventory(self) -> None:
        self.manifest({"macos-aarch64"})
        with self.assertRaisesRegex(ReleaseError, "four native platforms"):
            verify_publication(self.assets, "v0.1.0", self.commit)

    def test_tampered_archive(self) -> None:
        self.manifest()
        (self.assets / "mos-0.1.0-macos-aarch64.tar.gz").write_bytes(b"tampered")
        with self.assertRaises(ReleaseError):
            verify_publication(self.assets, "v0.1.0", self.commit)

    def test_forged_signature(self) -> None:
        self.manifest()
        with (
            patch.object(app_release, "PUBLISHER_PUBLIC_KEY", "00" * 32),
            self.assertRaises(ReleaseError),
        ):
            verify_publication(self.assets, "v0.1.0", self.commit)

    def test_invalid_tag_never_contacts_network(self) -> None:
        with patch("tools.prepare_npm_publication.download") as fetch:
            with self.assertRaises(ReleaseError):
                acquire_publication(self.assets / "received", "../wrong", self.commit)
            fetch.assert_not_called()

    def test_signed_lineage_rejected_before_archive_download(self) -> None:
        self.manifest()
        raw = (self.assets / "release.json").read_bytes()
        with patch("tools.prepare_npm_publication.download", return_value=raw) as fetch:
            with self.assertRaises(ReleaseError):
                acquire_publication(self.assets / "received", "v0.1.0", "b" * 40)
            self.assertEqual(fetch.call_count, 1)
            self.assertFalse((self.assets / "received").exists())


if __name__ == "__main__":
    unittest.main()
