"""Offline refusal cases for the fixed-source protected publication admission."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from typing import cast

import admit_rc16_publication as subject


def fixture() -> dict[str, object]:
    originals = ["gitleaks", "prepare", "standalone / sbom-coverage"]
    originals += [f"standalone / standalone ({o})" for o in subject.TARGETS]
    originals += [f"qualify-signed ({o})" for o in subject.TARGETS]
    original = {name: "success" for name in originals}
    original.update(
        {"qualify-signed (macos-15-intel)": "cancelled", "publish": "skipped"}
    )
    specs = [
        (
            42102119299,
            subject.SOURCE,
            subject.TAG,
            350992511,
            "push",
            "cancelled",
            original,
        ),
        (
            42233939365,
            "efba0d4781f0e5e4dd3c3cfa9e2b9efe31aa9d3c",
            "test/rc16-intel-recovery",
            408617556,
            "workflow_dispatch",
            "failure",
            {
                "offline": "success",
                "intel-recovery (0)": "failure",
                "intel-recovery (1)": "success",
                "intel-recovery (2)": "success",
                "intel-recovery (3)": "success",
                "discovery": "skipped",
            },
        ),
        (
            42246992124,
            subject.HARNESS,
            "test/rc16-startup-diagnostics",
            408617556,
            "workflow_dispatch",
            "success",
            {
                "offline": "success",
                "diagnostic": "success",
                "intel-qualification": "skipped",
                "discovery": "skipped",
            },
        ),
        (
            42282492215,
            subject.HARNESS,
            "test/rc16-startup-diagnostics",
            408617556,
            "workflow_dispatch",
            "success",
            {
                "offline": "success",
                "diagnostic": "skipped",
                "intel-qualification": "success",
                **{
                    f"discovery ({o}, {t})": "success"
                    for o, t in subject.TARGETS.items()
                },
            },
        ),
    ]
    records: dict[str, object] = {}
    for number, source, branch, workflow, event, conclusion, jobs in specs:
        endpoint = f"{subject.REPO}/actions/runs/{number}"
        records[endpoint] = {
            "id": number,
            "head_sha": source,
            "head_branch": branch,
            "workflow_id": workflow,
            "event": event,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": conclusion,
        }
        records[endpoint + "/jobs?per_page=100"] = {
            "jobs": [
                {"name": n, "conclusion": c, "status": "completed"}
                for n, c in jobs.items()
            ]
        }
    records[f"{subject.REPO}/check-runs/127590446087/annotations"] = [
        {
            "message": "The job has exceeded the maximum execution time of 1h15m0s",
            "annotation_level": "failure",
        }
    ]
    records[f"{subject.REPO}/pulls/371"] = {
        "merged": True,
        "merge_commit_sha": "4595957a822e4eaf7b7560c9c44820736c82cb8b",
        "head": {"sha": "78dc47e88434b79f1fa4431728af7653e6995007"},
    }
    records[f"{subject.REPO}/git/ref/tags/{subject.TAG}"] = {
        "object": {"type": "tag", "sha": subject.TAG_OBJECT}
    }
    records[f"{subject.REPO}/git/tags/{subject.TAG_OBJECT}"] = {
        "object": {"type": "commit", "sha": subject.SOURCE}
    }
    records[f"{subject.REPO}/compare/{subject.SOURCE}...main"] = {
        "merge_base_commit": {"sha": subject.SOURCE}
    }
    merge = "4595957a822e4eaf7b7560c9c44820736c82cb8b"
    head = "78dc47e88434b79f1fa4431728af7653e6995007"
    records[f"{subject.REPO}/git/commits/{merge}"] = {
        "sha": merge,
        "parents": [{"sha": "base"}, {"sha": head}],
        "tree": {"sha": "reviewed-tree"},
    }
    records[f"{subject.REPO}/git/commits/{head}"] = {
        "sha": head,
        "tree": {"sha": "reviewed-tree"},
    }
    records[f"{subject.REPO}/compare/{merge}...main"] = {
        "merge_base_commit": {"sha": merge}
    }
    # Version-pinned REST intentionally has no merge_commit_sha field.
    cast(dict[str, object], records[f"{subject.REPO}/pulls/371"]).pop(
        "merge_commit_sha"
    )
    return records


class PublicationAdmissionTests(unittest.TestCase):
    def validate(self, records: dict[str, object]) -> None:
        def api(arguments: list[str]) -> object:
            self.assertEqual(len(arguments), 1)
            return copy.deepcopy(records[arguments[0]])

        subject.validate_runs(api)

    def test_exact_separately_identified_run_chain_passes(self) -> None:
        self.validate(fixture())

    def test_wrong_run_source_attempt_or_conclusion_refused(self) -> None:
        for number in (42102119299, 42233939365, 42246992124, 42282492215):
            for key, value in (
                ("head_sha", "0" * 40),
                ("run_attempt", 2),
                ("status", "in_progress"),
                ("event", "pull_request"),
            ):
                records = fixture()
                run = cast(
                    dict[str, object], records[f"{subject.REPO}/actions/runs/{number}"]
                )
                run[key] = value
                with self.assertRaisesRegex(ValueError, "run identity"):
                    self.validate(records)

    def test_skipped_failed_missing_duplicate_discovery_refused(self) -> None:
        endpoint = f"{subject.REPO}/actions/runs/42282492215/jobs?per_page=100"
        for mode in ("skipped", "failure", "missing", "duplicate"):
            records = fixture()
            response = cast(dict[str, object], records[endpoint])
            jobs = cast(list[dict[str, object]], response["jobs"])
            if mode == "missing":
                jobs.pop()
            elif mode == "duplicate":
                jobs.append(copy.deepcopy(jobs[-1]))
            else:
                jobs[-1]["conclusion"] = mode
            with self.assertRaisesRegex(ValueError, "job matrix"):
                self.validate(records)

    def test_original_failure_and_timeout_must_remain_visible(self) -> None:
        records = fixture()
        records[f"{subject.REPO}/check-runs/127590446087/annotations"] = []
        with self.assertRaisesRegex(ValueError, "timeout"):
            self.validate(records)

    def test_unmerged_review_and_moved_tag_refused(self) -> None:
        for endpoint, field, value in (
            (f"{subject.REPO}/pulls/371", "merged", False),
            (
                f"{subject.REPO}/git/ref/tags/{subject.TAG}",
                "object",
                {"type": "tag", "sha": "0" * 40},
            ),
        ):
            records = fixture()
            cast(dict[str, object], records[endpoint])[field] = value
            with self.assertRaises(ValueError):
                self.validate(records)

    def test_wrong_merge_parent_tree_or_main_ancestry_refused(self) -> None:
        merge = "4595957a822e4eaf7b7560c9c44820736c82cb8b"
        for field, value in (
            ("parents", [{"sha": "other"}]),
            ("tree", {"sha": "other"}),
        ):
            records = fixture()
            cast(dict[str, object], records[f"{subject.REPO}/git/commits/{merge}"])[
                field
            ] = value
            with self.assertRaisesRegex(ValueError, "merge graph"):
                self.validate(records)
        records = fixture()
        records[f"{subject.REPO}/compare/{merge}...main"] = {
            "merge_base_commit": {"sha": "other"}
        }
        with self.assertRaisesRegex(ValueError, "absent from main"):
            self.validate(records)

    def test_duplicate_and_unexpected_report_input_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            source.mkdir()
            (source / "one.json").write_text("{}")
            subject.copy_reports(source, base / "out")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                subject.copy_reports(source, base / "out")
            (source / "foreign.txt").write_text("unexpected")
            with self.assertRaisesRegex(ValueError, "unexpected"):
                subject.copy_reports(source, base / "different")

    def test_modified_pinned_evidence_refused_before_software_admission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in subject.BINDINGS:
                (root / name).write_text("{}")
            with self.assertRaisesRegex(ValueError, "reviewed evidence changed"):
                subject.validate_artifacts(root / "absent", root)


if __name__ == "__main__":
    unittest.main()
