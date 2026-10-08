"""Subscription authority, cold resume and shared uncertain-usage boundaries."""

import asyncio
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from mos_eisley.conversation_subscription import (
    AuthorizedSubscriptionClient,
    SubscriptionChatIdentity,
    SubscriptionChatRuntime,
    check_authority,
)
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock, Turn, Usage
from mos_eisley.providers.codex_subscription import CodexSubscriptionClient
from mos_eisley.subscription_authorization import (
    SubscriptionAuthorization,
    SubscriptionGrant,
    executable_sha256,
    native_context_sha256,
    provider_family,
    read_authorization,
)
from mos_eisley.subscription_usage import reserve_usage


def response() -> ModelResponse:
    return ModelResponse(
        turn=Turn(role="assistant", blocks=(TextBlock(text="ok"),)),
        stop_reason="end_turn",
        usage=Usage(unit="tokens", input=5, output=1),
    )


class AuthorizationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        client_temporary = tempfile.TemporaryDirectory()
        self.addCleanup(client_temporary.cleanup)
        self.client = Path(client_temporary.name).resolve() / "codex"
        self.client.write_text("synthetic owner-selected native client")
        self.client.chmod(0o700)
        self.path = self.root / "authorization.json"
        self.auth = SubscriptionAuthorization(
            authorization_id=uuid4().hex,
            session_id=uuid4().hex,
            owner_uid=os.getuid(),
            workspace=self.root,
            usage_root=self.root,
            valid_until=datetime.now(UTC) + timedelta(minutes=10),
            grants=(
                SubscriptionGrant(
                    role="chat",
                    provider="openai_subscription",
                    model="gpt-6-sol",
                    effort="medium",
                    client=self.client,
                    client_sha256=executable_sha256(self.client),
                    authentication_context_sha256=native_context_sha256(
                        "openai_subscription"
                    ),
                    max_invocations=2,
                ),
            ),
            max_invocations=2,
            max_input_bytes=128000,
            max_output_bytes=8000,
            max_output_tokens=400,
            timeout_seconds=30,
            allow_data_transfer=True,
            allow_subscription_usage=True,
            accept_unverified_billing_and_native_retries=True,
        )
        self.save()
        self.request = ModelRequest(
            provider="openai_subscription",
            model="gpt-6-sol",
            effort="medium",
            turns=(Turn(role="user", blocks=(TextBlock(text="Synthetic request"),)),),
            max_output=10000,
            max_output_tokens=400,
        )

    def save(self) -> None:
        self.path.write_bytes(canonical_bytes(self.auth))
        self.path.chmod(0o600)

    def adapter(self, call_id: str = "chat-0000") -> AuthorizedSubscriptionClient:
        return AuthorizedSubscriptionClient(self.auth, self.path, "chat", call_id)

    def test_exact_authorization_round_trip_and_mutation_refusal(self) -> None:
        self.assertEqual(read_authorization(self.path, self.auth.sha256), self.auth)
        self.auth = self.auth.model_copy(update={"max_invocations": 3})
        self.save()
        with self.assertRaises(ValueError):
            read_authorization(self.path, "0" * 64)

    def test_owner_workspace_session_and_expiry_are_checked(self) -> None:
        for changes in (
            {"owner_uid": os.getuid() + 1},
            {"session_id": uuid4().hex},
            {"valid_until": datetime.now(UTC) - timedelta(seconds=1)},
            {"workspace": self.root / "different"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.auth.model_copy(update=changes).check_current(
                    self.root, self.auth.session_id
                )

    def test_native_binary_and_authentication_location_cannot_change(self) -> None:
        check_authority(self.auth, self.path, "chat")
        self.client.write_text("different native client")
        with self.assertRaises(ValueError):
            check_authority(self.auth, self.path, "chat")

    def test_missing_role_and_duplicate_role_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.auth.grant("judge")
        with self.assertRaises(ValueError):
            SubscriptionAuthorization.model_validate(
                {**self.auth.model_dump(), "grants": self.auth.grants * 2}
            )

    def test_provider_family_counts_subscription_and_api_once(self) -> None:
        self.assertEqual(
            provider_family("openai"), provider_family("openai_subscription")
        )
        self.assertEqual(
            provider_family("anthropic"), provider_family("anthropic_subscription")
        )
        with self.assertRaises(ValueError):
            provider_family("other")

    async def test_completed_usage_survives_new_runtime_and_enforces_ceiling(
        self,
    ) -> None:
        with patch(
            "mos_eisley.conversation_subscription.CodexSubscriptionClient.complete",
            new=AsyncMock(return_value=response()),
        ) as native:
            await self.adapter().complete(self.request)
            cold = AuthorizedSubscriptionClient(
                read_authorization(self.path), self.path, "chat", "chat-0001"
            )
            await cold.complete(self.request)
            with self.assertRaises(ValueError):
                await self.adapter("chat-0002").complete(self.request)
            self.assertEqual(native.await_count, 2)
        self.assertNotIn(
            "Synthetic request",
            (
                self.root
                / self.auth.authorization_id
                / "slot-0001"
                / "reservation.json"
            ).read_text(),
        )

    async def test_uncertain_usage_blocks_all_future_calls_after_restart(self) -> None:
        with patch(
            "mos_eisley.conversation_subscription.CodexSubscriptionClient.complete",
            new=AsyncMock(side_effect=asyncio.CancelledError),
        ) as native:
            with self.assertRaises(asyncio.CancelledError):
                await self.adapter().complete(self.request)
            with self.assertRaises(ValueError):
                await self.adapter("chat-0001").complete(self.request)
            self.assertEqual(native.await_count, 1)

    async def test_changed_schema_caps_or_route_are_not_reused_as_authority(
        self,
    ) -> None:
        for update in (
            {"provider": "openai"},
            {"effort": "high"},
            {"max_output_tokens": 401},
            {"max_output": 10001},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                await self.adapter().complete(self.request.model_copy(update=update))
        self.assertFalse((self.root / self.auth.authorization_id).exists())

    def test_concurrent_usage_is_refused_before_second_reservation(self) -> None:
        with reserve_usage(self.auth, "chat", "0" * 64, "test-0") as first:
            with (
                self.assertRaises(BlockingIOError),
                reserve_usage(self.auth, "chat", "1" * 64, "test-1"),
            ):
                pass
            first.complete()

    def test_missing_or_changed_ledger_binding_fails_closed(self) -> None:
        with reserve_usage(self.auth, "chat", "0" * 64, "test-0") as first:
            first.complete()
        binding = self.root / self.auth.authorization_id / "binding.json"
        binding.write_text('{"authorization_sha256":"wrong"}')
        with (
            self.assertRaises(ValueError),
            reserve_usage(self.auth, "chat", "0" * 64, "test-0"),
        ):
            pass

    def test_saved_identity_cannot_resume_another_session(self) -> None:
        identity = SubscriptionChatIdentity(
            authorization=self.auth, authorization_path=self.path
        )
        SubscriptionChatRuntime(identity, self.root, self.auth.session_id)
        with self.assertRaises(ValueError):
            SubscriptionChatRuntime(identity, self.root, uuid4().hex)

    async def test_saved_json_and_sqlite_subscription_resume_preserve_authority(
        self,
    ) -> None:
        from mos_eisley.conversation import ConversationController
        from mos_eisley.conversation_cli import demo_cassette
        from mos_eisley.conversation_state import ConversationState
        from mos_eisley.run.conversation_resume import inspect_sqlite_resume
        from mos_eisley.run.conversation_sqlite import SQLiteConversationStore

        identity = SubscriptionChatIdentity(
            authorization=self.auth, authorization_path=self.path
        )
        cassette = demo_cassette()
        state = ConversationController.fresh(self.root, cassette, live_chat=identity)
        runtime = SubscriptionChatRuntime(identity, self.root, state.session_id)
        controller = ConversationController(
            state, cassette, lambda state: None, run_live_chat=runtime.run
        )
        with patch(
            "mos_eisley.conversation_subscription.CodexSubscriptionClient.complete",
            new=AsyncMock(return_value=response()),
        ) as native:
            controller.submit("Synthetic first turn")
            self.assertTrue(await controller.step())
            self.assertEqual(controller.state.entries[0].status, "completed")
            saved = ConversationState.model_validate_json(
                controller.state.model_dump_json()
            )
            self.assertEqual(saved.mode, "subscription_conversation")
            self.assertEqual(saved.live_chat, identity)
            cold = SubscriptionChatRuntime(
                identity, self.root, saved.session_id, saved.exchanges_consumed
            )
            resumed = ConversationController(
                saved, cassette, lambda state: None, run_live_chat=cold.run
            )
            resumed.submit("Synthetic follow-up")
            self.assertTrue(await resumed.step())
            self.assertEqual(native.await_count, 2)
        with SQLiteConversationStore(
            self.root / "sessions", saved.session_id, self.root
        ) as store:
            store.save(state)
            self.assertEqual(store.load_working().live_chat, identity)
        inspected = inspect_sqlite_resume(
            self.root / "sessions", saved.session_id, self.root
        )
        self.assertEqual(inspected.header.live_chat, identity)
        self.assertEqual(inspected.header.mode, "subscription_conversation")
        with self.assertRaises(ValueError):
            ConversationState.model_validate_json(
                saved.model_copy(
                    update={"mode": "openai_live_conversation"}
                ).model_dump_json()
            )

    async def test_missing_usage_state_blocks_saved_resume(self) -> None:
        identity = SubscriptionChatIdentity(
            authorization=self.auth, authorization_path=self.path
        )
        with self.assertRaises(FileNotFoundError):
            SubscriptionChatRuntime(identity, self.root, self.auth.session_id, 1)

    async def test_completed_call_identifier_cannot_be_replayed(self) -> None:
        with patch(
            "mos_eisley.conversation_subscription.CodexSubscriptionClient.complete",
            new=AsyncMock(return_value=response()),
        ) as native:
            await self.adapter().complete(self.request)
            with self.assertRaises(ValueError):
                await self.adapter().complete(self.request)
            self.assertEqual(native.await_count, 1)

    async def test_scope_change_after_native_auth_preflight_prevents_dispatch(
        self,
    ) -> None:
        async def native_exchange(
            client: CodexSubscriptionClient, request: ModelRequest
        ) -> ModelResponse:
            self.path.write_text("{}")
            assert client.dispatch_guard is not None
            client.dispatch_guard()
            self.fail("Changed authorization reached native dispatch")

        with (
            patch(
                "mos_eisley.conversation_subscription.CodexSubscriptionClient.complete",
                new=native_exchange,
            ),
            self.assertRaises(ValueError),
        ):
            await self.adapter().complete(self.request)
        self.assertFalse(
            (
                self.root / self.auth.authorization_id / "slot-0001" / "completion.json"
            ).exists()
        )

    def test_extended_usage_root_acl_is_rejected(self) -> None:
        from mos_eisley.platform.storage import StorageAdmissionError

        with (
            patch(
                "mos_eisley.subscription_usage.NativeRootQueries.protection",
                side_effect=StorageAdmissionError("extended ACL"),
            ),
            self.assertRaises(StorageAdmissionError),
            reserve_usage(self.auth, "chat", "0" * 64, "test-0"),
        ):
            pass

    def test_corrupted_reservation_cannot_reset_role_allowance(self) -> None:
        import json

        with reserve_usage(self.auth, "chat", "0" * 64, "test-0") as slot:
            slot.complete()
        path = self.root / self.auth.authorization_id / "slot-0001" / "reservation.json"
        original = json.loads(path.read_text())
        for update in (
            {"role": "judge"},
            {"request_sha256": "bad"},
            {"billing_verified": True},
            {"state": "unknown"},
            {"extra": "unexpected"},
        ):
            path.write_text(json.dumps({**original, **update}))
            with (
                self.subTest(update=update),
                self.assertRaises(ValueError),
                reserve_usage(self.auth, "chat", "1" * 64, "test-1"),
            ):
                pass
        path.write_text(json.dumps(original))

    def test_authentication_context_change_is_rejected(self) -> None:
        with (
            patch.dict(os.environ, {"CODEX_HOME": str(self.root / "other-auth")}),
            self.assertRaises(ValueError),
        ):
            check_authority(self.auth, self.path, "chat")

    def test_authorization_cli_requires_consent_without_dispatch(
        self,
    ) -> None:
        import argparse
        import contextlib
        import io

        from mos_eisley.subscription_cli import add_command, run_command

        parser = argparse.ArgumentParser()
        add_command(parser.add_subparsers(dest="command", required=True).add_parser)
        output = self.root / "issued.json"
        arguments = [
            "subscription",
            "authorize",
            "--output",
            str(output),
            "--workspace",
            str(self.root),
            "--usage-root",
            str(self.root),
            "--session-id",
            self.auth.session_id,
            "--grant",
            "chat",
            "openai_subscription",
            "gpt-6-sol",
            "medium",
            str(self.client),
            "2",
            "--max-invocations",
            "2",
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run_command(parser.parse_args(arguments)), 2)
        self.assertFalse(output.exists())
        arguments += [
            "--allow-data-transfer",
            "--allow-subscription-usage",
            "--accept-unverified-billing-and-native-retries",
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_command(parser.parse_args(arguments)), 0)
        issued = read_authorization(output)
        self.assertEqual(issued.session_id, self.auth.session_id)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.root / issued.authorization_id).exists())

    def test_public_or_symlinked_authorization_file_is_rejected(self) -> None:
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            read_authorization(self.path)
        self.path.chmod(0o600)
        linked = self.root / "linked.json"
        linked.symlink_to(self.path)
        with self.assertRaises(OSError):
            read_authorization(linked)

    def test_selected_workspace_client_is_rejected_from_any_launch_directory(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            SubscriptionAuthorization.model_validate(
                {**self.auth.model_dump(), "workspace": self.client.parent}
            )

    def test_oversized_usage_directory_refuses_before_another_reservation(self) -> None:
        with reserve_usage(self.auth, "chat", "0" * 64, "test-0") as slot:
            slot.complete()
        root = self.root / self.auth.authorization_id
        for position in range(64):
            (root / f"unexpected-{position}").touch(mode=0o600)
        with (
            self.assertRaises(ValueError),
            reserve_usage(self.auth, "chat", "1" * 64, "test-1"),
        ):
            pass
        self.assertFalse((root / "slot-0002").exists())


if __name__ == "__main__":
    unittest.main()
