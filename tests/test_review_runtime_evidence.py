"""Local runtime measurements remain distinct from independent attestation."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import call, patch

from pydantic import JsonValue
from test_review_approval_flow import ScriptedUser
from test_review_broker_admission import output
from test_review_conformance_probe import ReviewProbeFixture

from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import (
    CriticSpec,
    Critique,
    JudgeDecision,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.registry import openai_registry
from mos_eisley.review.citations import citation_bound_request
from mos_eisley.run.duplex import ExchangeHandler
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_broker import PreparedReviewCall, PreparedReviewEnvelope
from mos_eisley.run.review_campaign import (
    CAMPAIGN_BYTES,
    CampaignAttempt,
    CampaignAttemptSubmission,
)
from mos_eisley.run.review_conformance_observation import (
    ReviewObservationPolicy,
    authenticate_review_probe,
    make_review_probe_observation,
    sign_review_probe_observation,
)
from mos_eisley.run.review_conformance_probe import BrokeredReviewConformanceProbe
from mos_eisley.run.review_launch import LaunchCritic, ReviewLaunchConfiguration
from mos_eisley.run.review_runtime_evidence import (
    RuntimeOperationEnd,
    RuntimeOperationStart,
    collect_review_runtime_exchange,
    collect_review_runtime_exchanges,
    verify_review_runtime_exchange,
)
from mos_eisley.run.review_standalone_evidence import (
    StandaloneReviewEvidence,
    decode_standalone_review_evidence,
    retain_standalone_review_evidence,
    verify_standalone_review_evidence,
)
from mos_eisley.run.spend_ledger import SpendLedger
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

    async def test_one_invalid_of_three_reaches_authenticated_retained_observation(
        self,
    ) -> None:
        ledger = SpendLedger.create(self.base.root / "redundant.sqlite", 2_000)
        directory = self.base.root / "redundant-review"
        personas = ("invalid-output", "correctness", "reliability")
        critics = tuple(
            CriticSpec(
                id=f"critic-{index}",
                provider="openai",
                model="gpt-6-astra",
                persona=persona,
            )
            for index, persona in enumerate(personas)
        )
        requests = tuple(
            citation_bound_request(self.guided.prepared.brief, critic.persona)
            for critic in critics
        )
        calls = tuple(
            PreparedReviewCall(
                self.base.reviewer,
                request,
                self.base.policy,
                ledger,
                critic=critic,
                guidance=self.admission,
            )
            for critic, request in zip(critics, requests, strict=True)
        )
        envelope = PreparedReviewEnvelope(
            calls,
            self.base.policy,
            ledger,
            max_total_microusd=1_300,
            directory=directory,
        )
        review_policy = ReviewPolicy(min_critics=2, min_providers=1)
        self.policy = self.policy.model_copy(update={"max_reserved_microusd": 2_000})

        containers: list[OfflineContainer] = []
        for index in range(4):
            container = OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "a" * 64)

            async def exchange(
                arguments: tuple[str, ...],
                payload: bytes,
                handler: ExchangeHandler,
                timeout: float,
                *,
                selected: OfflineContainer = container,
                selected_index: int = index,
            ) -> bytes:
                lifecycle = self.base.root / f"redundant-lifecycle-{selected_index}"
                lifecycle.mkdir(mode=0o700)
                lease = CleanupLease(
                    container_id=digest(str(lifecycle).encode()),
                    max_runtime_seconds=35,
                )
                private_write(lifecycle / "lease.json", canonical_bytes(lease))
                selected.lifecycle_path = lifecycle
                try:
                    return await self.base.exchange(
                        arguments, payload, handler, timeout
                    )
                finally:
                    private_write(
                        lifecycle / "result.json",
                        canonical_bytes(
                            CleanupRecord(
                                lease_sha256=digest(canonical_bytes(lease)),
                                container_id=lease.container_id,
                                state="removed",
                                attempts=1,
                            )
                        ),
                    )

            self.enterContext(
                patch.object(container, "exchange_async", side_effect=exchange)
            )
            containers.append(container)

        class RoutingTransport:
            async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
                return 10

            async def create_response(
                self, payload: dict[str, JsonValue]
            ) -> dict[str, JsonValue]:
                serialized = str(payload)
                if '"persona":"invalid-output"' in serialized:
                    return output("{}")
                if '"persona":' in serialized:
                    return output(canonical_bytes(Critique()).decode())
                return output(
                    canonical_bytes(
                        JudgeDecision(upheld=(), rationale="Fixture")
                    ).decode()
                )

        probe = BrokeredReviewConformanceProbe(
            envelope,
            self.base.reviewer,
            review_policy,
            ScriptedUser(("approve", "approve")),
            critic_containers=tuple(containers[:3]),
            judge_container=containers[3],
            authority_policy=lambda: self.policy,
            load_authorization=self.load_certificate,
            load_api_key=self.key_loader,
            total_seconds=30,
        )
        self.controller = probe.controller
        self.preview = probe.controller.preview
        with patch(
            "mos_eisley.run.review_conformance_probe.EphemeralOpenAITransport",
            return_value=RoutingTransport(),
        ):
            result = await probe.run()
        assert result is not None and probe.judge_preview is not None
        self.assertEqual(
            [item.status for item in result.result.critics],
            ["error", "completed", "completed"],
        )
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(len(probe.collect_runtime_exchanges()), 4)

        start = probe.controller.start
        assert start is not None
        observed_at = datetime.now(UTC)
        observation_policy = ReviewObservationPolicy(
            policy_id="redundant-observation",
            authority_policy_sha256=self.policy.sha256,
            critic_preview_sha256=digest(canonical_bytes(self.preview)),
            valid_from=self.policy.valid_from,
            valid_until=self.policy.valid_until,
            max_observation_age_seconds=600,
        )
        authorizations = probe.approval_ui.authorizations
        self.assertEqual(len(authorizations), 2)
        phase_authorizations = (authorizations[0], authorizations[1])
        observation = make_review_probe_observation(
            observation_policy,
            self.policy,
            self.preview,
            start,
            probe.judge_preview,
            phase_authorizations,
            self.base.reviewer,
            ledger,
            expected_result_sha256=digest(canonical_bytes(result)),
            exchanges=probe.collect_runtime_exchanges(),
            observed_at=observed_at,
        )
        signed = sign_review_probe_observation(
            observation, "observer", self.observer_key
        )
        output_limit = self.preview.requests[0].max_text_output_bytes
        assert output_limit is not None
        configuration = ReviewLaunchConfiguration(
            registry=openai_registry(),
            critics=tuple(
                LaunchCritic(critic=critic, spending=self.base.policy)
                for critic in critics
            ),
            judge_model="gpt-6-astra",
            judge_spending=self.base.policy,
            effort="medium",
            budget=BudgetPolicy(max_output_tokens=100),
            max_text_output_bytes=output_limit,
            policy=review_policy,
            total_seconds=30,
            max_total_microusd=1_300,
        )
        lifecycle_paths = probe.lifecycle_paths
        assert all(path is not None for path in lifecycle_paths)
        evidence = StandaloneReviewEvidence(
            attempt=CampaignAttempt(
                configuration=configuration,
                preview=self.preview,
                authority_policy=self.policy,
                observation_policy=observation_policy,
                ledger_path=str(ledger.path.resolve()),
            ),
            submission=CampaignAttemptSubmission(
                start=start,
                judge=probe.judge_preview,
                authorizations=phase_authorizations,
                signed_observation=signed,
                expected_result_sha256=digest(canonical_bytes(result)),
                lifecycle_directories=tuple(str(path) for path in lifecycle_paths),
            ),
        )
        retained = self.base.root / "standalone-evidence.json"
        authenticated = retain_standalone_review_evidence(
            retained, evidence, now=observed_at
        )
        self.assertTrue(authenticated.local_artifacts_verified)
        self.assertEqual(retained.stat().st_mode & 0o777, 0o600)
        decoded = decode_standalone_review_evidence(retained.read_bytes())
        self.assertEqual(
            verify_standalone_review_evidence(decoded, now=observed_at),
            authenticated,
        )
        duplicate = b'{"schema_version":1,' + retained.read_bytes()[1:]
        with self.assertRaisesRegex(ValueError, "invalid standalone review evidence"):
            decode_standalone_review_evidence(duplicate)
        with self.assertRaisesRegex(ValueError, "exceeds its byte limit"):
            decode_standalone_review_evidence(b" " * (CAMPAIGN_BYTES + 1))
        changed = decoded.model_copy(
            update={
                "submission": decoded.submission.model_copy(
                    update={"expected_result_sha256": "f" * 64}
                )
            }
        )
        changed_output = self.base.root / "changed-evidence.json"
        with self.assertRaises(ValueError):
            retain_standalone_review_evidence(changed_output, changed, now=observed_at)
        self.assertFalse(changed_output.exists())
        with self.assertRaisesRegex(ValueError, "new private output"):
            retain_standalone_review_evidence(retained, evidence, now=observed_at)
        public_parent = self.base.root / "public-evidence"
        public_parent.mkdir(mode=0o755)
        public_parent.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "new private output"):
            retain_standalone_review_evidence(
                public_parent / "evidence.json", evidence, now=observed_at
            )
        with self.assertRaisesRegex(ValueError, "outside runtime evidence"):
            retain_standalone_review_evidence(
                directory / "evidence.json", evidence, now=observed_at
            )

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
