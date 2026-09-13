"""Ordered campaign handoff with real offline workers and fixture observations."""

import shutil
import sys
import unittest
from pathlib import Path

from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.process import bounded_process


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from test_openai_spend import FakeTransport
    from test_review_campaign_runner import CampaignRunnerTests
    from test_review_runtime_evidence import RuntimeEvidenceFixture

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

    class DockerCampaignRunnerTests(CampaignRunnerTests):
        def create_fixture(self) -> RuntimeEvidenceFixture:
            fixture = super().create_fixture()
            fixture.base.container = OfflineContainer(
                Path(docker), image, fixture.base.root / "lifecycles"
            )

            def transport(*_: object) -> FakeTransport:
                path = fixture.base.container.lifecycle_path
                assert path is not None
                if path not in fixture.lifecycles:
                    fixture.lifecycles.append(path)
                return (
                    fixture.judge
                    if fixture.controller.phase == "judge_running"
                    else fixture.base.fake
                )

            fixture.sdk.side_effect = transport
            return fixture

    suite = unittest.TestSuite(
        DockerCampaignRunnerTests(name)
        for name in (
            "test_three_slots_require_verified_observation_before_the_next",
            "test_cancel_during_probe_awaits_worker_cleanup",
        )
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
