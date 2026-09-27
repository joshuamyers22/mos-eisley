"""Offline G6 one-use, stop-race and crash-conservative transaction tests."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import (
    ModelRequest,
    TextBlock,
    ToolDefinition,
    ToolSchema,
    Turn,
)
from mos_eisley.run.exact_route import (
    ExactRouteRequirements,
    ExactRouteSelection,
)
from mos_eisley.run.routing_preflight import RoutingRuntimePreflight
from mos_eisley.run.routing_transaction import (
    InertRoutingResponse,
    InertRoutingTransport,
    OfflineExecutionProfile,
    OfflineRoutingEnvelope,
    OfflineTransactionStore,
    SyntheticRoutingBudget,
    SyntheticRoutingMonitor,
    SyntheticRoutingWitness,
    execute_offline_routing_transaction,
    inspect_offline_routing_transaction,
    offline_provider_options_sha256,
    offline_toolset_sha256,
)
from tests import test_exact_route as route_module


def run_cut_from_bundle(bundle_path: str, cut_name: str) -> None:
    """Subprocess entry point: kill after an actual SQLite commit barrier."""
    root = Path(bundle_path).parent
    bundle = json.loads(Path(bundle_path).read_text())
    envelope = OfflineRoutingEnvelope.model_validate_json(
        json.dumps(bundle["envelope"])
    )
    selection = ExactRouteSelection.model_validate_json(json.dumps(bundle["selection"]))
    preflight = RoutingRuntimePreflight.model_validate_json(
        json.dumps(bundle["preflight"])
    )
    requirements = ExactRouteRequirements.model_validate_json(
        json.dumps(bundle["requirements"])
    )
    profile = OfflineExecutionProfile.model_validate_json(json.dumps(bundle["profile"]))
    request = ModelRequest.model_validate_json(json.dumps(bundle["request"]))
    witness = SyntheticRoutingWitness(root / "witness.sqlite")
    budget = SyntheticRoutingBudget(root / "budget.sqlite")
    store = OfflineTransactionStore(root / "transaction.sqlite")

    transport = InertRoutingTransport(
        provider=selection.route.provider,
        backend=selection.route.backend,
        client_version=selection.route.client_version,
        response=InertRoutingResponse(
            provider=selection.route.provider,
            model=selection.route.model,
            service_tier="default",
            input_tokens=1,
            output_tokens=1,
            charged_microusd=2,
        ),
        entry_log_path=root / "entries.log",
        exit_at_entry=cut_name == "transport_entered",
    )
    monitor = SyntheticRoutingMonitor()

    def kill_at(phase: str) -> None:
        if phase == cut_name:
            os._exit(77)

    asyncio.run(
        execute_offline_routing_transaction(
            envelope=envelope,
            selection=selection,
            preflight=preflight,
            requirements=requirements,
            profile=profile,
            request=request,
            witness=witness,
            budget=budget,
            store=store,
            transport=transport,
            monitor=monitor,
            now=preflight.checked_at,
            fault=kill_at,
        )
    )


class OfflineRoutingTransactionTests(TestCase):
    def setUp(self) -> None:
        self.route_fixture = route_module.ExactRouteTests()
        self.route_fixture.setUp()
        resolved = self.route_fixture.resolve()
        assert isinstance(resolved, ExactRouteSelection)
        self.selection = resolved
        self.preflight = self.route_fixture.preflight
        self.requirements = self.route_fixture.requirements
        self.now = self.route_fixture.now
        tool = ToolDefinition(
            name="read-file",
            description="Read a synthetic file",
            input_schema=ToolSchema(type="object"),
        )
        self.request = ModelRequest(
            provider=resolved.route.provider,
            model=resolved.route.model,
            effort=resolved.route.effort,
            system=resolved.route.prompt.instructions,
            tools=(tool,),
            turns=(Turn(role="user", blocks=(TextBlock(text="Synthetic task"),)),),
            max_output=1000,
            max_output_tokens=50,
        )
        self.profile = OfflineExecutionProfile(
            role=self.requirements.role,
            output_contract=self.requirements.output_contract,
            requires_structured_output=self.requirements.requires_structured_output,
            tool_names=self.requirements.tool_requirements,
            tools_sha256=offline_toolset_sha256(self.request.tools),
            provider_options_sha256=offline_provider_options_sha256(),
            max_context_bytes=10_000,
            max_output_bytes=self.request.max_output,
            max_output_tokens=50,
            max_input_tokens=50,
            input_microusd_per_token=1,
            output_microusd_per_token=1,
        )
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.witness = SyntheticRoutingWitness.create(
            self.root / "witness.sqlite", "a" * 64
        )
        self.budget = SyntheticRoutingBudget.create(
            self.root / "budget.sqlite",
            owner_id="owner-a",
            cohort_id="cohort-a",
            task_ceiling_microusd=100,
            session_ceiling_microusd=150,
            cohort_ceiling_microusd=200,
        )
        self.store = OfflineTransactionStore.create(
            self.root / "transaction.sqlite",
            owner_id="owner-a",
            cohort_id="cohort-a",
            witness=self.witness,
            budget=self.budget,
        )
        self.envelope = OfflineRoutingEnvelope(
            owner_id="owner-a",
            cohort_id="cohort-a",
            session_id="session-a",
            task_id="task-a",
            stage_id="stage-a",
            attempt_id="attempt-a",
            selection_sha256=digest(canonical_bytes(self.selection)),
            profile_sha256=self.profile.profile_sha256,
            request_sha256=digest(canonical_bytes(self.request)),
            control_sequence=0,
            control_digest="a" * 64,
            maximum_microusd=100,
        )
        self.transport = self.make_transport()
        self.monitor = SyntheticRoutingMonitor()

    def make_transport(
        self,
        response: InertRoutingResponse | None = None,
        error: BaseException | None = None,
    ) -> InertRoutingTransport:
        return InertRoutingTransport(
            provider=self.selection.route.provider,
            backend=self.selection.route.backend,
            client_version=self.selection.route.client_version,
            response=response
            or InertRoutingResponse(
                provider=self.selection.route.provider,
                model=self.selection.route.model,
                service_tier="default",
                input_tokens=10,
                output_tokens=5,
                charged_microusd=15,
            ),
            error=error,
        )

    def run_transaction(self, **changes: object) -> object:
        values: dict[str, object] = {
            "envelope": self.envelope,
            "selection": self.selection,
            "preflight": self.preflight,
            "requirements": self.requirements,
            "profile": self.profile,
            "request": self.request,
            "witness": self.witness,
            "budget": self.budget,
            "store": self.store,
            "transport": self.transport,
            "monitor": self.monitor,
            "now": self.now,
        }
        values.update(changes)
        return asyncio.run(execute_offline_routing_transaction(**values))  # type: ignore[arg-type]

    def status(self) -> object:
        return inspect_offline_routing_transaction(
            self.envelope, self.witness, self.budget, self.store
        )

    def bundle(self) -> dict[str, object]:
        return {
            "envelope": self.envelope.model_dump(mode="json"),
            "selection": self.selection.model_dump(mode="json"),
            "preflight": self.preflight.model_dump(mode="json"),
            "requirements": self.requirements.model_dump(mode="json"),
            "profile": self.profile.model_dump(mode="json"),
            "request": self.request.model_dump(mode="json"),
        }

    def test_exact_request_commits_once_and_settles(self) -> None:
        outcome = self.run_transaction()
        self.assertEqual(outcome.status, "settled")  # type: ignore[attr-defined]
        self.assertEqual(self.transport.entries, [self.envelope.request_sha256])
        status = inspect_offline_routing_transaction(
            self.envelope, self.witness, self.budget, self.store
        )
        self.assertEqual((status.phase, status.budget_status), ("finished", "settled"))
        with self.assertRaises((sqlite3.IntegrityError, ValueError)):
            self.run_transaction()
        self.assertEqual(len(self.transport.entries), 1)
        raw = (self.root / "transaction.sqlite").read_bytes()
        self.assertNotIn(b"Economy review.", raw)
        self.assertNotIn(b"Synthetic task", raw)

    def test_request_and_transport_drift_denied_before_spend(self) -> None:
        variants: list[tuple[str, object]] = [
            ("request", self.request.model_copy(update={"effort": "medium"})),
            ("request", self.request.model_copy(update={"system": "Changed"})),
            ("request", self.request.model_copy(update={"max_output": 500})),
            ("profile", self.profile.model_copy(update={"tools_sha256": "b" * 64})),
            (
                "transport",
                InertRoutingTransport(
                    provider="other", backend="fixture", client_version="fixture/1"
                ),
            ),
        ]
        for field, value in variants:
            with self.subTest(field=field, value=str(value)[:40]):
                with self.assertRaises(ValueError):
                    self.run_transaction(**{field: value})
                self.assertIsNone(self.budget.inspect(self.envelope.attempt_key))
                self.assertIsNone(self.witness.inspect_claim(self.envelope.attempt_key))

    def test_transport_retry_setting_denied_before_reservation(self) -> None:
        with (
            patch.object(self.transport, "automatic_retries", 1),
            self.assertRaises(ValueError),
        ):
            self.run_transaction()
        self.assertIsNone(self.budget.inspect(self.envelope.attempt_key))
        self.assertEqual(self.transport.entries, [])

    def test_stop_before_claim_keeps_reservation_and_does_not_send(self) -> None:
        def stop(phase: str) -> None:
            if phase == "after_reserve":
                self.witness.stop("b" * 64)

        with self.assertRaises(ValueError):
            self.run_transaction(fault=stop)
        status = inspect_offline_routing_transaction(
            self.envelope, self.witness, self.budget, self.store
        )
        self.assertEqual((status.phase, status.budget_status), ("reserved", "held"))
        self.assertEqual(self.transport.entries, [])

    def test_stop_after_claim_abandons_before_send(self) -> None:
        def stop(phase: str) -> None:
            if phase == "after_claim":
                self.witness.stop("b" * 64)

        outcome = self.run_transaction(fault=stop)
        self.assertEqual(outcome.status, "abandoned")  # type: ignore[attr-defined]
        self.assertEqual(self.transport.entries, [])
        self.assertEqual(self.budget.inspect(self.envelope.attempt_key).status, "held")  # type: ignore[union-attr]

    def test_monitor_outage_at_admission_and_final_check(self) -> None:
        self.monitor.healthy = False
        with self.assertRaises(ValueError):
            self.run_transaction()
        self.assertIsNone(self.budget.inspect(self.envelope.attempt_key))
        self.monitor.healthy = True

        def lose_monitor(phase: str) -> None:
            if phase == "after_claim":
                self.monitor.healthy = False

        outcome = self.run_transaction(fault=lose_monitor)
        self.assertEqual(outcome.status, "abandoned")  # type: ignore[attr-defined]
        self.assertEqual(self.transport.entries, [])

    def test_stop_after_final_check_can_leave_one_in_flight(self) -> None:
        def stop(phase: str) -> None:
            if phase == "after_final_check":
                self.witness.stop("b" * 64)

        outcome = self.run_transaction(fault=stop)
        self.assertEqual(outcome.status, "settled")  # type: ignore[attr-defined]
        self.assertEqual(len(self.transport.entries), 1)

    def test_transport_failure_is_uncertain_and_full_hold(self) -> None:
        self.transport = self.make_transport(error=RuntimeError("synthetic timeout"))
        outcome = self.run_transaction()
        self.assertEqual(outcome.status, "uncertain")  # type: ignore[attr-defined]
        entry = self.budget.inspect(self.envelope.attempt_key)
        self.assertEqual((entry.status, entry.charged_microusd), ("uncertain", 100))  # type: ignore[union-attr]
        self.assertEqual(len(self.transport.entries), 1)

    def test_cancellation_after_entry_is_uncertain(self) -> None:
        def cancel(phase: str) -> None:
            if phase == "after_final_check":
                task = asyncio.current_task()
                assert task is not None
                asyncio.get_running_loop().call_soon(task.cancel)

        with self.assertRaises(asyncio.CancelledError):
            self.run_transaction(fault=cancel)
        status = inspect_offline_routing_transaction(
            self.envelope, self.witness, self.budget, self.store
        )
        self.assertEqual(
            (status.outcome, status.budget_status), ("uncertain", "uncertain")
        )
        self.assertEqual(len(self.transport.entries), 1)

    def test_witness_timeout_after_reserve_never_sends(self) -> None:
        with (
            patch.object(self.witness, "claim", side_effect=TimeoutError("synthetic")),
            self.assertRaises(TimeoutError),
        ):
            self.run_transaction()
        status = inspect_offline_routing_transaction(
            self.envelope, self.witness, self.budget, self.store
        )
        self.assertEqual((status.phase, status.budget_status), ("reserved", "held"))
        self.assertEqual(self.transport.entries, [])

    def test_wrong_provider_or_price_is_violation(self) -> None:
        self.transport = self.make_transport(
            InertRoutingResponse(
                provider="wrong",
                model=self.request.model,
                service_tier="default",
                input_tokens=1,
                output_tokens=1,
                charged_microusd=5,
            )
        )
        outcome = self.run_transaction()
        self.assertEqual(outcome.status, "violation")  # type: ignore[attr-defined]
        entry = self.budget.inspect(self.envelope.attempt_key)
        assert entry is not None
        self.assertEqual(entry.charged_microusd, 100)
        with self.assertRaises(ValueError):
            self.run_transaction(
                envelope=self.envelope.model_copy(
                    update={"attempt_id": "attempt-b", "task_id": "task-b"}
                )
            )

    def test_wrong_price_is_violation(self) -> None:
        self.transport = self.make_transport(
            InertRoutingResponse(
                provider=self.request.provider,
                model=self.request.model,
                service_tier="default",
                input_tokens=10,
                output_tokens=5,
                charged_microusd=1,
            )
        )
        outcome = self.run_transaction()
        self.assertEqual(outcome.status, "violation")  # type: ignore[attr-defined]

    def test_owner_replay_and_expired_preflight_deny_before_reserve(self) -> None:
        with self.assertRaises(ValueError):
            self.run_transaction(
                envelope=self.envelope.model_copy(update={"owner_id": "owner-b"})
            )
        with self.assertRaises(ValueError):
            self.run_transaction(now=self.preflight.valid_until)
        self.assertIsNone(self.budget.inspect(self.envelope.attempt_key))

    def test_caps_and_duplicate_id_are_atomic(self) -> None:
        first = self.budget.reserve(self.envelope)
        self.assertEqual(first.status, "held")
        with self.assertRaises(ValueError):
            self.budget.reserve(self.envelope)
        second = self.envelope.model_copy(
            update={
                "attempt_id": "attempt-b",
                "task_id": "task-b",
                "maximum_microusd": 60,
            }
        )
        with self.assertRaises(ValueError):
            self.budget.reserve(second)
        self.assertIsNone(self.budget.inspect(second.attempt_key))

    def test_each_budget_scope_can_deny_without_partial_reservation(self) -> None:
        for scope in ("task", "session", "cohort"):
            with self.subTest(scope=scope):
                path = self.root / f"budget-{scope}.sqlite"
                kwargs = {
                    "task_ceiling_microusd": 200,
                    "session_ceiling_microusd": 200,
                    "cohort_ceiling_microusd": 200,
                }
                kwargs[f"{scope}_ceiling_microusd"] = 99
                budget = SyntheticRoutingBudget.create(
                    path, owner_id="owner-a", cohort_id="cohort-a", **kwargs
                )
                with self.assertRaises(ValueError):
                    budget.reserve(self.envelope)
                self.assertIsNone(budget.inspect(self.envelope.attempt_key))

    def test_threaded_duplicate_has_one_local_entry(self) -> None:
        def run_one() -> str:
            try:
                self.run_transaction()
                return "sent"
            except (ValueError, sqlite3.IntegrityError):
                return "denied"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run_one) for _ in range(2)]
            results = [future.result() for future in futures]
        self.assertEqual(sorted(results), ["denied", "sent"])
        self.assertEqual(len(self.transport.entries), 1)

    def test_process_kills_preserve_partial_state_without_retry(self) -> None:
        bundle = self.bundle()
        for cut, phase in (
            ("before_reserve", "absent"),
            ("after_reserve", "reserved"),
            ("after_claim", "claimed"),
            ("after_intent", "intent"),
            ("transport_entered", "intent"),
        ):
            with self.subTest(cut=cut), TemporaryDirectory() as temporary:
                root = Path(temporary)
                witness = SyntheticRoutingWitness.create(
                    root / "witness.sqlite", "a" * 64
                )
                budget = SyntheticRoutingBudget.create(
                    root / "budget.sqlite",
                    owner_id="owner-a",
                    cohort_id="cohort-a",
                    task_ceiling_microusd=100,
                    session_ceiling_microusd=150,
                    cohort_ceiling_microusd=200,
                )
                store = OfflineTransactionStore.create(
                    root / "transaction.sqlite",
                    owner_id="owner-a",
                    cohort_id="cohort-a",
                    witness=witness,
                    budget=budget,
                )
                bundle_path = root / "bundle.json"
                bundle_path.write_text(json.dumps(bundle))
                process = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "import sys; from tests.test_routing_transaction import "
                        "run_cut_from_bundle; "
                        "run_cut_from_bundle(sys.argv[1], sys.argv[2])",
                        str(bundle_path),
                        cut,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(process.returncode, 77, process.stderr)
                status = inspect_offline_routing_transaction(
                    self.envelope, witness, budget, store
                )
                expected_budget = "absent" if cut == "before_reserve" else "held"
                self.assertEqual(
                    (status.phase, status.budget_status), (phase, expected_budget)
                )
                self.assertFalse(status.retry_permitted)
                if cut == "transport_entered":
                    self.assertEqual((root / "entries.log").read_text(), "entered\n")
                if cut != "before_reserve":
                    with self.assertRaises(ValueError):
                        self.run_transaction(
                            witness=witness, budget=budget, store=store
                        )
                self.assertEqual(self.transport.entries, [])

    def test_two_processes_consume_one_attempt(self) -> None:
        bundle_path = self.root / "bundle.json"
        bundle_path.write_text(json.dumps(self.bundle()))
        command = [
            sys.executable,
            "-c",
            "import sys; from tests.test_routing_transaction import "
            "run_cut_from_bundle; "
            "run_cut_from_bundle(sys.argv[1], sys.argv[2])",
            str(bundle_path),
            "no_cut",
        ]
        processes = [
            subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(2)
        ]
        results = [process.communicate(timeout=10) for process in processes]
        self.assertEqual(sorted(process.returncode for process in processes), [0, 1])
        self.assertEqual(
            (self.root / "entries.log").read_text().splitlines(), ["entered"]
        )
        self.assertEqual(len(results), 2)
        status = inspect_offline_routing_transaction(
            self.envelope, self.witness, self.budget, self.store
        )
        self.assertEqual(status.phase, "finished")

    def test_settlement_and_outcome_write_failures_remain_visible(self) -> None:
        with (
            patch.object(self.store, "finish", side_effect=OSError("synthetic fsync")),
            self.assertRaises(OSError),
        ):
            self.run_transaction()
        status = inspect_offline_routing_transaction(
            self.envelope, self.witness, self.budget, self.store
        )
        self.assertEqual((status.phase, status.budget_status), ("intent", "settled"))
        self.assertEqual(len(self.transport.entries), 1)

    def test_budget_settlement_failure_leaves_held_intent(self) -> None:
        with (
            patch.object(self.budget, "settle", side_effect=OSError("synthetic fsync")),
            self.assertRaises(OSError),
        ):
            self.run_transaction()
        status = inspect_offline_routing_transaction(
            self.envelope, self.witness, self.budget, self.store
        )
        self.assertEqual((status.phase, status.budget_status), ("intent", "held"))
        self.assertEqual(len(self.transport.entries), 1)

    def test_intent_commit_failure_prevents_transport(self) -> None:
        with (
            patch.object(
                self.store, "record_before_send", side_effect=OSError("synthetic fsync")
            ),
            self.assertRaises(OSError),
        ):
            self.run_transaction()
        status = inspect_offline_routing_transaction(
            self.envelope, self.witness, self.budget, self.store
        )
        self.assertEqual((status.phase, status.budget_status), ("claimed", "held"))
        self.assertEqual(self.transport.entries, [])

    def test_local_copy_does_not_reclaim_same_attempt(self) -> None:
        copy_path = self.root / "old.sqlite"
        shutil.copyfile(self.root / "transaction.sqlite", copy_path)
        self.run_transaction()
        shutil.copyfile(copy_path, self.root / "transaction.sqlite")
        with self.assertRaises((ValueError, sqlite3.IntegrityError)):
            self.run_transaction()
        self.assertEqual(len(self.transport.entries), 1)
