"""Prepare and explicitly run bounded synthetic subscription role qualification."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from pydantic import JsonValue

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_live_coding import (
    CodingRoute,
    LiveCodingSelection,
    LiveCodingWorkflow,
    read_coding_selection,
)
from mos_eisley.conversation_live_coding_transport import SubscriptionCodingModels
from mos_eisley.conversation_subscription import (
    AuthorizedSubscriptionClient,
    SubscriptionChatIdentity,
    SubscriptionChatRuntime,
)
from mos_eisley.core.agent import AgentConfig, AgentResult
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import (
    JsonSchemaOutput,
    ModelRequest,
    ModelResponse,
    TextBlock,
    Turn,
)
from mos_eisley.providers import claude_subscription, codex_subscription
from mos_eisley.run.coding_child import CodingContainer, DockerCodingChild
from mos_eisley.run.coding_vcs import CodingVCS
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.subscription_authorization import (
    SubscriptionAuthorization,
    SubscriptionGrant,
    SubscriptionProvider,
    SubscriptionRole,
    executable_sha256,
    native_context_sha256,
    read_authorization,
)
from mos_eisley.subscription_usage import private_directory, verify_saved_attempts

BASE_SOURCE = "def add(a,b):\n    return 0\n"
BASE_TEST = (
    "import unittest\nfrom adder import add\nclass Tests(unittest.TestCase):\n"
    "    def test_add(self):\n        self.assertEqual(add(2,3),5)\n"
)


def write(path: Path, value: dict[str, JsonValue]) -> None:
    parent = private_directory(path.parent)
    try:
        codex_subscription.write_receipt(parent, path.name, value)
    finally:
        os.close(parent)


def prepare(args: argparse.Namespace) -> None:
    root = args.root.absolute()
    root.mkdir(mode=0o700, exist_ok=False)
    fd = private_directory(root)
    os.close(fd)
    workspace = root / "workspace"
    workspace.mkdir(mode=0o700)
    (workspace / "adder.py").write_text(BASE_SOURCE)
    (workspace / "tests").mkdir(mode=0o700)
    (workspace / "tests/test_adder.py").write_text(BASE_TEST)
    usage = root / "usage"
    usage.mkdir(mode=0o700)
    clients = {
        "openai_subscription": codex_subscription.select_client(args.codex),
        "anthropic_subscription": codex_subscription.select_client(args.claude),
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in codex_subscription.CLIENT_ENVIRONMENT
    }
    environment.update(
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0"
    )
    for arguments in (
        ("init", "-q"),
        ("add", "adder.py", "tests/test_adder.py"),
        (
            "-c",
            "user.name=Synthetic qualification",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgSign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "Synthetic qualification base",
        ),
    ):
        subprocess.run(
            [str(args.git), "-C", str(workspace), *arguments],
            env=environment,
            check=True,
            timeout=20,
            capture_output=True,
        )
    profiles: tuple[
        tuple[SubscriptionRole, SubscriptionProvider, str, str, int], ...
    ] = (
        ("chat", "openai_subscription", "gpt-6-sol", "medium", 2),
        ("creator", "openai_subscription", "gpt-6-sol", "medium", 4),
        ("child", "openai_subscription", "gpt-6-sol", "medium", 1),
        ("critic_openai", "openai_subscription", "gpt-5.6-terra", "medium", 2),
        ("critic_anthropic", "anthropic_subscription", "claude-sonnet-5", "high", 4),
        ("judge", "openai_subscription", "gpt-6-astra", "medium", 2),
    )
    grants = tuple(
        SubscriptionGrant.model_validate_json(
            json.dumps(
                {
                    "role": role,
                    "provider": provider,
                    "model": model,
                    "effort": effort,
                    "client": str(clients[provider]),
                    "client_sha256": executable_sha256(clients[provider]),
                    "authentication_context_sha256": native_context_sha256(provider),
                    "max_invocations": calls,
                }
            )
        )
        for role, provider, model, effort, calls in profiles
    )
    authorization = SubscriptionAuthorization(
        authorization_id=uuid4().hex,
        session_id=uuid4().hex,
        owner_uid=os.getuid(),
        workspace=workspace.resolve(),
        usage_root=usage.resolve(),
        valid_until=datetime.now(UTC) + timedelta(seconds=args.valid_for_seconds),
        grants=grants,
        max_invocations=14,
        max_input_bytes=128000,
        max_output_bytes=16000,
        max_output_tokens=2048,
        timeout_seconds=60,
        allow_data_transfer=True,
        allow_subscription_usage=True,
        accept_unverified_billing_and_native_retries=True,
    )
    authority_path = root / "authorization.json"
    write(authority_path, json.loads(canonical_bytes(authorization)))
    routes = tuple(
        CodingRoute(
            provider=g.provider,
            model=g.model,
            effort=g.effort,
            subscription_authorization=authority_path,
            expected_subscription_sha256=authorization.sha256,
            subscription_role=g.role,
        )
        for g in grants
        if g.role != "chat"
    )
    selection = LiveCodingSelection(
        mode="operator_subscription_session_coding",
        workspace=workspace.resolve(),
        source_paths=("adder.py",),
        test_paths=("tests/test_adder.py",),
        creator=routes[0],
        child=routes[1],
        critics=routes[2:4],
        judge=routes[4],
        artifacts_root=usage.resolve(),
        staging_root=root / "staging",
        git=args.git,
        docker=args.docker,
        image_id=args.image_id,
        valid_until=authorization.valid_until,
        correction_cycles=0,
        wall_seconds=600,
        max_input_bytes=1000000,
        max_output_bytes=500000,
    )
    write(root / "selection.json", json.loads(canonical_bytes(selection)))
    write(
        root / "prepared.json",
        {
            "authorization_sha256": authorization.sha256,
            "selection_sha256": digest(canonical_bytes(selection)),
            "source_sha256": digest(BASE_SOURCE.encode()),
            "test_sha256": digest(BASE_TEST.encode()),
            "inference_invocations": 0,
        },
    )
    print(
        json.dumps(
            {
                "root": str(root),
                "authorization_sha256": authorization.sha256,
                "maximum_native_inference_invocations": 14,
                "billing_verified": False,
                "prepared_only": True,
            }
        )
    )


async def exercise(root: Path) -> dict[str, JsonValue]:
    authority_path = root / "authorization.json"
    auth = read_authorization(authority_path)
    selection, selection_sha = read_coding_selection(
        root / "selection.json", auth.workspace
    )
    prepared = json.loads((root / "prepared.json").read_text())
    if (
        prepared["authorization_sha256"] != auth.sha256
        or prepared["selection_sha256"] != selection_sha
        or auth.max_invocations != 14
        or selection.correction_cycles != 0
        or (auth.workspace / "adder.py").read_text() != BASE_SOURCE
        or (auth.workspace / "tests/test_adder.py").read_text() != BASE_TEST
    ):
        raise ValueError("Prepared synthetic scope changed")
    write(
        root / "run-started.json",
        {
            "authorization_sha256": auth.sha256,
            "selection_sha256": selection_sha,
            "automatic_replay": False,
        },
    )
    report: dict[str, JsonValue] = {
        "authorization_sha256": auth.sha256,
        "selection_sha256": selection_sha,
        "billing_verified": False,
        "journeys": [],
    }
    journeys: list[JsonValue] = []
    report["journeys"] = journeys
    try:
        identity = SubscriptionChatIdentity(
            authorization=auth,
            authorization_path=authority_path,
            coding_selection_sha256=selection_sha,
        )
        cassette = demo_cassette()
        state = ConversationController.fresh(
            auth.workspace, cassette, live_chat=identity
        )
        storage = root / "sessions"
        with ConversationStore(storage, state.session_id, auth.workspace) as store:
            store.save(state)
            runtime = SubscriptionChatRuntime(
                identity, auth.workspace, state.session_id
            )
            controller = ConversationController(
                state, cassette, store.save, run_live_chat=runtime.run
            )
            controller.submit(
                "Synthetic qualification. Remember marker ORBIT-17. Return exactly ACK."
            )
            await controller.step()
            if controller.state.entries[-1].answer != "ACK":
                raise ValueError("First saved subscription turn failed")
        with ConversationStore(
            storage, state.session_id, auth.workspace, create=False
        ) as store:
            saved = store.load()
            runtime = SubscriptionChatRuntime(
                identity, auth.workspace, state.session_id, saved.exchanges_consumed
            )
            controller = ConversationController(
                saved, cassette, store.save, run_live_chat=runtime.run
            )
            controller.submit(
                "Return exactly the synthetic marker remembered in the preceding turn."
            )
            await controller.step()
            if controller.state.entries[-1].answer != "ORBIT-17":
                raise ValueError("Cold-resume subscription context failed")
            journeys.append({"name": "saved_session_cold_resume", "passed": True})
            critic = auth.grant("critic_anthropic")
            schema = JsonSchemaOutput(
                name="qualification",
                json_schema={
                    "type": "object",
                    "properties": {"status": {"type": "string", "enum": ["ok"]}},
                    "required": ["status"],
                    "additionalProperties": False,
                },
            )
            request = ModelRequest(
                provider=critic.provider,
                model=critic.model,
                effort=critic.effort,
                turns=(
                    Turn(
                        role="user",
                        blocks=(
                            TextBlock(
                                text=(
                                    "Synthetic qualification. Return exactly "
                                    '{"status":"ok"}.'
                                )
                            ),
                        ),
                    ),
                ),
                max_output=18000,
                max_text_output_bytes=16000,
                max_output_tokens=2048,
                response_format=schema,
            )
            await AuthorizedSubscriptionClient(
                auth, authority_path, "critic_anthropic", "qualification-json"
            ).complete(request)
            journeys.append({"name": "claude_strict_json", "passed": True})
            broker = CodingVCS(
                selection.git, selection.workspace, selection.staging_root
            )
            try:
                executor = DockerCodingChild(
                    CodingContainer(
                        selection.docker,
                        selection.image_id,
                        selection.artifacts_root / "coding-lifecycles",
                    )
                )

                def guard() -> None:
                    observed, sha = read_coding_selection(
                        root / "selection.json", auth.workspace
                    )
                    if observed != selection or sha != selection_sha:
                        raise ValueError("Coding qualification selection changed")

                workflow = LiveCodingWorkflow(
                    selection,
                    selection_sha,
                    SubscriptionCodingModels(),
                    executor,
                    broker,
                    guard,
                )

                async def coding(config: AgentConfig, attempt: int) -> AgentResult:
                    return await workflow.run(config, attempt, auth.session_id)

                controller.run_live_coding = coding
                controller.submit(
                    "Implement add(a,b) to return a+b for integers, preserving "
                    "existing tests. Add creator tests for zero and negative values.",
                    implementation_request=True,
                )
                await controller.step()
                if controller.state.entries[-1].status != "completed":
                    raise ValueError("Provider-diverse coding workflow failed")
            finally:
                broker.close()
            verify_saved_attempts(auth, controller.state.exchanges_consumed)
            journeys.append(
                {
                    "name": "provider_diverse_creator_child_critics_judge",
                    "passed": True,
                    "provider_families": ["openai", "anthropic"],
                }
            )
        # Observe native init without retaining payloads; usage remains uncertain.
        original = claude_subscription.invoke
        cancelled_task: asyncio.Task[ModelResponse] | None = None
        native_started = asyncio.Event()
        original_read = codex_subscription.read_stream

        async def observe_read(stream: asyncio.StreamReader, limit: int) -> bytes:
            if limit != codex_subscription.MAX_EVENTS:
                return await original_read(stream, limit)
            chunks: list[bytes] = []
            size = 0
            pending: bytes = b""
            while part := await stream.read(4096):
                size += len(part)
                if size > limit:
                    raise ValueError("Native cancellation event limit exceeded")
                chunks.append(part)
                pending += part
                while b"\n" in pending:
                    parts: list[bytes] = pending.split(b"\n", 1)
                    line = parts[0]
                    pending = parts[1]
                    value = json.loads(line)
                    if value.get("type") == "system" and value.get("subtype") == "init":
                        assert cancelled_task is not None
                        native_started.set()
                        asyncio.get_running_loop().call_later(
                            0.25, cancelled_task.cancel
                        )
            return b"".join(chunks)

        async def observe_invoke(
            executable: Path,
            arguments: tuple[str, ...],
            cwd: Path,
            *,
            data: bytes = b"",
            timeout: float = 15,
            output_limit: int = codex_subscription.MAX_EVENTS,
        ) -> tuple[int, bytes, bytes]:
            if "--print" in arguments:
                with patch.object(codex_subscription, "read_stream", observe_read):
                    return await original(
                        executable,
                        arguments,
                        cwd,
                        data=data,
                        timeout=timeout,
                        output_limit=output_limit,
                    )
            return await original(
                executable,
                arguments,
                cwd,
                data=data,
                timeout=timeout,
                output_limit=output_limit,
            )

        cancelled_request = request.model_copy(
            update={
                "response_format": None,
                "turns": (
                    Turn(
                        role="user",
                        blocks=(
                            TextBlock(
                                text="Synthetic cancellation qualification. "
                                "Write a numbered list describing integers "
                                "from 1 to 500. Do not use tools."
                            ),
                        ),
                    ),
                ),
            }
        )
        with patch.object(claude_subscription, "invoke", observe_invoke):
            cancelled_task = asyncio.create_task(
                AuthorizedSubscriptionClient(
                    auth, authority_path, "critic_anthropic", "qualification-cancel"
                ).complete(cancelled_request)
            )
            try:
                await cancelled_task
            except asyncio.CancelledError:
                if not native_started.is_set():
                    raise ValueError(
                        "Claude cancellation lacked native startup observation"
                    ) from None
            else:
                raise ValueError("Claude cancellation did not interrupt the invocation")
        try:
            await AuthorizedSubscriptionClient(
                auth, authority_path, "critic_anthropic", "qualification-cancel"
            ).complete(cancelled_request)
        except ValueError:
            pass
        else:
            raise ValueError("Cancelled native call was replayed")
        journeys.append(
            {
                "name": "claude_cancellation_recovery",
                "passed": True,
                "remote_usage": "uncertain",
                "replay_refused": True,
            }
        )
        report["result"] = "passed"
    except (Exception, asyncio.CancelledError) as error:
        report["result"] = "stopped_on_first_failure"
        report["failure_type"] = type(error).__name__
        write(root / "qualification.json", report)
        raise RuntimeError(
            "Subscription qualification stopped; inspect sanitized receipts"
        ) from None
    write(root / "qualification.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--codex", type=Path)
    parser.add_argument("--claude", type=Path)
    parser.add_argument("--git", type=Path, default=Path("/usr/bin/git"))
    parser.add_argument("--docker", type=Path, default=Path("/usr/local/bin/docker"))
    parser.add_argument("--image-id")
    parser.add_argument("--valid-for-seconds", type=int, default=1200)
    parser.add_argument(
        "--approve-live-subscription-qualification", action="store_true"
    )
    args = parser.parse_args()
    if args.action == "prepare":
        if (
            args.codex is None
            or args.claude is None
            or args.image_id is None
            or not 1 <= args.valid_for_seconds <= 3600
        ):
            parser.error(
                "prepare requires both absolute clients, image ID and bounded expiry"
            )
        prepare(args)
    else:
        if not args.approve_live_subscription_qualification:
            parser.error(
                "run requires explicit reviewed live subscription "
                "qualification approval"
            )
        print(json.dumps(asyncio.run(exercise(args.root.absolute()))))


if __name__ == "__main__":
    main()
