"""Validated semantic discovery over frozen author task-profile candidates."""

import os
import subprocess
import sys
from pathlib import Path
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase

from test_conversation_review import review_packet
from test_task_profile_acquisition import AcquisitionFixture, CapturingClient

from mos_eisley.conversation import (
    ConversationController,
    conversation_config,
    prepare_conversation_request,
)
from mos_eisley.conversation_admission_inspection import inspect_admission
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import TextBlock, Turn
from mos_eisley.project_guidance_role_admission import RoleContextSelection
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.task_profile import RuntimeTaskProfile
from mos_eisley.task_profile_acquisition import FrozenRoleTaskProfileSelection
from mos_eisley.task_semantic_discovery import (
    OmittedTaskProfile,
    SemanticTaskDecision,
    SemanticTaskProfileDiscovery,
    SemanticTaskSignal,
    ValidatedSemanticTaskProfileAcquirer,
    decode_semantic_task_discovery,
    task_profile_acquirer_from_paths,
)
from mos_eisley.task_state import WorkUnitReference


class SemanticDiscoveryFixture(AcquisitionFixture):
    def prepare_discovery(self, owner: TestCase) -> None:
        self.prepare_role_fixture(owner)
        receipt = self.guidance.freeze()
        snapshot = self.guidance.snapshot(receipt)
        guidance = RoleContextSelection(
            snapshot_sha256=cast(str, receipt["snapshot_sha256"]),
            context_sha256=cast(str, receipt["context_sha256"]),
            role=snapshot.context.role,
            scope=snapshot.context.scope,
        )
        work = WorkUnitReference(
            work_unit_id="validated-semantic-discovery", revision=1
        )
        policy_sha = digest(self.policy_path.read_bytes())
        self.candidates = (
            FrozenRoleTaskProfileSelection(
                profile_id="documentation-profile",
                project_id="mos-eisley",
                work_unit=work,
                guidance=guidance,
                expected_policy_sha256=policy_sha,
            ),
            FrozenRoleTaskProfileSelection(
                profile_id="implementation-profile",
                project_id="mos-eisley",
                work_unit=work,
                guidance=guidance,
                expected_policy_sha256=policy_sha,
            ),
        )
        self.discovery_path = self.guidance.base / "task-discovery.json"

    def discovery(
        self,
        task_text: str = DEMO_PROMPTS[0],
        *,
        signal_quote: str | None = None,
    ) -> SemanticTaskProfileDiscovery:
        quote = "fixture boundary" if signal_quote is None else signal_quote
        start = task_text.find("fixture boundary")
        if start < 0:
            start = 0
        decision = SemanticTaskDecision(
            decision_id="implement-exact-task",
            task_text_sha256=digest(task_text.encode("utf-8")),
            work_unit=self.candidates[1].work_unit,
            category="implementation",
            objective="PRIVATE-SEMANTIC-OBJECTIVE-CANARY",
            signals=(
                SemanticTaskSignal(
                    start=start,
                    end=start + len(quote),
                    quote=quote,
                ),
            ),
            selected_profile_id=self.candidates[1].profile_id,
            selection_reason="The exact task requests an implementation action.",
            omitted_profiles=(
                OmittedTaskProfile(
                    profile_id=self.candidates[0].profile_id,
                    reason="The exact task is not documentation-only.",
                ),
            ),
        )
        return SemanticTaskProfileDiscovery(
            project_id="mos-eisley",
            candidates=self.candidates,
            decisions=(decision,),
        )

    def semantic_acquirer(
        self, plan: SemanticTaskProfileDiscovery | None = None
    ) -> ValidatedSemanticTaskProfileAcquirer:
        self.discovery_path.write_bytes(canonical_bytes(plan or self.discovery()))
        acquired = task_profile_acquirer_from_paths(
            self.storage, self.discovery_path, self.policy_path
        )
        if not isinstance(acquired, ValidatedSemanticTaskProfileAcquirer):
            raise AssertionError("semantic discovery factory returned legacy acquirer")
        return acquired


