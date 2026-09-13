"""Exercise complete synthetic reviews and cancellation with real Docker workers."""

import shutil
import sys
import unittest
from pathlib import Path

from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.process import bounded_process
from mos_eisley.run.watchdog import CleanupRecord


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from test_review_controller import ControllerTests

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

    class DockerControllerTests(ControllerTests):
        def setUp(self) -> None:
            super().setUp()
            self.containers = tuple(
                OfflineContainer(Path(docker), image, self.base.root / "lifecycles")
                for _ in self.transports
            )
            self.base.container = self.containers[0]

        def tearDown(self) -> None:
            results = tuple((self.base.root / "lifecycles").rglob("result.json"))
            expected = 2 if "cancellation" in self._testMethodName else 3
            self.assertEqual(len(results), expected)
            for path in results:
                receipt = CleanupRecord.model_validate_json(path.read_bytes())
                self.assertEqual(receipt.state, "removed")

    suite = unittest.TestSuite(
        DockerControllerTests(name)
        for name in (
            "test_exact_approvals_pause_judge_and_reconstruct_final_result",
            "test_critic_fanout_and_repeated_cancellation_await_all_children",
            "test_failed_judge_retains_infrastructure_result_and_uncertain_spend",
        )
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
