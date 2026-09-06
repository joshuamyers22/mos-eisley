"""Provider transactions commit before send and settle without retry authority."""

import asyncio
import io
import json
import sqlite3
from collections.abc import Callable
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, cast
from unittest import TestCase
from unittest.mock import patch

from pydantic import JsonValue

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.ports import ProviderError
from mos_eisley.run.skill_runtime_grant import SkillRuntimeBrokerCapability
from mos_eisley.run.skill_runtime_preflight import PreparedSkillRuntimeRequest
from mos_eisley.run.skill_runtime_provider import (
    SkillRuntimeProviderReply,
    SkillRuntimeProviderTransactionStore,
    SkillRuntimeProviderTransport,
    execute_skill_runtime_provider_transaction,
    inspect_skill_runtime_provider_transaction,
)
from mos_eisley.run.store import private_write
from tests import test_skill_runtime_grant as grant_module
from tests.test_skill_runtime_preflight import SkillRuntimePreflightTests


class FakeProviderTransport:
    provider: Literal["openai"] = "openai"
    automatic_retries: Literal[0] = 0

    def __init__(
        self,
        response: dict[str, JsonValue] | BaseException,
        on_send: Callable[[], None] | None = None,
    ) -> None:
        self.response = response
        self.on_send = on_send
        self.payloads: list[dict[str, JsonValue]] = []

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.payloads.append(payload)
        if self.on_send is not None:
            self.on_send()
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class SlowProviderTransport:
    provider: Literal["openai"] = "openai"
    automatic_retries: Literal[0] = 0

    def __init__(self) -> None:
        self.calls = 0

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls += 1
        await asyncio.sleep(2)
        return {}


class RetryingProviderTransport:
    provider = "openai"
    automatic_retries = 1

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        raise AssertionError("retrying transport must not be invoked")


