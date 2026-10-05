"""Actual offline child exchange, parent reservation and retained store reports."""

import asyncio
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from mos_eisley.conversation import ConversationController, prepare_conversation_request
from mos_eisley.conversation_agents import (
    AgentInspectionScope,
    ImplementationAssignment,
)
from mos_eisley.conversation_branch_controller import observe_branch_workspace
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_goal import GoalDefinition
from mos_eisley.conversation_local_child import LocalChildAuthorization, child_system
from mos_eisley.core.agent import AgentConfig
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.duplex import ExchangeHandler
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.local_child import DockerLocalChild
from mos_eisley.run.process import bounded_process
from mos_eisley.task_state import ResourceCeiling


class WaitingChildContainer(OfflineContainer):
    """Hold the real worker at its host exchange to exercise propagated cancel."""

    def __init__(self, docker: Path, image: str, root: Path):
        super().__init__(docker, image, root)
        self.started = asyncio.Event()

    async def exchange_async(
        self,
        arguments: tuple[str, ...],
        payload: bytes,
        exchange_handler: ExchangeHandler,
        timeout: float = 30,
    ) -> bytes:
        async def held(claim: bytes) -> bytes:
            self.started.set()
            await asyncio.Event().wait()
            return await exchange_handler(claim)

        return await super().exchange_async(arguments, payload, held, timeout)


async def exercise(root: Path, docker: Path, image: str) -> None:
    for backend in (ConversationStore, SQLiteConversationStore):
        cassette = demo_cassette()
        initial = ConversationController.fresh(root, cassette)
        approved: set[str] = set()

        def authorize(
            assignment: ImplementationAssignment,
            scope: AgentInspectionScope,
            approved: set[str] = approved,
        ) -> LocalChildAuthorization:
            if assignment.sha256 not in approved:
                raise ValueError("Fixture assignment was not explicitly approved.")
            return LocalChildAuthorization(
                scope=scope,
                assignment_sha256=assignment.sha256,
                workspace_observation_sha256=observe_branch_workspace(str(root)),
                expires_at=1000,
            )

        with backend(root / backend.__name__, initial.session_id, root) as store:
            store.save(initial)
            chat = ConversationController(
                initial,
                cassette,
                store.save,
                goal_clock=lambda: 100.0,
                local_child_authorizer=authorize,
                local_child_executor=DockerLocalChild(
                    OfflineContainer(docker, image, root / "lifecycles")
                ),
            )
            goal = chat.create_goal(
                GoalDefinition(
                    objective="Analyze a bounded implementation fixture",
                    success_criteria=("Retain a creator-reviewable proposal",),
                    remaining_work=("Analyze the explicit brief",),
                )
            )
            assignment = ImplementationAssignment(
                task_id="local-proposal",
                parent_task_id=goal.goal_id,
                objective="Propose a bounded cache design for creator integration.",
                provider="fixture",
                model="tool-reviewer-v1",
                effort="high",
                workspace=str(root),
                plan_sha256=digest(b"Frozen smoke-fixture plan"),
                tests_sha256=digest(b"Frozen smoke-fixture tests"),
                allowance=ResourceCeiling(
                    input_bytes=32000,
                    output_bytes=16000,
                    attempts=1,
                    cost_microusd=0,
                    correction_cycles=0,
                    review_rounds=0,
                ),
            )
            config = AgentConfig(
                provider=assignment.provider,
                model=assignment.model,
                effort=assignment.effort,
                system=child_system(assignment),
                initial_turns=(
                    Turn(role="user", blocks=(TextBlock(text=assignment.objective),)),
                ),
                max_iterations=1,
                max_tool_calls=0,
                request_timeout_seconds=5,
            )
            request, _ = prepare_conversation_request(config)
            child_recording = AgentCassette(
                exchanges=(
                    AgentExchange(
                        request_sha256=digest(canonical_bytes(request)),
                        response=cassette.exchanges[0].response,
                    ),
                )
            )
            approved.add(assignment.sha256)
            report = await chat.run_local_child(
                assignment, child_recording, expected_revision=chat.state.revision
            )
            loaded = store.load()
            assert loaded.local_children[0].report == report
            assert chat.inspect_agents(report.child_id).report_status == "available"
            assert not report.integration_approved
            assert loaded.entries == () and loaded.exchanges_consumed == 0
            assert loaded.goals[0].ledger.attempts == 1
            assert loaded.goals[0].jobs[0].state == "passed"
            waiting = WaitingChildContainer(docker, image, root / "cancel-lifecycles")
            chat.local_child_executor = DockerLocalChild(waiting)
            operation = asyncio.create_task(
                chat.run_local_child(
                    assignment, child_recording, expected_revision=chat.state.revision
                )
            )
            await asyncio.wait_for(waiting.started.wait(), 10)
            chat.goal_control("cancel")
            try:
                await operation
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("Goal cancellation did not reach its child.")
            cancelled = store.load()
            assert cancelled.local_children[-1].state == "cancelled"
            assert cancelled.goals[0].status == "cancelled"
            assert cancelled.goals[0].ledger.attempts == 2
            assert cancelled.goals[0].ledger.uncertain_effects == 1
            approved.clear()
            assert chat.inspect_agents(report.child_id).report_status == "stale"
            assert chat.inspect_agents(report.child_id).report is None
    print("Offline local child execution and both retained report backends passed.")


def main() -> int:
    executable = shutil.which("docker")
    if executable is None:
        raise ValueError("Docker is required for local execution qualification.")
    docker = Path(executable).absolute()
    image = (
        bounded_process(
            [str(docker), "image", "inspect", "--format", "{{.Id}}", "mos-eisley:local"]
        )
        .decode()
        .strip()
    )
    with TemporaryDirectory() as temporary:
        asyncio.run(exercise(Path(temporary).resolve(), docker, image))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
