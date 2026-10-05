"""Explicit, budgeted OpenAI text turns for saved terminal conversations."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from pathlib import Path

from pydantic import JsonValue

from mos_eisley.conversation_state import LiveChatIdentity
from mos_eisley.core.agent import AgentConfig, AgentResult, run_agent
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.openai_live import EphemeralOpenAITransport
from mos_eisley.providers.openai_responses import OpenAIResponsesClient
from mos_eisley.providers.openai_spend import (
    BudgetedOpenAITransport,
    CountedTransport,
    SpendPolicy,
)
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.tools.none import NoToolsDispatcher
from mos_eisley.tools.repository_read import (
    INSPECTION_SYSTEM,
    RepositoryReadDispatcher,
    RepositoryReader,
)


def private_artifacts_root(path: Path) -> Path:
    """Require an existing owner-only directory; do not follow a root symlink."""
    absolute = path.absolute()
    info = absolute.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("live artifacts root must be an owner-only directory")
    return absolute.resolve(strict=True)


class LiveChatRuntime:
    def __init__(
        self,
        identity: LiveChatIdentity,
        policy: SpendPolicy,
        ledger: SpendLedger,
        api_key: str,
        session_id: str,
        workspace: Path | None = None,
    ) -> None:
        policy.check_current()
        if policy.provider != "openai" or policy.model != identity.model:
            raise ValueError("live chat spending policy model mismatch")
        if policy.schema_version != 2:
            raise ValueError("live chat requires a schema-2 spending policy")
        if policy.policy_sha256 != identity.spend_policy_sha256:
            raise ValueError("live chat spending policy changed")
        if ledger.policy.ledger_id != identity.spend_ledger_id:
            raise ValueError("live chat spending ledger changed")
        if ledger.snapshot().blocked:
            raise ValueError("shared spending ledger is blocked")
        if policy.max_output_tokens != identity.max_output_tokens:
            raise ValueError("live chat output cap changed")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for live chat")
        root = private_artifacts_root(Path(identity.artifacts_root))
        if str(root) != identity.artifacts_root:
            raise ValueError("live chat artifacts root changed")
        openai_registry().resolve("openai", identity.model, identity.effort)
        self.identity = identity
        self.policy = policy
        self.ledger = ledger
        self.api_key = api_key
        self.session_id = session_id
        self.root = root
        self.workspace = workspace
        self.repository_reader = (
            RepositoryReader(workspace)
            if identity.repository_read and workspace is not None
            else None
        )

    async def run(self, config: AgentConfig, attempt: int) -> AgentResult:
        tools_requested = config.max_tool_calls > 0
        if (
            config.provider != "openai"
            or config.model != self.identity.model
            or config.effort != self.identity.effort
            or config.max_iterations != (5 if tools_requested else 1)
            or config.max_tool_calls != (6 if tools_requested else 0)
            or config.budget.max_output_tokens != self.identity.max_output_tokens
        ):
            raise ValueError("live chat request differs from saved provider identity")
        if tools_requested and (
            not self.identity.repository_read
            or self.workspace is None
            or not config.system.endswith(INSPECTION_SYSTEM)
        ):
            raise ValueError("repository inspection is not authorized for this turn")
        self.policy.check_current()
        if self.ledger.snapshot().blocked:
            raise ValueError("shared spending ledger is blocked")
        session = self.root / self.session_id
        session.mkdir(mode=0o700, exist_ok=True)
        info = session.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise ValueError("live chat session artifacts directory is unsafe")
        directory = session / f"attempt-{attempt:04d}"
        directory.mkdir(mode=0o700, exist_ok=False)
        dispatcher = (
            RepositoryReadDispatcher(self.workspace, reader=self.repository_reader)
            if tools_requested and self.workspace is not None
            else NoToolsDispatcher()
        )
        if tools_requested:
            assert isinstance(dispatcher, RepositoryReadDispatcher)
            transport = _MultiResponseTransport(
                self.api_key,
                config.request_timeout_seconds,
                self.policy,
                self.ledger,
                directory,
                dispatcher.reader.verify,
            )
        else:
            transport = BudgetedOpenAITransport(
                EphemeralOpenAITransport(self.api_key, config.request_timeout_seconds),
                self.policy,
                directory,
                self.ledger,
            )
        result = await run_agent(
            config,
            openai_registry(),
            OpenAIResponsesClient(transport),
            dispatcher,
        )
        if isinstance(dispatcher, RepositoryReadDispatcher) and dispatcher.sources:
            result = result.model_copy(
                update={
                    "final_text": _answer_with_sources(
                        result.final_text, dispatcher.sources
                    )
                }
            )
        return result


class _MultiResponseTransport:
    """One independent reservation and ledger entry for each bounded model response."""

    def __init__(
        self,
        api_key: str,
        timeout: float,
        policy: SpendPolicy,
        ledger: SpendLedger,
        directory: Path,
        verify_workspace: Callable[[], None],
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.policy = policy
        self.ledger = ledger
        self.directory = directory
        self.count = 0
        self.verify_workspace = verify_workspace

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.verify_workspace()
        self.count += 1
        if self.count > 5:
            raise ValueError("live repository inspection response limit reached")
        child = self.directory / f"response-{self.count:04d}"
        child.mkdir(mode=0o700, exist_ok=False)
        transport = BudgetedOpenAITransport(
            _WorkspaceCheckedTransport(
                EphemeralOpenAITransport(self.api_key, self.timeout),
                self.verify_workspace,
            ),
            self.policy,
            child,
            self.ledger,
            allow_repository_tools=True,
        )
        return await transport.create_response(payload)


class _WorkspaceCheckedTransport:
    def __init__(
        self, transport: CountedTransport, verify_workspace: Callable[[], None]
    ) -> None:
        self.transport = transport
        self.verify_workspace = verify_workspace

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        self.verify_workspace()
        count = await self.transport.count_input_tokens(payload)
        self.verify_workspace()
        return count

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.verify_workspace()
        return await self.transport.create_response(payload)


def _answer_with_sources(answer: str, sources: list[str]) -> str:
    references: list[str] = []
    unique = list(dict.fromkeys(sources))
    for source in unique[:8]:
        if len(", ".join((*references, source))) > 4200:
            break
        references.append(source)
    footer = "\n\nSources: " + ", ".join(references)
    if len(references) < len(unique):
        footer += " (more sources omitted)"
    if len(answer) + len(footer) > 8000:
        marker = "\n[Answer shortened to retain source references.]"
        answer = answer[: 8000 - len(footer) - len(marker)] + marker
    return answer + footer
