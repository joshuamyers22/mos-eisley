"""Wall-clock discontinuities cannot age setup; explicit expiry still refuses."""

from datetime import UTC, timedelta, tzinfo
from datetime import datetime as RealDatetime
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import Mock, patch

from review_fixture_clock import ReviewFixtureClock, install_review_fixture_clock
from test_review_conformance_acceptance import create_runtime_fixture
from test_review_runtime_evidence import RuntimeEvidenceFixture

from mos_eisley.run import review_broker, review_conformance_probe
from mos_eisley.run.review_conformance_authorization import (
    review_conformance_scope,
    verify_review_conformance_authorization,
)


def stepped_datetime(offset: list[timedelta]) -> type[RealDatetime]:
    class SteppedDatetime(RealDatetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> RealDatetime:
            return RealDatetime.now(tz) + offset[0]

    return SteppedDatetime


class ReviewFixtureClockTests(IsolatedAsyncioTestCase):
    def test_utc_progress_uses_elapsed_time_after_wall_clock_steps(self):
        wall = [RealDatetime.now(UTC)]
        elapsed = [10.0]
        read_wall = Mock(side_effect=lambda: wall[0])
        clock = ReviewFixtureClock(utc_now=read_wall, monotonic=lambda: elapsed[0])
        initial = clock.now()
        for jump in (timedelta(hours=2), -timedelta(days=1)):
            wall[0] += jump
            elapsed[0] += 0.5
            self.assertEqual(clock.now(), initial + timedelta(seconds=elapsed[0] - 10))
        read_wall.assert_called_once()

    def test_one_clock_is_shared_and_all_module_patches_are_restored(self):
        before = review_broker.datetime
        owner = TestCase()
        clock = ReviewFixtureClock()
        install_review_fixture_clock(owner, clock)
        try:
            self.assertIs(review_broker.datetime, review_conformance_probe.datetime)
            self.assertIsNot(review_broker.datetime, before)
            self.assertIsInstance(RealDatetime.now(UTC), review_broker.datetime)
            self.assertEqual(review_broker.datetime.now(UTC).tzinfo, UTC)
        finally:
            self.assertTrue(owner.doCleanups())
        self.assertIs(review_broker.datetime, before)

    async def test_real_pipe_review_retains_verified_receipts_across_wall_steps(self):
        offset = [timedelta()]
        self.enterContext(
            patch.object(review_conformance_probe, "datetime", stepped_datetime(offset))
        )
        install_review_fixture_clock(self)
        fixture = create_runtime_fixture(self)
        probe = fixture.probe()

        def stepped() -> str:
            if probe.controller.phase == "judge_running":
                offset[0] += timedelta(hours=2)
            return "synthetic-test-key"

        fixture.key_loader.side_effect = stepped
        result = await probe.run()
        assert result is not None
        self.assertNotEqual(result.result.verdict.decision, "infrastructure_error")
        self.assertEqual(probe.controller.phase, "finished")
        self.assertEqual(fixture.base.workers, 2)
        self.assertEqual(len(probe.collect_runtime_exchanges()), 2)
        self.assertEqual(fixture.base.ledger.snapshot().unresolved_entries, 0)
        (fixture.directory / "judge" / "runtime-count-start.json").unlink()
        with self.assertRaises(FileNotFoundError):
            probe.collect_runtime_exchanges()

    async def test_unshared_wall_step_reproduces_missing_judge_runtime_start(self):
        offset = [timedelta()]
        self.enterContext(
            patch.object(review_conformance_probe, "datetime", stepped_datetime(offset))
        )
        fixture = RuntimeEvidenceFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        probe = fixture.probe()

        def stepped() -> str:
            if probe.controller.phase == "judge_running":
                offset[0] += timedelta(hours=2)
            return "synthetic-test-key"

        fixture.key_loader.side_effect = stepped
        result = await probe.run()
        assert result is not None
        self.assertEqual(result.result.verdict.decision, "infrastructure_error")
        self.assertFalse(
            (fixture.directory / "judge" / "runtime-count-start.json").exists()
        )

    async def test_elapsed_expiry_still_rejects_the_unchanged_signed_grant(self):
        elapsed = [0.0]
        clock = ReviewFixtureClock(monotonic=lambda: elapsed[0])
        install_review_fixture_clock(self, clock)
        fixture = create_runtime_fixture(self)
        probe = fixture.probe()
        scope = review_conformance_scope(
            probe.controller.preview, **fixture.runtime.model_dump()
        )
        signed = await fixture.load_certificate(scope)
        elapsed[0] += fixture.policy.max_authorization_seconds + 1
        with self.assertRaises(ValueError):
            verify_review_conformance_authorization(
                signed, fixture.policy, scope, clock.now()
            )
        self.assertEqual(fixture.base.ledger.snapshot().entries, 0)
        fixture.key_loader.assert_not_called()
