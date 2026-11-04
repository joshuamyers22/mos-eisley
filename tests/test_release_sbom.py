"""Artifact-semantic completeness, hostile framing and publication refusals."""

from __future__ import annotations

import gzip
import io
import json
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zlib
from pathlib import Path
from typing import cast
from unittest.mock import patch

from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import Schema
from sbom_fixtures import COMMIT, carchive, publication, tar

from tools.release_sbom import build_sbom, validate_sbom
from tools.sbom_archive import (
    COOKIE,
    ENTRY,
    carchive_inventory,
    tar_inventory,
    wheel_inventory,
)
from tools.sbom_metadata import environment, marker_applies, runtime_export


class SbomTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        publication(self.root)

    def write(self) -> dict[str, object]:
        value = build_sbom(self.root, COMMIT)
        (self.root / "release-sbom.cdx.json").write_text(json.dumps(value))
        return value

    def test_complete_artifact_inventory_is_deterministic_and_stdlib_only(self) -> None:
        value = self.write()
        self.assertEqual(value, build_sbom(self.root, COMMIT))
        validate_sbom(self.root, COMMIT, "0.2.0-rc.1")
        text = json.dumps(value)
        for name in (
            "cryptography",
            "cffi",
            "pycparser",
            "CPython",
            "python-runtime-LICENSE.txt",
        ):
            self.assertIn(name, text)
        self.assertNotIn('"name": "pywin32"', text)
        checked = subprocess.run(
            [
                sys.executable,
                "-S",
                "-m",
                "tools.release_sbom",
                "check",
                "--artifacts",
                str(self.root),
                "--commit",
                COMMIT,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_official_cyclonedx_schema_offline(self) -> None:
        fixtures = Path(__file__).parent / "fixtures/sbom"
        schema = json.loads((fixtures / "bom-1.6.schema.json").read_text())
        spdx = json.loads((fixtures / "spdx.schema.json").read_text())
        registry = Registry[Schema]().with_resource(
            "http://cyclonedx.org/schema/spdx.schema.json", Resource.from_contents(spdx)
        )
        Draft7Validator.check_schema(schema)
        validator = Draft7Validator(schema, registry=registry)
        # jsonschema's overloaded third-party stub leaves the method partial.
        validator.validate(self.write())  # pyright: ignore[reportUnknownMemberType]

    def test_native_missing_metadata_license_or_interpreter_refuses(self) -> None:
        path = self.root / "standalone/mos-0.2.0-rc.1-linux-aarch64.tar.gz"
        with tarfile.open(path) as source:
            originals: dict[str, bytes] = {}
            for member in source:
                stream = source.extractfile(member)
                assert stream is not None
                originals[member.name] = stream.read()
        for removed, reason in (
            ("_internal/cffi-2.1.1.dist-info/METADATA", "missing locked"),
            ("_internal/cffi-2.1.1.dist-info/licenses/LICENSE", "license file"),
            ("_internal/libpython3.12.so.1.0", "interpreter"),
            ("_internal/python-runtime-LICENSE.txt", "CPython license"),
            ("_internal/mos-runtime.json", "runtime inventory"),
        ):
            with self.subTest(removed=removed):
                tar(path, {k: v for k, v in originals.items() if k != removed})
                with self.assertRaisesRegex(ValueError, reason):
                    build_sbom(self.root, COMMIT)
        tar(path, originals)
        for key, value in (
            ("python_version", "3.12.13"),
            ("platform", "linux-x86_64"),
            ("source_commit", "b" * 40),
            ("version", "0.2.0-rc.2"),
        ):
            changed = dict(originals)
            facts = json.loads(changed["_internal/mos-runtime.json"])
            facts[key] = value
            changed["_internal/mos-runtime.json"] = json.dumps(facts).encode()
            tar(path, changed)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "identity"):
                build_sbom(self.root, COMMIT)

    def test_single_critical_component_and_edge_removal_refuse(self) -> None:
        baseline = self.write()
        for field in ("components", "dependencies"):
            changed = dict(baseline)
            changed[field] = cast(list[object], baseline[field])[1:]
            (self.root / "release-sbom.cdx.json").write_text(json.dumps(changed))
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ValueError, "completeness"),
            ):
                validate_sbom(self.root, COMMIT)

    def test_empty_padded_missing_relationship_or_hash_tampering_refuses(self) -> None:
        baseline = self.write()
        updates: tuple[dict[str, object], ...] = (
            {"components": []},
            {"dependencies": []},
            {"components": [{"type": "library", "name": "padding"}]},
            {"serialNumber": "urn:uuid:00000000-0000-0000-0000-000000000000"},
        )
        for update in updates:
            value = dict(baseline)
            value.update(update)
            (self.root / "release-sbom.cdx.json").write_text(json.dumps(value))
            with (
                self.subTest(value=list(value)),
                self.assertRaisesRegex(ValueError, "completeness"),
            ):
                validate_sbom(self.root, COMMIT)
        self.write()
        (self.root / "standalone/install.sh").write_text("changed")
        with self.assertRaisesRegex(ValueError, "completeness"):
            validate_sbom(self.root, COMMIT)

    def test_missing_bootstrap_platform_export_pin_and_wrong_source_or_version_refuse(
        self,
    ) -> None:
        self.write()
        with self.assertRaises(ValueError):
            validate_sbom(self.root, "b" * 40)
        with self.assertRaisesRegex(ValueError, "selected tag"):
            validate_sbom(self.root, COMMIT, "0.2.0")
        export = self.root / "requirements.runtime.txt"
        export.write_text(export.read_text().replace("cffi==2.1.1", "cffi==2.1.0"))
        with self.assertRaisesRegex(ValueError, "identity"):
            build_sbom(self.root, COMMIT)
        (self.root / "standalone/mos-install-linux-aarch64").unlink()
        with self.assertRaisesRegex(ValueError, "platform set"):
            build_sbom(self.root, COMMIT)

    def test_duplicate_json_and_unsafe_export_refuse(self) -> None:
        (self.root / "release-sbom.cdx.json").write_text('{"version":1,"version":1}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_sbom(self.root, COMMIT)
        export = self.root / "requirements.runtime.txt"
        export.write_text("cryptography==50.0.2\n")
        with self.assertRaisesRegex(ValueError, "hash-pinned"):
            runtime_export(export, "macos-aarch64")


class ReaderTests(unittest.TestCase):
    def test_real_framing_contents_not_extracted_or_deserialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture"
            path.write_bytes(
                carchive({"PYZ.pyz": b"not executable marshal", "value": b"payload"})
            )
            result = carchive_inventory(path)
            self.assertEqual(result.python_tag, 312)
            self.assertEqual(
                {f.name for f in result.files}, {"_internal/PYZ.pyz", "_internal/value"}
            )
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)
            raw = path.read_bytes()
            path.write_bytes(raw[:-10])
            with self.assertRaises(ValueError):
                carchive_inventory(path)

    def test_tar_extended_header_is_bounded_before_payload_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bomb.tar.gz"
            header = tarfile.TarInfo("./PaxHeaders/value")
            header.type = tarfile.XHDTYPE
            header.size = 128 * 1024 * 1024
            # No giant allocation is needed to construct or reject this input.
            path.write_bytes(gzip.compress(header.tobuf()))
            with self.assertRaisesRegex(ValueError, "tar read size bound"):
                tar_inventory(path)

    def test_tar_links_traversal_and_duplicate_names_refuse(self) -> None:
        for kind in ("link", "traversal", "duplicate"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "bad.tar.gz"
                with tarfile.open(path, "w:gz") as stream:
                    entry = tarfile.TarInfo(
                        "../escape" if kind == "traversal" else "value"
                    )
                    if kind == "link":
                        entry.type = tarfile.SYMTYPE
                        entry.linkname = "/outside"
                        stream.addfile(entry)
                    else:
                        entry.size = 1
                        stream.addfile(entry, io.BytesIO(b"x"))
                        if kind == "duplicate":
                            stream.addfile(entry, io.BytesIO(b"x"))
                with self.assertRaises(ValueError):
                    tar_inventory(path)

    def test_carchive_expansion_limit_and_unsafe_names_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture"
            path.write_bytes(carchive({"value": b"x" * 100}))
            with (
                patch("tools.sbom_archive.MAX_EXPANDED", 50),
                self.assertRaisesRegex(ValueError, "payload|expansion"),
            ):
                carchive_inventory(path)
            path.write_bytes(carchive({"../escape": b"x"}))
            with self.assertRaisesRegex(ValueError, "unsafe"):
                carchive_inventory(path)

    def test_wheel_directory_is_bounded_before_zipfile_parses_it(self) -> None:
        import zipfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.whl"
            with zipfile.ZipFile(path, "w") as wheel:
                wheel.writestr("a", "x")
                wheel.writestr("b", "x")
            raw = bytearray(path.read_bytes())
            struct.pack_into("<2H", raw, len(raw) - 22 + 8, 1, 1)
            path.write_bytes(raw)
            with (
                patch("tools.sbom_archive.zipfile.ZipFile") as parser,
                self.assertRaisesRegex(ValueError, "count differs"),
            ):
                wheel_inventory(path)
            parser.assert_not_called()

    def test_zip_symlink_and_metadata_resource_bounds_refuse(self) -> None:
        import stat
        import zipfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.whl"
            with zipfile.ZipFile(path, "w") as wheel:
                member = zipfile.ZipInfo("linked")
                member.external_attr = (stat.S_IFLNK | 0o777) << 16
                wheel.writestr(member, "../outside")
            with self.assertRaisesRegex(ValueError, "links"):
                wheel_inventory(path)
            tar(path, {"a.dist-info/METADATA": b"x" * 60})
            with (
                patch("tools.sbom_archive.MAX_METADATA", 50),
                self.assertRaisesRegex(ValueError, "size bound"),
            ):
                tar_inventory(path)
            tar(path, {"a/METADATA": b"x" * 30, "b/METADATA": b"x" * 30})
            with (
                patch("tools.sbom_archive.MAX_RETAINED", 50),
                self.assertRaisesRegex(ValueError, "retained"),
            ):
                tar_inventory(path)

    def test_carchive_corruption_overlap_and_forged_lengths_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad"
            original = carchive({"a": b"payload", "b": b"payload"})
            cookie = COOKIE.unpack(original[-COOKIE.size :])
            base = len(original) - cookie[1]
            toc = base + cookie[2]
            first_length = ENTRY.unpack_from(original, toc)[0]
            # Actual TOC length, member offset, advertised expansion, compression.
            for offset, value in (
                (toc, 1),
                (toc + first_length + 4, 0),
                (toc + 12, 1_000_000),
            ):
                raw = bytearray(original)
                struct.pack_into("!I", raw, offset, value)
                path.write_bytes(raw)
                with self.subTest(offset=offset), self.assertRaises(ValueError):
                    carchive_inventory(path)
            raw = bytearray(original)
            raw[base] ^= 0xFF
            path.write_bytes(raw)
            with self.assertRaises(zlib.error):
                carchive_inventory(path)

    def test_bootstrap_runtime_info_does_not_download_or_install(
        self,
    ) -> None:
        import contextlib
        import platform

        from tools import app_bootstrap

        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["mos-install", "--runtime-info"]),
            patch.object(app_bootstrap, "download") as download,
            patch.object(app_bootstrap, "install") as install,
            patch.object(app_bootstrap, "release_metadata") as metadata,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(app_bootstrap.main(), 0)
        self.assertEqual(
            json.loads(output.getvalue())["python_runtime"],
            {
                "implementation": platform.python_implementation(),
                "version": platform.python_version(),
            },
        )
        download.assert_not_called()
        install.assert_not_called()
        metadata.assert_not_called()

    def test_markers_do_not_execute_and_unknown_vocabulary_refuses(self) -> None:
        values = environment("linux-aarch64")
        self.assertTrue(
            marker_applies(
                "sys_platform == 'linux' and python_version >= '3.12'", values
            )
        )
        self.assertFalse(marker_applies("sys_platform == 'win32'", values))
        self.assertTrue(marker_applies("python_full_version == '3.12.14'", values))
        for marker in (
            "__import__('os').system('false')",
            "unknown == 'x'",
            "python_version < '3.13a1'",
            "True",
        ):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                marker_applies(marker, values)


if __name__ == "__main__":
    unittest.main()
