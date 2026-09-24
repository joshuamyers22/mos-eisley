"""Immutable blind reviewer-test package and freezer boundaries."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.reviewer_test_package import (
    BlindReviewReference,
    DeclaredTestMarker,
    FileKind,
    FrozenReviewerTestPackage,
    MediaType,
    ReferenceKind,
    ReviewerTestPackageManifest,
    TestCollectionContract,
    TestFileDeclaration,
    decode_frozen_reviewer_test_package,
    decode_reviewer_test_manifest,
    freeze_reviewer_test_package,
)


class ReviewerTestPackageTests(TestCase):
    def _fixture(
        self,
        root: Path,
        *,
        test_source: bytes | None = None,
        marker: DeclaredTestMarker | None = None,
    ) -> tuple[
        ReviewerTestPackageManifest,
        Path,
        tuple[Path, ...],
        dict[str, Path],
    ]:
        references_root = root / "references"
        package_root = root / "package"
        references_root.mkdir()
        (package_root / "fixtures").mkdir(parents=True)
        (package_root / "oracles").mkdir()
        (package_root / "tests").mkdir()

        reference_values: list[tuple[ReferenceKind, str, bytes]] = [
            ("approved_plan", "plan", b"approved G4 plan"),
            ("creator_approval", "creator", b"Joshua Myers approves derivation"),
            ("interface", "public-interface", b"public interface v1"),
            ("rubric", "rubric", b"reviewer rubric v1"),
        ]
        if marker is not None:
            reference_values.append(
                ("marker_approval", "marker-approval", b"approved skip marker")
            )
        reference_values.sort(key=lambda item: (item[0], item[1]))
        references: list[BlindReviewReference] = []
        reference_paths: list[Path] = []
        for kind, reference_id, payload in reference_values:
            path = references_root / reference_id
            path.write_bytes(payload)
            references.append(
                BlindReviewReference(
                    reference_id=reference_id,
                    kind=kind,
                    content_sha256=digest(payload),
                    bytes=len(payload),
                )
            )
            reference_paths.append(path)

        source = test_source or (
            b"import unittest\n\n"
            b"class TestBehavior(unittest.TestCase):\n"
            b"    def test_expected(self):\n"
            b"        self.assertEqual(2 + 2, 4)\n"
        )
        payloads = {
            "fixtures/case.json": b'{"input":2}\n',
            "oracles/expected.json": b'{"result":4}\n',
            "tests/test_behavior.py": source,
        }
        kinds: dict[str, FileKind] = {
            "fixtures/case.json": "fixture",
            "oracles/expected.json": "oracle",
            "tests/test_behavior.py": "test",
        }
        media_types: dict[str, MediaType] = {
            "fixtures/case.json": "application/json",
            "oracles/expected.json": "application/json",
            "tests/test_behavior.py": "text/x-python",
        }
        paths: dict[str, Path] = {}
        declarations: list[TestFileDeclaration] = []
        for relative, payload in payloads.items():
            path = package_root / relative
            path.write_bytes(payload)
            paths[relative] = path
            declarations.append(
                TestFileDeclaration(
                    path=relative,
                    kind=kinds[relative],
                    media_type=media_types[relative],
                    content_sha256=digest(payload),
                    bytes=len(payload),
                )
            )

        manifest = ReviewerTestPackageManifest(
            package_id="blind-reviewer-tests-v1",
            references=tuple(references),
            collection=TestCollectionContract(
                start_directory="tests",
                top_level_directory=".",
                expected_collected_tests=2 if marker else 1,
                expected_executed_tests=1,
                expected_skipped_tests=1 if marker else 0,
            ),
            files=tuple(declarations),
            declared_markers=(marker,) if marker else (),
        )
        return manifest, package_root, tuple(reference_paths), paths

    def test_freeze_is_deterministic_self_contained_and_without_authority(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, paths = self._fixture(root)
            sentinel = root / "executed"
            source = (
                "from pathlib import Path\n"
                f"Path({str(sentinel)!r}).write_text('bad')\n"
                "import unittest\n"
                "class TestBehavior(unittest.TestCase):\n"
                "    def test_expected(self): self.assertTrue(True)\n"
            ).encode()
            test_path = paths["tests/test_behavior.py"]
            test_path.write_bytes(source)
            updated_files = tuple(
                item.model_copy(
                    update={
                        "content_sha256": digest(source),
                        "bytes": len(source),
                    }
                )
                if item.path == "tests/test_behavior.py"
                else item
                for item in manifest.files
            )
            manifest = ReviewerTestPackageManifest.model_validate(
                {**manifest.model_dump(), "files": updated_files}
            )

            first = freeze_reviewer_test_package(manifest, package_root, references)
            second = freeze_reviewer_test_package(manifest, package_root, references)
            self.assertEqual(first, second)
            self.assertFalse(sentinel.exists())
            self.assertFalse(first.test_execution_authorized)
            self.assertFalse(first.implementation_binding_authorized)
            self.assertFalse(first.correction_authorized)
            self.assertFalse(first.acceptance_authorized)
            self.assertEqual(
                decode_frozen_reviewer_test_package(canonical_bytes(first)), first
            )
            embedded = {
                item.declaration.path: item.content for item in first.payload.files
            }
            self.assertEqual(embedded["tests/test_behavior.py"], source)
            with self.assertRaises(ValidationError):
                first.payload.files[0].declaration.path = "changed"  # type: ignore[misc]

    def test_changed_file_or_reference_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, paths = self._fixture(root)
            paths["oracles/expected.json"].write_text('{"result":5}\n')
            with self.assertRaisesRegex(ValueError, "differs"):
                freeze_reviewer_test_package(manifest, package_root, references)
            paths["oracles/expected.json"].write_bytes(b'{"result":4}\n')
            references[0].write_text("changed plan")
            with self.assertRaisesRegex(ValueError, "reference differs"):
                freeze_reviewer_test_package(manifest, package_root, references)

    def test_manifest_rejects_noncanonical_and_vacuous_declarations(self) -> None:
        with TemporaryDirectory() as directory:
            manifest, _, _, _ = self._fixture(Path(directory))
            raw = manifest.model_dump()
            cases = (
                {**raw, "files": tuple(reversed(manifest.files))},
                {**raw, "files": (*manifest.files, manifest.files[-1])},
                {
                    **raw,
                    "files": tuple(
                        sorted(
                            (
                                *manifest.files,
                                manifest.files[-1].model_copy(
                                    update={"path": "outside/test_extra.py"}
                                ),
                            ),
                            key=lambda item: item.path,
                        )
                    ),
                },
                {
                    **raw,
                    "collection": {
                        **manifest.collection.model_dump(),
                        "pattern": "missing*.py",
                    },
                },
                {
                    **raw,
                    "collection": {
                        **manifest.collection.model_dump(),
                        "expected_executed_tests": 0,
                        "expected_skipped_tests": 1,
                    },
                },
            )
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValidationError):
                    ReviewerTestPackageManifest.model_validate(case)
            file_raw = manifest.files[0].model_dump()
            for bad_path in ("../escape", "/absolute", "a\\b", "a/../b", "."):
                with self.subTest(path=bad_path), self.assertRaises(ValidationError):
                    TestFileDeclaration.model_validate({**file_raw, "path": bad_path})

    def test_filesystem_aliases_and_special_inputs_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, paths = self._fixture(root)
            target = paths["fixtures/case.json"]
            alias = package_root / "fixtures" / "alias.json"
            os.link(target, alias)
            declaration = TestFileDeclaration(
                path="fixtures/alias.json",
                kind="fixture",
                media_type="application/json",
                content_sha256=digest(alias.read_bytes()),
                bytes=alias.stat().st_size,
            )
            files = tuple(
                sorted((*manifest.files, declaration), key=lambda item: item.path)
            )
            aliased = ReviewerTestPackageManifest.model_validate(
                {**manifest.model_dump(), "files": files}
            )
            with self.assertRaisesRegex(ValueError, "filesystem aliases"):
                freeze_reviewer_test_package(aliased, package_root, references)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, paths = self._fixture(root)
            target = paths["fixtures/case.json"]
            target.unlink()
            target.symlink_to(paths["oracles/expected.json"])
            with self.assertRaises(OSError):
                freeze_reviewer_test_package(manifest, package_root, references)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, paths = self._fixture(root)
            target = paths["fixtures/case.json"]
            target.unlink()
            os.mkfifo(target)
            with self.assertRaisesRegex(ValueError, "regular file"):
                freeze_reviewer_test_package(manifest, package_root, references)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, paths = self._fixture(root)
            fixture = paths["fixtures/case.json"]
            fixture.unlink()
            fixture.parent.rmdir()
            (package_root / "fixtures").symlink_to(package_root / "oracles")
            with self.assertRaises(OSError):
                freeze_reviewer_test_package(manifest, package_root, references)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, _ = self._fixture(root)
            package_alias = root / "package-alias"
            package_alias.symlink_to(package_root, target_is_directory=True)
            with self.assertRaises(OSError):
                freeze_reviewer_test_package(manifest, package_alias, references)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, _ = self._fixture(root)
            reference_alias = root / "reference-alias"
            reference_alias.symlink_to(references[0])
            with self.assertRaises(OSError):
                freeze_reviewer_test_package(
                    manifest,
                    package_root,
                    (reference_alias, *references[1:]),
                )

    def test_skip_marker_requires_exact_declaration_and_approval(self) -> None:
        source = (
            b"import unittest\n\n"
            b"@unittest.skip('approved reason')\n"
            b"class TestBehavior(unittest.TestCase):\n"
            b"    def test_expected(self): self.fail()\n"
            b"class TestControl(unittest.TestCase):\n"
            b"    def test_control(self): self.assertTrue(True)\n"
        )
        marker = DeclaredTestMarker(
            path="tests/test_behavior.py",
            line=3,
            kind="skip",
            reason="Approved because this interface is unavailable.",
            approval_reference_id="marker-approval",
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, _ = self._fixture(
                root, test_source=source, marker=marker
            )
            package = freeze_reviewer_test_package(manifest, package_root, references)
            self.assertEqual(package.payload.manifest.declared_markers, (marker,))

            without_marker = ReviewerTestPackageManifest.model_validate(
                {
                    **manifest.model_dump(),
                    "references": tuple(
                        item
                        for item in manifest.references
                        if item.kind != "marker_approval"
                    ),
                    "declared_markers": (),
                }
            )
            with self.assertRaisesRegex(ValueError, "detected skip/xfail"):
                freeze_reviewer_test_package(
                    without_marker,
                    package_root,
                    tuple(
                        path
                        for reference, path in zip(
                            manifest.references, references, strict=True
                        )
                        if reference.kind != "marker_approval"
                    ),
                )
            wrong_line = marker.model_copy(update={"line": 4})
            stale = ReviewerTestPackageManifest.model_validate(
                {**manifest.model_dump(), "declared_markers": (wrong_line,)}
            )
            with self.assertRaisesRegex(ValueError, "detected skip/xfail"):
                freeze_reviewer_test_package(stale, package_root, references)

            second_marker = marker.model_copy(update={"line": 5, "kind": "xfail"})
            with self.assertRaisesRegex(ValidationError, "marker approvals"):
                ReviewerTestPackageManifest.model_validate(
                    {
                        **manifest.model_dump(),
                        "declared_markers": (marker, second_marker),
                    }
                )

    def test_invalid_python_and_tampered_frozen_package_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, paths = self._fixture(root)
            invalid = b"def broken(:\n"
            paths["tests/test_behavior.py"].write_bytes(invalid)
            files = tuple(
                item.model_copy(
                    update={"content_sha256": digest(invalid), "bytes": len(invalid)}
                )
                if item.kind == "test"
                else item
                for item in manifest.files
            )
            invalid_manifest = ReviewerTestPackageManifest.model_validate(
                {**manifest.model_dump(), "files": files}
            )
            with self.assertRaisesRegex(ValueError, "invalid Python"):
                freeze_reviewer_test_package(invalid_manifest, package_root, references)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, _ = self._fixture(root)
            package = freeze_reviewer_test_package(manifest, package_root, references)
            tampered = package.model_dump()
            tampered["payload_sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                decode_frozen_reviewer_test_package(json.dumps(tampered).encode())
            duplicate = canonical_bytes(package).replace(
                b'{"acceptance_authorized":false,',
                (b'{"acceptance_authorized":false,"acceptance_authorized":false,'),
                1,
            )
            with self.assertRaises(ValueError):
                decode_frozen_reviewer_test_package(duplicate)

    def test_cli_freezes_privately_and_replay_verifies_without_execution(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, _ = self._fixture(root)
            manifest_path = root / "manifest.json"
            output_path = root / "frozen" / "package.json"
            manifest_path.write_bytes(canonical_bytes(manifest))
            arguments = [
                "g4-freeze-reviewer-test-package",
                "--manifest",
                str(manifest_path),
                "--package-root",
                str(package_root),
            ]
            for reference in references:
                arguments.extend(("--reference", str(reference)))
            arguments.extend(("--output", str(output_path)))
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(arguments), 0)
            event = json.loads(stdout.getvalue())
            self.assertEqual(event["type"], "g4.reviewer_test_package.frozen")
            self.assertFalse(event["test_execution_authorized"])
            self.assertFalse(event["implementation_binding_authorized"])
            self.assertEqual(output_path.stat().st_mode & 0o777, 0o600)

            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(
                    main(
                        [
                            "g4-verify-reviewer-test-package",
                            "--package",
                            str(output_path),
                        ]
                    ),
                    0,
                )
            self.assertEqual(
                json.loads(stdout.getvalue())["type"],
                "g4.reviewer_test_package.verified",
            )
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)

    def test_cli_rejects_input_output_overlap_and_invalid_json(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_root, references, _ = self._fixture(root)
            manifest_path = root / "manifest.json"
            manifest_path.write_bytes(canonical_bytes(manifest))
            arguments = [
                "g4-freeze-reviewer-test-package",
                "--manifest",
                str(manifest_path),
                "--package-root",
                str(package_root),
            ]
            for reference in references:
                arguments.extend(("--reference", str(reference)))
            arguments.extend(("--output", str(package_root / "frozen.json")))
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)

            with self.assertRaisesRegex(ValueError, "invalid reviewer-test"):
                decode_reviewer_test_manifest(b'{"package_id":"x","package_id":"y"}')

    def test_contract_rejects_unknown_fields_and_mutable_authority(self) -> None:
        with TemporaryDirectory() as directory:
            manifest, _, _, _ = self._fixture(Path(directory))
            for update in (
                {"unknown": True},
                {"implementation_inspected": True},
                {"test_execution_authorized": True},
                {"implementation_binding_authorized": True},
                {"repository_write_authorized": True},
                {"vcs_authorized": True},
                {"network_authorized": True},
                {"credential_access_authorized": True},
                {"provider_dispatch_authorized": True},
            ):
                with self.subTest(update=update), self.assertRaises(ValidationError):
                    ReviewerTestPackageManifest.model_validate(
                        {**manifest.model_dump(), **update}
                    )

            package_raw = {
                "payload": {
                    "manifest": manifest.model_dump(),
                    "files": (),
                },
                "payload_sha256": "0" * 64,
            }
            with self.assertRaises(ValidationError):
                FrozenReviewerTestPackage.model_validate(package_raw)
