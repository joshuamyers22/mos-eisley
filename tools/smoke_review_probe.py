"""Exercise probe dispatch admission and cancellation with real Docker workers."""

import shutil
import sys
import unittest
from pathlib import Path

from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.process import bounded_process
from mos_eisley.run.watchdog import CleanupRecord


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from test_review_conformance_probe import ReviewProbeTests

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

    class DockerProbeTests(ReviewProbeTests):
        def setUp(self) -> None:
            super().setUp()
            self.base.container = OfflineContainer(
                Path(docker), image, self.base.root / "lifecycles"
            )

        def tearDown(self) -> None:
            results = tuple((self.base.root / "lifecycles").rglob("result.json"))
            expected = 2 if "both_phases" in self._testMethodName else 1
            self.assertEqual(len(results), expected)
            for path in results:
                receipt = CleanupRecord.model_validate_json(path.read_bytes())
                self.assertEqual(receipt.state, "removed")

    suite = unittest.TestSuite(
        DockerProbeTests(name)
        for name in (
            "test_probe_checks_both_phases_and_keeps_credentials_in_host",
            "test_repeated_cancellation_awaits_provider_and_worker_cleanup",
        )
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
