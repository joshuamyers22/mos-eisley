"""Allowlisted reviewer implementation-binding boundaries."""

import base64
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.reviewer_implementation_binding import (
    AllowlistedImplementationAdapter,
    DirectSymbolBinding,
    ImmutableImplementationBindingRecord,
    ImplementationBindingManifest,
    ImplementationFileDeclaration,
    create_implementation_binding_record,
    decode_implementation_binding_manifest,
    decode_implementation_binding_record,
    verify_implementation_binding_record,
)
from mos_eisley.reviewer_test_package import (
    BlindReviewReference,
    FrozenReviewerTestPackage,
    FrozenTestFile,
    ReferenceKind,
    ReviewerTestPackageManifest,
    ReviewerTestPackagePayload,
    TestCollectionContract,
    TestFileDeclaration,
)


class ReviewerImplementationBindingTests(unittest.TestCase):
    def _package(
        self, source: bytes | None = None, *, helper_source: bytes | None = None
    ) -> FrozenReviewerTestPackage:
        test_source = source or (
            b"from mos_eisley_reviewer_adapter import add\n"
            b"import unittest\n\n"
            b"class TestAdd(unittest.TestCase):\n"
            b"    def test_add(self): self.assertEqual(add(2, 3), 5)\n"
        )
        reference_values: tuple[tuple[ReferenceKind, str, bytes], ...] = (
            ("approved_plan", "plan", b"approved plan"),
            ("creator_approval", "creator", b"creator approval"),
            ("interface", "interface", b"public interface"),
            ("rubric", "rubric", b"review rubric"),
        )
        references = tuple(
            BlindReviewReference(
                reference_id=reference_id,
                kind=kind,
                content_sha256=digest(payload),
                bytes=len(payload),
            )
            for kind, reference_id, payload in reference_values
        )
        test_declaration = TestFileDeclaration(
            path="tests/test_add.py",
            kind="test",
            media_type="text/x-python",
            content_sha256=digest(test_source),
            bytes=len(test_source),
        )
        declarations = [test_declaration]
        frozen_files = [
            FrozenTestFile(
                declaration=test_declaration,
                content_base64=base64.b64encode(test_source).decode("ascii"),
            )
        ]
        if helper_source is not None:
            helper_declaration = TestFileDeclaration(
                path="helpers/reviewer_helper.py",
                kind="fixture",
                media_type="text/x-python",
                content_sha256=digest(helper_source),
                bytes=len(helper_source),
            )
            declarations.append(helper_declaration)
            frozen_files.append(
                FrozenTestFile(
                    declaration=helper_declaration,
                    content_base64=base64.b64encode(helper_source).decode("ascii"),
                )
            )
        declarations.sort(key=lambda item: item.path)
        frozen_files.sort(key=lambda item: item.declaration.path)
        manifest = ReviewerTestPackageManifest(
            package_id="reviewer-add-tests",
            references=references,
            collection=TestCollectionContract(
                start_directory="tests",
                expected_collected_tests=1,
                expected_executed_tests=1,
            ),
            files=tuple(declarations),
        )
        payload = ReviewerTestPackagePayload(
            manifest=manifest,
            files=tuple(frozen_files),
        )
        return FrozenReviewerTestPackage(
            payload=payload,
            payload_sha256=digest(canonical_bytes(payload)),
        )

    def _fixture(
        self, root: Path, *, package: FrozenReviewerTestPackage | None = None
    ) -> tuple[ImplementationBindingManifest, Path, Path, dict[str, Path]]:
        implementation_root = root / "implementation"
        (implementation_root / "src" / "demo").mkdir(parents=True)
        package_path = root / "reviewer" / "package.json"
        package_path.parent.mkdir()
        frozen_package = package or self._package()
        package_path.write_bytes(canonical_bytes(frozen_package))
        sentinel = root / "executed"
        payloads = {
            "pyproject.toml": b"[project]\nname='demo'\n",
            "src/demo/__init__.py": b'"""Demo package."""\n',
            "src/demo/api.py": (
                b"from pathlib import Path\n"
                + f"Path({str(sentinel)!r}).write_text('executed')\n".encode()
                + b"def add(left: int, right: int) -> int:\n"
                + b"    return left + right\n"
            ),
            "uv.lock": b"version = 1\n",
        }
        kinds = {
            "pyproject.toml": "build_metadata",
            "src/demo/__init__.py": "implementation_source",
            "src/demo/api.py": "implementation_source",
            "uv.lock": "dependency_lock",
        }
        media_types = {
            "pyproject.toml": "application/toml",
            "src/demo/__init__.py": "text/x-python",
            "src/demo/api.py": "text/x-python",
            "uv.lock": "text/plain",
        }
        paths: dict[str, Path] = {}
        files: list[ImplementationFileDeclaration] = []
        for relative, payload in payloads.items():
            path = implementation_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            paths[relative] = path
            files.append(
                ImplementationFileDeclaration(
                    path=relative,
                    kind=kinds[relative],  # type: ignore[arg-type]
                    media_type=media_types[relative],  # type: ignore[arg-type]
                    content_sha256=digest(payload),
                    bytes=len(payload),
                )
            )
        manifest = ImplementationBindingManifest(
            binding_id="demo-reviewer-binding",
            source_revision="a" * 40,
            frozen_reviewer_test_package_sha256=frozen_package.frozen_package_sha256,
            source_roots=("src",),
            files=tuple(sorted(files, key=lambda item: item.path)),
            adapter=AllowlistedImplementationAdapter(
                exports=(
                    DirectSymbolBinding(
                        exposed_name="add",
                        target_module="demo.api",
                        target_symbol="add",
                        target_file="src/demo/api.py",
                    ),
                )
            ),
        )
        return manifest, package_path, implementation_root, paths

    def test_binding_is_deterministic_inert_and_replayable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, _ = self._fixture(root)
            first = create_implementation_binding_record(
                manifest, package_path, implementation_root
            )
            second = create_implementation_binding_record(
                manifest, package_path, implementation_root
            )
            self.assertEqual(first, second)
            self.assertFalse((root / "executed").exists())
            self.assertTrue(first.binding_validated)
            self.assertFalse(first.implementation_binding_authorized)
            self.assertFalse(first.test_execution_authorized)
            self.assertFalse(first.repository_write_authorized)
            self.assertEqual(
                decode_implementation_binding_record(canonical_bytes(first)), first
            )
            verify_implementation_binding_record(
                first, package_path, implementation_root
            )
            with self.assertRaises(ValidationError):
                first.payload.manifest.binding_id = "changed"  # type: ignore[misc]

    def test_source_package_and_revision_drift_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, paths = self._fixture(root)
            record = create_implementation_binding_record(
                manifest, package_path, implementation_root
            )
            paths["src/demo/api.py"].write_text("def add(left, right): return 0\n")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_implementation_binding_record(
                    record, package_path, implementation_root
                )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, _ = self._fixture(root)
            package_path.write_bytes(canonical_bytes(self._package()) + b"\n")
            with self.assertRaisesRegex(ValueError, "canonical"):
                create_implementation_binding_record(
                    manifest, package_path, implementation_root
                )
            with self.assertRaises(ValidationError):
                ImplementationBindingManifest.model_validate(
                    {**manifest.model_dump(), "source_revision": "branch-name"}
                )

    def test_complete_inventory_dependency_and_metadata_are_mandatory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, _ = self._fixture(root)
            extra = implementation_root / "src" / "demo" / "hidden.py"
            extra.write_text("VALUE = 1\n")
            with self.assertRaisesRegex(ValueError, "complete source-root inventory"):
                create_implementation_binding_record(
                    manifest, package_path, implementation_root
                )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, _ = self._fixture(root)
            resource = implementation_root / "src" / "demo" / "schema.json"
            resource.write_text('{"type":"object"}\n')
            with self.assertRaisesRegex(ValueError, "complete source-root inventory"):
                create_implementation_binding_record(
                    manifest, package_path, implementation_root
                )
            resource_payload = resource.read_bytes()
            declaration = ImplementationFileDeclaration(
                path="src/demo/schema.json",
                kind="implementation_resource",
                media_type="application/json",
                content_sha256=digest(resource_payload),
                bytes=len(resource_payload),
            )
            complete = ImplementationBindingManifest.model_validate(
                {
                    **manifest.model_dump(),
                    "files": tuple(
                        sorted(
                            (*manifest.files, declaration), key=lambda item: item.path
                        )
                    ),
                }
            )
            create_implementation_binding_record(
                complete, package_path, implementation_root
            )

            raw = manifest.model_dump()
            for omitted_kind in ("dependency_lock", "build_metadata"):
                files = tuple(
                    item for item in manifest.files if item.kind != omitted_kind
                )
                with (
                    self.subTest(kind=omitted_kind),
                    self.assertRaises(ValidationError),
                ):
                    ImplementationBindingManifest.model_validate(
                        {**raw, "files": files}
                    )
            with self.assertRaises(ValidationError):
                ImplementationBindingManifest.model_validate(
                    {**raw, "files": tuple(reversed(manifest.files))}
                )
            with self.assertRaises(ValidationError):
                ImplementationBindingManifest.model_validate(
                    {**raw, "source_roots": ("src", "src/demo")}
                )

    def test_adapter_is_exact_direct_and_structurally_non_mutating(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, _ = self._fixture(root)
            raw = manifest.model_dump()
            adapter = manifest.adapter.model_dump()
            for update in (
                {"wrapper_code_authorized": True},
                {"monkeypatch_authorized": True},
                {"result_substitution_authorized": True},
                {"exception_translation_authorized": True},
                {"discovery_override_authorized": True},
                {"test_result_interception_authorized": True},
            ):
                with self.subTest(update=update), self.assertRaises(ValidationError):
                    AllowlistedImplementationAdapter.model_validate(
                        {**adapter, **update}
                    )

            export = manifest.adapter.exports[0]
            for bad_export in (
                export.model_copy(update={"target_module": "api"}),
                export.model_copy(update={"target_file": "src/demo/missing.py"}),
            ):
                with (
                    self.subTest(export=bad_export),
                    self.assertRaises(ValidationError),
                ):
                    ImplementationBindingManifest.model_validate(
                        {
                            **raw,
                            "adapter": {**adapter, "exports": (bad_export,)},
                        }
                    )

            missing = export.model_copy(update={"target_symbol": "subtract"})
            missing_manifest = ImplementationBindingManifest.model_validate(
                {**raw, "adapter": {**adapter, "exports": (missing,)}}
            )
            with self.assertRaisesRegex(ValueError, "defined directly"):
                create_implementation_binding_record(
                    missing_manifest, package_path, implementation_root
                )

    def test_reviewer_must_use_exact_adapter_surface(self) -> None:
        cases = (
            b"from demo.api import add\n",
            b"import mos_eisley_reviewer_adapter\n",
            b"from mos_eisley_reviewer_adapter import *\n",
            b"from mos_eisley_reviewer_adapter import subtract\n",
        )
        for index, source in enumerate(cases):
            with self.subTest(index=index), TemporaryDirectory() as directory:
                root = Path(directory)
                package = self._package(source)
                manifest, package_path, implementation_root, _ = self._fixture(
                    root, package=package
                )
                with self.assertRaisesRegex(ValueError, "reviewer|adapter"):
                    create_implementation_binding_record(
                        manifest, package_path, implementation_root
                    )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package(helper_source=b"from demo.api import add\n")
            manifest, package_path, implementation_root, _ = self._fixture(
                root, package=package
            )
            with self.assertRaisesRegex(ValueError, "import implementation directly"):
                create_implementation_binding_record(
                    manifest, package_path, implementation_root
                )

    def test_aliases_symlinks_special_files_and_package_race_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, paths = self._fixture(root)
            os.link(paths["uv.lock"], implementation_root / "duplicate.lock")
            duplicate = ImplementationFileDeclaration(
                path="duplicate.lock",
                kind="dependency_lock",
                media_type="text/plain",
                content_sha256=digest(paths["uv.lock"].read_bytes()),
                bytes=paths["uv.lock"].stat().st_size,
            )
            files = tuple(
                sorted((*manifest.files, duplicate), key=lambda item: item.path)
            )
            aliased = ImplementationBindingManifest.model_validate(
                {**manifest.model_dump(), "files": files}
            )
            with self.assertRaisesRegex(ValueError, "filesystem aliases"):
                create_implementation_binding_record(
                    aliased, package_path, implementation_root
                )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, paths = self._fixture(root)
            paths["src/demo/api.py"].unlink()
            paths["src/demo/api.py"].symlink_to(paths["src/demo/__init__.py"])
            with self.assertRaisesRegex(ValueError, "symlinks"):
                create_implementation_binding_record(
                    manifest, package_path, implementation_root
                )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, _ = self._fixture(root)
            bytecode = implementation_root / "src" / "demo" / "__pycache__"
            bytecode.mkdir()
            (bytecode / "api.pyc").write_bytes(b"generated")
            with self.assertRaisesRegex(ValueError, "generated bytecode"):
                create_implementation_binding_record(
                    manifest, package_path, implementation_root
                )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, paths = self._fixture(root)
            paths["uv.lock"].unlink()
            os.mkfifo(paths["uv.lock"])
            with self.assertRaisesRegex(ValueError, "regular file"):
                create_implementation_binding_record(
                    manifest, package_path, implementation_root
                )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, _ = self._fixture(root)
            original_package = package_path.read_bytes()
            reads = 0

            def staged_package_read(path: Path, limit: int) -> bytes:
                nonlocal reads
                self.assertEqual(path, package_path)
                self.assertGreater(limit, len(original_package))
                reads += 1
                return original_package if reads == 1 else original_package + b"\n"

            with (
                patch(
                    "mos_eisley.reviewer_implementation_binding._read_stable_file",
                    side_effect=staged_package_read,
                ),
                self.assertRaisesRegex(ValueError, "changed during binding"),
            ):
                create_implementation_binding_record(
                    manifest, package_path, implementation_root
                )

    def test_cli_creates_private_record_reverifies_and_refuses_overwrite(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, _ = self._fixture(root)
            manifest_path = root / "inputs" / "manifest.json"
            manifest_path.parent.mkdir()
            manifest_path.write_bytes(canonical_bytes(manifest))
            output = root / "records" / "binding.json"
            arguments = [
                "g4-bind-reviewer-implementation",
                "--manifest",
                str(manifest_path),
                "--reviewer-package",
                str(package_path),
                "--implementation-root",
                str(implementation_root),
                "--output",
                str(output),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(arguments), 0)
            event = json.loads(stdout.getvalue())
            self.assertEqual(
                event["type"], "g4.reviewer_implementation_binding.created"
            )
            self.assertFalse(event["test_execution_authorized"])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)

            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(
                    main(
                        [
                            "g4-verify-reviewer-implementation-binding",
                            "--binding",
                            str(output),
                            "--reviewer-package",
                            str(package_path),
                            "--implementation-root",
                            str(implementation_root),
                        ]
                    ),
                    0,
                )
            self.assertEqual(
                json.loads(stdout.getvalue())["type"],
                "g4.reviewer_implementation_binding.verified",
            )

    def test_cli_rejects_overlap_and_decoders_reject_tampering(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, package_path, implementation_root, _ = self._fixture(root)
            manifest_path = root / "manifest.json"
            manifest_path.write_bytes(canonical_bytes(manifest))
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "g4-bind-reviewer-implementation",
                            "--manifest",
                            str(manifest_path),
                            "--reviewer-package",
                            str(package_path),
                            "--implementation-root",
                            str(implementation_root),
                            "--output",
                            str(implementation_root / "binding.json"),
                        ]
                    ),
                    2,
                )
            record = create_implementation_binding_record(
                manifest, package_path, implementation_root
            )
            tampered = record.model_dump()
            tampered["payload_sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                decode_implementation_binding_record(json.dumps(tampered).encode())
            with self.assertRaisesRegex(ValueError, "invalid implementation-binding"):
                decode_implementation_binding_record(canonical_bytes(record) + b"\n")
            with self.assertRaisesRegex(ValueError, "invalid implementation-binding"):
                decode_implementation_binding_manifest(
                    b'{"binding_id":"one","binding_id":"two"}'
                )
            with self.assertRaises(ValidationError):
                ImmutableImplementationBindingRecord.model_validate(
                    {**record.model_dump(), "test_execution_authorized": True}
                )


if __name__ == "__main__":
    unittest.main()
