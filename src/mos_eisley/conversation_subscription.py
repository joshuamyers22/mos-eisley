"""Saved subscription identity and role dispatch under immutable local authority."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field

from mos_eisley.core.agent import AgentConfig, AgentResult, run_agent
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.ports import ModelClient
from mos_eisley.core.protocol import Effort, ModelRequest, ModelResponse
from mos_eisley.providers.claude_subscription import ClaudeSubscriptionClient
from mos_eisley.providers.codex_subscription import (
    CodexSubscriptionClient,
    select_client,
)
from mos_eisley.subscription_authorization import (
    SubscriptionAuthorization,
    SubscriptionRole,
    executable_sha256,
    native_context_sha256,
    read_authorization,
    subscription_registry,
)
from mos_eisley.subscription_usage import reserve_usage, verify_saved_attempts
from mos_eisley.tools.none import NoToolsDispatcher


class SubscriptionChatIdentity(Contract):
    authorization: SubscriptionAuthorization
    authorization_path: Path
    coding_selection_sha256: Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @property
    def model(self) -> str:
        return self.authorization.grant("chat").model

    @property
    def effort(self) -> Effort:
        return self.authorization.grant("chat").effort

    @property
    def provider(self) -> str:
        return self.authorization.grant("chat").provider

    @property
    def max_output_tokens(self) -> int:
        return self.authorization.max_output_tokens

    @property
    def artifacts_root(self) -> str:
        return str(self.authorization.usage_root)

    @property
    def repository_read(self) -> bool:
        return False


def check_authority(
    authorization: SubscriptionAuthorization, path: Path, role: SubscriptionRole
) -> None:
    authorization.check_current(authorization.workspace, authorization.session_id)
    read_authorization(path, authorization.sha256)
    grant = authorization.grant(role)
    selected = select_client(grant.client)
    if (
        selected != grant.client
        or executable_sha256(selected) != grant.client_sha256
        or native_context_sha256(grant.provider) != grant.authentication_context_sha256
    ):
        raise ValueError(
            "Subscription native client or authentication location changed"
        )


class AuthorizedSubscriptionClient:
    def __init__(
        self,
        authorization: SubscriptionAuthorization,
        path: Path,
        role: SubscriptionRole,
        call_id: str,
    ) -> None:
        self.authorization = authorization
        self.path = path
        self.role: SubscriptionRole = role
        self.call_id = call_id

    async def complete(self, request: ModelRequest) -> ModelResponse:
        auth = self.authorization
        grant = auth.grant(self.role)
        check_authority(auth, self.path, self.role)
        if (
            (request.provider, request.model, request.effort)
            != (grant.provider, grant.model, grant.effort)
            or request.tools
            or request.max_output > auth.max_output_bytes + 2000
            or request.max_output_tokens is None
            or request.max_output_tokens > auth.max_output_tokens
        ):
            raise ValueError(
                "Subscription request differs from its immutable role grant"
            )
        request = request.model_copy(
            update={
                "max_text_output_bytes": min(
                    request.max_text_output_bytes or auth.max_output_bytes,
                    auth.max_output_bytes,
                )
            }
        )
        raw = canonical_bytes(request)
        if len(raw) > auth.max_input_bytes:
            raise ValueError(
                "Subscription canonical request exceeds its input allowance"
            )
        with reserve_usage(auth, self.role, digest(raw), self.call_id) as slot:

            def guard() -> None:
                check_authority(auth, self.path, self.role)

            native: ModelClient
            if grant.provider == "openai_subscription":
                native = CodexSubscriptionClient(
                    grant.client,
                    slot.path / "native",
                    allow_data_transfer=True,
                    allow_subscription_usage=True,
                    timeout=auth.timeout_seconds,
                    authorized_profile=(grant.model, grant.effort),
                    dispatch_guard=guard,
                )
            else:
                native = ClaudeSubscriptionClient(
                    grant.client,
                    slot.path / "native",
                    allow_data_transfer=True,
                    allow_subscription_usage=True,
                    timeout=auth.timeout_seconds,
                    dispatch_guard=guard,
                )
            response = await native.complete(request)
            guard()
            slot.complete()
            return response


async def run_subscription_role(
    authorization: SubscriptionAuthorization,
    path: Path,
    role: SubscriptionRole,
    config: AgentConfig,
    call_id: str,
) -> AgentResult:
    grant = authorization.grant(role)
    if (
        (config.provider, config.model, config.effort)
        != (grant.provider, grant.model, grant.effort)
        or config.max_iterations != 1
        or config.max_tool_calls != 0
    ):
        raise ValueError("Subscription role requires one exact tool-free invocation")
    # Bound native auth preflight and owned cleanup in the outer deadline.
    config = config.model_copy(
        update={
            "request_timeout_seconds": min(300.0, authorization.timeout_seconds + 35.0)
        }
    )
    result = await run_agent(
        config,
        subscription_registry(),
        AuthorizedSubscriptionClient(authorization, path, role, call_id),
        NoToolsDispatcher(),
    )
    return result.model_copy(
        update={"usage": result.usage.model_copy(update={"billing_verified": False})}
    )


class SubscriptionChatRuntime:
    def __init__(
        self,
        identity: SubscriptionChatIdentity,
        workspace: Path,
        session_id: str,
        consumed: int = 0,
    ) -> None:
        identity.authorization.check_current(workspace, session_id)
        if not identity.authorization_path.is_absolute():
            raise ValueError("Subscription authorization path must be absolute")
        check_authority(identity.authorization, identity.authorization_path, "chat")
        verify_saved_attempts(identity.authorization, consumed)
        self.identity = identity

    async def run(self, config: AgentConfig, attempt: int) -> AgentResult:
        if (
            not 0 <= attempt < 16
            or os.getuid() != self.identity.authorization.owner_uid
        ):
            raise ValueError("Subscription session attempt is inadmissible")
        verify_saved_attempts(self.identity.authorization, attempt)
        return await run_subscription_role(
            self.identity.authorization,
            self.identity.authorization_path,
            "chat",
            config,
            f"chat-{attempt:04d}",
        )
