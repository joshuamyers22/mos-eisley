"""Exercise separate host approvals and decline/cancel with real Docker workers."""

import shutil
import sys
import unittest
from pathlib import Path

from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.process import bounded_process
from mos_eisley.run.watchdog import CleanupRecord


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from test_review_approval_flow import ApprovalFlowTests

    docker = shutil.which("docker")
    if docker is None:
        raise ValueError("Docker executable required")
    image = (
        bounded_process(
            [docker, "image", "inspect", "--format", "{{.Id}}", "mos-eisley:local"]
        )
        .decode()
        .strip()
    )

    class DockerApprovalTests(ApprovalFlowTests):
        def setUp(self) -> None:
            super().setUp()
            self.containers = tuple(
                OfflineContainer(Path(docker), image, self.base.root / "lifecycles")
                for _ in self.transports
            )
            self.base.container = self.containers[0]

        def tearDown(self) -> None:
            results = tuple((self.base.root / "lifecycles").rglob("result.json"))
            expected = 3 if "two_separate" in self._testMethodName else 2
            self.assertEqual(len(results), expected)
            for path in results:
                receipt = CleanupRecord.model_validate_json(path.read_bytes())
                self.assertEqual(receipt.state, "removed")

    suite = unittest.TestSuite(
        DockerApprovalTests(name)
        for name in (
            "test_two_separate_approvals_return_and_display_verified_result",
            "test_repeated_flow_cancellation_awaits_both_critic_cleanups",
            "test_declining_judge_preserves_allowance_and_does_not_dispatch",
        )
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
