"""Real Docker coding, creator-owned tests, VCS handoff and final integration."""

import asyncio
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from mos_eisley.coding_child import (
    CodeFile,
    CodeSnapshot,
    CodingBrief,
    CodingIntegrationApproval,
    CodingPatch,
    CodingReview,
    FileChange,
)
from mos_eisley.conversation import ConversationController, prepare_conversation_request
from mos_eisley.conversation_agents import (
    AgentInspectionScope,
    ImplementationAssignment,
)
from mos_eisley.conversation_branch_controller import observe_branch_workspace
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_goal import GoalDefinition
from mos_eisley.conversation_local_child import (
    LocalChildAuthorization,
    LocalChildRecord,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn, Usage
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.coding_child import (
    CodingContainer,
    DockerCodingChild,
    coding_config,
)
from mos_eisley.run.coding_vcs import CodingVCS
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.duplex import ExchangeHandler
from mos_eisley.run.process import bounded_process
from mos_eisley.task_state import ResourceCeiling

SOURCE = "def clamp(value, low, high):\n    return value\n"
IMPLEMENTED = (
    "def clamp(value, low, high):\n    if low > high:\n"
    '        raise ValueError("Invalid bounds")\n'
    "    return max(low, min(high, value))\n"
)
TESTS = (
    "import unittest\nfrom clamp import clamp\n"
    "class ClampTests(unittest.TestCase):\n"
    "    def test_values(self):\n"
    "        self.assertEqual(clamp(-9, 0, 3), 0)\n"
    "        self.assertEqual(clamp(8, 0, 3), 3)\n"
    "        self.assertEqual(clamp(2, 0, 3), 2)\n"
    "    def test_invalid(self):\n"
    "        with self.assertRaises(ValueError): clamp(2, 3, 0)\n"
    "    def test_isolation(self):\n"
    "        import os\n"
    "        self.assertEqual(os.getuid(), 10002)\n"
    "        with self.assertRaises(PermissionError):\n"
    "            open('clamp.py', 'w')\n"
    "        with self.assertRaises(PermissionError):\n"
    "            os.kill(os.getppid(), 0)\n"
)


class HeldCodingContainer(CodingContainer):
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
        async def hold(_: bytes) -> bytes:
            self.started.set()
            await asyncio.Event().wait()
            raise ValueError("Cancelled fixture must not dispatch its payload.")

        return await super().exchange_async(arguments, payload, hold, timeout)


async def exercise(root: Path, docker: Path, image: str) -> None:
    for backend in (ConversationStore, SQLiteConversationStore):
        workspace = root / backend.__name__ / "repo"
        workspace.mkdir(parents=True)

        def git(*args: str, workspace: Path = workspace) -> str:
            return (
                subprocess.check_output(["/usr/bin/git", "-C", str(workspace), *args])
                .decode()
                .strip()
            )

        git("init", "-q")
        (workspace / "clamp.py").write_text(SOURCE)
        (workspace / "tests").mkdir()
        (workspace / "tests/test_clamp.py").write_text(TESTS)
        git("add", ".")
        git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Creator plan tests before child",
        )
        broker = CodingVCS(
            Path("/usr/bin/git"), workspace, root / backend.__name__ / "staging"
        )
        executor = DockerCodingChild(
            CodingContainer(docker, image, root / "lifecycles")
        )
        approved: set[str] = set()
        integration_approved: set[str] = set()

        def review(brief: CodingBrief, patch: CodingPatch | None) -> CodingReview:
            # Fixed independent recorded critic/judge inputs are checked exactly.
            if (
                next(
                    f.content
                    for f in brief.snapshot.files
                    if f.path == "tests/test_clamp.py"
                )
                != TESTS
            ):
                raise ValueError(
                    "Recorded plan/test review differs from the creator tests."
                )
            if patch is not None and patch.changes[0].file.content != IMPLEMENTED:
                raise ValueError("Final recorded review rejects this implementation.")
            return CodingReview(
                brief_sha256=brief.sha256,
                plan_sha256=brief.assignment.plan_sha256,
                tests_sha256=brief.assignment.tests_sha256,
                phase="plan_tests" if patch is None else "final",
                patch_sha256=None if patch is None else patch.sha256,
                critic_sha256=digest(
                    b"Recorded critic: require boundary and invalid-range tests."
                ),
                judge_sha256=digest(
                    b"Recorded judge: accept exact tests and bounded implementation."
                ),
                decision="accept",
            )

        def authorize(
            brief: CodingBrief,
            scope: AgentInspectionScope,
            approved: set[str] = approved,
            workspace: Path = workspace,
        ) -> LocalChildAuthorization:
            if brief.sha256 not in approved:
                raise ValueError("Exact creator assignment is not approved.")
            return LocalChildAuthorization(
                scope=scope,
                assignment_sha256=brief.assignment.sha256,
                workspace_observation_sha256=observe_branch_workspace(str(workspace)),
                expires_at=1000,
                mode="recorded_coding",
                brief_sha256=brief.sha256,
                review_sha256=digest(canonical_bytes(review(brief, None))),
            )

        def integrate(
            record: LocalChildRecord,
            review: CodingReview,
            integration_approved: set[str] = integration_approved,
        ) -> CodingIntegrationApproval:
            if record.child_id not in integration_approved:
                raise ValueError("Creator has not approved patch integration.")
            assert record.coding is not None and record.coding.handoff is not None
            return CodingIntegrationApproval(
                owner_uid=record.authorization.scope.owner_uid,
                parent_session_id=record.authorization.scope.parent_session_id,
                child_id=record.child_id,
                handoff_sha256=digest(canonical_bytes(record.coding.handoff)),
                review_sha256=digest(canonical_bytes(review)),
                expires_at=1000,
            )

        cassette = demo_cassette()
        initial = ConversationController.fresh(workspace, cassette)
        try:
            with backend(
                root / backend.__name__ / "sessions", initial.session_id, workspace
            ) as store:
                store.save(initial)
                chat = ConversationController(
                    initial,
                    cassette,
                    store.save,
                    goal_clock=lambda: 100.0,
                    coding_authorizer=authorize,
                    coding_reviewer=review,
                    coding_executor=executor,
                    coding_broker=broker,
                    coding_integration_authorizer=integrate,
                )
                goal = chat.create_goal(
                    GoalDefinition(
                        objective="Implement bounded numeric clamping",
                        success_criteria=("Boundaries and invalid ranges pass",),
                        remaining_work=(
                            "Delegate meaningful implementation and integrate",
                        ),
                    )
                )
                commit, snapshot = broker.snapshot(("clamp.py", "tests/test_clamp.py"))
                plan = "Implement numeric boundaries and invalid-range rejection."
                brief = CodingBrief(
                    assignment=ImplementationAssignment(
                        task_id="clamp-child",
                        parent_task_id=goal.goal_id,
                        objective=plan,
                        provider="fixture",
                        model="tool-reviewer-v1",
                        effort="high",
                        workspace=str(workspace),
                        worktree=str(broker.staging_root / "child"),
                        plan_sha256=digest(plan.encode()),
                        tests_sha256=CodeSnapshot(files=(snapshot.files[1],)).sha256,
                        allowance=ResourceCeiling(
                            input_bytes=32000,
                            output_bytes=16000,
                            attempts=1,
                            cost_microusd=0,
                            correction_cycles=0,
                            review_rounds=0,
                        ),
                    ),
                    base_commit=commit,
                    snapshot=snapshot,
                    plan=plan,
                    interfaces="clamp(value, low, high)",
                    acceptance="Frozen tests pass, including inverted bounds.",
                    owned_paths=("clamp.py",),
                    test_paths=("tests/test_clamp.py",),
                )
                approved.add(brief.sha256)
                looping_tests = CodeFile(
                    path="tests/test_clamp.py", content="import time\ntime.sleep(10)\n"
                )
                limited_snapshot = CodeSnapshot(
                    files=(snapshot.files[0], looping_tests)
                )
                limited = brief.model_copy(
                    update={
                        "snapshot": limited_snapshot,
                        "wall_seconds": 1,
                        "assignment": brief.assignment.model_copy(
                            update={
                                "tests_sha256": CodeSnapshot(
                                    files=(looping_tests,)
                                ).sha256
                            }
                        ),
                    }
                )
                try:
                    await executor.verify(limited, limited_snapshot)
                except ValueError:
                    pass
                else:
                    raise AssertionError(
                        "Actual isolated test timeout did not close its worker."
                    )
                # Known-bad baseline must fail in the actual isolated verifier.
                assert not (await executor.verify(brief, snapshot)).passed
                patch = CodingPatch(
                    brief_sha256=brief.sha256,
                    summary="Implement bounds and invalid-range rejection.",
                    changes=(
                        FileChange(
                            file=CodeFile(path="clamp.py", content=IMPLEMENTED),
                            before_sha256=snapshot.files[0].sha256,
                        ),
                    ),
                )
                request, _ = prepare_conversation_request(coding_config(brief))
                response = demo_cassette().exchanges[0].response
                assert response is not None
                text = canonical_bytes(patch).decode()
                response = response.model_copy(
                    update={
                        "turn": Turn(role="assistant", blocks=(TextBlock(text=text),)),
                        "usage": Usage(
                            input=len(canonical_bytes(request)),
                            output=len(text.encode()),
                            unit="bytes",
                        ),
                    }
                )
                child_cassette = AgentCassette(
                    exchanges=(
                        AgentExchange(
                            request_sha256=digest(canonical_bytes(request)),
                            response=response,
                        ),
                    )
                )
                report = await chat.run_coding_child(
                    brief, child_cassette, expected_revision=chat.state.revision
                )
                assert not report.integration_approved
                assert (workspace / "clamp.py").read_text() == SOURCE
                assert chat.inspect_agents(report.child_id).report_status == "available"
                assert chat.current_goal is not None
                assert (
                    next(
                        j
                        for j in chat.current_goal.jobs
                        if j.operation_id.endswith("-integration")
                    ).state
                    == "running"
                )
                try:
                    await chat.integrate_coding_child(
                        report.child_id, expected_revision=chat.state.revision
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError("Child bypassed creator integration approval.")
                integration_approved.add(report.child_id)
                integrated = await chat.integrate_coding_child(
                    report.child_id, expected_revision=chat.state.revision
                )
                assert git("rev-parse", "HEAD") == integrated
                assert (workspace / "clamp.py").read_text() == IMPLEMENTED
                assert (workspace / "tests/test_clamp.py").read_text() == TESTS
                retained = store.load()
                resumed = ConversationController(
                    retained, cassette, store.save, goal_clock=lambda: 100.0
                )
                coding = resumed.state.local_children[0].coding
                assert coding is not None and coding.integration_state == "integrated"
                assert coding.applied_commit == integrated
                assert resumed.current_goal is not None
                assert (
                    resumed.current_goal.ledger.attempts == 2
                    and resumed.current_goal.ledger.uncertain_effects == 0
                )
                assert (
                    next(
                        j
                        for j in resumed.current_goal.jobs
                        if j.operation_id.endswith("-integration")
                    ).state
                    == "passed"
                )
                # A second real worker is cancelled before its stdin payload arrives.
                commit, snapshot = broker.snapshot(("clamp.py", "tests/test_clamp.py"))
                brief = brief.model_copy(
                    update={
                        "base_commit": commit,
                        "snapshot": snapshot,
                        "assignment": brief.assignment.model_copy(
                            update={
                                "task_id": "cancelled-child",
                                "worktree": str(
                                    broker.staging_root / "cancelled-child"
                                ),
                            }
                        ),
                    }
                )
                approved.add(brief.sha256)
                request, _ = prepare_conversation_request(coding_config(brief))
                cancelled_patch = CodingPatch(
                    brief_sha256=brief.sha256,
                    summary="Bounded cancelled refinement.",
                    changes=(
                        FileChange(
                            file=CodeFile(
                                path="clamp.py",
                                content=IMPLEMENTED.replace(
                                    "max(low, min(high, value))",
                                    "min(high, max(low, value))",
                                ),
                            ),
                            before_sha256=snapshot.files[0].sha256,
                        ),
                    ),
                )
                cancelled_text = canonical_bytes(cancelled_patch).decode()
                response = response.model_copy(
                    update={
                        "turn": Turn(
                            role="assistant", blocks=(TextBlock(text=cancelled_text),)
                        ),
                        "usage": Usage(
                            input=len(canonical_bytes(request)),
                            output=len(cancelled_text.encode()),
                            unit="bytes",
                        ),
                    }
                )
                cancelled_recording = AgentCassette(
                    exchanges=(
                        AgentExchange(
                            request_sha256=digest(canonical_bytes(request)),
                            response=response,
                        ),
                    )
                )
                held = HeldCodingContainer(docker, image, root / "lifecycles")
                chat.coding_executor = DockerCodingChild(held)
                task = asyncio.create_task(
                    chat.run_coding_child(
                        brief,
                        cancelled_recording,
                        expected_revision=chat.state.revision,
                    )
                )
                await held.started.wait()
                chat.goal_control("cancel")
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                else:
                    raise AssertionError("Real coding worker was not cancelled.")
                assert chat.current_goal is not None
                assert chat.current_goal.status == "cancelled"
                assert (
                    chat.current_goal.ledger.attempts == 3
                    and chat.current_goal.ledger.uncertain_effects == 1
                )
                assert chat.state.local_children[-1].state == "cancelled"
                assert git("rev-parse", "HEAD") == integrated
        finally:
            broker.close()


def main() -> None:
    executable = shutil.which("docker")
    if executable is None:
        raise ValueError("Docker qualification requires the local daemon.")
    docker = Path(executable)
    image = (
        bounded_process(
            [str(docker), "image", "inspect", "--format", "{{.Id}}", "mos-eisley:local"]
        )
        .decode()
        .strip()
    )
    with TemporaryDirectory(prefix="mos-coding-") as temporary:
        asyncio.run(exercise(Path(temporary).resolve(), docker, image))
    print(
        "Writable coding, protected tests, VCS integration, stores and cancellation "
        "passed."
    )


if __name__ == "__main__":
    main()
