"""Explicit, budgeted OpenAI text turns for saved terminal conversations."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from mos_eisley.conversation_state import LiveChatIdentity
from mos_eisley.core.agent import AgentConfig, AgentResult, run_agent
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.openai_live import EphemeralOpenAITransport
from mos_eisley.providers.openai_responses import OpenAIResponsesClient
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport, SpendPolicy
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.tools.none import NoToolsDispatcher


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
    ) -> None:
        policy.check_current()
        if policy.provider != "openai" or policy.model != identity.model:
            raise ValueError("live chat spending policy model mismatch")
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

    async def run(self, config: AgentConfig, attempt: int) -> AgentResult:
        if (
            config.provider != "openai"
            or config.model != self.identity.model
            or config.effort != self.identity.effort
            or config.max_iterations != 1
            or config.max_tool_calls != 0
            or config.budget.max_output_tokens != self.identity.max_output_tokens
        ):
            raise ValueError("live chat request differs from saved provider identity")
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
        transport = BudgetedOpenAITransport(
            EphemeralOpenAITransport(self.api_key, config.request_timeout_seconds),
            self.policy,
            directory,
            self.ledger,
        )
        return await run_agent(
            config,
            openai_registry(),
            OpenAIResponsesClient(transport),
            NoToolsDispatcher(),
        )