class SkillRuntimeProviderTransactionTests(TestCase):
    def setUp(self) -> None:
        self.grant = grant_module.SkillRuntimeBrokerGrantTests()
        self.grant.setUp()
        self.addCleanup(self.grant.doCleanups)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = SkillRuntimeProviderTransactionStore.create(
            self.root / "provider-transactions.sqlite",
            self.grant.dispatch.transaction_policy,
            self.grant.store,
            self.runtime.sources.routing.control_anchor,
            self.runtime.sources.control_anchor,
            self.runtime.sources.default_store,
            self.grant.dispatch.runtime.ledger,
        )
        self.now = self.grant.issue_at + timedelta(seconds=1)

    @property
    def runtime(self) -> SkillRuntimePreflightTests:
        return self.grant.dispatch.runtime

    def response(self, **updates: JsonValue) -> dict[str, JsonValue]:
        response: dict[str, JsonValue] = {
            "id": "resp_provider_transaction",
            "model": self.runtime.spend_policy.model,
            "service_tier": "default",
            "output": [],
            "usage": {"input_tokens": 12, "output_tokens": 7},
        }
        response.update(updates)
        return response

    def execute(
        self,
        transport: SkillRuntimeProviderTransport,
        *,
        capability: SkillRuntimeBrokerCapability | None = None,
        prepared: PreparedSkillRuntimeRequest | None = None,
        store: SkillRuntimeProviderTransactionStore | None = None,
    ) -> tuple[SkillRuntimeBrokerCapability, SkillRuntimeProviderReply]:
        active = capability or self.grant.issue()
        wire = canonical_bytes(active.claim())
        result = asyncio.run(
            execute_skill_runtime_provider_transaction(
                self.runtime.sources,
                self.runtime.routing_preflight,
                prepared or self.grant.dispatch.admission_fixture.prepared,
                active,
                wire,
                self.runtime.spend_policy,
                self.runtime.ledger,
                self.grant.store,
                store or self.store,
                transport,
                self.now,
            )
        )
        return active, result

    def test_commits_before_one_exact_send_and_settles_existing_reservation(
        self,
    ) -> None:
        capability = self.grant.issue()
        issuance = capability.issuance
        wire = canonical_bytes(capability.claim())
        before = self.runtime.ledger.snapshot()

        def assert_before_send() -> None:
            stored = self.store.get(issuance.issuance_sha256)
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertIsNone(stored[1])
            entry = self.runtime.ledger.entry_status(issuance.ledger_entry_id)
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertEqual(entry.status, "held")

        transport = FakeProviderTransport(self.response(), assert_before_send)
        reply = asyncio.run(
            execute_skill_runtime_provider_transaction(
                self.runtime.sources,
                self.runtime.routing_preflight,
                self.grant.dispatch.admission_fixture.prepared,
                capability,
                wire,
                self.runtime.spend_policy,
                self.runtime.ledger,
                self.grant.store,
                self.store,
                transport,
                self.now,
            )
        )

        self.assertEqual(len(transport.payloads), 1)
        self.assertEqual(transport.payloads[0]["store"], False)
        self.assertEqual(transport.payloads[0]["truncation"], "disabled")
        self.assertEqual(transport.payloads[0]["service_tier"], "default")
        self.assertTrue(reply.intent.before_send_committed)
        self.assertTrue(reply.intent.capability_redeemed)
        self.assertFalse(reply.intent.second_reservation_created)
        self.assertEqual(reply.outcome.status, "response_received")
        self.assertFalse(reply.outcome.retry_permitted)
        self.assertEqual(self.runtime.ledger.snapshot().entries, before.entries)
        entry = self.runtime.ledger.entry_status(issuance.ledger_entry_id)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.status, "settled")
        self.assertEqual(entry.charged_microusd, self.runtime.spend_policy.cost(12, 7))
        status = inspect_skill_runtime_provider_transaction(
            issuance, self.grant.store, self.store, self.runtime.ledger
        )
        self.assertEqual(
            (status.phase, status.outcome), ("finished", "response_received")
        )
        self.assertFalse(status.retry_permitted)
        self.assertFalse(status.automatic_budget_release_authorized)

        with self.assertRaisesRegex(ValueError, "exact held|rejected"):
            asyncio.run(
                execute_skill_runtime_provider_transaction(
                    self.runtime.sources,
                    self.runtime.routing_preflight,
                    self.grant.dispatch.admission_fixture.prepared,
                    capability,
                    wire,
                    self.runtime.spend_policy,
                    self.runtime.ledger,
                    self.grant.store,
                    self.store,
                    transport,
                    self.now,
                )
            )

    def test_transport_failure_is_uncertain_and_retains_full_reservation(self) -> None:
        transport = FakeProviderTransport(RuntimeError("lost response"))
        capability = self.grant.issue()
        reserved = self.grant.dispatch.admission_fixture.prepared.ledger_entry
        with self.assertRaisesRegex(ProviderError, "response unavailable"):
            self.execute(transport, capability=capability)
        self.assertEqual(len(transport.payloads), 1)
        entry = self.runtime.ledger.entry_status(reserved.entry_id)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            (entry.status, entry.charged_microusd),
            ("uncertain", reserved.reserved_microusd),
        )
        status = inspect_skill_runtime_provider_transaction(
            capability.issuance, self.grant.store, self.store, self.runtime.ledger
        )
        self.assertEqual((status.phase, status.outcome), ("finished", "uncertain"))
        self.assertTrue(status.provider_transfer_may_have_started)
        self.assertFalse(status.retry_permitted)

    def test_cancellation_is_uncertain_and_never_releases_or_retries(self) -> None:
        capability = self.grant.issue()
        with self.assertRaises(asyncio.CancelledError):
            self.execute(
                FakeProviderTransport(asyncio.CancelledError()),
                capability=capability,
            )
        status = inspect_skill_runtime_provider_transaction(
            capability.issuance, self.grant.store, self.store, self.runtime.ledger
        )
        self.assertEqual(
            (status.phase, status.outcome, status.ledger_status),
            ("finished", "uncertain", "uncertain"),
        )
        self.assertFalse(status.retry_permitted)

    def test_transaction_timeout_is_uncertain_and_invokes_transport_once(self) -> None:
        capability = self.grant.issue()
        transport = SlowProviderTransport()
        with self.assertRaisesRegex(ProviderError, "response unavailable"):
            self.execute(transport, capability=capability)
        self.assertEqual(transport.calls, 1)
        status = inspect_skill_runtime_provider_transaction(
            capability.issuance, self.grant.store, self.store, self.runtime.ledger
        )
        self.assertEqual(
            (status.phase, status.outcome, status.ledger_status),
            ("finished", "uncertain", "uncertain"),
        )

    def test_retrying_transport_is_rejected_before_capability_redemption(self) -> None:
        capability = self.grant.issue()
        wire = canonical_bytes(capability.claim())
        with self.assertRaisesRegex(ValueError, "zero-retry OpenAI"):
            asyncio.run(
                execute_skill_runtime_provider_transaction(
                    self.runtime.sources,
                    self.runtime.routing_preflight,
                    self.grant.dispatch.admission_fixture.prepared,
                    capability,
                    wire,
                    self.runtime.spend_policy,
                    self.runtime.ledger,
                    self.grant.store,
                    self.store,
                    cast(SkillRuntimeProviderTransport, RetryingProviderTransport()),
                    self.now,
                )
            )
        self.assertIsNone(self.store.get(capability.issuance.issuance_sha256))
        result = asyncio.run(
            execute_skill_runtime_provider_transaction(
                self.runtime.sources,
                self.runtime.routing_preflight,
                self.grant.dispatch.admission_fixture.prepared,
                capability,
                wire,
                self.runtime.spend_policy,
                self.runtime.ledger,
                self.grant.store,
                self.store,
                FakeProviderTransport(self.response()),
                self.now,
            )
        )
        self.assertEqual(result.outcome.status, "response_received")

    def test_missing_usage_is_uncertain_and_response_is_not_persisted(self) -> None:
        capability = self.grant.issue()
        marker = "provider-secret-response-marker"
        with self.assertRaisesRegex(ProviderError, "omitted billable usage"):
            self.execute(
                FakeProviderTransport(
                    self.response(output=[{"text": marker}], usage=None)
                ),
                capability=capability,
            )
        record = self.store.get(capability.issuance.issuance_sha256)
        self.assertIsNotNone(record)
        assert record is not None and record[1] is not None
        self.assertEqual(record[1].status, "uncertain")
        self.assertTrue(record[1].provider_response_observed)
        self.assertNotIn(marker.encode(), self.store.path.read_bytes())

    def test_oversize_response_is_uncertain_and_not_returned(self) -> None:
        capability = self.grant.issue()
        response = self.response(output=[{"text": "x" * 1_000_001}])
        with self.assertRaisesRegex(ProviderError, "response unavailable"):
            self.execute(FakeProviderTransport(response), capability=capability)
        status = inspect_skill_runtime_provider_transaction(
            capability.issuance, self.grant.store, self.store, self.runtime.ledger
        )
        self.assertEqual(
            (status.phase, status.outcome, status.ledger_status),
            ("finished", "uncertain", "uncertain"),
        )

    def test_pricing_violation_blocks_ledger_and_retains_full_reservation(self) -> None:
        capability = self.grant.issue()
        prepared = self.grant.dispatch.admission_fixture.prepared
        response = self.response(
            usage={
                "input_tokens": prepared.spend_reservation.input_tokens + 1,
                "output_tokens": 0,
            }
        )
        with self.assertRaisesRegex(ProviderError, "violated"):
            self.execute(FakeProviderTransport(response), capability=capability)
        entry = self.runtime.ledger.entry_status(prepared.ledger_entry.entry_id)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            (entry.status, entry.charged_microusd),
            ("violation", prepared.ledger_entry.reserved_microusd),
        )
        self.assertTrue(self.runtime.ledger.snapshot().blocked)

    def test_substituted_request_is_rejected_without_burning_valid_bearer(self) -> None:
        capability = self.grant.issue()
        prepared = self.grant.dispatch.admission_fixture.prepared
        changed_request = prepared.provider_request.model_copy(
            update={"payload": {**prepared.provider_request.payload, "input": []}}
        )
        changed = prepared.model_copy(update={"provider_request": changed_request})
        wire = canonical_bytes(capability.claim())
        transport = FakeProviderTransport(self.response())
        with self.assertRaisesRegex(ValueError, "request provenance"):
            asyncio.run(
                execute_skill_runtime_provider_transaction(
                    self.runtime.sources,
                    self.runtime.routing_preflight,
                    changed,
                    capability,
                    wire,
                    self.runtime.spend_policy,
                    self.runtime.ledger,
                    self.grant.store,
                    self.store,
                    transport,
                    self.now,
                )
            )
        self.assertEqual(transport.payloads, [])
        result = asyncio.run(
            execute_skill_runtime_provider_transaction(
                self.runtime.sources,
                self.runtime.routing_preflight,
                prepared,
                capability,
                wire,
                self.runtime.spend_policy,
                self.runtime.ledger,
                self.grant.store,
                self.store,
                transport,
                self.now,
            )
        )
        self.assertEqual(result.outcome.status, "response_received")

    def test_before_send_store_failure_prevents_transport_and_leaves_spend_held(
        self,
    ) -> None:
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_intent BEFORE INSERT ON transactions "
                "BEGIN SELECT RAISE(ABORT, 'simulated intent failure'); END"
            )
            connection.commit()
        capability = self.grant.issue()
        transport = FakeProviderTransport(self.response())
        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated"):
            self.execute(transport, capability=capability)
        self.assertEqual(transport.payloads, [])
        self.assertIsNone(self.store.get(capability.issuance.issuance_sha256))
        status = self.runtime.ledger.entry_status(capability.issuance.ledger_entry_id)
        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status.status, "held")

    def test_ledger_failure_after_send_leaves_durable_ambiguous_marker(self) -> None:
        capability = self.grant.issue()
        transport = FakeProviderTransport(self.response())
        with (
            patch.object(
                self.runtime.ledger,
                "settle",
                side_effect=sqlite3.OperationalError("simulated ledger failure"),
            ),
            self.assertRaisesRegex(sqlite3.OperationalError, "simulated ledger"),
        ):
            self.execute(transport, capability=capability)
        self.assertEqual(len(transport.payloads), 1)
        record = self.store.get(capability.issuance.issuance_sha256)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertIsNone(record[1])
        status = inspect_skill_runtime_provider_transaction(
            capability.issuance, self.grant.store, self.store, self.runtime.ledger
        )
        self.assertEqual(
            (status.phase, status.ledger_status, status.retry_permitted),
            ("before_send", "held", False),
        )

    def test_outcome_store_failure_keeps_settled_ledger_and_before_send_marker(
        self,
    ) -> None:
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_outcome BEFORE INSERT ON outcomes "
                "BEGIN SELECT RAISE(ABORT, 'simulated outcome failure'); END"
            )
            connection.commit()
        capability = self.grant.issue()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated outcome"):
            self.execute(FakeProviderTransport(self.response()), capability=capability)
        status = inspect_skill_runtime_provider_transaction(
            capability.issuance, self.grant.store, self.store, self.runtime.ledger
        )
        self.assertEqual(
            (status.phase, status.ledger_status, status.retry_permitted),
            ("before_send", "settled", False),
        )

    def test_store_does_not_persist_bearer_prompt_or_response_body(self) -> None:
        capability = self.grant.issue()
        claim = capability.claim()
        prompt = self.runtime.request.user_input
        response_marker = "private-provider-body-marker"
        result = asyncio.run(
            execute_skill_runtime_provider_transaction(
                self.runtime.sources,
                self.runtime.routing_preflight,
                self.grant.dispatch.admission_fixture.prepared,
                capability,
                canonical_bytes(claim),
                self.runtime.spend_policy,
                self.runtime.ledger,
                self.grant.store,
                self.store,
                FakeProviderTransport(
                    self.response(output=[{"text": response_marker}])
                ),
                self.now,
            )
        )
        self.assertEqual(result.outcome.status, "response_received")
        stored = self.store.path.read_bytes()
        self.assertNotIn(claim.capability.encode(), stored)
        self.assertNotIn(prompt.encode(), stored)
        self.assertNotIn(response_marker.encode(), stored)

    def test_concurrent_attempts_invoke_transport_exactly_once(self) -> None:
        capability = self.grant.issue()
        wire = canonical_bytes(capability.claim())
        transport = FakeProviderTransport(self.response())

        async def run_twice():
            async def attempt():
                try:
                    await execute_skill_runtime_provider_transaction(
                        self.runtime.sources,
                        self.runtime.routing_preflight,
                        self.grant.dispatch.admission_fixture.prepared,
                        capability,
                        wire,
                        self.runtime.spend_policy,
                        self.runtime.ledger,
                        self.grant.store,
                        self.store,
                        transport,
                        self.now,
                    )
                except (ProviderError, ValueError):
                    return "rejected"
                return "sent"

            return await asyncio.gather(attempt(), attempt())

        results = asyncio.run(run_twice())
        self.assertEqual(results.count("sent"), 1)
        self.assertEqual(results.count("rejected"), 1)
        self.assertEqual(len(transport.payloads), 1)

    def test_cli_creates_and_inspects_store_without_send_or_secret(self) -> None:
        policy_path = self.root / "provider-transaction-policy.json"
        private_write(
            policy_path, canonical_bytes(self.grant.dispatch.transaction_policy)
        )
        cli_path = self.root / "cli-provider-transactions.sqlite"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-provider-transaction-store-create",
                        "--path",
                        str(cli_path),
                        "--provider-transaction-store-policy",
                        str(policy_path),
                        "--broker-grant-store",
                        str(self.grant.store.path),
                        "--routing-control-anchor",
                        str(self.runtime.sources.routing.control_anchor.path),
                        "--skill-control-anchor",
                        str(self.runtime.sources.control_anchor.path),
                        "--default-store",
                        str(self.runtime.sources.default_store.path),
                        "--spend-ledger",
                        str(self.runtime.ledger.path),
                    ]
                ),
                0,
            )
        self.assertEqual(
            json.loads(stdout.getvalue())["type"],
            "evaluation.skill_runtime.provider_transaction_store_created",
        )
        capability = self.grant.issue()
        secret = capability.claim().capability
        # The status command needs only hash-bearing issuance metadata.
        issuance_path = self.root / "issued-grant.json"
        private_write(issuance_path, canonical_bytes(capability.issuance))
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-provider-transaction-status",
                        "--issued-broker-grant",
                        str(issuance_path),
                        "--broker-grant-store",
                        str(self.grant.store.path),
                        "--provider-transaction-store",
                        str(cli_path),
                        "--spend-ledger",
                        str(self.runtime.ledger.path),
                    ]
                ),
                0,
            )
        status = json.loads(stdout.getvalue())
        self.assertEqual((status["phase"], status["ledger_status"]), ("absent", "held"))
        self.assertFalse(status["retry_permitted"])
        self.assertNotIn(secret, stdout.getvalue())
