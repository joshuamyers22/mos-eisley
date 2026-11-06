"""Offline adversarial admission cases for the rc.16 timeout continuation."""

import copy
import unittest
from typing import cast

import rc16_qualification_gate as subject


class QualificationGateTests(unittest.TestCase):
    def fixture(self) -> tuple[dict[str, object], dict[str, object], list[object]]:
        run: dict[str, object] = {
            "id": 42102119299,
            "head_sha": subject.SOURCE,
            "head_branch": "v0.1.0-rc.16",
            "event": "push",
            "workflow_id": 350992511,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "cancelled",
        }
        rows = [
            {"id": i, "name": n, "conclusion": c}
            for i, (n, c) in subject.SIGNED.items()
        ]
        rows.append({"id": 127516552543, "name": "prepare", "conclusion": "success"})
        return (
            run,
            {"jobs": rows},
            [{"annotation_level": "failure", "message": subject.TIMEOUT}],
        )

    def test_exact_timeout_is_admitted(self) -> None:
        self.assertTrue(subject.admitted(*self.fixture()))

    def test_wrong_source_attempt_workflow_or_incomplete_run_refused(self) -> None:
        for field, value in (
            ("head_sha", "0" * 40),
            ("run_attempt", 2),
            ("workflow_id", 1),
            ("status", "in_progress"),
        ):
            run, jobs, annotations = self.fixture()
            run[field] = value
            self.assertFalse(subject.admitted(run, jobs, annotations))

    def test_cancellation_without_timeout_refused(self) -> None:
        run, jobs, _ = self.fixture()
        for annotations in (
            [],
            [{"annotation_level": "failure", "message": "The operation was canceled."}],
        ):
            self.assertFalse(subject.admitted(run, jobs, annotations))

    def test_missing_duplicate_or_failed_platform_refused(self) -> None:
        run, jobs, annotations = self.fixture()
        rows = cast(list[dict[str, object]], jobs["jobs"])
        for candidate in (rows[:-1], rows + rows[:1], rows[1:]):
            self.assertFalse(subject.admitted(run, {"jobs": candidate}, annotations))
        failed = copy.deepcopy(rows)
        failed[0]["conclusion"] = "failure"
        self.assertFalse(subject.admitted(run, {"jobs": failed}, annotations))

    def test_malformed_inputs_refused(self) -> None:
        self.assertFalse(subject.admitted(None, None, None))
        run, _, annotations = self.fixture()
        self.assertFalse(subject.admitted(run, {"jobs": [None]}, annotations))


if __name__ == "__main__":
    unittest.main()
