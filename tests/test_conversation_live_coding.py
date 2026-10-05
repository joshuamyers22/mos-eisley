"""Real Git and executable-test coverage of the connected session workflow."""

import asyncio
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from pydantic import JsonValue
from test_coding_controller import FixtureCodingExecutor

from mos_eisley.coding_child import CodeFile, CodingBrief, CodingPatch, FileChange
from mos_eisley.conversation import ConversationController, conversation_config
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_live_coding import (
    CodingRoute,
    CreatorApproval,
    LiveCodingSelection,
    LiveCodingWorkflow,
    ModelReview,
    decode_model,
)
from mos_eisley.conversation_live_coding_transport import LiveCodingModels
from mos_eisley.conversation_state import LiveChatIdentity
from mos_eisley.core.agent import AgentConfig, AgentResult, run_agent
from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock, Turn, Usage
from mos_eisley.core.registry import anthropic_registry, openai_registry
from mos_eisley.providers.openai_spend import SpendPolicy
from mos_eisley.run.coding_vcs import CodingVCS
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.tools.none import NoToolsDispatcher


class ResponseClient:
    def __init__(self, output: str) -> None:
        self.output = output

    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            turn=Turn(role="assistant", blocks=(TextBlock(text=self.output),)),
            stop_reason="end_turn",
            usage=Usage(input=20, output=20, unit="tokens"),
        )


class CountedRoleTransport:
    def __init__(self) -> None:
        self.calls = 0
        self.cancel = False

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        return 20

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls += 1
        if self.cancel:
            raise asyncio.CancelledError
        if "messages" in payload:
            return {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "model": payload["model"],
                "content": [{"type": "text", "text": "{}"}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            }
        return {
            "id": "resp_fixture",
            "model": payload["model"],
            "service_tier": "default",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "{}"}],
                }
            ],
            "usage": {
                "input_tokens": 20,
                "output_tokens": 20,
                "input_tokens_details": {"cache_write_tokens": 0},
            },
        }


class WorkflowModels:
    def __init__(self) -> None:
        self.roles: list[str] = []
        self.packets: list[dict[str, object]] = []
        self.input_block_counts: list[int] = []
        self.large_plan = False
        self.fail_child_once = False
        self.reject_plan = False
        self.reject_final = False
        self.deny_creator = False
        self.started = asyncio.Event()
        self.hold = False
        self.wrong_subject = False
        self.tamper_tests = False
        self.deny_final_once = False

    async def call(
        self, route: CodingRoute, config: AgentConfig, directory: Path
    ) -> AgentResult:
        blocks = config.initial_turns[0].blocks
        assert all(isinstance(block, TextBlock) for block in blocks)
        packet = json.loads(
            "".join(block.text for block in blocks if isinstance(block, TextBlock))
        )
        self.input_block_counts.append(len(blocks))
        self.packets.append(packet)
        system = config.system
        if system.startswith("Create a concrete"):
            role = "plan"
            output = {
                "plan": "Implement addition with signed values.",
                "interfaces": "add(a,b)",
                "acceptance": "Correct addition for signed values and zero.",
                "creator_tests": {
                    "files": [
                        {
                            "path": "tests/test_mos_add.py",
                            "content": (
                                "import unittest\nfrom adder import add\n"
                                "class More(unittest.TestCase):\n"
                            )
                            + (
                                "    def test_zero(self):\n        "
                                "self.assertEqual(add(0,-7),-7)\n"
                            ),
                        }
                    ]
                },
            }
            if self.large_plan:
                output["plan"] = "Implement addition. " * 300
        elif system.startswith("Independently review") or system.startswith(
            "Adjudicate"
        ):
            role = "critic" if system.startswith("Independently") else "judge"
            final = '"patch"' in packet["artifact"]
            rejected = self.reject_final if final else self.reject_plan
            output = ModelReview(
                subject_sha256=digest(b"wrong")
                if self.wrong_subject
                else packet["subject_sha256"],
                decision="revise" if rejected else "accept",
                findings=("Concrete unresolved defect.",) if rejected else (),
            ).model_dump(mode="json")
        elif system.startswith("As creator"):
            role = "approve"
            output = CreatorApproval(
                subject_sha256=packet["subject_sha256"],
                judge_sha256=packet["judge_sha256"],
                decision="revise"
                if self.deny_creator
                or (
                    self.deny_final_once
                    and '"patch"' in packet["artifact"]
                    and self.roles.count("approve") == 1
                )
                else "approve",
                reason="Check addition across zero again.",
            ).model_dump(mode="json")
        else:
            role = "child"
            brief = CodingBrief.model_validate_json(json.dumps(packet["brief"]))
            first = self.roles.count("child") == 0
            old = next(f for f in brief.snapshot.files if f.path == "adder.py")
            patch = CodingPatch(
                brief_sha256=brief.sha256,
                changes=(
                    FileChange(
                        file=CodeFile(
                            path="adder.py",
                            content="def add(a,b):\n    return "
                            + ("0" if self.fail_child_once and first else "a+b")
                            + "\n",
                        ),
                        before_sha256=old.sha256,
                    ),
                ),
                summary="Implement addition",
            )
            # A failed candidate must still make a change from the old snapshot.
            if self.fail_child_once and first:
                patch = patch.model_copy(
                    update={
                        "changes": (
                            FileChange(
                                file=CodeFile(
                                    path="adder.py",
                                    content="def add(a,b):\n    return a-b\n",
                                ),
                                before_sha256=old.sha256,
                            ),
                        )
                    }
                )
            if self.tamper_tests:
                protected = next(
                    f for f in brief.snapshot.files if f.path.startswith("tests/")
                )
                patch = patch.model_copy(
                    update={
                        "changes": (
                            FileChange(
                                file=CodeFile(path=protected.path, content="pass\n"),
                                before_sha256=protected.sha256,
                            ),
                        )
                    }
                )
            output = patch.model_dump(mode="json")
        self.roles.append(role)
        if self.hold:
            self.started.set()
            await asyncio.Event().wait()
        registry = (
            openai_registry() if route.provider == "openai" else anthropic_registry()
        )
        return await run_agent(
            config, registry, ResponseClient(json.dumps(output)), NoToolsDispatcher()
        )


class LiveCodingTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        (self.repo / "adder.py").write_text("def add(a,b):\n    return 0\n")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/test_adder.py").write_text(
            "import unittest\nfrom adder import add\nclass "
            "Tests(unittest.TestCase):\n    def test_add(self):\n        "
            "self.assertEqual(add(2,3),5)\n"
        )
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Creator-owned base",
        )
        self.base = self.git("rev-parse", "HEAD").strip()
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir(mode=0o700)
        self.routes: list[CodingRoute] = []
        roster: tuple[tuple[Literal["openai", "anthropic"], str], ...] = (
            ("openai", "gpt-6-astra"),
            ("openai", "gpt-5.6-luna"),
            ("openai", "gpt-5.6-terra"),
            ("anthropic", "claude-sonnet-5"),
            ("anthropic", "claude-opus-5-5"),
        )
        for i, (provider, model) in enumerate(roster):
            now = datetime.now(UTC)
            policy = SpendPolicy(
                schema_version=2,
                provider=provider,
                model=model,
                pricing_source="Fixture",
                valid_from=now - timedelta(minutes=1),
                valid_until=now + timedelta(hours=1),
                input_microusd_per_million=1_000_000,
                cache_write_microusd_per_million=1_000_000,
                output_microusd_per_million=1_000_000,
                max_cost_microusd=6000,
                max_input_tokens=5000,
                max_output_tokens=512,
            )
            path = self.root / f"policy-{i}.json"
            path.write_bytes(canonical_bytes(policy))
            self.routes.append(
                CodingRoute(
                    provider=provider,
                    model=model,
                    effort="high",
                    spend_policy=path,
                    expected_policy_sha256=policy.policy_sha256,
                )
            )
        self.selection = LiveCodingSelection(
            workspace=self.repo,
            source_paths=("adder.py",),
            test_paths=("tests/test_adder.py",),
            creator=self.routes[0],
            child=self.routes[1],
            critics=tuple(self.routes[2:4]),
            judge=self.routes[4],
            spend_ledger=self.root / "ledger.sqlite",
            expected_ledger_id=digest(b"ledger"),
            artifacts_root=self.artifacts,
            staging_root=self.root / "staging",
            git=Path("/usr/bin/git"),
            docker=Path("/usr/bin/docker"),
            image_id="sha256:" + "1" * 64,
            valid_until=datetime.now(UTC) + timedelta(hours=1),
            max_total_microusd=100_000,
        )
        self.models = WorkflowModels()
        self.executor = FixtureCodingExecutor()
        self.broker = CodingVCS(Path("/usr/bin/git"), self.repo, self.root / "staging")
        self.addCleanup(self.broker.close)
        self.workflow = LiveCodingWorkflow(
            self.selection,
            digest(b"selection"),
            self.models,
            self.executor,
            self.broker,
            lambda: None,
        )
        self.config = conversation_config(
            (
                Turn(
                    role="user",
                    blocks=(TextBlock(text="Private author history."),),
                ),
                Turn(role="assistant", blocks=(TextBlock(text="Acknowledged."),)),
                Turn(role="user", blocks=(TextBlock(text="Fix addition."),)),
            )
        )

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["/usr/bin/git", "-C", str(self.repo), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        )

    async def run_workflow(self, attempt: int = 0) -> AgentResult:
        return await self.workflow.run(self.config, attempt, "1" * 32)

    async def test_complete_live_path_preserves_tests_and_blinds_review(self) -> None:
        result = await self.run_workflow()
        self.assertEqual(
            self.models.roles,
            [
                "plan",
                "critic",
                "critic",
                "judge",
                "approve",
                "child",
                "critic",
                "critic",
                "judge",
                "approve",
            ],
        )
        self.assertEqual(result.usage.requests, 10)
        self.assertEqual(
            (self.repo / "adder.py").read_text(), "def add(a,b):\n    return a+b\n"
        )
        self.assertFalse((self.repo / "tests/test_mos_add.py").exists())
        self.assertIn("Frozen tests passed", result.final_text)
        self.assertNotEqual(self.git("rev-parse", "HEAD").strip(), self.base)
        self.assertTrue(
            (self.artifacts / ("1" * 32) / "coding-0000/completion.json").is_file()
        )
        for role, packet in zip(self.models.roles, self.models.packets, strict=True):
            if role in {"critic", "judge", "approve"}:
                # The explicit task remains visible; unrelated author history does not.
                self.assertNotIn("request", packet)
                self.assertNotIn("gpt-6-astra", json.dumps(packet))
                self.assertNotIn("claude-sonnet", json.dumps(packet))
                self.assertNotIn("Private author history.", json.dumps(packet))
                artifact = json.loads(str(packet["artifact"]))
                self.assertIn(artifact["phase"], {"plan", "implementation"})
                self.assertEqual(artifact["workflow_bounds"]["candidate_attempts"], 2)
                self.assertEqual(artifact["workflow_bounds"]["correction_cycles"], 1)
                self.assertEqual(
                    artifact["workflow_bounds"]["brief_assignment_scope"],
                    "one unpaid offline verification invocation",
                )
                self.assertEqual(
                    artifact["brief"]["assignment"]["allowance"]["attempts"], 1
                )

    async def test_large_review_packets_preserve_exact_artifact_through_integration(
        self,
    ) -> None:
        self.models.large_plan = True
        result = await self.run_workflow()
        self.assertIn("Frozen tests passed", result.final_text)
        self.assertTrue(any(n > 1 for n in self.models.input_block_counts))
        for role, packet in zip(self.models.roles, self.models.packets, strict=True):
            if role in {"critic", "judge", "approve"}:
                artifact = json.loads(str(packet["artifact"]))
                self.assertEqual(
                    artifact["brief"]["plan"], "Implement addition. " * 300
                )
                self.assertEqual(
                    packet["subject_sha256"], digest(str(packet["artifact"]).encode())
                )

    async def test_failed_tests_get_bounded_correction_with_identical_brief(
        self,
    ) -> None:
        self.models.fail_child_once = True
        await self.run_workflow()
        children = [
            p
            for r, p in zip(self.models.roles, self.models.packets, strict=True)
            if r == "child"
        ]
        self.assertEqual(len(children), 2)
        self.assertEqual(children[0]["brief"], children[1]["brief"])
        self.assertIn("verification", str(children[1]["previous"]))

    async def test_plan_review_rejection_prevents_child_and_all_writes(self) -> None:
        self.models.reject_plan = True
        with self.assertRaisesRegex(ValueError, "Plan/tests need revision"):
            await self.run_workflow()
        self.assertNotIn("child", self.models.roles)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.base)

    async def test_creator_rejection_prevents_child(self) -> None:
        self.models.deny_creator = True
        with self.assertRaisesRegex(ValueError, "creator approval"):
            await self.run_workflow()
        self.assertNotIn("child", self.models.roles)

    async def test_creator_revision_uses_same_bounded_correction_budget(self) -> None:
        self.models.deny_final_once = True
        await self.run_workflow()
        self.assertEqual(self.models.roles.count("child"), 2)

    async def test_child_cannot_replace_protected_tests(self) -> None:
        self.models.tamper_tests = True
        with self.assertRaisesRegex(ValueError, "unowned, protected"):
            await self.run_workflow()
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.base)

    async def test_prior_uncertain_integration_blocks_new_attempt(self) -> None:
        session = self.artifacts / ("1" * 32)
        session.mkdir(mode=0o700)
        prior = session / "coding-0000"
        prior.mkdir(mode=0o700)
        (prior / "integration-started.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "prior uncertain integration"):
            await self.run_workflow(1)
        self.assertEqual(self.models.roles, [])

    async def test_unsupported_source_stops_before_any_paid_role(self) -> None:
        (self.repo / "adder.py").write_text("import os\n")
        self.git("add", "adder.py")
        self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Unsupported source profile",
        )
        with self.assertRaises(ValueError):
            await self.run_workflow()
        self.assertEqual(self.models.roles, [])

    async def test_changed_source_stops_before_next_paid_role(self) -> None:
        calls = 0

        def guard() -> None:
            nonlocal calls
            calls += 1
            if calls == 3:
                (self.repo / "adder.py").write_text("def add(a,b):\n    return 9\n")

        self.workflow.guard = guard
        with self.assertRaisesRegex(ValueError, "Workspace contains"):
            await self.run_workflow()
        self.assertEqual(self.models.roles, ["plan"])

    async def test_final_review_rejection_exhausts_without_integrating(self) -> None:
        self.models.reject_final = True
        with self.assertRaisesRegex(ValueError, "Correction budget"):
            await self.run_workflow()
        self.assertEqual(self.models.roles.count("child"), 2)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.base)

    async def test_wrong_subject_stops_before_child(self) -> None:
        self.models.wrong_subject = True
        with self.assertRaisesRegex(ValueError, "different frozen subject"):
            await self.run_workflow()
        self.assertNotIn("child", self.models.roles)

    async def test_expired_selection_stops_without_any_provider_call(self) -> None:
        self.workflow.selection = self.selection.model_copy(
            update={
                "valid_until": datetime.now(UTC) - timedelta(seconds=1),
            }
        )
        with self.assertRaisesRegex(ValueError, "selection expired"):
            await self.run_workflow()
        self.assertEqual(self.models.roles, [])

    async def test_duplicate_decision_fields_cannot_override_review(self) -> None:
        malformed = (
            '{"subject_sha256":"'
            + digest(b"subject")
            + '","decision":"revise","decision":"accept","findings":[]}'
        )
        with self.assertRaisesRegex(ValueError, "invalid frozen artifact"):
            decode_model(ModelReview, malformed)

    async def test_duplicate_attempt_and_cancellation_never_replay(self) -> None:
        self.models.hold = True
        task = asyncio.create_task(self.run_workflow())
        await asyncio.wait_for(self.models.started.wait(), 5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        with self.assertRaises(FileExistsError):
            await self.run_workflow()
        self.assertEqual(len(self.models.roles), 1)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.base)

    async def test_whole_workflow_budget_stops_new_calls(self) -> None:
        self.workflow.selection = self.selection.model_copy(
            update={"max_total_microusd": 6000}
        )
        with self.assertRaisesRegex(ValueError, "ceiling exhausted"):
            await self.run_workflow()
        self.assertEqual(self.models.roles, ["plan"])

    async def test_completed_session_result_survives_both_stores(self) -> None:
        identity = LiveChatIdentity(
            model=self.routes[0].model,
            effort="high",
            max_output_tokens=512,
            spend_policy_sha256=self.routes[0].expected_policy_sha256,
            spend_ledger_id=digest(b"ledger"),
            artifacts_root=str(self.artifacts),
            coding_selection_sha256=digest(b"selection"),
        )
        cassette = demo_cassette()
        for kind in (ConversationStore, SQLiteConversationStore):
            with self.subTest(kind=kind.__name__):
                storage = self.root / kind.__name__
                state = ConversationController.fresh(
                    self.repo, cassette, live_chat=identity
                )

                async def run(config: AgentConfig, attempt: int) -> AgentResult:
                    registry = openai_registry()
                    return await run_agent(
                        config,
                        registry,
                        ResponseClient("Connected workflow receipt"),
                        NoToolsDispatcher(),
                    )

                with kind(storage, state.session_id, self.repo, create=True) as store:
                    store.save(state)
                    controller = ConversationController(
                        state,
                        cassette,
                        store.save,
                        run_live_chat=run,
                        run_live_coding=run,
                    )
                    controller.submit("Fix addition", implementation_request=True)
                    await controller.step()
                    self.assertEqual(store.load().live_chat, identity)
                    self.assertEqual(
                        store.load().entries[0].answer, "Connected workflow receipt"
                    )
                    self.assertTrue(store.load().entries[0].implementation_request)
                    controller.run_live_coding = None
                    controller.submit("Another change", implementation_request=True)
                    with self.assertRaisesRegex(ValueError, "exact workflow runner"):
                        await controller.step()
                    self.assertEqual(controller.state.entries[1].status, "queued")

    async def test_real_spending_adapters_settle_and_burn_both_provider_calls(
        self,
    ) -> None:
        ledger = SpendLedger.create(self.root / "transport-ledger.sqlite", 100_000)
        models = LiveCodingModels(
            ledger, ledger.policy.ledger_id, "fixture-openai", "fixture-anthropic"
        )
        for index in (1, 3):
            route = self.routes[index]
            config = AgentConfig(
                provider=route.provider,
                model=route.model,
                effort=route.effort,
                initial_turns=(
                    Turn(role="user", blocks=(TextBlock(text="Fixture role input"),)),
                ),
                system="Fixture tool-free role instructions",
                max_iterations=1,
                max_tool_calls=0,
                budget=BudgetPolicy(max_output_tokens=512),
            )
            directory = self.root / f"transport-{index}"
            directory.mkdir(mode=0o700)
            transport = CountedRoleTransport()
            target = (
                "EphemeralOpenAITransport"
                if index == 1
                else "EphemeralAnthropicTransport"
            )
            with patch(
                "mos_eisley.conversation_live_coding_transport." + target,
                return_value=transport,
            ):
                result = await models.call(route, config, directory)
                self.assertEqual(result.usage.requests, 1)
                self.assertEqual(transport.calls, 1)
                self.assertEqual(ledger.snapshot().unresolved_entries, 0)
                with self.assertRaises(FileExistsError):
                    await models.call(route, config, directory)
                self.assertEqual(transport.calls, 1)
        self.assertEqual(ledger.snapshot().entries, 2)
        self.assertEqual(ledger.snapshot().charged_microusd, 80)

    async def test_cancelled_provider_call_keeps_full_shared_exposure(self) -> None:
        ledger = SpendLedger.create(self.root / "cancel-ledger.sqlite", 100_000)
        models = LiveCodingModels(
            ledger, ledger.policy.ledger_id, "fixture-openai", "fixture-anthropic"
        )
        route = self.routes[1]
        config = AgentConfig(
            provider=route.provider,
            model=route.model,
            effort=route.effort,
            initial_turns=(
                Turn(role="user", blocks=(TextBlock(text="Fixture input"),)),
            ),
            max_iterations=1,
            max_tool_calls=0,
            budget=BudgetPolicy(max_output_tokens=512),
        )
        directory = self.root / "cancelled-transport"
        directory.mkdir(mode=0o700)
        transport = CountedRoleTransport()
        transport.cancel = True
        with (
            patch(
                "mos_eisley.conversation_live_coding_transport.EphemeralOpenAITransport",
                return_value=transport,
            ),
            self.assertRaises(asyncio.CancelledError),
        ):
            await models.call(route, config, directory)
        self.assertEqual(ledger.snapshot().unresolved_entries, 1)
        self.assertEqual(ledger.snapshot().charged_microusd, 5512)