class SemanticDiscoveryAdmissionTests(
    SemanticDiscoveryFixture, IsolatedAsyncioTestCase
):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_discovery(self)

    async def test_exact_task_selects_profile_and_binds_text_free_admission(
        self,
    ) -> None:
        acquirer = self.semantic_acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_profile_acquirer=acquirer
        )
        controller.submit(DEMO_PROMPTS[0])
        preview = preview_context(controller.state, task_profile_acquirer=acquirer)
        client = CapturingClient()

        await controller.step(client)

        admission = controller.state.entries[0].request_admission
        assert admission is not None and admission.task_profile is not None
        acquisition = admission.task_profile.acquisition
        assert acquisition is not None and acquisition.semantic_discovery is not None
        discovery = acquisition.semantic_discovery
        self.assertEqual(discovery.category, "implementation")
        self.assertEqual(discovery.selected_profile_id, "implementation-profile")
        self.assertEqual(discovery.omitted_profile_ids, ("documentation-profile",))
        self.assertEqual(admission.task_profile, preview.task_profile)
        self.assertIn("Use batch execution.", client.requests[0].system)
        self.assertNotIn("PRIVATE-SEMANTIC-OBJECTIVE-CANARY", client.requests[0].system)
        self.assertEqual(client.requests[0].tools, ())
        described = inspect_admission(controller.state, 0).describe()
        self.assertIn("Validated semantic discovery: implementation", described)

    async def test_changed_task_or_signal_fails_before_attempt(self) -> None:
        for plan, text, error in (
            (
                self.discovery(),
                DEMO_PROMPTS[1],
                "no exact queued-task decision",
            ),
            (
                self.discovery(signal_quote="wrong source text"),
                DEMO_PROMPTS[0],
                "signal does not match",
            ),
        ):
            acquirer = self.semantic_acquirer(plan)
            cassette = demo_cassette()
            state = ConversationController.fresh(self.workspace, cassette)
            controller = ConversationController(
                state, cassette, lambda _: None, task_profile_acquirer=acquirer
            )
            controller.submit(text)
            client = CapturingClient()

            with self.assertRaisesRegex(ValueError, error):
                await controller.step(client)

            self.assertEqual(controller.state.entries[0].status, "queued")
            self.assertEqual(controller.state.exchanges_consumed, 0)
            self.assertEqual(client.requests, [])

    async def test_sqlite_round_trip_preserves_discovery_evidence(self) -> None:
        acquirer = self.semantic_acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        with SQLiteConversationStore(
            self.guidance.base / "sessions", state.session_id, self.workspace
        ) as store:
            store.save(state)
            controller = ConversationController(
                state,
                cassette,
                store.save,
                load_entry=store.load_working_entry,
                task_profile_acquirer=acquirer,
            )
            controller.submit(DEMO_PROMPTS[0])
            await controller.step(CapturingClient())
            restored = store.load_working().entries[0]

        assert restored.request_admission is not None
        assert restored.request_admission.task_profile is not None
        acquisition = restored.request_admission.task_profile.acquisition
        assert acquisition is not None
        self.assertIsNotNone(acquisition.semantic_discovery)
        self.assertNotIn(
            "PRIVATE-SEMANTIC-OBJECTIVE-CANARY",
            restored.request_admission.model_dump_json(),
        )

    async def test_review_bypasses_author_semantic_discovery(self) -> None:
        acquirer = self.semantic_acquirer()
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        controller = ConversationController(
            state, cassette, lambda _: None, task_profile_acquirer=acquirer
        )
        controller.submit_review(review_packet())

        await controller.step()

        self.assertIsNone(controller.state.entries[0].request_admission)
        self.assertIsNotNone(controller.state.entries[0].review_result)


