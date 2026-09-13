"""Check signed review approvals with real workers and synthetic provider responses."""

import shutil
import sys
import unittest
from importlib.metadata import version
from pathlib import Path

from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.process import bounded_process
from mos_eisley.run.review_conformance_admission import ReviewConformanceRuntime
from mos_eisley.run.review_conformance_authorization import review_conformance_scope
from mos_eisley.run.watchdog import CleanupRecord


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from test_review_conformance_admission import ReviewConformanceTests

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

    class DockerConformanceTests(ReviewConformanceTests):
        def setUp(self) -> None:
            super().setUp()
            self.base.container = OfflineContainer(
                Path(docker), image, self.base.root / "lifecycles"
            )
            self.runtime = ReviewConformanceRuntime(
                sdk_version=version("openai"), image_id=image
            )
            self.scope = review_conformance_scope(
                self.preview, **self.runtime.model_dump()
            )

        def tearDown(self) -> None:
            results = tuple((self.base.root / "lifecycles").rglob("result.json"))
            expected = 2 if "two_independent" in self._testMethodName else 1
            self.assertEqual(len(results), expected)
            for path in results:
                receipt = CleanupRecord.model_validate_json(path.read_bytes())
                self.assertEqual(receipt.state, "removed")

    suite = unittest.TestSuite(
        DockerConformanceTests(name)
        for name in (
            "test_two_independent_signatures_and_local_approvals_complete_fixture",
            "test_critic_signature_cannot_be_reused_for_judge",
        )
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
