"""One-use live coding role calls over the existing reviewed spending transports."""

from pathlib import Path
from uuid import uuid4

from pydantic import JsonValue

from mos_eisley.conversation_live_coding import CodingRoute
from mos_eisley.core.agent import (
    AgentConfig,
    AgentResult,
    build_request,
    check_request_budget,
    run_agent,
)
from mos_eisley.core.budget import resolve_budget
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.registry import anthropic_registry, openai_registry
from mos_eisley.providers.anthropic_live import EphemeralAnthropicTransport
from mos_eisley.providers.anthropic_messages import (
    AnthropicMessagesClient,
)
from mos_eisley.providers.anthropic_messages import (
    request_payload as anthropic_payload,
)
from mos_eisley.providers.anthropic_spend import (
    PreReservedAnthropicTransport,
    prepare_full_anthropic_reservation,
)
from mos_eisley.providers.openai_live import EphemeralOpenAITransport
from mos_eisley.providers.openai_responses import OpenAIResponsesClient, request_payload
from mos_eisley.providers.openai_spend import (
    PreReservedOpenAITransport,
    SpendPolicy,
    prepare_full_reservation,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
from mos_eisley.run.store import private_write
from mos_eisley.tools.none import NoToolsDispatcher


class _AnthropicMessageTransport:
    def __init__(self, transport: PreReservedAnthropicTransport) -> None:
        self.transport = transport

    async def create_message(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return await self.transport.create_response(payload)

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        raise ValueError(
            "Token counting belongs to the pre-reserved spending boundary."
        )


class LiveCodingModels:
    def __init__(
        self,
        ledger: SpendLedger,
        expected_ledger_id: str,
        openai_key: str,
        anthropic_key: str,
    ) -> None:
        if (
            ledger.policy.ledger_id != expected_ledger_id
            or not openai_key
            or not anthropic_key
        ):
            raise ValueError(
                "Live coding requires the selected ledger and both "
                "provider credentials."
            )
        self.ledger = ledger
        self.openai_key = openai_key
        self.anthropic_key = anthropic_key

    async def call(
        self, route: CodingRoute, config: AgentConfig, directory: Path
    ) -> AgentResult:
        policy = SpendPolicy.model_validate_json(
            read_bounded(route.spend_policy, 64_000)
        )
        policy.check_current()
        if (
            policy.policy_sha256 != route.expected_policy_sha256
            or (config.provider, config.model, config.effort)
            != (route.provider, route.model, route.effort)
            or (policy.provider, policy.model) != (route.provider, route.model)
            or policy.schema_version != 2
        ):
            raise ValueError(
                "Live coding request differs from its reviewed route/policy."
            )
        registry = (
            openai_registry() if route.provider == "openai" else anthropic_registry()
        )
        resolved = registry.resolve(route.provider, route.model, route.effort)
        if resolved.substituted or config.max_iterations != 1 or config.max_tool_calls:
            raise ValueError(
                "Live coding permits one tool-free response with exact effort."
            )
        budget = resolve_budget(resolved.spec, resolved.effort, config.budget)
        request = build_request(
            config, resolved, budget, NoToolsDispatcher(), config.initial_turns
        )
        check_request_budget(request, budget)
        payload = (
            request_payload(request)
            if route.provider == "openai"
            else anthropic_payload(request)
        )
        reservation = (
            prepare_full_reservation(payload, policy)
            if route.provider == "openai"
            else prepare_full_anthropic_reservation(payload, policy)
        )
        entry = LedgerEntry(
            entry_id=digest(uuid4().bytes),
            reservation_sha256=digest(canonical_bytes(reservation)),
            reserved_microusd=reservation.reserved_microusd,
        )
        # This exclusive marker precedes reservation and credential use. A failed
        # or cancelled call is never automatically retried or refunded.
        private_write(directory / "before-send.json", canonical_bytes(entry))
        self.ledger.reserve(entry, max_unresolved_entries=1)
        if route.provider == "openai":
            transport = PreReservedOpenAITransport(
                EphemeralOpenAITransport(
                    self.openai_key, config.request_timeout_seconds
                ),
                policy,
                directory,
                self.ledger,
                reservation,
                entry,
            )
            return await run_agent(
                config, registry, OpenAIResponsesClient(transport), NoToolsDispatcher()
            )
        anthropic = PreReservedAnthropicTransport(
            EphemeralAnthropicTransport(
                self.anthropic_key, config.request_timeout_seconds
            ),
            policy,
            directory,
            self.ledger,
            reservation,
            entry,
        )
        return await run_agent(
            config,
            registry,
            AnthropicMessagesClient(_AnthropicMessageTransport(anthropic)),
            NoToolsDispatcher(),
        )
