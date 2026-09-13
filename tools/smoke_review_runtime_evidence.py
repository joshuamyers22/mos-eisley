"""Collect runtime evidence from real workers with synthetic provider responses."""

import shutil
import sys
import unittest
from pathlib import Path

from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.process import bounded_process


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from test_openai_spend import FakeTransport
    from test_review_runtime_evidence import RuntimeEvidenceTests

    docker = shutil.which("docker")
    if docker is None:
        raise ValueError("Docker executable required")
    image = (
        bounded_process(
            [
                docker,
                "image",
                "inspect",
                "--format",
                "{{.Id}}",
                "mos-eisley:local",
            ]
        )
        .decode()
        .strip()
    )

    class DockerRuntimeEvidenceTests(RuntimeEvidenceTests):
        def setUp(self) -> None:
            super().setUp()
            self.base.container = OfflineContainer(
                Path(docker), image, self.base.root / "lifecycles"
            )

            def transport(*_: object) -> FakeTransport:
                path = self.base.container.lifecycle_path
                assert path is not None
                if path not in self.lifecycles:
                    self.lifecycles.append(path)
                return (
                    self.judge
                    if self.controller.phase == "judge_running"
                    else self.base.fake
                )

            self.sdk.side_effect = transport

    suite = unittest.TestSuite(
        DockerRuntimeEvidenceTests(name)
        for name in (
            "test_collect_exact_records_for_both_phases_without_exporting_secrets",
            "test_cancelled_count_has_receipt_after_owned_cleanup",
        )
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
