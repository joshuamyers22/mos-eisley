"""Local runtime measurements remain distinct from independent attestation."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import call, patch

from pydantic import JsonValue
from test_review_conformance_probe import ReviewProbeFixture

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.duplex import ExchangeHandler
from mos_eisley.run.review_conformance_observation import (
    ReviewObservationPolicy,
    authenticate_review_probe,
    make_review_probe_observation,
    sign_review_probe_observation,
)
from mos_eisley.run.review_runtime_evidence import (
    RuntimeOperationEnd,
    RuntimeOperationStart,
    collect_review_runtime_exchange,
    collect_review_runtime_exchanges,
    verify_review_runtime_exchange,
)
from mos_eisley.run.store import private_write
from mos_eisley.run.watchdog import CleanupLease, CleanupRecord


class RuntimeEvidenceFixture(ReviewProbeFixture):
    def setUp(self) -> None:
        super().setUp()
        self.lifecycles: list[Path] = []
        self.enterContext(
            patch.object(
                self.base.container, "exchange_async", side_effect=self.exchange
            )
        )

    async def exchange(
        self,
        arguments: tuple[str, ...],
        payload: bytes,
        handler: ExchangeHandler,
        timeout: float,
    ) -> bytes:
        # Synthetic lease/cleanup only. The Docker smoke test replaces this
        # exchange with actual workers and independently selected lifecycle paths.
        directory = self.base.root / f"fixture-lifecycle-{len(self.lifecycles)}"
        directory.mkdir(mode=0o700)
        lease = CleanupLease(
            container_id=digest(str(directory).encode()), max_runtime_seconds=35
        )
        private_write(directory / "lease.json", canonical_bytes(lease))
        self.base.container.lifecycle_path = directory
        self.lifecycles.append(directory)
        try:
            return await self.base.exchange(arguments, payload, handler, timeout)
        finally:
            private_write(
                directory / "result.json",
                canonical_bytes(
                    CleanupRecord(
                        lease_sha256=digest(canonical_bytes(lease)),
                        container_id=lease.container_id,
                        state="removed",
                        attempts=1,
                    )
                ),
            )

    def critic_directory(self) -> Path:
        return self.directory / self.call.authorization.ledger_entry_id


class RuntimeEvidenceTests(RuntimeEvidenceFixture, IsolatedAsyncioTestCase):
    def test_probe_cannot_collect_runtime_evidence_before_completion(self):
        with self.assertRaisesRegex(ValueError, "completed review"):
            self.probe().collect_runtime_exchanges()

    async def test_collect_exact_records_for_both_phases_without_exporting_secrets(
        self,
    ):
        probe = self.probe()
        observation_policy = ReviewObservationPolicy(
            policy_id="runtime-fixture",
            authority_policy_sha256=self.policy.sha256,
            critic_preview_sha256=digest(canonical_bytes(self.preview)),
            valid_from=self.policy.valid_from,
            valid_until=self.policy.valid_until,
            max_observation_age_seconds=600,
        )
        result = await probe.run()
        assert result is not None and probe.judge_preview is not None
        observed = probe.collect_runtime_exchanges()
        self.assertEqual(len(observed), 2)
        self.assertEqual(probe.lifecycle_paths, tuple(self.lifecycles))
        verify_review_runtime_exchange(
            observed[0],
            self.critic_directory(),
            self.lifecycles[0],
            self.preview.requests[0],
            probe.approval_ui.authorizations[0].authorization,
        )
        with self.assertRaisesRegex(ValueError, "pinned observer"):
            verify_review_runtime_exchange(
                observed[0].model_copy(update={"transport_evidence_sha256": "f" * 64}),
                self.critic_directory(),
                self.lifecycles[0],
                self.preview.requests[0],
                probe.approval_ui.authorizations[0].authorization,
            )
        self.assertLessEqual(
            observed[0].generation_finished_at, observed[1].count_started_at
        )
        self.assertLessEqual(observed[-1].generation_finished_at, datetime.now(UTC))
        for directory in (self.critic_directory(), self.directory / "judge"):
            paths = tuple(directory.glob("runtime-*.json"))
            self.assertEqual(len(paths), 4)
            for path in paths:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn(b"synthetic-test-key", path.read_bytes())
                self.assertNotIn(b"Fixture", path.read_bytes())
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 40)
        start = probe.controller.start
        assert start is not None
        critic_signed, judge_signed = probe.approval_ui.authorizations
        observation = make_review_probe_observation(
            observation_policy,
            self.policy,
            self.preview,
            start,
            probe.judge_preview,
            (critic_signed, judge_signed),
            self.base.reviewer,
            self.base.ledger,
            expected_result_sha256=digest(canonical_bytes(result)),
            exchanges=observed,
            observed_at=datetime.now(UTC),
        )
        # Only a deterministic test observer signs this synthetic-provider run.
        signed = sign_review_probe_observation(
            observation, "observer", self.observer_key
        )
        verified = authenticate_review_probe(
            signed,
            observation_policy,
            self.policy,
            self.preview,
            start,
            probe.judge_preview,
            (critic_signed, judge_signed),
            self.base.reviewer,
            self.base.ledger,
            expected_result_sha256=digest(canonical_bytes(result)),
            now=datetime.now(UTC),
        )
        self.assertTrue(verified.local_artifacts_verified)
        self.assertFalse(verified.live_review_activation_authorized)

    def test_multi_critic_collection_reuses_critic_phase_authorization(self):
        critic_request = self.preview.requests[0]
        judge_request = critic_request.model_copy(update={"system": "judge"})
        critic_authorization = self.certificate().authorization
        judge_authorization = critic_authorization.model_copy(
            update={
                "scope": critic_authorization.scope.model_copy(
                    update={"phase": "judge"}
                )
            }
        )
        directories = tuple(
            Path(f"/evidence/{role}") for role in ("one", "two", "judge")
        )
        lifecycles = tuple(
            Path(f"/lifecycle/{role}") for role in ("one", "two", "judge")
        )
        with patch(
            "mos_eisley.run.review_runtime_evidence.collect_review_runtime_exchange",
            side_effect=("critic-one", "critic-two", "judge"),
        ) as collect:
            observed = collect_review_runtime_exchanges(
                directories,
                lifecycles,
                (critic_request, critic_request),
                judge_request,
                (critic_authorization, judge_authorization),
            )
        self.assertEqual(observed, ("critic-one", "critic-two", "judge"))
        self.assertEqual(
            collect.call_args_list,
            [
                call(
                    directories[0], lifecycles[0], critic_request, critic_authorization
                ),
                call(
                    directories[1], lifecycles[1], critic_request, critic_authorization
                ),
                call(directories[2], lifecycles[2], judge_request, judge_authorization),
            ],
        )

    def test_grouped_collection_rejects_incomplete_exchange_shape(self):
        authorization = self.certificate().authorization
        with (
            patch(
                "mos_eisley.run.review_runtime_evidence.collect_review_runtime_exchange"
            ) as collect,
            self.assertRaisesRegex(ValueError, "every critic"),
        ):
            collect_review_runtime_exchanges(
                (Path("/critic"),),
                (Path("/critic-lifecycle"), Path("/judge-lifecycle")),
                (self.preview.requests[0],),
                self.preview.requests[0],
                (authorization, authorization),
            )
        collect.assert_not_called()

    def test_grouped_collection_rejects_reversed_phase_authorizations(self):
        critic = self.certificate().authorization
        judge = critic.model_copy(
            update={"scope": critic.scope.model_copy(update={"phase": "judge"})}
        )
        with (
            patch(
                "mos_eisley.run.review_runtime_evidence.collect_review_runtime_exchange"
            ) as collect,
            self.assertRaisesRegex(ValueError, "match review phases"),
        ):
            collect_review_runtime_exchanges(
                (Path("/critic"), Path("/judge")),
                (Path("/critic-lifecycle"), Path("/judge-lifecycle")),
                (self.preview.requests[0],),
                self.preview.requests[0],
                (judge, critic),
            )
        collect.assert_not_called()

    async def test_missing_begin_record_is_not_reconstructed_as_success(self):
        probe = self.probe()
        await probe.run()
        directory = self.critic_directory()
        (directory / "runtime-count-start.json").rename(directory / "hidden-start")
        with self.assertRaises(FileNotFoundError):
            collect_review_runtime_exchange(
                directory,
                self.lifecycles[0],
                self.preview.requests[0],
                probe.approval_ui.authorizations[0].authorization,
            )

    async def test_cleanup_from_another_worker_is_rejected(self):
        probe = self.probe()
        await probe.run()
        with self.assertRaisesRegex(ValueError, "approved exchange"):
            collect_review_runtime_exchange(
                self.critic_directory(),
                self.lifecycles[1],
                self.preview.requests[0],
                probe.approval_ui.authorizations[0].authorization,
            )

    async def test_changed_response_rejects_runtime_evidence(self):
        probe = self.probe()
        await probe.run()
        (self.critic_directory() / "broker-response.json").write_text(
            '{"response":{},"schema_version":1}'
        )
        with self.assertRaisesRegex(ValueError, "retained provider response"):
            collect_review_runtime_exchange(
                self.critic_directory(),
                self.lifecycles[0],
                self.preview.requests[0],
                probe.approval_ui.authorizations[0].authorization,
            )

    async def test_missing_cleanup_result_does_not_imply_removed_worker(self):
        probe = self.probe()
        await probe.run()
        (self.lifecycles[0] / "result.json").rename(
            self.lifecycles[0] / "hidden-result"
        )
        with self.assertRaises(FileNotFoundError):
            collect_review_runtime_exchange(
                self.critic_directory(),
                self.lifecycles[0],
                self.preview.requests[0],
                probe.approval_ui.authorizations[0].authorization,
            )

    async def test_record_write_failure_prevents_provider_operation(self):
        with (
            patch.object(
                self.base.fake,
                "count_input_tokens",
                wraps=self.base.fake.count_input_tokens,
            ) as count,
            patch(
                "mos_eisley.run.review_runtime_evidence.private_write",
                side_effect=OSError("fixture storage failure"),
            ),
            self.assertRaises(ValueError),
        ):
            await self.probe().run()
        count.assert_not_called()
        self.assertEqual(self.base.fake.calls, [])
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 650)

    async def test_failure_record_omits_provider_error_details(self):
        with (
            patch.object(
                self.base.fake,
                "count_input_tokens",
                side_effect=OSError("SECRET-PROVIDER-DETAIL"),
            ),
            self.assertRaises(ValueError),
        ):
            await self.probe().run()
        path = self.critic_directory() / "runtime-count-end.json"
        end = RuntimeOperationEnd.model_validate_json(path.read_bytes())
        self.assertEqual(end.status, "failed")
        self.assertIsNone(end.result_sha256)
        self.assertNotIn(b"SECRET-PROVIDER-DETAIL", path.read_bytes())
        self.assertFalse(
            (self.critic_directory() / "runtime-generation-start.json").exists()
        )

    async def test_cancelled_count_has_receipt_after_owned_cleanup(self):
        entered = asyncio.Event()

        async def pending(_payload: dict[str, JsonValue]) -> int:
            entered.set()
            await asyncio.Event().wait()
            return 0

        with patch.object(self.base.fake, "count_input_tokens", side_effect=pending):
            probe = self.probe()
            task = asyncio.create_task(probe.run())
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        end = RuntimeOperationEnd.model_validate_json(
            (self.critic_directory() / "runtime-count-end.json").read_bytes()
        )
        self.assertEqual(end.status, "cancelled")
        cleanup = CleanupRecord.model_validate_json(
            (self.lifecycles[0] / "result.json").read_bytes()
        )
        self.assertEqual(cleanup.state, "removed")
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 650)

    async def test_rewritten_runtime_start_breaks_end_binding(self):
        probe = self.probe()
        await probe.run()
        path = self.critic_directory() / "runtime-count-start.json"
        start = RuntimeOperationStart.model_validate_json(path.read_bytes())
        path.write_bytes(
            canonical_bytes(start.model_copy(update={"sdk_version": "changed"}))
        )
        with self.assertRaises(ValueError):
            collect_review_runtime_exchange(
                self.critic_directory(),
                self.lifecycles[0],
                self.preview.requests[0],
                probe.approval_ui.authorizations[0].authorization,
            )
