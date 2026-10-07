"""Executable installation, fault and signed supply-chain boundary evidence."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley import app_install, app_release, app_update
from mos_eisley.app_release import Release, ReleaseError, canonical, parse_release


class DistributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="mos-distribution-")
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name).resolve()
        self.root = self.base / "app"
        self.bin = self.base / "bin with spaces"
        self.key = Ed25519PrivateKey.generate()
        self.trust = patch.object(
            app_release,
            "PUBLISHER_PUBLIC_KEY",
            self.key.public_key().public_bytes_raw().hex(),
        )
        self.trust.start()
        self.addCleanup(self.trust.stop)
        self.target = app_release.platform_id()

    def archive(self, version: str, *, bad: str | None = None) -> bytes:
        output = io.BytesIO()
        with (
            gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w") as stream,
        ):
            item = tarfile.TarInfo("mos")
            item.mode = 0o755
            raw = f"#!/bin/sh\nprintf 'mos-eisley {version}\\n'\n".encode()
            item.size = len(raw)
            stream.addfile(item, io.BytesIO(raw))
            if bad is not None:
                item = tarfile.TarInfo(bad)
                stream.addfile(item, io.BytesIO(b""))
        return output.getvalue()

    def release(
        self,
        version: str = "0.1.0",
        *,
        raw: bytes | None = None,
        change: dict[str, object] | None = None,
    ) -> tuple[Release, bytes]:
        archive = raw if raw is not None else self.archive(version)
        payload: dict[str, object] = {
            "schema": 1,
            "version": version,
            "channel": "stable",
            "source_commit": "a" * 40,
            "notes": "Release notes; no executable instructions.",
            "storage_epoch": 1,
            "withdrawn": False,
            "artifacts": [
                {
                    "platform": self.target,
                    "url": (
                        f"{app_release.RELEASE_ORIGIN}v{version}/"
                        f"mos-{version}-{self.target}.tar.gz"
                    ),
                    "sha256": hashlib.sha256(archive).hexdigest(),
                    "size": len(archive),
                }
            ],
        }
        if change:
            payload.update(change)
        signed = canonical(
            {
                "payload": payload,
                "signature": base64.b64encode(
                    self.key.sign(canonical(payload))
                ).decode(),
            }
        )
        return parse_release(signed), archive

    def current_version(self) -> str:
        current = app_install.installed_release(self.root)
        assert current is not None
        return current.version

    def install(self, version: str = "0.1.0") -> None:
        release, raw = self.release(version)
        app_install.install(self.root, self.bin, release, raw)

    def test_install_upgrade_rollback_preserve_state(self) -> None:
        state = self.base / "sessions"
        state.mkdir()
        evidence = state / "uncertain-spend.json"
        evidence.write_bytes(b"original immutable evidence")
        self.install()
        self.assertTrue((self.bin / "mos").is_symlink())
        self.install("0.1.1")
        self.assertEqual(self.current_version(), "0.1.1")
        self.assertEqual(app_install.rollback(self.root), "0.1.0")
        self.assertEqual(evidence.read_bytes(), b"original immutable evidence")
        self.assertEqual(app_install.recover(self.root), "0.1.0")

    def test_repeat_install_and_uninstall_preserve_siblings(self) -> None:
        self.install()
        self.install()
        sibling = self.base / "credentials"
        sibling.write_bytes(b"synthetic sentinel")
        app_install.uninstall(self.root)
        self.assertFalse((self.bin / "mos").exists())
        self.assertEqual(sibling.read_bytes(), b"synthetic sentinel")

    def test_tampered_archive_keeps_current(self) -> None:
        self.install()
        release, raw = self.release("0.1.1")
        with self.assertRaisesRegex(ReleaseError, "integrity"):
            app_install.install(self.root, self.bin, release, raw + b"x")
        self.assertEqual(self.current_version(), "0.1.0")

    def test_signature_alteration_rejected(self) -> None:
        release, _ = self.release()
        altered = release.raw.replace(b"Release notes", b"Altered notes")
        with self.assertRaisesRegex(ReleaseError, "signature"):
            parse_release(altered)
        with self.assertRaisesRegex(ReleaseError, "signature"):
            parse_release(
                release.raw,
                public_key=Ed25519PrivateKey.generate()
                .public_key()
                .public_bytes_raw()
                .hex(),
            )

    def test_release_compatibility_boundaries(self) -> None:
        changes: tuple[dict[str, object], ...] = (
            {"withdrawn": True},
            {"storage_epoch": 2},
            {"version": "../bad"},
            {"source_commit": "xyz"},
            {"artifacts": []},
            {"notes": "escape\x1bcode"},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ReleaseError):
                self.release(change=change)

    def test_archive_path_boundaries(self) -> None:
        for name in (
            "../escape",
            "/absolute",
            "a/../../escape",
            "a\\escape",
            "mos",
            "./bad",
        ):
            with (
                self.subTest(name=name),
                tempfile.TemporaryDirectory(dir=self.base) as target,
                self.assertRaises((ReleaseError, OSError)),
            ):
                app_install.extract_archive(
                    self.archive("0.1.0", bad=name), Path(target)
                )
        self.assertFalse((self.base / "escape").exists())

    def test_archive_links_and_special_files_refused(self) -> None:
        for kind in (
            tarfile.SYMTYPE,
            tarfile.LNKTYPE,
            tarfile.FIFOTYPE,
            tarfile.CHRTYPE,
        ):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w:gz") as stream:
                item = tarfile.TarInfo("mos")
                item.type = kind
                item.linkname = "/tmp/foreign"
                stream.addfile(item)
            with self.subTest(kind=kind), self.assertRaises(ReleaseError):
                app_install.extract_archive(output.getvalue(), self.base)

    def test_shared_root_and_symlink_root_refused(self) -> None:
        self.root.mkdir(mode=0o755)
        release, raw = self.release()
        with self.assertRaisesRegex(ReleaseError, "private"):
            app_install.install(self.root, self.bin, release, raw)
        self.root.rmdir()
        self.root.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ReleaseError):
            app_install.install(self.root, self.bin, release, raw)

    def test_launcher_conflict_preserves_foreign_command(self) -> None:
        self.bin.mkdir()
        foreign = self.bin / "mos"
        foreign.write_text("foreign tool")
        release, raw = self.release()
        with self.assertRaisesRegex(ReleaseError, "another command"):
            app_install.install(self.root, self.bin, release, raw)
        self.assertEqual(foreign.read_text(), "foreign tool")

    def test_active_clients_block_replacement(self) -> None:
        self.install()
        release, raw = self.release("0.1.1")
        with (
            app_install.lock(self.root, shared=True),
            self.assertRaisesRegex(ReleaseError, "client is active"),
        ):
            app_install.install(self.root, self.bin, release, raw)
        self.assertEqual(self.current_version(), "0.1.0")

    def test_downgrade_refused(self) -> None:
        self.install("0.1.1")
        release, raw = self.release()
        with self.assertRaisesRegex(ReleaseError, "downgrade"):
            app_install.install(self.root, self.bin, release, raw)

    def test_failed_staged_binary_keeps_old_release(self) -> None:
        self.install()
        release, raw = self.release("0.1.1", raw=self.archive("9.9.9"))
        with self.assertRaisesRegex(ReleaseError, "version verification"):
            app_install.install(self.root, self.bin, release, raw)
        self.assertEqual(self.current_version(), "0.1.0")

    def test_pre_activation_failure_and_recovery(self) -> None:
        self.install()
        release, raw = self.release("0.1.1")
        original = app_install.activate_pointer

        def fail_current(root: Path, name: str, value: str) -> None:
            if name == "current":
                raise OSError("synthetic interrupted activation")
            original(root, name, value)

        with (
            patch.object(app_install, "activate_pointer", side_effect=fail_current),
            self.assertRaises(OSError),
        ):
            app_install.install(self.root, self.bin, release, raw)
        self.assertEqual(app_install.recover(self.root), "0.1.0")
        self.install("0.1.1")

    def test_post_activation_interruption_recovery(self) -> None:
        self.install()
        release, raw = self.release("0.1.1")
        original = app_install.activate_pointer

        def interrupted(root: Path, name: str, value: str) -> None:
            original(root, name, value)
            if name == "current":
                raise OSError("synthetic acknowledgement loss")

        with (
            patch.object(app_install, "activate_pointer", side_effect=interrupted),
            self.assertRaises(OSError),
        ):
            app_install.install(self.root, self.bin, release, raw)
        self.assertEqual(app_install.recover(self.root), "0.1.1")
        self.assertFalse((self.root / "transaction.json").exists())

    def test_check_cache_failure_skip_and_deferral(self) -> None:
        release, _ = self.release("0.1.1")
        with patch.object(
            app_update, "release_metadata", return_value=release.raw
        ) as fetch:
            result = app_update.check(self.root, force=True)
            self.assertTrue(result["notify"])
            app_update.check(self.root)
            self.assertEqual(fetch.call_count, 1)
            app_update.change_policy(self.root, "skip", "0.1.1")
            self.assertFalse(app_update.check(self.root)["notify"])
        with patch.object(
            app_update, "release_metadata", side_effect=OSError("offline")
        ):
            result = app_update.check(self.root, force=True)
            self.assertEqual(result["status"], "unable_to_check")
            self.assertTrue(result["cached"])
            self.assertEqual(result["latest"], "0.1.1")
            self.assertFalse(result["notify"])
        app_update.change_policy(self.root, "later")
        self.assertGreater(app_update.policy(self.root).deferred_until, 0)

    def test_disabled_managed_checks_never_fetch(self) -> None:
        for action in ("disabled", "managed"):
            app_update.change_policy(self.root, action)
            with patch.object(app_update, "release_metadata") as fetch:
                self.assertEqual(
                    app_update.check(self.root, force=True)["status"], action
                )
                fetch.assert_not_called()

    def test_admin_policy_cannot_be_overridden_by_user(self) -> None:
        app_update.change_policy(self.root, "automatic")
        with (
            patch.object(app_update, "system_mode", return_value="managed"),
            patch.object(app_update, "release_metadata") as fetch,
        ):
            app_update.change_policy(self.root, "automatic")
            self.assertEqual(
                app_update.check(self.root, force=True)["status"], "managed"
            )
            fetch.assert_not_called()

    def test_policy_repository_cannot_select_or_modify(self) -> None:
        self.root.mkdir(mode=0o700)
        foreign = self.base / "foreign.json"
        foreign.write_text("{}")
        (self.root / "update-policy.json").symlink_to(foreign)
        with self.assertRaisesRegex(ReleaseError, "unsafe"):
            app_update.policy(self.root)

    def test_preview_requires_explicit_selection(self) -> None:
        release, _ = self.release("0.1.1-rc.1", change={"channel": "preview"})
        with patch.object(app_update, "release_metadata", return_value=release.raw):
            self.assertEqual(
                app_update.check(self.root, force=True)["status"], "unable_to_check"
            )
            app_update.change_policy(self.root, "preview")
            self.assertEqual(
                app_update.check(self.root, force=True)["status"], "available"
            )

    def test_updates_require_confirmation_and_exact_target(self) -> None:
        with self.assertRaisesRegex(ReleaseError, "confirmation"):
            app_update.update(self.root, confirmed=False)
        self.install()
        release, raw = self.release("0.1.1")
        with (
            patch.object(app_update, "installation_origin", return_value="standalone"),
            patch.object(app_update, "release_metadata", return_value=release.raw),
            patch.object(app_update, "download", return_value=raw),
        ):
            self.assertEqual(
                app_update.update(self.root, confirmed=True, target="0.1.1"), "0.1.1"
            )
        with (
            patch.object(app_update, "installation_origin", return_value="standalone"),
            patch.object(app_update, "release_metadata", return_value=release.raw),
            self.assertRaisesRegex(ReleaseError, "changed"),
        ):
            app_update.update(self.root, confirmed=True, target="0.1.2")

    def test_manager_origin_does_not_replace_other_environment(self) -> None:
        for origin in ("npm", "homebrew", "developer"):
            with (
                patch.object(app_update, "installation_origin", return_value=origin),
                patch.object(app_update, "release_metadata") as fetch,
            ):
                with self.assertRaises(ReleaseError):
                    app_update.update(self.root, confirmed=True)
                fetch.assert_not_called()

    def test_developer_origin_not_inferred_from_standalone_root(self) -> None:
        self.install()
        self.assertEqual(app_update.installation_origin(self.root), "developer")

    def test_damaged_installed_runtime_refuses_recovery(self) -> None:
        self.install()
        pointer = self.root / "current"
        (pointer / "mos").write_text("damaged runtime")
        with self.assertRaisesRegex(ReleaseError, "damaged"):
            app_install.recover(self.root)

    def test_semantic_order_and_invalid_versions(self) -> None:
        self.assertLess(
            app_release.version_key("0.1.1-rc.2"), app_release.version_key("0.1.1")
        )
        for value in ("1.2", "v1.2.3", "01.2.3", "../bad", "1.2.3;whoami"):
            with self.assertRaises(ReleaseError):
                app_release.version_key(value)

    def test_untrusted_network_origins_refused_before_fetch(self) -> None:
        for url in (
            "http://github.com/evil",
            "https://evil.invalid",
            "file:///tmp/file",
        ):
            with self.assertRaises(ReleaseError):
                app_release.download(url, 100)

    def test_metadata_and_archive_size_bounds(self) -> None:
        with self.assertRaises(ReleaseError):
            parse_release(b"x" * (app_release.MAX_METADATA + 1))
        with (
            patch.object(app_install, "MAX_EXPANDED", 1),
            self.assertRaises(ReleaseError),
        ):
            app_install.extract_archive(self.archive("0.1.0"), self.base)

    def test_browser_login_uses_official_client_without_api_credentials(self) -> None:
        from mos_eisley import provider_auth_cli

        with (
            patch.object(provider_auth_cli.sys.stdin, "isatty", return_value=True),
            patch.object(
                provider_auth_cli.shutil, "which", return_value="/official/codex"
            ),
            patch.object(provider_auth_cli.subprocess, "run") as process,
            patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "synthetic-key",
                    "CODEX_ACCESS_TOKEN": "synthetic-token",
                },
            ),
        ):
            process.return_value.returncode = 0
            self.assertEqual(
                provider_auth_cli.run_command(
                    argparse.Namespace(action="login", provider="openai")
                ),
                0,
            )
            self.assertEqual(process.call_args.args[0], ["/official/codex", "login"])
            environment = process.call_args.kwargs["env"]
            self.assertNotIn("OPENAI_API_KEY", environment)
            self.assertNotIn("CODEX_ACCESS_TOKEN", environment)
            self.assertEqual(process.call_args.kwargs["cwd"], Path.home())

    def test_browser_login_ignores_relative_and_project_path_entries(self) -> None:
        from mos_eisley import provider_auth_cli

        with (
            patch.object(provider_auth_cli.sys.stdin, "isatty", return_value=True),
            patch.object(provider_auth_cli.Path, "cwd", return_value=self.base),
            patch.dict(os.environ, {"PATH": f".:bin:{self.base}/bin:/usr/local/bin"}),
            patch.object(
                provider_auth_cli.shutil, "which", return_value=None
            ) as lookup,
        ):
            self.assertEqual(
                provider_auth_cli.run_command(
                    argparse.Namespace(action="login", provider="openai")
                ),
                2,
            )
            lookup.assert_called_once_with("codex", path="/usr/local/bin")

    def test_browser_login_requires_owner_terminal(self) -> None:
        from mos_eisley import provider_auth_cli

        with patch.object(provider_auth_cli.sys.stdin, "isatty", return_value=False):
            self.assertEqual(
                provider_auth_cli.run_command(
                    argparse.Namespace(action="login", provider="openai")
                ),
                2,
            )

    def test_update_cli_uses_the_running_custom_installation_root(self) -> None:
        from mos_eisley import app_update_cli, app_update_session

        with (
            patch.object(app_update_session, "runtime_root", return_value=self.base),
            patch.object(
                app_update, "check", return_value={"status": "disabled"}
            ) as check,
        ):
            self.assertEqual(
                app_update_cli.run_command(
                    argparse.Namespace(
                        command="update", action="check", root=None, json=True
                    )
                ),
                0,
            )
            check.assert_called_once_with(self.base, force=True)

    def test_provider_auth_command_is_finite_and_explicit(self) -> None:
        from mos_eisley.provider_auth_cli import auth_command

        self.assertEqual(auth_command("openai", "status"), ("codex", "login", "status"))
        self.assertEqual(
            auth_command("anthropic", "login"), ("claude", "auth", "login")
        )
        with self.assertRaises(ValueError):
            auth_command("untrusted", "login")

    def test_setup_does_not_print_keys_or_call_provider(self) -> None:
        from mos_eisley.app_update_cli import setup_result

        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-secret-sentinel"}):
            result = setup_result()
        self.assertNotIn("synthetic-secret-sentinel", json.dumps(result))
        self.assertFalse(result["credentials_required_to_install"])


if __name__ == "__main__":
    unittest.main()
