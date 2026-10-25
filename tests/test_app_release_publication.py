"""Draft retries and upload failures cannot prematurely publish a release."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

import yaml

from tools.publish_app_release import (
    finalize,
    github_api,
    inventory,
    mapping,
    preflight,
)

ROOT = Path(__file__).resolve().parents[1]
REPO = "owner/repo"
TAG = "v0.2.0-rc.1"
COMMIT = "a" * 40


class GithubFixture:
    def __init__(self, assets: dict[str, tuple[int, str]]) -> None:
        self.exists = True
        self.annotated = False
        self.tag_commit = COMMIT
        self.immutable = True
        self.release: dict[str, object] = {
            "id": 42,
            "tag_name": TAG,
            "target_commitish": COMMIT,
            "draft": True,
            "prerelease": True,
        }
        self.assets: list[dict[str, object]] = [
            {"name": name, "size": size, "digest": digest, "state": "uploaded"}
            for name, (size, digest) in assets.items()
        ]
        self.calls: list[list[str]] = []
        self.patches: list[list[str]] = []

    def __call__(self, arguments: list[str]) -> object:
        self.calls.append(arguments)
        endpoint = arguments[0]
        if "/git/ref/tags/" in endpoint:
            return {
                "object": {
                    "type": "tag" if self.annotated else "commit",
                    "sha": "b" * 40 if self.annotated else self.tag_commit,
                }
            }
        if "/git/tags/" in endpoint:
            return {"object": {"type": "commit", "sha": self.tag_commit}}
        if endpoint == f"repos/{REPO}/releases":
            return [[], [self.release] if self.exists else []]
        if endpoint == f"repos/{REPO}/releases/42/assets":
            return [self.assets[:2], self.assets[2:]]
        if endpoint == f"repos/{REPO}/releases/42":
            if "--method" in arguments:
                self.patches.append(arguments)
                self.release = {
                    **self.release,
                    "draft": False,
                    "immutable": self.immutable,
                }
            return self.release
        raise AssertionError(f"unexpected API request: {endpoint}")


class DraftPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        names = [
            "mos_eisley-0.2.0rc1-py3-none-any.whl",
            "mos_eisley-0.2.0rc1.tar.gz",
            "SOURCE_COMMIT",
            "SHA256SUMS",
            "release-sbom.cdx.json",
            "standalone/release.json",
            "standalone/install.sh",
            "standalone/BOOTSTRAP_SHA256SUMS",
            "managers/mos-eisley-preview.rb",
        ]
        for target in (
            "linux-aarch64",
            "linux-x86_64",
            "macos-aarch64",
            "macos-x86_64",
        ):
            names.extend(
                [
                    f"standalone/mos-0.2.0-rc.1-{target}.tar.gz",
                    f"standalone/mos-install-{target}",
                    f"qualification/{target}/qualification-{target}.json",
                ]
            )
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                (COMMIT + "\n" if name == "SOURCE_COMMIT" else name).encode()
            )
        self.expected = inventory(self.root, COMMIT)
        self.api = GithubFixture(self.expected)

    def finalize(self, tag: str = TAG) -> None:
        finalize(REPO, tag, COMMIT, self.root, 42, self.api)

    def test_new_subject_preflight_is_read_only(self) -> None:
        self.api.exists = False
        preflight(REPO, TAG, COMMIT, self.root, self.api)
        self.assertFalse(self.api.patches)

    def test_matching_partial_draft_resumes_then_complete_upload_publishes(
        self,
    ) -> None:
        complete = self.api.assets.copy()
        self.api.assets = complete[:2]
        preflight(REPO, TAG, COMMIT, self.root, self.api)
        with self.assertRaisesRegex(ValueError, "missing qualified assets"):
            self.finalize()
        self.assertFalse(self.api.patches)
        self.api.assets = complete
        self.finalize()
        self.assertEqual(len(self.api.patches), 1)
        self.assertIn("draft=false", self.api.patches[0])
        self.assertIn(f"tag_name={TAG}", self.api.patches[0])
        self.assertIn(f"target_commitish={COMMIT}", self.api.patches[0])

    def test_published_release_refuses_preflight_and_replay(self) -> None:
        self.api.release["draft"] = False
        with self.assertRaisesRegex(ValueError, "already-published"):
            preflight(REPO, TAG, COMMIT, self.root, self.api)
        with self.assertRaisesRegex(ValueError, "already-published"):
            self.finalize()
        self.assertFalse(self.api.patches)

    def test_partial_corrupt_or_unfinished_asset_refuses_even_preflight(self) -> None:
        for field, value in (
            ("digest", "sha256:" + "0" * 64),
            ("size", 0),
            ("state", "starter"),
            ("digest", None),
        ):
            with self.subTest(field=field, value=value):
                self.api = GithubFixture(self.expected)
                self.api.assets[0][field] = value
                with self.assertRaisesRegex(ValueError, "differs from qualified bytes"):
                    preflight(REPO, TAG, COMMIT, self.root, self.api)
                with self.assertRaisesRegex(ValueError, "differs from qualified bytes"):
                    self.finalize()
                self.assertFalse(self.api.patches)

    def test_unexpected_or_duplicate_uploaded_assets_refuse(self) -> None:
        for name in ("unreviewed.txt", self.api.assets[0]["name"]):
            with self.subTest(name=name):
                self.api = GithubFixture(self.expected)
                self.api.assets.append(
                    {
                        "name": name,
                        "size": 0,
                        "digest": "sha256:" + "0" * 64,
                        "state": "uploaded",
                    }
                )
                with self.assertRaisesRegex(ValueError, "unexpected or duplicate"):
                    self.finalize()
                self.assertFalse(self.api.patches)

    def test_wrong_draft_subject_or_classification_refuses(self) -> None:
        for field, value in (
            ("tag_name", "v9.9.9"),
            ("target_commitish", "c" * 40),
            ("prerelease", False),
            ("id", 99),
        ):
            with self.subTest(field=field):
                self.api = GithubFixture(self.expected)
                self.api.release[field] = value
                with self.assertRaises(ValueError):
                    self.finalize()
                self.assertFalse(self.api.patches)

    def test_wrong_tag_commit_refuses_before_publication(self) -> None:
        self.api.tag_commit = "c" * 40
        with self.assertRaisesRegex(ValueError, "qualified source commit"):
            self.finalize()
        self.assertFalse(self.api.patches)

    def test_annotated_tag_and_stable_classification(self) -> None:
        self.api.annotated = True
        self.api.release.update(tag_name="v0.2.0", prerelease=False)
        self.finalize("v0.2.0")
        self.assertEqual(len(self.api.patches), 1)

    def test_missing_local_pattern_or_wrong_source_refuses_before_api(self) -> None:
        (self.root / "SOURCE_COMMIT").write_text("c" * 40)
        with self.assertRaisesRegex(ValueError, "different source commit"):
            self.finalize()
        self.assertFalse(self.api.calls)
        (self.root / "SOURCE_COMMIT").write_text(COMMIT)
        (self.root / "SHA256SUMS").unlink()
        with self.assertRaisesRegex(ValueError, "missing required"):
            self.finalize()
        self.assertFalse(self.api.calls)

    def test_local_flattened_name_collision_refuses_before_api(self) -> None:
        (self.root / "managers/extra.rb").write_text("fixture")
        duplicate = self.root / "qualification/duplicate/extra.rb.json"
        duplicate.parent.mkdir()
        duplicate.write_text("fixture")
        other = self.root / "qualification/other/extra.rb.json"
        other.parent.mkdir()
        other.write_text("different")
        with self.assertRaisesRegex(ValueError, "duplicate publication asset"):
            self.finalize()
        self.assertFalse(self.api.calls)

    def test_mutable_response_is_not_reported_as_success(self) -> None:
        self.api.immutable = False
        with self.assertRaisesRegex(ValueError, "immutable publication"):
            self.finalize()
        self.assertEqual(len(self.api.patches), 1)
        # An ambiguous/postcondition failure must not blindly republish the tag.
        with self.assertRaisesRegex(ValueError, "already-published"):
            self.finalize()
        self.assertEqual(len(self.api.patches), 1)

    def test_api_error_never_reaches_publication(self) -> None:
        def failing_api(arguments: list[str]) -> object:
            if arguments[0].endswith("/assets"):
                raise subprocess.CalledProcessError(1, ["gh", "api"])
            return self.api(arguments)

        with self.assertRaises(subprocess.CalledProcessError):
            finalize(REPO, TAG, COMMIT, self.root, 42, failing_api)
        self.assertFalse(self.api.patches)

    def test_github_client_uses_scoped_cli_and_finite_timeout(self) -> None:
        result = subprocess.CompletedProcess(["gh"], 0, '{"draft": true}')
        with patch(
            "tools.publish_app_release.subprocess.run", return_value=result
        ) as run:
            self.assertEqual(
                github_api(["repos/owner/repo/releases/42"]), {"draft": True}
            )
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["timeout"], 60)
        self.assertTrue(run.call_args.kwargs["check"])

    def test_historical_harness_retains_the_reviewed_artifact_metadata(self) -> None:
        workflow = cast(
            dict[object, object],
            yaml.safe_load(
                (ROOT / ".github/workflows/published-upgrade.yml").read_text()
            ),
        )
        environment = mapping(workflow["env"])
        signed = json.loads(
            (ROOT / "docs/qualification/rc2-upgrade-candidate.json").read_bytes()
        )
        self.assertEqual(
            signed["payload"]["source_commit"], environment["ARTIFACT_SOURCE"]
        )
        steps = [
            mapping(step)
            for step in cast(
                list[object], mapping(mapping(workflow["jobs"])["upgrade"])["steps"]
            )
        ]
        checkouts = [
            index
            for index, step in enumerate(steps)
            if str(step.get("uses", "")).startswith("actions/checkout@")
        ]
        self.assertEqual(len(checkouts), 2)
        self.assertNotIn("ref", mapping(steps[checkouts[0]]["with"]))
        self.assertEqual(
            mapping(steps[checkouts[1]]["with"])["ref"],
            "${{ env.CANDIDATE_SOURCE }}",
        )
        retained = "$RUNNER_TEMP/mos-rc2-upgrade-candidate.json"
        copies = [
            (index, str(step.get("run", "")))
            for index, step in enumerate(steps)
            if retained in str(step.get("run", ""))
        ]
        self.assertEqual(len(copies), 2)
        self.assertLess(checkouts[0], copies[0][0])
        self.assertLess(copies[0][0], checkouts[1])
        self.assertIn("docs/qualification/rc2-upgrade-candidate.json", copies[0][1])
        self.assertGreater(copies[1][0], checkouts[1])
        self.assertIn('"' + retained + '" .work/candidate/release.json', copies[1][1])

    def test_workflow_upload_is_draft_and_finalization_follows_qualified_gates(
        self,
    ) -> None:
        # PyYAML's YAML 1.1 loader interprets the top-level `on` key as a boolean.
        # The publication job itself has ordinary string keys and typed booleans.
        workflow = cast(
            dict[object, object],
            yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text()),
        )
        publish = mapping(mapping(workflow["jobs"])["publish"])
        self.assertEqual(publish["needs"], ["prepare", "qualify-signed"])
        qualify = mapping(mapping(workflow["jobs"])["qualify-signed"])
        qualification_steps = [mapping(s) for s in cast(list[object], qualify["steps"])]
        installed = next(
            s
            for s in qualification_steps
            if s.get("name")
            == "Qualify installed terminal, diff and recovery on both stores"
        )
        self.assertEqual(
            mapping(installed["env"])["SOURCE_COMMIT"], "${{ github.sha }}"
        )
        for required in (
            "tools/qualify_installed_candidate.py",
            "--artifacts dist/standalone",
            '--expected-source "$SOURCE_COMMIT"',
            '--expected-version "${RELEASE_TAG#v}"',
            "qualification-installed-",
        ):
            self.assertIn(required, str(installed["run"]))
        self.assertNotIn("continue-on-error", installed)
        self.assertNotIn("if", installed)
        reports = next(
            s
            for s in qualification_steps
            if mapping(s.get("with", {})).get("name")
            == "signed-qualification-${{ matrix.os }}"
        )
        self.assertEqual(reports["if"], "${{ always() }}")
        self.assertNotIn("continue-on-error", qualify)
        predecessor = next(
            s
            for s in qualification_steps
            if s.get("name") == "Qualify upgrade from the actual published predecessor"
        )
        self.assertEqual(
            mapping(predecessor["env"])["SOURCE_COMMIT"], "${{ github.sha }}"
        )
        journey = str(predecessor["run"])
        self.assertIn("gh release download v0.1.0-rc.1", journey)
        self.assertIn("tools/qualify_published_upgrade.py", journey)
        self.assertIn("--candidate dist/standalone", journey)
        self.assertIn('--candidate-commit "$SOURCE_COMMIT"', journey)
        self.assertNotIn("continue-on-error", predecessor)
        self.assertNotIn("if", predecessor)
        rc2 = next(
            s
            for s in qualification_steps
            if s.get("name") == "Qualify upgrade from published rc.2"
        )
        self.assertEqual(mapping(rc2["env"])["SOURCE_COMMIT"], "${{ github.sha }}")
        rc2_journey = str(rc2["run"])
        self.assertIn("gh release download v0.1.0-rc.2", rc2_journey)
        self.assertIn("413979297", rc2_journey)
        self.assertIn("ef6a66fc8911902cef7a91828b4b26e7d329020c", rc2_journey)
        self.assertIn(".immutable == true", rc2_journey)
        self.assertIn("--predecessor-version 0.1.0-rc.2", rc2_journey)
        self.assertIn('--candidate-commit "$SOURCE_COMMIT"', rc2_journey)
        self.assertIn("qualification-upgrade-rc2-", rc2_journey)
        self.assertNotIn("continue-on-error", rc2)
        self.assertNotIn("if", rc2)
        rc7 = next(
            s
            for s in qualification_steps
            if s.get("name") == "Qualify upgrade from published rc.7"
        )
        self.assertEqual(mapping(rc7["env"])["SOURCE_COMMIT"], "${{ github.sha }}")
        rc7_journey = str(rc7["run"])
        for required in (
            "gh release download v0.1.0-rc.7",
            "421278021",
            "78bc17ce561df7e641a4dd0fc5aef56aa9deee58",
            ".immutable == true",
            ".draft == false",
            "--predecessor-version 0.1.0-rc.7",
            '--candidate-commit "$SOURCE_COMMIT"',
            "qualification-upgrade-rc7-",
        ):
            self.assertIn(required, rc7_journey)
        self.assertNotIn("continue-on-error", rc7)
        self.assertNotIn("if", rc7)
        self.assertEqual(publish["environment"], "application-release")
        steps = [mapping(s) for s in cast(list[object], publish["steps"])]
        upload = next(
            i
            for i, s in enumerate(steps)
            if str(s.get("uses", "")).startswith("softprops/action-gh-release@")
        )
        options = mapping(steps[upload]["with"])
        self.assertIs(options["draft"], True)
        self.assertIs(options["overwrite_files"], False)
        self.assertIs(options["fail_on_unmatched_files"], True)
        self.assertIn("preflight", str(steps[upload - 1]["run"]))
        self.assertIn("finalize", str(steps[upload + 1]["run"]))
        self.assertEqual(
            mapping(steps[upload + 1]["env"])["DRAFT_RELEASE_ID"],
            "${{ steps.draft.outputs.id }}",
        )
        self.assertNotIn("continue-on-error", steps[upload])
        self.assertNotIn("continue-on-error", steps[upload + 1])


if __name__ == "__main__":
    unittest.main()
