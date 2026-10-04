"""Fresh briefs, durable parent charges, inspection and offline child boundaries."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from test_conversation_goal import definition

from mos_eisley.conversation import ConversationController, prepare_conversation_request
from mos_eisley.conversation_agents import (
    AgentInspectionScope,
    ImplementationAssignment,
)
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_input import ConversationInput
from mos_eisley.conversation_local_child import (
    LocalChildAuthorization,
    LocalChildExecution,
    LocalChildJob,
    child_system,
)
from mos_eisley.conversation_loop_commands import recorded_loop_observer
from mos_eisley.conversation_schedule import InertScheduleSpec, ScheduleBinding
from mos_eisley.conversation_schedule_driver import ActiveSessionTimers
from mos_eisley.conversation_state import ConversationState
from mos_eisley.core.agent import AgentConfig
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.duplex import ExchangeHandler
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.local_child import (
    ChildWire,
    DockerLocalChild,
    LocalChildAck,
    LocalChildOffer,
    replay_child,
)
from mos_eisley.task_state import ResourceCeiling

IMAGE = "sha256:" + "1" * 64


class FixtureExecutor:
    image_id = IMAGE

    def __init__(self) -> None:
        self.calls: list[LocalChildJob] = []
        self.started = asyncio.Event()
        self.release: asyncio.Event | None = None
        self.fail = False

    async def execute(self, job: LocalChildJob) -> LocalChildExecution:
        self.calls.append(job)
        self.started.set()
        if self.release is not None:
            await self.release.wait()
        if self.fail:
            raise OSError("Lost child acknowledgement")
        return await replay_child(job, self.image_id)


class LocalChildTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.executor = FixtureExecutor()
        self.approval_enabled = True
        cassette = demo_cassette()
        self.chat = ConversationController(
            ConversationController.fresh(self.root, cassette),
            cassette,
            lambda _: None,
            goal_clock=lambda: 100.0,
            local_child_executor=self.executor,
            local_child_authorizer=self.authorize,
        )
        self.chat.create_goal(definition())

    async def asyncTearDown(self) -> None:
        self.temporary.cleanup()

    def authorize(
        self, assignment: ImplementationAssignment, scope: AgentInspectionScope
    ) -> LocalChildAuthorization:
        if not self.approval_enabled:
            raise ValueError("Creator revoked the exact plan/test approval")
        return LocalChildAuthorization(
            scope=scope,
            assignment_sha256=assignment.sha256,
            workspace_observation_sha256=self.chat.observe_branch_workspace(
                str(self.root)
            ),
            expires_at=400.0,
        )

    def assignment(self) -> ImplementationAssignment:
        goal = self.chat.current_goal
        assert goal is not None
        return ImplementationAssignment(
            task_id="bounded-analysis",
            parent_task_id=goal.goal_id,
            objective="Propose a bounded implementation for the approved cache task.",
            provider="fixture",
            model="tool-reviewer-v1",
            effort="high",
            workspace=str(self.root),
            plan_sha256=digest(b"Frozen creator plan"),
            tests_sha256=digest(b"Frozen creator tests"),
            allowance=ResourceCeiling(
                input_bytes=32000,
                output_bytes=16384,
                attempts=1,
                cost_microusd=0,
                correction_cycles=0,
                review_rounds=0,
            ),
        )

    def job(self, assignment: ImplementationAssignment | None = None) -> LocalChildJob:
        a = assignment or self.assignment()
        config = AgentConfig(
            provider=a.provider,
            model=a.model,
            effort=a.effort,
            system=child_system(a),
            initial_turns=(Turn(role="user", blocks=(TextBlock(text=a.objective),)),),
            max_iterations=1,
            max_tool_calls=0,
            request_timeout_seconds=5,
        )
        request, _ = prepare_conversation_request(config)
        return LocalChildJob(
            assignment=a,
            config=config,
            cassette=AgentCassette(
                exchanges=(
                    AgentExchange(
                        request_sha256=digest(canonical_bytes(request)),
                        response=demo_cassette().exchanges[0].response,
                    ),
                )
            ),
        )

    async def run_child(self) -> None:
        job = self.job()
        await self.chat.run_local_child(
            job.assignment, job.cassette, expected_revision=self.chat.state.revision
        )

    async def test_fresh_brief_and_parent_charge_precede_execution(self) -> None:
        self.executor.release = asyncio.Event()
        task = asyncio.create_task(self.run_child())
        await self.executor.started.wait()
        record = self.chat.state.local_children[0]
        goal = self.chat.current_goal
        assert goal is not None
        self.assertEqual(record.state, "running")
        self.assertEqual(goal.ledger.attempts, 1)
        self.assertEqual(goal.jobs[0].operation_id, record.child_id)
        self.assertEqual(self.chat.state.entries, ())
        self.assertEqual(self.executor.calls[0].config.max_tool_calls, 0)
        with self.assertRaises(ValueError):
            await self.run_child()
        self.executor.release.set()
        await task
        view = self.chat.inspect_agents(record.child_id)
        self.assertEqual(view.report_status, "available")
        self.assertFalse(view.grants_authority)
        assert view.report is not None
        self.assertFalse(view.report.integration_approved)
        self.assertEqual(self.chat.state.exchanges_consumed, 0)
        self.assertEqual(self.chat.state.entries, ())

    async def test_private_stores_keep_committed_reports_without_replay(self) -> None:
        for kind in (ConversationStore, SQLiteConversationStore):
            initial = ConversationController.fresh(self.root, self.chat.cassette)
            with kind(
                self.root / kind.__name__, initial.session_id, self.root
            ) as store:
                store.save(initial)
                self.chat = ConversationController(
                    initial,
                    self.chat.cassette,
                    store.save,
                    goal_clock=lambda: 100.0,
                    local_child_executor=self.executor,
                    local_child_authorizer=self.authorize,
                )
                self.chat.create_goal(definition())
                await self.run_child()
                loaded = store.load()
                calls = len(self.executor.calls)
                resumed = ConversationController(
                    loaded,
                    self.chat.cassette,
                    store.save,
                    goal_clock=lambda: 100.0,
                    local_child_executor=self.executor,
                    local_child_authorizer=self.authorize,
                )
                self.assertEqual(len(self.executor.calls), calls)
                self.assertEqual(resumed.state.local_children, loaded.local_children)
                self.assertEqual(
                    resumed.inspect_agents().snapshot.children[-1].state, "completed"
                )

    async def test_failure_cancellation_and_restart_keep_exposure_once(self) -> None:
        self.executor.release = asyncio.Event()
        task = asyncio.create_task(self.run_child())
        await self.executor.started.wait()
        running = self.chat.state
        reserved = running.local_children[0].reserved
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.chat.state.local_children[0].state, "cancelled")
        restarted = ConversationController(
            running, self.chat.cassette, lambda _: None, goal_clock=lambda: 100.0
        )
        assert restarted.current_goal is not None
        self.assertEqual(
            restarted.current_goal.ledger.input_bytes, reserved.input_bytes
        )
        self.assertEqual(restarted.current_goal.ledger.uncertain_effects, 1)
        self.assertEqual(restarted.state.local_children[0].state, "uncertain")
        again = ConversationController(
            restarted.state, self.chat.cassette, lambda _: None
        )
        self.assertEqual(again.state.local_children, restarted.state.local_children)
        assert again.current_goal is not None
        self.assertEqual(again.current_goal.ledger.uncertain_effects, 1)

    async def test_lost_acknowledgement_blocks_new_dispatch_and_inspection_content(
        self,
    ) -> None:
        self.executor.fail = True
        with self.assertRaises(OSError):
            await self.run_child()
        before = self.chat.state
        with self.assertRaises(ValueError):
            await self.run_child()
        self.assertEqual(self.chat.state, before)
        child = before.local_children[0]
        self.assertEqual(
            self.chat.inspect_agents(child.child_id).report_status, "missing"
        )

    async def test_revision_approval_budget_and_workspace_fail_before_execution(
        self,
    ) -> None:
        job = self.job()
        with self.assertRaises(ValueError):
            await self.chat.run_local_child(
                job.assignment,
                job.cassette,
                expected_revision=self.chat.state.revision - 1,
            )
        self.approval_enabled = False
        with self.assertRaises(ValueError):
            await self.run_child()
        self.approval_enabled = True
        invalid = job.assignment.model_copy(
            update={"workspace": str(self.root / "other")}
        )
        with self.assertRaises(ValueError):
            await self.chat.run_local_child(
                invalid, job.cassette, expected_revision=self.chat.state.revision
            )
        tiny = job.assignment.model_copy(
            update={
                "allowance": job.assignment.allowance.model_copy(
                    update={"input_bytes": 1}
                )
            }
        )
        with self.assertRaises(ValueError):
            await self.chat.run_local_child(
                tiny, job.cassette, expected_revision=self.chat.state.revision
            )
        self.assertEqual(self.executor.calls, [])
        self.assertEqual(self.chat.state.local_children, ())

    async def test_revoked_approval_hides_committed_report(self) -> None:
        await self.run_child()
        child = self.chat.state.local_children[0]
        self.approval_enabled = False
        before = self.chat.state
        view = self.chat.inspect_agents(child.child_id)
        self.assertEqual(view.report_status, "stale")
        self.assertIsNone(view.report)
        self.assertEqual(self.chat.state, before)

    async def test_transcript_tools_paid_routes_and_worktrees_are_not_child_briefs(
        self,
    ) -> None:
        job = self.job()
        for config in (
            job.config.model_copy(update={"max_tool_calls": 1}),
            job.config.model_copy(update={"system": "Ambient parent transcript"}),
            job.config.model_copy(update={"max_iterations": 2}),
        ):
            with self.assertRaises(ValueError):
                LocalChildJob(
                    assignment=job.assignment, config=config, cassette=job.cassette
                )
        for assignment in (
            job.assignment.model_copy(update={"provider": "openai"}),
            job.assignment.model_copy(update={"worktree": str(self.root)}),
            job.assignment.model_copy(
                update={
                    "allowance": job.assignment.allowance.model_copy(
                        update={"cost_microusd": 1}
                    )
                }
            ),
        ):
            with self.assertRaises(ValueError):
                LocalChildJob(
                    assignment=assignment, config=job.config, cassette=job.cassette
                )

    async def test_failed_admission_save_dispatches_nothing(self) -> None:
        def fail(_: object) -> None:
            raise OSError("Store failed before admission")

        self.chat.save = fail
        with self.assertRaises(OSError):
            await self.run_child()
        self.assertEqual(self.executor.calls, [])

    async def test_committed_child_event_uses_existing_queue_and_coalesces(
        self,
    ) -> None:
        await self.run_child()
        child = self.chat.state.local_children[0]
        goal = self.chat.current_goal
        assert goal is not None
        self.chat.schedule_observer = recorded_loop_observer(self.chat)
        spec = InertScheduleSpec(
            schedule_id="child-watch",
            binding=ScheduleBinding(
                owner_uid=self.chat.state.owner_uid,
                session_id=self.chat.state.session_id,
                workspace_sha256=digest(str(self.root).encode()),
                revision_sha256="0" * 64,
                policy_sha256="0" * 64,
                goal_id=goal.goal_id,
                goal_definition_sha256=goal.definition.sha256,
                task_id=child.assignment.task_id,
            ),
            prompt="Inspect the committed local child result.",
            interval_seconds=100,
            minimum_interval_seconds=100,
            maximum_interval_seconds=100,
            expires_at=300,
            maximum_fires=1,
            ceiling=child.assignment.allowance,
            local_sources=(child.child_id,),
        )
        spec = spec.model_copy(update={"binding": self.chat.schedule_observer(spec)})
        self.chat.add_schedule(spec, expected_revision=self.chat.state.revision)
        event = self.chat.local_child_event("child-watch", child.child_id)
        self.chat.validate_local_child_event(event)
        for altered in (
            event.model_copy(update={"payload_sha256": "f" * 64}),
            event.model_copy(update={"kind": "local_test"}),
            event.model_copy(update={"sequence": 2}),
        ):
            with self.assertRaises(ValueError):
                self.chat.validate_local_child_event(altered)
        timers = ActiveSessionTimers(self.chat, lambda _: None)
        timers.open()
        try:
            # The result wakes before its timer, without injecting report content.
            self.assertEqual(len(timers.tick()), 1)
            self.assertEqual(len(self.chat.state.entries), 1)
            self.assertEqual(self.chat.state.entries[0].text, spec.prompt)
            before = self.chat.state
            self.assertEqual(timers.tick(), ())
            self.assertEqual(self.chat.state, before)
            self.assertEqual(self.chat.state.schedules[0].state.accepted_events, 1)
            self.assertEqual(self.chat.state.schedules[0].state.pending_events, 0)
        finally:
            timers.close()

    async def test_child_state_cannot_cross_owner_or_lose_its_job_binding(self) -> None:
        await self.run_child()
        state = self.chat.state
        child = state.local_children[0]
        for changed in (
            child.model_copy(
                update={
                    "authorization": child.authorization.model_copy(
                        update={
                            "scope": child.authorization.scope.model_copy(
                                update={"owner_uid": state.owner_uid + 1}
                            )
                        }
                    )
                }
            ),
            child.model_copy(update={"child_id": "another-operation"}),
        ):
            with self.assertRaises(ValueError):
                ConversationState.model_validate_json(
                    state.model_copy(
                        update={"local_children": (changed,)}
                    ).model_dump_json()
                )

    async def test_container_exchange_binds_offer_image_and_result(self) -> None:
        class Container(OfflineContainer):
            corrupt = False

            async def exchange_async(
                self,
                arguments: tuple[str, ...],
                payload: bytes,
                exchange_handler: ExchangeHandler,
                timeout: float = 30,
            ) -> bytes:
                if arguments != ("-m", "mos_eisley.run.local_child_worker"):
                    raise AssertionError("Unexpected worker")
                self_test.assertEqual(timeout, 5)
                offer = LocalChildOffer.model_validate_json(payload)
                wire = ChildWire.model_validate_json(await exchange_handler(payload))
                self_test.assertEqual(
                    digest(canonical_bytes(wire.job)), offer.job_sha256
                )
                result = await replay_child(wire.job, wire.image_id)
                return canonical_bytes(
                    LocalChildAck(
                        job_sha256=offer.job_sha256,
                        execution_sha256="f" * 64
                        if self.corrupt
                        else digest(canonical_bytes(result)),
                    )
                )

        self_test = self
        container = Container(Path("/explicit/docker"), IMAGE)
        adapter = DockerLocalChild(container)
        job = self.job()
        expected = await replay_child(job, IMAGE)
        self.assertEqual(await adapter.execute(job), expected)
        container.corrupt = True
        with self.assertRaises(ValueError):
            await adapter.execute(job)

    async def test_expired_and_cross_owner_authorizations_dispatch_nothing(
        self,
    ) -> None:
        original = self.chat.local_child_authorizer
        assert original is not None
        for change in ("expiry", "owner", "assignment"):

            def altered(
                assignment: ImplementationAssignment,
                scope: AgentInspectionScope,
                change: str = change,
            ) -> LocalChildAuthorization:
                approval = original(assignment, scope)
                if change == "expiry":
                    return approval.model_copy(update={"expires_at": 100.0})
                if change == "assignment":
                    return approval.model_copy(update={"assignment_sha256": "f" * 64})
                return approval.model_copy(
                    update={
                        "scope": scope.model_copy(
                            update={"owner_uid": scope.owner_uid + 1}
                        )
                    }
                )

            self.chat.local_child_authorizer = altered
            with self.assertRaises(ValueError):
                await self.run_child()
            self.assertEqual(self.executor.calls, [])
            self.assertEqual(self.chat.state.local_children, ())

    async def test_result_after_revocation_never_creates_a_report(self) -> None:
        self.executor.release = asyncio.Event()
        task = asyncio.create_task(self.run_child())
        await self.executor.started.wait()
        self.approval_enabled = False
        self.executor.release.set()
        with self.assertRaises(ValueError):
            await task
        self.assertEqual(self.chat.state.local_children[0].state, "uncertain")
        self.assertIsNone(self.chat.state.local_children[0].report)
        assert self.chat.current_goal is not None
        self.assertEqual(self.chat.current_goal.ledger.uncertain_effects, 1)

    async def test_goal_cancel_propagates_and_survives_child_failure_and_restart(
        self,
    ) -> None:
        self.executor.release = asyncio.Event()
        task = asyncio.create_task(self.run_child())
        await self.executor.started.wait()
        self.chat.goal_control("cancel")
        with self.assertRaises(asyncio.CancelledError):
            await task
        assert self.chat.current_goal is not None
        self.assertEqual(self.chat.current_goal.status, "cancelled")
        self.assertEqual(self.chat.state.local_children[0].state, "cancelled")
        self.assertEqual(self.chat.current_goal.ledger.uncertain_effects, 1)
        restarted = ConversationController(
            self.chat.state, self.chat.cassette, lambda _: None
        )
        assert restarted.current_goal is not None
        self.assertEqual(restarted.current_goal.status, "cancelled")
        self.assertEqual(restarted.current_goal.ledger.uncertain_effects, 1)
        with self.assertRaises(ValueError):
            restarted.goal_control("resume")

    async def test_terminal_exit_awaits_owned_child_cleanup(self) -> None:
        self.executor.release = asyncio.Event()
        operation = asyncio.create_task(self.run_child())
        await self.executor.started.wait()
        queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
        queue.put_nowait("/quit")
        await asyncio.wait_for(terminal(self.chat, queue, lambda _: None), 2)
        self.assertTrue(operation.done())
        with self.assertRaises(asyncio.CancelledError):
            await operation
        assert self.chat.current_goal is not None
        self.assertEqual(self.chat.state.local_children[0].state, "cancelled")
        self.assertEqual(self.chat.current_goal.ledger.uncertain_effects, 1)
