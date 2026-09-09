"""Whole-run reservations for opt-in OpenAI analysis; no content artifacts."""

import copy
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import JsonValue

from mos_eisley.analysis.controller import AnalysisConfig, analysis_mcp_config
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import (
    CountedTransport,
    SpendPolicy,
    SpendReceipt,
)
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement, SpendLedger
from mos_eisley.tools.mcp import MCPConfig


class AnalysisSpending:
    """Reserve before credentials/transfer; finish even on cancellation.

    A crash leaves a held reservation. Uncertain generation retains the entire run
    reservation and consumes an admission slot. An operator must use the same local
    ledger for every run in an account; this is not a distributed account authority.
    """

    def __init__(
        self,
        config: AnalysisConfig,
        mcp: MCPConfig,
        policy: SpendPolicy,
        ledger: SpendLedger,
        expected_ledger_id: str,
        accepted_microusd: int,
    ) -> None:
        self.config = AnalysisConfig.model_validate_json(config.model_dump_json())
        self.mcp = analysis_mcp_config(mcp)
        self.policy = SpendPolicy.model_validate_json(policy.model_dump_json())
        self.ledger = ledger
        self.policy.check_current()
        if (
            config.provider != "openai"
            or config.model != policy.model
            or policy.schema_version != 2
            or config.max_output_tokens > policy.max_output_tokens
            or policy.valid_until
            <= datetime.now(UTC) + timedelta(seconds=config.run_timeout_seconds)
            or ledger.policy.ledger_id != expected_ledger_id
            or ledger.path.stat().st_uid != os.getuid()
            or ledger.path.stat().st_mode & 0o077
        ):
            raise ValueError("analytical spending scope is invalid")
        self.reserved = (
            policy.reservation_cost(
                config.max_total_input_tokens, config.max_total_output_tokens
            )
            + config.max_model_turns
            - 1
        )
        if (
            type(accepted_microusd) is not int
            or self.reserved > accepted_microusd
            or self.reserved > policy.max_cost_microusd
        ):
            raise ValueError("analytical run reservation exceeds accepted spending")
        binding = {
            "config_sha256": digest(canonical_bytes(self.config)),
            "mcp_sha256": digest(canonical_bytes(self.mcp)),
            "policy_sha256": policy.policy_sha256,
            "ledger_id": expected_ledger_id,
            "uid": os.getuid(),
            "account": config.account,
            "reserved_microusd": self.reserved,
        }
        self.entry = LedgerEntry(
            entry_id=digest(uuid4().bytes),
            reservation_sha256=digest(json.dumps(binding, sort_keys=True).encode()),
            reserved_microusd=self.reserved,
        )
        self.requests = self.input_tokens = self.output_tokens = self.cache_writes = 0
        self.charged = 0
        self._active = self._busy = self._pending = self._violation = False
        self._uncertain = False
        self._tools: list[JsonValue] | None = None
        self.receipt: SpendReceipt | None = None

    def reserve(self) -> None:
        if self._active or self.receipt is not None:
            raise ValueError("analytical reservation is single use")
        self.ledger.reserve(
            self.entry, max_unresolved_entries=self.config.max_active_runs
        )
        self._active = True

    def finish(self) -> SpendReceipt:
        if not self._active or self._busy:
            raise ValueError("analytical reservation cannot finish in this state")
        status = (
            "violation"
            if self._violation
            else "uncertain"
            if self._pending or self._uncertain
            else "settled"
        )
        retained = self.charged if status == "settled" else self.reserved
        self.ledger.settle(
            LedgerSettlement(
                entry_id=self.entry.entry_id,
                reservation_sha256=self.entry.reservation_sha256,
                status=status,
                charged_microusd=retained,
            )
        )
        self._active = False
        self.receipt = SpendReceipt(
            reservation_sha256=self.entry.reservation_sha256,
            status=status,
            retained_microusd=retained,
            input_tokens=self.input_tokens if status == "settled" else None,
            output_tokens=self.output_tokens if status == "settled" else None,
            cache_write_tokens=self.cache_writes if status == "settled" else None,
            ledger_id=self.ledger.policy.ledger_id,
            ledger_entry_id=self.entry.entry_id,
        )
        return self.receipt

    def transport(self, upstream: CountedTransport) -> "AnalysisTransport":
        return AnalysisTransport(self, upstream)

    async def create_response(
        self, payload: dict[str, JsonValue], upstream: CountedTransport
    ) -> dict[str, JsonValue]:
        s = self
        if (
            not s._active
            or s._busy
            or s._pending
            or s._uncertain
            or s._violation
            or s.requests >= s.config.max_model_turns
        ):
            raise ProviderError("analytical spending controller is unavailable")
        s._busy = True
        try:
            return await self._create(copy.deepcopy(payload), upstream)
        finally:
            s._busy = False

    async def _create(
        self, request: dict[str, JsonValue], upstream: CountedTransport
    ) -> dict[str, JsonValue]:
        s = self
        s.policy.check_current()
        permitted = {
            "model",
            "instructions",
            "input",
            "tools",
            "reasoning",
            "max_output_tokens",
            "parallel_tool_calls",
            "include",
            "store",
            "truncation",
            "service_tier",
        }
        tools = request.get("tools")
        if (
            set(request) - permitted
            or request.get("model") != s.policy.model
            or request.get("store") is not False
            or request.get("truncation") != "disabled"
            or request.get("service_tier") not in (None, "default")
            or not isinstance(tools, list)
            or not tools
            or any(
                not isinstance(tool, dict)
                or tool.get("type") != "function"
                or tool.get("name") not in s.mcp.tools
                for tool in tools
            )
        ):
            raise ProviderError("analytical request exceeded its approved scope")
        if s._tools is None:
            s._tools = copy.deepcopy(tools)
        elif s._tools != tools:
            raise ProviderError("analytical tool definitions changed")
        output_cap = request.get("max_output_tokens")
        if (
            type(output_cap) is not int
            or not 1 <= output_cap <= s.config.max_output_tokens
            or s.output_tokens + output_cap > s.config.max_total_output_tokens
        ):
            raise ProviderError("analytical output token budget reached")
        request["service_tier"] = "default"
        count_payload = {
            key: value
            for key, value in request.items()
            if key not in {"max_output_tokens", "store", "include", "service_tier"}
        }
        s.requests += 1  # Failed count attempts also consume the request allowance.
        tokens = await upstream.count_input_tokens(copy.deepcopy(count_payload))
        if (
            type(tokens) is not int
            or not 0 <= tokens <= s.policy.max_input_tokens
            or s.input_tokens + tokens > s.config.max_total_input_tokens
        ):
            raise ProviderError("analytical input token budget reached")
        s.policy.check_current()
        s._pending = (
            True  # Any ambiguous dispatch, including cancellation, retains all.
        )
        try:
            response = await upstream.create_response(request)
        except BaseException:
            s._uncertain = True
            raise
        usage = response.get("usage")
        if not isinstance(usage, dict):
            raise ProviderError("analytical response omitted usage")
        actual_input, actual_output = (
            usage.get("input_tokens"),
            usage.get("output_tokens"),
        )
        details = usage.get("input_tokens_details")
        cache_write = (
            details.get("cache_write_tokens") if isinstance(details, dict) else None
        )
        if any(
            type(value) is not int or value < 0
            for value in (actual_input, actual_output, cache_write)
        ):
            raise ProviderError("analytical response returned invalid usage")
        # Narrow after exact-type checks, including rejection of bool-as-int.
        assert isinstance(actual_input, int) and isinstance(actual_output, int)
        assert isinstance(cache_write, int)
        if (
            actual_input > tokens
            or actual_output > output_cap
            or cache_write > actual_input
            or response.get("model") != s.policy.model
            or response.get("service_tier") != "default"
        ):
            s._violation = True
            raise ProviderError("analytical response violated pricing assumptions")
        s.charged += s.policy.cost(actual_input, actual_output, cache_write)
        s.input_tokens += actual_input
        s.output_tokens += actual_output
        s.cache_writes += cache_write
        s._pending = False
        return response


class AnalysisTransport:
    def __init__(self, spending: AnalysisSpending, upstream: CountedTransport) -> None:
        self.spending, self.upstream = spending, upstream

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return await self.spending.create_response(payload, self.upstream)
