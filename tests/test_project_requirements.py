import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import patch

from mos_eisley.conversation_memory_registry import MappedDirectory
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.project_guidance_storage import publish_file
from mos_eisley.project_requirement_store import (
    RequirementStore,
    requirement_history_name,
    requirement_name,
)
from mos_eisley.project_requirements import (
    INPUT_BYTES,
    SOURCE_BYTES,
    SavedRequirements,
    decode_selection,
    inspect_requirements,
)


class RequirementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "private"
        self.store = RequirementStore(self.storage)
        self.input = self.base / "selection.json"
        self.source = self.base / "brief.md"
        self.text = "Retain project data locally."
        self.source.write_text("# Brief\n\n" + self.text + "\n")
        self.selection: dict[str, object] = {
            "review_rationale": "Accepted the project's retention requirement.",
            "sources": [
                {
                    "id": "brief",
                    "kind": "brief",
                    "content_sha256": digest(self.source.read_bytes()),
                }
            ],
            "requirements": [
                {
                    "id": "REQ1",
                    "source_id": "brief",
                    "text": self.text,
                    "applies_when": "Storing project data",
                    "rationale": "Project ownership",
                    "checks": ["Verify storage stays local"],
                }
            ],
        }
        self.write_selection()

    def write_selection(self) -> None:
        self.input.write_text(json.dumps(self.selection))

    def apply(self, *, clear: bool = False) -> dict[str, object]:
        path = None if clear else self.input
        sources = () if clear else (self.source,)
        preview = self.store.change(self.workspace, path, sources)
        return self.store.change(
            self.workspace,
            path,
            sources,
            expected_sha256=cast(str, preview["preview_sha256"]),
        )

    def current_path(self) -> Path:
        return self.storage / requirement_name(MappedDirectory.inspect(self.workspace))

    def test_preview_is_read_only_and_acceptance_pins_exact_provenance(self) -> None:
        self.assertFalse(self.store.show(self.workspace)["accepted_current"])
        preview = self.store.change(self.workspace, self.input, (self.source,))
        self.assertFalse(preview["applied"])
        self.assertFalse(self.storage.exists())
        result = self.apply()
        saved = SavedRequirements.model_validate_json(json.dumps(result["after"]))
        assert saved.proposal is not None
        self.assertEqual(saved.proposal.selection_json, self.input.read_text())
        self.assertEqual(saved.proposal.sources[0].text, self.source.read_text())
        self.assertEqual(saved.proposal.sources[0].path, str(self.source))
        self.assertEqual(saved.owner_uid, os.getuid())
        self.assertFalse(saved.context_materialized)
        self.assertFalse(saved.execution_authorized)
        self.assertTrue(self.store.show(self.workspace)["accepted_current"])
        self.assertEqual(self.storage.stat().st_mode & 0o777, 0o700)
        for path in self.storage.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_multiple_explicit_sources_and_unique_exact_spans(self) -> None:
        adr = self.base / "adr.md"
        adr.write_text("Use batch execution.\n")
        sources = cast(list[dict[str, object]], self.selection["sources"])
        sources.append(
            {
                "id": "decision",
                "kind": "adr",
                "content_sha256": digest(adr.read_bytes()),
            }
        )
        requirements = cast(list[dict[str, object]], self.selection["requirements"])
        requirements.append(
            {
                **requirements[0],
                "id": "REQ2",
                "source_id": "decision",
                "text": "Use batch execution.",
            }
        )
        self.write_selection()
        proposal = inspect_requirements(self.input, (self.source, adr))
        self.assertEqual(len(proposal.sources), 2)
        with self.assertRaises(ValueError):
            inspect_requirements(self.input, (adr, self.source))
        with self.assertRaises(ValueError):
            inspect_requirements(self.input, (self.source,))
        self.source.write_text(self.text + "\n" + self.text)
        sources[0]["content_sha256"] = digest(self.source.read_bytes())
        self.write_selection()
        with self.assertRaisesRegex(ValueError, "exact source span"):
            inspect_requirements(self.input, (self.source, adr))
        requirements[0]["text"] = "Missing requirement"
        self.write_selection()
        with self.assertRaisesRegex(ValueError, "exact source span"):
            inspect_requirements(self.input, (self.source, adr))

    def test_replace_clear_and_historical_inspection_survive_deleted_sources(
        self,
    ) -> None:
        first = self.apply()
        self.selection["review_rationale"] = "Re-reviewed the accepted requirement."
        self.write_selection()
        second = self.apply()
        self.assertEqual(
            SavedRequirements.model_validate_json(json.dumps(second["after"])).revision,
            2,
        )
        self.source.unlink()
        self.input.unlink()
        self.assertTrue(self.store.show(self.workspace)["accepted_current"])
        historical = self.store.show(
            self.workspace, snapshot_sha256=cast(str, first["snapshot_sha256"])
        )
        self.assertTrue(historical["historical_snapshot"])
        self.assertFalse(historical["accepted_current"])
        cleared = self.apply(clear=True)
        self.assertEqual(
            SavedRequirements.model_validate_json(
                json.dumps(cleared["after"])
            ).revision,
            3,
        )
        self.assertFalse(self.store.show(self.workspace)["accepted_current"])
        with self.assertRaises(ValueError):
            self.apply(clear=True)

    def test_stale_source_input_path_and_review_fail_before_bootstrap(self) -> None:
        preview = self.store.change(self.workspace, self.input, (self.source,))
        sha = cast(str, preview["preview_sha256"])
        self.input.write_text(self.input.read_text() + " ")
        with self.assertRaises(ValueError):
            self.store.change(
                self.workspace, self.input, (self.source,), expected_sha256=sha
            )
        self.assertFalse(self.storage.exists())
        self.write_selection()
        alternate = self.base / "alternate.md"
        alternate.write_bytes(self.source.read_bytes())
        with self.assertRaises(ValueError):
            self.store.change(
                self.workspace, self.input, (alternate,), expected_sha256=sha
            )
        self.source.write_text("Changed source")
        with self.assertRaises(ValueError):
            self.store.change(
                self.workspace, self.input, (self.source,), expected_sha256=sha
            )
        self.assertFalse(self.storage.exists())

    def test_clear_reapply_does_not_allow_replayed_review(self) -> None:
        original = self.store.change(self.workspace, self.input, (self.source,))
        self.apply()
        self.apply(clear=True)
        with self.assertRaises(ValueError):
            self.store.change(
                self.workspace,
                self.input,
                (self.source,),
                expected_sha256=cast(str, original["preview_sha256"]),
            )
        self.assertEqual(
            SavedRequirements.model_validate_json(
                json.dumps(self.apply()["after"])
            ).revision,
            3,
        )
        with self.assertRaisesRegex(ValueError, "no changes"):
            self.apply()

    def test_project_owner_and_nested_directory_isolation(self) -> None:
        first = self.apply()
        for workspace in (self.base / "another", self.workspace / "nested"):
            workspace.mkdir()
            self.assertFalse(self.store.show(workspace)["accepted_current"])
            with self.assertRaises(ValueError):
                self.store.show(
                    workspace, snapshot_sha256=cast(str, first["snapshot_sha256"])
                )
        with (
            patch(
                "mos_eisley.project_requirement_store.os.getuid",
                return_value=os.getuid() + 1,
            ),
            self.assertRaises((ValueError, PermissionError)),
        ):
            self.store.show(self.workspace)
        self.workspace.rename(self.base / "old-project")
        self.workspace.mkdir()
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)

    def test_reject_authority_duplicate_keys_ids_and_bad_content(self) -> None:
        raw = self.input.read_bytes()
        for key, value in (
            ("execution_authorized", True),
            ("kind", "mandatory"),
            ("review_rationale", " "),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                decode_selection(json.dumps({**self.selection, key: value}).encode())
        with self.assertRaises(ValueError):
            decode_selection(raw[:-1] + b', "review_rationale":"duplicate"}')
        with self.assertRaises(ValueError):
            decode_selection(b"\xff")
        requirements = cast(list[dict[str, object]], self.selection["requirements"])
        requirements.append(dict(requirements[0]))
        self.write_selection()
        with self.assertRaises(ValueError):
            decode_selection(self.input.read_bytes())
        requirements.pop()
        requirements[0]["source_id"] = "missing"
        self.write_selection()
        with self.assertRaises(ValueError):
            decode_selection(self.input.read_bytes())

    def test_input_and_source_byte_bounds_and_symlinks(self) -> None:
        raw = self.input.read_bytes()
        self.input.write_bytes(raw + b" " * (INPUT_BYTES - len(raw)))
        inspect_requirements(self.input, (self.source,))
        self.input.write_bytes(self.input.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            inspect_requirements(self.input, (self.source,))
        self.write_selection()
        self.source.write_bytes(b"x" * (SOURCE_BYTES + 1))
        with self.assertRaises(ValueError):
            inspect_requirements(self.input, (self.source,))
        self.source.unlink()
        self.source.symlink_to(self.input)
        with self.assertRaises(OSError):
            inspect_requirements(self.input, (self.source,))
        link = self.base / "linked.json"
        link.symlink_to(self.input)
        with self.assertRaises(OSError):
            inspect_requirements(link, (self.source,))

    def test_corruption_missing_history_and_unsafe_private_files_fail_closed(
        self,
    ) -> None:
        receipt = self.apply()
        original = self.current_path().read_bytes()
        self.current_path().write_bytes(original + b" ")
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        self.current_path().write_bytes(original)
        self.current_path().chmod(0o644)
        with self.assertRaises((ValueError, PermissionError)):
            self.store.show(self.workspace)
        self.current_path().chmod(0o600)
        history = self.storage / requirement_history_name(
            cast(str, receipt["snapshot_sha256"])
        )
        history.unlink()
        with self.assertRaises(ValueError):
            self.store.show(self.workspace)
        with self.assertRaises(ValueError):
            self.store.show(self.workspace, snapshot_sha256="../../escape")

    def test_mid_publication_mutation_and_failure_do_not_accept_candidate(self) -> None:
        preview = self.store.change(self.workspace, self.input, (self.source,))

        def mutate(
            root: int,
            name: str,
            payload: bytes,
            verify: Callable[[], None],
            *,
            immutable: bool = False,
        ) -> None:
            self.input.write_text(self.input.read_text() + " ")
            publish_file(root, name, payload, verify, immutable=immutable)

        with (
            patch(
                "mos_eisley.project_requirement_store.publish_file", side_effect=mutate
            ),
            self.assertRaises(ValueError),
        ):
            self.store.change(
                self.workspace,
                self.input,
                (self.source,),
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertFalse(self.current_path().exists())
        self.assertFalse(self.store.show(self.workspace)["accepted_current"])
        preview = self.store.change(self.workspace, self.input, (self.source,))
        with (
            patch(
                "mos_eisley.project_requirement_store.publish_file",
                side_effect=OSError("injected failure"),
            ),
            self.assertRaises(OSError),
        ):
            self.store.change(
                self.workspace,
                self.input,
                (self.source,),
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertFalse(self.current_path().exists())

    def test_retained_provenance_tampering_is_rejected(self) -> None:
        receipt = self.apply()
        saved = SavedRequirements.model_validate_json(json.dumps(receipt["after"]))
        data = json.loads(canonical_bytes(saved))
        data["proposal"]["sources"][0]["text"] = "Forged source"
        with self.assertRaises(ValueError):
            SavedRequirements.model_validate_json(json.dumps(data))

        data = json.loads(canonical_bytes(saved))
        data["context_materialized"] = True
        with self.assertRaises(ValueError):
            SavedRequirements.model_validate_json(json.dumps(data))

    def test_aggregate_source_limit_and_utf8_are_byte_bounded(self) -> None:
        sources: list[dict[str, object]] = []
        requirements: list[dict[str, object]] = []
        paths: list[Path] = []
        for index in range(3):
            path = self.base / f"source-{index}.md"
            text = f"Requirement {index}."
            path.write_text(text + "x" * (SOURCE_BYTES - len(text)))
            sources.append(
                {
                    "id": f"source{index}",
                    "kind": "adr",
                    "content_sha256": digest(path.read_bytes()),
                }
            )
            requirements.append(
                {
                    "id": f"REQ{index}",
                    "source_id": f"source{index}",
                    "text": text,
                    "applies_when": "Always",
                    "rationale": "Reviewed",
                    "checks": ["Check result"],
                }
            )
            paths.append(path)
        self.selection["sources"] = sources[:2]
        self.selection["requirements"] = requirements[:2]
        self.write_selection()
        inspect_requirements(self.input, tuple(paths[:2]))
        self.selection["sources"] = sources
        self.selection["requirements"] = requirements
        self.write_selection()
        with self.assertRaisesRegex(ValueError, "128 KiB"):
            inspect_requirements(self.input, tuple(paths))
        paths[0].write_text("é" * (SOURCE_BYTES // 2 + 1))
        with self.assertRaises(ValueError):
            inspect_requirements(self.input, tuple(paths))

    def test_current_publication_failure_preserves_previous_acceptance(self) -> None:
        first = self.apply()
        self.selection["review_rationale"] = "Updated rationale."
        self.write_selection()
        preview = self.store.change(self.workspace, self.input, (self.source,))

        def fail_current(
            root: int,
            name: str,
            payload: bytes,
            verify: Callable[[], None],
            *,
            immutable: bool = False,
        ) -> None:
            if not immutable:
                raise OSError("before current publication")
            publish_file(root, name, payload, verify, immutable=True)

        with (
            patch(
                "mos_eisley.project_requirement_store.publish_file",
                side_effect=fail_current,
            ),
            self.assertRaises(OSError),
        ):
            self.store.change(
                self.workspace,
                self.input,
                (self.source,),
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertEqual(
            self.store.show(self.workspace)["snapshot_sha256"], first["snapshot_sha256"]
        )
        # An archived candidate is inspectable evidence, never current acceptance.
        candidate = self.store.show(
            self.workspace, snapshot_sha256=cast(str, preview["snapshot_sha256"])
        )
        self.assertFalse(candidate["accepted_current"])

    def test_workspace_replacement_and_changed_source_during_publication_reject(
        self,
    ) -> None:
        preview = self.store.change(self.workspace, self.input, (self.source,))

        def change_source(
            root: int,
            name: str,
            payload: bytes,
            verify: Callable[[], None],
            *,
            immutable: bool = False,
        ) -> None:
            self.source.write_text("Changed after preview.")
            publish_file(root, name, payload, verify, immutable=immutable)

        with (
            patch(
                "mos_eisley.project_requirement_store.publish_file",
                side_effect=change_source,
            ),
            self.assertRaises(ValueError),
        ):
            self.store.change(
                self.workspace,
                self.input,
                (self.source,),
                expected_sha256=cast(str, preview["preview_sha256"]),
            )
        self.assertFalse(self.current_path().exists())
        self.source.write_text("# Brief\n\n" + self.text + "\n")
        preview = self.store.change(self.workspace, self.input, (self.source,))
        self.workspace.rename(self.base / "replaced")
        self.workspace.mkdir()
        with self.assertRaises(ValueError):
            self.store.change(
                self.workspace,
                self.input,
                (self.source,),
                expected_sha256=cast(str, preview["preview_sha256"]),
            )

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "requirements",
                *args,
                "-C",
                str(self.workspace),
                "--guidance-storage",
                str(self.storage),
                "--json",
            ],
            cwd=self.base,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_review_accept_show_clear_and_history(self) -> None:
        args = ("set", "--input", str(self.input), "--source", str(self.source))
        preview = self.cli(*args)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(self.storage.exists())
        receipt = self.cli(
            *args,
            "--apply",
            "--expected-sha256",
            json.loads(preview.stdout)["preview_sha256"],
        )
        self.assertEqual(receipt.returncode, 0, receipt.stderr)
        saved = json.loads(receipt.stdout)
        shown = self.cli("show")
        self.assertTrue(json.loads(shown.stdout)["accepted_current"])
        clear = self.cli("clear")
        applied = self.cli(
            "clear",
            "--apply",
            "--expected-sha256",
            json.loads(clear.stdout)["preview_sha256"],
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        historical = self.cli("show", "--snapshot-sha256", saved["snapshot_sha256"])
        self.assertEqual(historical.returncode, 0, historical.stderr)
        self.assertFalse(json.loads(historical.stdout)["accepted_current"])

    def test_cli_rejects_invalid_combinations_and_redacts_bad_input(self) -> None:
        for args in (
            ("show", "--apply"),
            ("clear", "--source", str(self.source)),
            ("set", "--input", str(self.input), "--apply"),
            ("set", "--input", str(self.input)),
            ("show", "--input", str(self.input)),
        ):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertNotEqual(result.returncode, 0)
        self.input.write_text('{"secret":"SENSITIVE-REQUIREMENT-CANARY"}')
        result = self.cli(
            "set", "--input", str(self.input), "--source", str(self.source)
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("SENSITIVE-REQUIREMENT-CANARY", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
