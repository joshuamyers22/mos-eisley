"""Synthetic probe retains a conservative ledger state on every outcome."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase

from pydantic import JsonValue

from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import SpendPolicy, SpendReceipt
from mos_eisley.run.anthropic_probe import PROBE_MODEL, run_anthropic_probe
from mos_eisley.run.spend_ledger import SpendLedger


def _policy() -> SpendPolicy:
    now = datetime.now(UTC)
    return SpendPolicy(
        provider="anthropic",
        model=PROBE_MODEL,
        pricing_source="https://platform.claude.com/docs/en/models/sonnet-5/overview",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
        input_microusd_per_million=2_000_000,
        output_microusd_per_million=10_000_000,
        max_cost_microusd=10_000,
        max_input_tokens=256,
        max_output_tokens=32,
    )


class StubTransport:
    def __init__(
        self,
        *,
        failed: bool = False,
        wrong_model: bool = False,
        model: str = PROBE_MODEL,
    ) -> None:
        self.failed = failed
        self.wrong_model = wrong_model
        self.model = model
        self.calls = 0

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        assert payload["model"] == self.model
        return 50

    async def create_message(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls += 1
        if self.failed:
            raise ProviderError("synthetic transport failed")
        return {
            "id": "msg_synthetic",
            "type": "message",
            "role": "assistant",
            "model": "wrong" if self.wrong_model else self.model,
            "stop_reason": "end_turn",
            "content": cast(JsonValue, [{"type": "text", "text": "OK"}]),
            "usage": {
                "input_tokens": 50,
                "output_tokens": 2,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        }


class AnthropicProbeTests(IsolatedAsyncioTestCase):
    async def test_opus_policy_selects_a_distinct_credentialed_probe_model(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "opus"
            directory.mkdir()
            ledger = SpendLedger.create(root / "spend.sqlite", 10_000)
            policy = _policy().model_copy(
                update={
                    "model": "claude-opus-5-5",
                    "input_microusd_per_million": 4_000_000,
                    "output_microusd_per_million": 20_000_000,
                }
            )
            result = await run_anthropic_probe(
                policy=policy,
                ledger=ledger,
                directory=directory,
                transport=StubTransport(model="claude-opus-5-5"),
            )
            self.assertEqual(result.model, "claude-opus-5-5")
            self.assertEqual(ledger.snapshot().unresolved_entries, 0)

    async def test_success_settles_and_retains_metadata_only(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "probe"
            directory.mkdir()
            ledger = SpendLedger.create(root / "spend.sqlite", 10_000)
            result = await run_anthropic_probe(
                policy=_policy(),
                ledger=ledger,
                directory=directory,
                transport=StubTransport(),
            )
            self.assertTrue(result.credentialed_exchange_observed)
            self.assertFalse(result.review_role_conformance_proven)
            self.assertEqual(result.usage.input, 50)
            entry = ledger.entry_status(result.ledger_entry_id)
            assert entry is not None
            self.assertEqual(entry.status, "settled")
            self.assertNotIn("Synthetic API", (directory / "result.json").read_text())

    async def test_transport_failure_retains_full_uncertain_reservation(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "probe"
            directory.mkdir()
            ledger = SpendLedger.create(root / "spend.sqlite", 10_000)
            with self.assertRaises(ProviderError):
                await run_anthropic_probe(
                    policy=_policy(),
                    ledger=ledger,
                    directory=directory,
                    transport=StubTransport(failed=True),
                )
            receipt = SpendReceipt.model_validate_json(
                (directory / "receipt.json").read_bytes()
            )
            self.assertEqual(receipt.status, "uncertain")
            self.assertEqual(ledger.snapshot().unresolved_entries, 1)
            self.assertFalse((directory / "result.json").exists())

    async def test_wrong_model_blocks_ledger_and_does_not_publish_result(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "probe"
            directory.mkdir()
            ledger = SpendLedger.create(root / "spend.sqlite", 10_000)
            with self.assertRaises(ProviderError):
                await run_anthropic_probe(
                    policy=_policy(),
                    ledger=ledger,
                    directory=directory,
                    transport=StubTransport(wrong_model=True),
                )
            self.assertTrue(ledger.snapshot().blocked)
            self.assertFalse((directory / "result.json").exists())
