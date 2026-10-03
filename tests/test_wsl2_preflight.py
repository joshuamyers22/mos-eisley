"""Preparation rejects unqualified hosts/storage without reading private content."""

import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.wsl2_preflight import (
    MAX_METADATA_BYTES,
    Mount,
    check_directory,
    classify_kernel,
    covering_mount,
    distribution_metadata,
    main,
    parse_mounts,
    read_metadata,
)

KERNEL = "6.6.87.2-microsoft-standard-WSL2"
ROOT_MOUNT = "21 1 8:0 / / rw,relatime shared:1 - ext4 /dev/sdc rw\n"


class WSL2PreflightTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="mos-wsl-preflight-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.storage = self.root / "private"
        self.storage.mkdir(mode=0o700)
        self.mounts = parse_mounts(ROOT_MOUNT)

    def test_kernel_requires_linux_and_explicit_wsl2_marker(self) -> None:
        self.assertEqual(classify_kernel("Linux", KERNEL), "wsl2_candidate")
        for system, kernel, expected in (
            ("Darwin", KERNEL, "not_wsl"),
            ("Windows", KERNEL, "not_wsl"),
            ("Linux", "6.8.0-generic", "not_wsl"),
            ("Linux", "4.4.0-19041-Microsoft", "wsl1_or_unrecognized_wsl"),
            ("Linux", "5.15.0-microsoft-custom", "wsl1_or_unrecognized_wsl"),
            ("Linux", "6.6-microsoft-WSL20", "wsl1_or_unrecognized_wsl"),
        ):
            with self.subTest(system=system, kernel=kernel):
                self.assertEqual(classify_kernel(system, kernel), expected)

    def test_nested_mount_and_component_boundaries(self) -> None:
        mounts = parse_mounts(
            ROOT_MOUNT
            + "22 21 0:9 / /mnt/c rw - 9p C: rw,aname=drvfs\n"
            + "23 21 0:10 / /home/user/network rw - nfs server:/share rw\n"
        )
        mount = covering_mount(PurePosixPath("/mnt/c/repo"), mounts)
        self.assertIsNotNone(mount)
        assert mount is not None
        self.assertEqual(mount.filesystem, "9p")
        self.assertEqual(
            covering_mount(PurePosixPath("/mnt/clone/repo"), mounts), mounts[0]
        )
        self.assertEqual(
            covering_mount(PurePosixPath("/home/user/network/project"), mounts),
            mounts[2],
        )
        self.assertIsNone(covering_mount(PurePosixPath("/"), ()))
        self.assertIsNone(covering_mount(PurePosixPath("/"), mounts + (mounts[0],)))

    def test_mount_escapes_and_read_only_flags(self) -> None:
        mounts = parse_mounts(
            "21 1 8:0 / /with\\040space rw - ext4 /dev/sdc ro\n"
            "22 1 8:0 / /with\\134slash ro - ext4 /dev/sdc rw\n"
            "23 1 8:0 / /tab\\011newline\\012 rw - ext4 /dev/sdc rw\n"
        )
        self.assertEqual(str(mounts[0].point), "/with space")
        self.assertEqual(str(mounts[1].point), "/with\\slash")
        self.assertEqual(str(mounts[2].point), "/tab\tnewline\n")
        self.assertFalse(mounts[0].writable)
        self.assertFalse(mounts[1].writable)

    def test_invalid_mount_metadata_rejects(self) -> None:
        for text in (
            "",
            "bad",
            "21 1 8:0 / / rw - ext4 device",
            "id 1 8:0 / / rw - ext4 device rw",
            "21 1 8:0 / relative rw - ext4 device rw",
            "x" * (MAX_METADATA_BYTES + 1),
        ):
            with self.subTest(length=len(text)), self.assertRaises(ValueError):
                parse_mounts(text)

    def test_private_owner_mode_and_existing_directory(self) -> None:
        uid = os.getuid()
        result = check_directory(
            "storage", self.storage, self.mounts, uid, private=True
        )
        self.assertEqual(result.issues, ())
        self.storage.chmod(0o750)
        self.assertIn(
            "private_directory_not_private",
            check_directory(
                "storage", self.storage, self.mounts, uid, private=True
            ).issues,
        )
        self.assertIn(
            "private_directory_wrong_owner",
            check_directory(
                "storage", self.storage, self.mounts, uid + 1, private=True
            ).issues,
        )
        missing = self.root / "missing"
        self.assertEqual(
            check_directory("storage", missing, self.mounts, uid, private=True).issues,
            ("directory_unavailable",),
        )
        self.assertFalse(missing.exists())
        file = self.root / "file"
        file.touch(mode=0o600)
        self.assertIn(
            "not_a_directory",
            check_directory("storage", file, self.mounts, uid, private=True).issues,
        )

    def test_alias_resolves_to_unqualified_mount_and_unknown_rejects(self) -> None:
        alias = self.root / "alias"
        alias.symlink_to(self.storage, target_is_directory=True)
        for filesystem in ("9p", "drvfs", "cifs", "nfs", "overlay", "tmpfs", "unknown"):
            mount = Mount(PurePosixPath(str(self.storage)), filesystem, True)
            with self.subTest(filesystem=filesystem):
                result = check_directory(
                    "storage", alias, self.mounts + (mount,), os.getuid(), private=True
                )
                self.assertEqual(result.path, str(self.storage))
                self.assertIn("filesystem_not_qualified_candidate", result.issues)
        readonly = Mount(PurePosixPath(str(self.storage)), "ext4", False)
        self.assertIn(
            "mount_read_only",
            check_directory(
                "storage", alias, (readonly,), os.getuid(), private=True
            ).issues,
        )
        self.assertIn(
            "mount_unknown_or_ambiguous",
            check_directory(
                "workspace", self.root, (), os.getuid(), private=False
            ).issues,
        )

    def test_metadata_reads_are_bounded_and_distro_fields_allowlisted(self) -> None:
        metadata = self.root / "metadata"
        metadata.write_bytes(b"x" * (MAX_METADATA_BYTES + 1))
        with self.assertRaises(ValueError):
            read_metadata(metadata)
        metadata.write_bytes(b"\xff")
        with self.assertRaises(UnicodeError):
            read_metadata(metadata)
        metadata.write_text("ID=ubuntu\nVERSION_ID=24.04\nSECRET=canary\n")
        self.assertEqual(
            distribution_metadata(read_metadata(metadata)),
            {"ID": "ubuntu", "VERSION_ID": "24.04"},
        )
        self.assertEqual(
            len(
                distribution_metadata('PRETTY_NAME="' + "x" * 300 + '"')["PRETTY_NAME"]
            ),
            256,
        )

    def test_command_reports_candidate_without_authority_or_content(self) -> None:
        secret = self.storage / "credentials"
        secret.write_text("private-content-canary")
        output = io.StringIO()

        def metadata(path: Path) -> str:
            return (
                ROOT_MOUNT
                if path.name == "mountinfo"
                else "ID=ubuntu\nVERSION_ID=24.04\n"
            )

        with (
            patch("mos_eisley.wsl2_preflight.platform.system", return_value="Linux"),
            patch("mos_eisley.wsl2_preflight.platform.release", return_value=KERNEL),
            patch("mos_eisley.wsl2_preflight.read_metadata", side_effect=metadata),
            patch.dict(
                os.environ, {"WSL_DISTRO_NAME": "do-not-copy", "API_KEY": "canary"}
            ),
            redirect_stdout(output),
        ):
            status = main(
                [
                    "--workspace",
                    str(self.root),
                    "--storage",
                    str(self.storage),
                    "--private-dir",
                    str(self.storage),
                ]
            )
        report = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertTrue(report["preparation_passed"])
        self.assertFalse(report["platform_qualified"])
        self.assertFalse(report["execution_authorized"])
        self.assertEqual(report["execution_backend"], "not_probed")
        self.assertNotIn("canary", output.getvalue())
        self.assertNotIn("do-not-copy", output.getvalue())
        self.assertEqual(secret.read_text(), "private-content-canary")

    def test_command_rejects_missing_metadata_nonwsl_and_root(self) -> None:
        output = io.StringIO()
        with (
            patch("mos_eisley.wsl2_preflight.platform.system", return_value="Linux"),
            patch("mos_eisley.wsl2_preflight.platform.release", return_value="generic"),
            patch("mos_eisley.wsl2_preflight.os.getuid", return_value=0),
            patch("mos_eisley.wsl2_preflight.read_metadata", side_effect=OSError),
            redirect_stdout(output),
        ):
            status = main(
                ["--workspace", str(self.root), "--storage", str(self.storage)]
            )
        report = json.loads(output.getvalue())
        self.assertEqual(status, 2)
        self.assertIn("recognized_wsl2_kernel_required", report["issues"])
        self.assertIn("non_root_posix_user_required", report["issues"])
        self.assertIn("distribution_metadata_unavailable", report["issues"])
        self.assertIn("mount_metadata_unavailable_or_invalid", report["issues"])

    def test_command_bounds_private_directory_count_before_inspection(self) -> None:
        with patch("mos_eisley.wsl2_preflight.read_metadata") as read:
            with (
                redirect_stdout(io.StringIO()),
                patch("sys.stderr", new=io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                main(
                    ["--workspace", str(self.root), "--storage", str(self.storage)]
                    + [
                        item
                        for _ in range(17)
                        for item in ("--private-dir", str(self.storage))
                    ]
                )
            read.assert_not_called()
