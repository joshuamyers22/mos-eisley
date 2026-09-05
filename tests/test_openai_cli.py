"""Explicit live-data consent, credential handling, and durable CLI output."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.core.agent import AgentConfig, AgentResult, AgentUsage
from mos_eisley.core.budget import resolve_budget
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.ports import Journal
from mos_eisley.core.protocol import (
    JournalEvent,
    ModelResponse,
    TextBlock,
    Turn,
    Usage,
)
from mos_eisley.core.registry import openai_registry
from mos_eisley.providers.openai_spend import (
    SpendPolicy,
    SpendReceipt,
    SpendReservation,
)
from mos_eisley.run.live_store import load_live_run


class OpenAICliTests(TestCase):
    def test_missing_policy_cannot_start_live_run(self) -> None:
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "secret-test-key"}),
            patch("mos_eisley.cli._openai_run") as run,
            patch("mos_eisley.cli.read_bounded") as read,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(
                main(["openai-run", "--prompt", "missing", "--allow-data-transfer"]),
                2,
            )
            run.assert_not_called()
            read.assert_not_called()

    def test_consent_and_api_key_are_required_before_file_or_network_access(
        self,
    ) -> None:
        with redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(main(["openai-run", "--prompt", "missing"]), 2)
        self.assertIn("validation failed", errors.getvalue())

        with (
            patch.dict(os.environ, {}, clear=True),
            redirect_stderr(io.StringIO()) as errors,
        ):
            self.assertEqual(
                main(
                    [
                        "openai-run",
                        "--prompt",
                        "missing",
                        "--allow-data-transfer",
                    ]
                ),
                2,
            )
        self.assertNotIn("OPENAI_API_KEY", errors.getvalue())

    def test_live_command_saves_result_without_credential(self) -> None:
        async def fake_run(
            config: AgentConfig,
            api_key: str,
            journal: Journal,
            spend_policy: SpendPolicy,
            directory: Path,
        ) -> AgentResult:
            self.assertEqual(api_key, "secret-test-key")
            registry = openai_registry()
            resolved = registry.resolve("openai", "gpt-6-astra", "medium")
            budget = resolve_budget(resolved.spec, resolved.effort, config.budget)
            response = ModelResponse(
                turn=Turn(
                    role="assistant", blocks=(TextBlock(text="Live-shaped result."),)
                ),
                stop_reason="end_turn",
                usage=Usage(unit="tokens", input=12, output=3),
                provider_request_id="resp_test",
            )
            journal.record(
                JournalEvent(
                    type="model.request.started",
                    request_id="model-0001",
                    sequence=0,
                    payload_sha256="0" * 64,
                )
            )
            journal.record(
                JournalEvent(
                    type="model.response.completed",
                    request_id="model-0001",
                    sequence=1,
                    payload_sha256=digest(canonical_bytes(response)),
                )
            )
            reservation = SpendReservation(
                policy_sha256=spend_policy.policy_sha256,
                request_sha256="a" * 64,
                input_tokens=12,
                max_output_tokens=4096,
                reserved_microusd=spend_policy.cost(12, 4096),
            )
            (directory / "spend-reservation.json").write_bytes(
                canonical_bytes(reservation)
            )
            (directory / "spend-receipt.json").write_bytes(
                canonical_bytes(
                    SpendReceipt(
                        reservation_sha256=digest(canonical_bytes(reservation)),
                        status="settled",
                        retained_microusd=spend_policy.cost(12, 3),
                        input_tokens=12,
                        output_tokens=3,
                    )
                )
            )
            return AgentResult(
                resolved_model=resolved,
                budget=budget,
                turns=config.initial_turns + (response.turn,),
                responses=(response,),
                final_text="Live-shaped result.",
                usage=AgentUsage(
                    unit="tokens",
                    requests=1,
                    tools=0,
                    billed_input=12,
                    billed_output=3,
                    largest_request=500,
                ),
            )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "prompt.txt"
            prompt.write_text("Review this explicit prompt.")
            policy_path = root / "spend-policy.json"
            policy_path.write_bytes(
                canonical_bytes(
                    SpendPolicy(
                        model="gpt-6-astra",
                        pricing_source="fixture",
                        valid_from=datetime.now(UTC) - timedelta(days=1),
                        valid_until=datetime.now(UTC) + timedelta(days=1),
                        input_microusd_per_million=1_000_000,
                        output_microusd_per_million=1_000_000,
                        max_cost_microusd=10_000,
                    )
                )
            )
            output = root / "runs"
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret-test-key"}),
                patch("mos_eisley.cli._openai_run", side_effect=fake_run),
                redirect_stdout(io.StringIO()) as stdout,
            ):
                exit_code = main(
                    [
                        "openai-run",
                        "--prompt",
                        str(prompt),
                        "--output",
                        str(output),
                        "--allow-data-transfer",
                        "--spend-policy",
                        str(policy_path),
                        "--json",
                    ]
                )
            self.assertEqual(exit_code, 0)
            event = json.loads(stdout.getvalue())
            self.assertEqual(event["type"], "openai.completed")
            self.assertEqual(event["cost_upper_bound_microusd"], 15)
            run = Path(event["path"])
            config, events, result = load_live_run(run)
            self.assertEqual(config.provider, "openai")
            self.assertEqual(len(events), 2)
            self.assertEqual(result.usage.unit, "tokens")
            self.assertNotIn(
                b"secret-test-key",
                b"".join(path.read_bytes() for path in run.iterdir()),
            )
            # Rehashing a changed receipt cannot hide inconsistency with usage.
            receipt_path = run / "spend-receipt.json"
            receipt = SpendReceipt.model_validate_json(receipt_path.read_bytes())
            payload = canonical_bytes(receipt.model_copy(update={"input_tokens": 0}))
            receipt_path.write_bytes(payload)
            manifest_path = run / "manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            for artifact in manifest["artifacts"]:
                if artifact["name"] == "spend-receipt.json":
                    artifact["sha256"] = digest(payload)
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "spending artifacts"):
                load_live_run(run)
