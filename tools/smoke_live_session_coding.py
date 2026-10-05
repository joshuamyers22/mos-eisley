"""Offline role fixtures with real Docker verification and real Git integration."""

import argparse
import asyncio
import sys
from pathlib import Path

from mos_eisley.run.coding_child import CodingContainer, DockerCodingChild


async def exercise(docker: Path, image: str) -> None:
    # Reuse the exact behavior fixtures; this script deliberately sends no paid
    # requests and does not label role fixtures as live provider qualification.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from test_conversation_live_coding import LiveCodingTests

    for method in (
        "test_complete_live_path_preserves_tests_and_blinds_review",
        "test_failed_tests_get_bounded_correction_with_identical_brief",
        "test_final_review_rejection_exhausts_without_integrating",
    ):
        fixture = LiveCodingTests(method)
        await fixture.asyncSetUp()
        try:
            fixture.workflow.executor = DockerCodingChild(
                CodingContainer(docker, image, fixture.root / "lifecycles")
            )
            await getattr(fixture, method)()
        finally:
            fixture.doCleanups()
    print(
        "Connected workflow, frozen creator tests, bounded correction "
        "and real Docker/Git checks passed. Provider calls were fixtures."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", type=Path, required=True)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    asyncio.run(exercise(args.docker, args.image_id))


if __name__ == "__main__":
    main()
