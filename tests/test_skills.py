"""Adversarial coverage for inert, digest-pinned prompt skills."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.skills import SkillRoster, SkillRosterAssignment
from mos_eisley.demo import demo_inputs
from mos_eisley.run.skills import SkillCatalog, bind_skill_roster, discover_skills
from mos_eisley.run.store import Manifest, load_run, load_skill_run_manifest


def write_skill(
    root: Path,
    name: str,
    body: str,
    *,
    metadata: str = "",
    sidecar: str | None = None,
) -> Path:
    path = root / name
    path.mkdir(parents=True)
    metadata_block = f"metadata:\n{metadata}" if metadata else ""
    (path / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: Use {name} for a bounded review procedure.\n"
        f"{metadata_block}\n"
        "---\n"
        f"{body}\n"
    )
    if sidecar is not None:
        (path / "mos.yaml").write_text(sidecar)
    return path


class SkillDiscoveryTests(TestCase):
    def test_standard_skill_discovers_metadata_then_activates_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_skill(root, "review-carefully", "Original instructions")
            catalog = discover_skills(user_roots=(root,))
            descriptor = catalog.descriptors[0]
            self.assertEqual(descriptor.identity.kind, "procedure")
            self.assertNotIn(
                "Original instructions",
                json.dumps(descriptor.model_dump(mode="json")),
            )
            reference = descriptor.identity.qualified_reference
            (path / "SKILL.md").write_text("mutated after discovery")
            self.assertEqual(
                catalog.activate(reference).instructions, "Original instructions"
            )

    def test_whole_package_digest_includes_lazy_resources(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_skill(root, "resourceful", "Read references/check.md")
            references = path / "references"
            references.mkdir()
            (references / "check.md").write_text("first")
            first = discover_skills(user_roots=(root,))
            first_identity = first.descriptors[0].identity
            self.assertEqual(
                first.resource(
                    first_identity.qualified_reference, "references/check.md"
                ),
                b"first",
            )
            (references / "check.md").write_text("second")
            second = discover_skills(user_roots=(root,))
            self.assertNotEqual(
                first_identity.package_sha256,
                second.descriptors[0].identity.package_sha256,
            )
            self.assertEqual(
                first.resource(
                    first_identity.qualified_reference, "references/check.md"
                ),
                b"first",
            )
            with self.assertRaisesRegex(ValueError, "path is invalid"):
                first.resource(first_identity.qualified_reference, "../outside")

    def test_project_source_never_shadows_or_activates_implicitly(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            user = base / "user"
            project = base / "project"
            write_skill(user, "same-name", "user body")
            write_skill(project, "same-name", "project body")
            catalog = discover_skills(user_roots=(user,), project_roots=(project,))
            self.assertEqual(catalog.shadowed_names, ("same-name",))
            descriptors = {item.identity.source: item for item in catalog.descriptors}
            project_reference = descriptors["project"].identity.qualified_reference
            with self.assertRaisesRegex(ValueError, "explicit approval"):
                catalog.activate(project_reference)
            self.assertEqual(
                catalog.activate(project_reference, allow_project=True).instructions,
                "project body",
            )

    def test_sidecar_is_narrow_and_must_agree_with_metadata(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_skill(
                root,
                "critic-correctness",
                "Check correctness.",
                metadata='  mos.version: "3"\n  mos.kind: persona\n',
                sidecar="version: 3\nkind: persona\n",
            )
            descriptor = discover_skills(user_roots=(root,)).descriptors[0]
            self.assertEqual(descriptor.identity.version, "3")
            self.assertEqual(descriptor.identity.kind, "persona")
            (root / "critic-correctness" / "mos.yaml").write_text(
                "version: 4\nkind: persona\n"
            )
            with self.assertRaisesRegex(ValueError, "disagree"):
                discover_skills(user_roots=(root,))

    def test_executable_surfaces_and_yaml_indirection_are_rejected(self) -> None:
        cases = {
            "allowed": (
                "---\nname: bad\ndescription: bad skill\n"
                "allowed-tools: null\n---\nbody\n",
                None,
            ),
            "anchor": (
                "---\nname: bad\ndescription: &copy bad skill\n"
                "metadata: {note: *copy}\n---\nbody\n",
                None,
            ),
            "toolbundle": (
                "---\nname: bad\ndescription: bad skill\n---\nbody\n",
                "version: 1\nkind: toolbundle\n",
            ),
        }
        for label, (skill, sidecar) in cases.items():
            with self.subTest(label=label), TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / "bad"
                path.mkdir()
                (path / "SKILL.md").write_text(skill)
                if sidecar is not None:
                    (path / "mos.yaml").write_text(sidecar)
                with self.assertRaises(ValueError):
                    discover_skills(user_roots=(root,))

    def test_scripts_executables_symlinks_and_duplicate_names_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "skills"
            path = write_skill(root, "unsafe", "body")
            scripts = path / "scripts"
            scripts.mkdir()
            (scripts / "run.py").write_text("pass")
            with self.assertRaisesRegex(ValueError, "scripts"):
                discover_skills(user_roots=(root,))
            for child in scripts.iterdir():
                child.unlink()
            scripts.rmdir()
            executable = path / "reference.txt"
            executable.write_text("data")
            executable.chmod(0o700)
            with self.assertRaisesRegex(ValueError, "executable"):
                discover_skills(user_roots=(root,))
            executable.unlink()
            target = base / "outside"
            target.write_text("secret")
            (path / "escape").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlinks"):
                discover_skills(user_roots=(root,))
            (path / "escape").unlink()
            hardlink = path / "hardlink"
            os.link(target, hardlink)
            with self.assertRaisesRegex(ValueError, "hard-linked"):
                discover_skills(user_roots=(root,))
            hardlink.unlink()
            duplicate_root = base / "duplicate-skills"
            write_skill(duplicate_root, "unsafe", "other body")
            with self.assertRaisesRegex(ValueError, "duplicate source-qualified"):
                discover_skills(user_roots=(root, duplicate_root))

    def test_duplicate_yaml_keys_and_oversized_body_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "bad"
            path.mkdir()
            (path / "SKILL.md").write_text(
                "---\nname: bad\nname: bad\ndescription: bad\n---\nbody\n"
            )
            with self.assertRaisesRegex(ValueError, "duplicate YAML"):
                discover_skills(user_roots=(root,))
            (path / "SKILL.md").write_text(
                "---\nname: bad\ndescription: bad\n---\n" + "x" * 32_001
            )
            with self.assertRaisesRegex(ValueError, "body"):
                discover_skills(user_roots=(root,))

    def test_mutation_during_snapshot_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_skill(root, "moving-target", "original")
            skill_file = path / "SKILL.md"
            from mos_eisley.run import skills as skill_module

            original_read = skill_module.read_bounded

            def mutate_after_read(candidate: Path, limit: int) -> bytes:
                payload = original_read(candidate, limit)
                if candidate == skill_file:
                    skill_file.write_bytes(payload + b"changed")
                return payload

            with (
                patch(
                    "mos_eisley.run.skills.read_bounded",
                    side_effect=mutate_after_read,
                ),
                self.assertRaisesRegex(ValueError, "changed while"),
            ):
                discover_skills(user_roots=(root,))

    def test_yaml_depth_and_directory_entries_are_bounded(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "nested"
            path.mkdir()
            nested = "[" * 17 + "value" + "]" * 17
            (path / "SKILL.md").write_text(
                "---\nname: nested\ndescription: nested\n"
                f"metadata: {{value: {nested}}}\n---\nbody\n"
            )
            with self.assertRaisesRegex(ValueError, "nesting limit"):
                discover_skills(user_roots=(root,))
            write_skill(root, "second", "body")
            with (
                patch("mos_eisley.run.skills.MAX_SKILLS", 1),
                self.assertRaisesRegex(ValueError, "root exceeds"),
            ):
                discover_skills(user_roots=(root,))


class SkillReviewBindingTests(TestCase):
    def _catalog_and_roster(self, root: Path) -> tuple[SkillCatalog, SkillRoster]:
        brief, cassette = demo_inputs()
        del brief
        for recording in cassette.critics:
            write_skill(
                root,
                recording.critic.id,
                recording.critic.persona,
                sidecar="version: 1\nkind: persona\n",
            )
        catalog = discover_skills(user_roots=(root,))
        references = {
            item.identity.name: item.identity.qualified_reference
            for item in catalog.descriptors
        }
        roster = SkillRoster(
            assignments=tuple(
                SkillRosterAssignment(
                    critic_id=item.critic.id,
                    skill=references[item.critic.id],
                )
                for item in cassette.critics
            )
        )
        return catalog, roster

    def test_binding_requires_exact_persona_and_critic_coverage(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, roster = self._catalog_and_roster(root)
            _, cassette = demo_inputs()
            manifest = bind_skill_roster(cassette, roster, catalog)
            self.assertEqual(len(manifest.assignments), 2)
            incomplete = roster.model_copy(
                update={"assignments": roster.assignments[:1]}
            )
            with self.assertRaisesRegex(ValueError, "exactly cover"):
                bind_skill_roster(cassette, incomplete, catalog)
            changed = cassette.model_copy(
                update={
                    "critics": (
                        cassette.critics[0].model_copy(
                            update={
                                "critic": cassette.critics[0].critic.model_copy(
                                    update={"persona": "different"}
                                )
                            }
                        ),
                        cassette.critics[1],
                    )
                }
            )
            with self.assertRaisesRegex(ValueError, "does not match"):
                bind_skill_roster(changed, roster, catalog)

    def test_cli_records_and_replays_exact_skill_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            skills = base / "skills"
            catalog, roster = self._catalog_and_roster(skills)
            del catalog
            source = base / "source"
            output = base / "runs"
            source.mkdir()
            brief, cassette = demo_inputs()
            (source / "brief.json").write_bytes(canonical_bytes(brief))
            (source / "cassette.json").write_bytes(canonical_bytes(cassette))
            (source / "roster.json").write_bytes(canonical_bytes(roster))
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "review",
                            "--brief",
                            str(source / "brief.json"),
                            "--cassette",
                            str(source / "cassette.json"),
                            "--skill-roster",
                            str(source / "roster.json"),
                            "--user-skill-root",
                            str(skills),
                            "--output",
                            str(output),
                        ]
                    ),
                    1,
                )
            run = next(path for path in output.iterdir() if path.is_dir())
            manifest = Manifest.model_validate_json(
                (run / "manifest.json").read_bytes()
            )
            self.assertEqual(manifest.schema_version, 2)
            self.assertIsNotNone(load_skill_run_manifest(run))
            self.assertEqual(main(["replay", str(run)]), 0)
            payload = json.loads((run / "events.jsonl").read_text().splitlines()[1])
            self.assertEqual(payload["type"], "skill.loaded")
            (run / "skills.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                load_run(run)

    def test_project_review_binding_needs_explicit_flag(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, cassette = demo_inputs()
            for recording in cassette.critics:
                write_skill(
                    root,
                    recording.critic.id,
                    recording.critic.persona,
                    sidecar="version: 1\nkind: persona\n",
                )
            catalog = discover_skills(project_roots=(root,))
            roster = SkillRoster(
                assignments=tuple(
                    SkillRosterAssignment(
                        critic_id=item.critic.id,
                        skill=next(
                            descriptor.identity.qualified_reference
                            for descriptor in catalog.descriptors
                            if descriptor.identity.name == item.critic.id
                        ),
                    )
                    for item in cassette.critics
                )
            )
            with self.assertRaisesRegex(ValueError, "explicit approval"):
                bind_skill_roster(cassette, roster, catalog)
            self.assertEqual(
                len(
                    bind_skill_roster(
                        cassette, roster, catalog, allow_project=True
                    ).assignments
                ),
                2,
            )

    def test_cli_list_reports_shadowing_without_loading_body(self) -> None:
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()) as out:
            root = Path(directory)
            write_skill(root, "listed", "do not leak this body")
            self.assertEqual(
                main(["skills", "list", "--user-root", str(root), "--json"]), 0
            )
            value = out.getvalue()
            self.assertIn('"authority_granted": false', value)
            self.assertNotIn("do not leak this body", value)