class SemanticDiscoveryBoundaryTests(SemanticDiscoveryFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_discovery(self)

    def test_decoder_rejects_duplicate_keys_and_incomplete_omissions(self) -> None:
        payload = canonical_bytes(self.discovery())
        duplicate = payload.replace(
            b'"schema_version":1',
            b'"schema_version":1,"schema_version":1',
            1,
        )
        with self.assertRaisesRegex(ValueError, "Invalid semantic"):
            decode_semantic_task_discovery(duplicate)

        decision = (
            self.discovery().decisions[0].model_copy(update={"omitted_profiles": ()})
        )
        with self.assertRaisesRegex(ValueError, "cover every unselected"):
            SemanticTaskProfileDiscovery(
                project_id="mos-eisley",
                candidates=self.candidates,
                decisions=(decision,),
            )

    def test_forged_review_candidate_is_rejected_by_concrete_acquirer(self) -> None:
        forged_guidance = self.candidates[1].guidance.model_copy(
            update={"role": "critic"}
        )
        forged_candidate = FrozenRoleTaskProfileSelection.model_construct(
            schema_version=1,
            kind="frozen_role_task_profile",
            profile_id=self.candidates[1].profile_id,
            project_id=self.candidates[1].project_id,
            work_unit=self.candidates[1].work_unit,
            guidance=forged_guidance,
            expected_policy_sha256=self.candidates[1].expected_policy_sha256,
        )
        plan = self.discovery().model_copy(
            update={"candidates": (self.candidates[0], forged_candidate)}
        )

        with self.assertRaisesRegex(ValueError, "Invalid semantic"):
            ValidatedSemanticTaskProfileAcquirer(
                guidance_storage=self.storage,
                policy_path=self.policy_path,
                discovery_payload=canonical_bytes(plan),
            )

    def test_editable_discovery_example_decodes(self) -> None:
        example = Path("templates") / "TASK_SEMANTIC_DISCOVERY_EXAMPLE.json"

        discovery = decode_semantic_task_discovery(example.read_bytes())

        self.assertEqual(discovery.decisions[0].category, "implementation")
        self.assertFalse(discovery.selects_tools)

    def test_tampered_discovery_binding_is_rejected(self) -> None:
        profile = self.semantic_acquirer().acquire(
            owner_uid=os.getuid(),
            workspace=str(Path(self.workspace).resolve()),
            task_text=DEMO_PROMPTS[0],
        )
        acquisition = profile.acquisition
        assert acquisition is not None and acquisition.semantic_discovery is not None
        forged = acquisition.model_copy(
            update={
                "semantic_discovery": acquisition.semantic_discovery.model_copy(
                    update={"discovery_source_sha256": "f" * 64}
                )
            }
        )

        with self.assertRaisesRegex(ValueError, "evidence differs"):
            RuntimeTaskProfile.model_validate(
                profile.model_copy(update={"acquisition": forged}).model_dump()
            )

    def test_plain_terminal_uses_semantic_discovery(self) -> None:
        acquirer = self.semantic_acquirer()
        profile = acquirer.acquire(
            owner_uid=os.getuid(),
            workspace=str(Path(self.workspace).resolve()),
            task_text=DEMO_PROMPTS[0],
        )
        turn = Turn(role="user", blocks=(TextBlock(text=DEMO_PROMPTS[0]),))
        request, _ = prepare_conversation_request(
            conversation_config((turn,), task_profile=profile), profile
        )
        response = demo_cassette().exchanges[0].response
        assert response is not None
        cassette = AgentCassette(
            exchanges=(
                AgentExchange(
                    request_sha256=digest(canonical_bytes(request)), response=response
                ),
            )
        )
        cassette_path = self.guidance.base / "semantic-cassette.json"
        cassette_path.write_bytes(canonical_bytes(cassette))

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "--plain",
                "--no-memory",
                "-C",
                str(self.workspace),
                "--storage",
                str(self.guidance.base / "sessions"),
                "--cassette",
                str(cassette_path),
                "--task-profile-selection",
                str(self.discovery_path),
                "--task-profile-policy",
                str(self.policy_path),
                "--task-guidance-storage",
                str(self.storage),
            ],
            input=DEMO_PROMPTS[0] + "\n",
            text=True,
            capture_output=True,
            timeout=20,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("The fixture boundary is ten.", result.stdout)
