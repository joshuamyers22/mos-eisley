"""Canonical streaming parity, digest reuse and fresh mutation checks."""

import gc
import json
import weakref
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from pydantic import Field

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_inputs import ActiveInputLimitError, ActiveInputLimits
from mos_eisley.conversation_state import ConversationState
from mos_eisley.core import models
from mos_eisley.core.models import (
    Contract,
    canonical_bytes,
    canonical_fingerprint,
    digest,
)
from mos_eisley.core.protocol import ModelResponse, ToolCallBlock, Turn, Usage
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange


class Payload(Contract):
    values: dict[str, Any]
    omitted: str | None = Field(default=None, exclude_if=lambda value: value is None)


def recording_with_arguments() -> AgentCassette:
    return AgentCassette(
        exchanges=(
            AgentExchange(
                request_sha256="0" * 64,
                response=ModelResponse(
                    turn=Turn(
                        role="assistant",
                        blocks=(
                            ToolCallBlock(
                                id="call", name="fixture", args={"value": "before"}
                            ),
                        ),
                    ),
                    usage=Usage(input=1, output=1),
                    stop_reason="tool_use",
                ),
            ),
        )
    )


class StreamedInputTests(TestCase):
    def test_fingerprint_matches_canonical_bytes_for_json_edge_cases(self) -> None:
        cases: tuple[dict[str, Any], ...] = (
            {},
            {"z": [None, True, False, 0, -1, 1.25, -0.0, 1e-20, 1e20], "a": {}},
            {"text": 'é🪐\n\r\t"\\\x00', "nested": {"β": ["x", {"a": 1}]}},
            {"time": datetime(2026, 9, 10, tzinfo=UTC), "tuple": (1, 2)},
            {"long": "unicode é " * 20_000},
        )
        for values in cases:
            with self.subTest(keys=list(values)):
                value = Payload(values=values)
                encoded = canonical_bytes(value)
                fingerprint = canonical_fingerprint(value)
                self.assertEqual(fingerprint.sha256, digest(encoded))
                self.assertEqual(fingerprint.bytes, len(encoded))

    def test_measurement_does_not_call_full_json_dumps(self) -> None:
        cassette = demo_cassette()
        expected = canonical_bytes(cassette)
        with patch.object(
            models.json, "dumps", side_effect=AssertionError("joined JSON")
        ):
            fingerprint = canonical_fingerprint(cassette)
            ActiveInputLimits().admit(None, cassette)
        self.assertEqual(fingerprint.sha256, digest(expected))
        self.assertEqual(fingerprint.bytes, len(expected))

    def test_fresh_admission_and_digest_share_one_recording_dump(self) -> None:
        cassette = demo_cassette()
        original = AgentCassette.model_dump
        with (
            TemporaryDirectory() as directory,
            patch.object(
                AgentCassette, "model_dump", autospec=True, side_effect=original
            ) as dump,
        ):
            state = ConversationController.fresh(
                Path(directory), cassette, input_limits=ActiveInputLimits()
            )
            self.assertEqual(dump.call_count, 1)
        self.assertEqual(state.cassette_sha256, digest(canonical_bytes(cassette)))

    def test_controller_admission_and_resume_digest_share_one_recording_dump(
        self,
    ) -> None:
        cassette = demo_cassette()
        with TemporaryDirectory() as directory:
            state = ConversationController.fresh(Path(directory), cassette)
            with patch.object(
                AgentCassette,
                "model_dump",
                autospec=True,
                side_effect=AgentCassette.model_dump,
            ) as dump:
                ConversationController(
                    state, cassette, lambda _: None, input_limits=ActiveInputLimits()
                )
                self.assertEqual(dump.call_count, 1)

    def test_mismatched_recording_is_still_rejected_after_admission(self) -> None:
        cassette = demo_cassette()
        with TemporaryDirectory() as directory:
            state = ConversationController.fresh(Path(directory), cassette).model_copy(
                update={"cassette_sha256": "0" * 64}
            )
            with self.assertRaisesRegex(ValueError, "exact recorded cassette"):
                ConversationController(
                    state, cassette, lambda _: None, input_limits=ActiveInputLimits()
                )

    def test_input_policy_cannot_supply_the_recording_integrity_digest(self) -> None:
        cassette = demo_cassette()
        with TemporaryDirectory() as directory:
            state = ConversationController.fresh(Path(directory), cassette).model_copy(
                update={"cassette_sha256": "0" * 64}
            )
            with (
                patch.object(
                    ActiveInputLimits,
                    "admit_recording",
                    return_value=models.CanonicalFingerprint("0" * 64, 1),
                ),
                self.assertRaisesRegex(ValueError, "exact recorded cassette"),
            ):
                ConversationController(
                    state, cassette, lambda _: None, input_limits=ActiveInputLimits()
                )

    def test_recording_limit_boundaries_use_exact_canonical_bytes(self) -> None:
        cassette = recording_with_arguments()
        response = cassette.exchanges[0].response
        assert response is not None
        block = response.turn.blocks[0]
        assert isinstance(block, ToolCallBlock)
        block.args["value"] = "é" * 3000
        size = len(canonical_bytes(cassette))
        self.assertEqual(
            ActiveInputLimits(recording_max_bytes=size).admit_recording(cassette).bytes,
            size,
        )
        with self.assertRaisesRegex(ActiveInputLimitError, f"needs {size} bytes"):
            ActiveInputLimits(recording_max_bytes=size - 1).admit_recording(cassette)

    def test_nested_mutation_is_remeasured_instead_of_reusing_identity(self) -> None:
        cassette = recording_with_arguments()
        limits = ActiveInputLimits(recording_max_bytes=4096)
        first = limits.admit_recording(cassette)
        response = cassette.exchanges[0].response
        assert response is not None
        block = response.turn.blocks[0]
        assert isinstance(block, ToolCallBlock)
        block.args["value"] = "x" * 5000
        with self.assertRaises(ActiveInputLimitError):
            limits.admit_recording(cassette)
        block.args["value"] = "after"
        second = limits.admit_recording(cassette)
        self.assertNotEqual(first.sha256, second.sha256)
        self.assertEqual(second.sha256, digest(canonical_bytes(cassette)))

    def test_retained_recording_validation_detects_nested_mutation(self) -> None:
        cassette = recording_with_arguments()
        with TemporaryDirectory() as directory:
            fresh = ConversationController.fresh(Path(directory), cassette)
            state = ConversationState.model_validate(
                {**dict(fresh), "retained_cassette": cassette}
            )
            response = cassette.exchanges[0].response
            assert response is not None
            block = response.turn.blocks[0]
            assert isinstance(block, ToolCallBlock)
            block.args["value"] = "changed"
            with self.assertRaisesRegex(ValueError, "retained recording"):
                ConversationState.model_validate(dict(state))

    def test_late_encoding_failure_returns_no_fingerprint(self) -> None:
        value = Payload(values={"a": "valid", "z": "\ud800"})
        with self.assertRaises(UnicodeEncodeError):
            canonical_fingerprint(value)
        with self.assertRaises(UnicodeEncodeError):
            canonical_bytes(value)

    def test_fingerprint_does_not_retain_source_without_cyclic_gc(self) -> None:
        enabled = gc.isenabled()
        gc.disable()
        try:
            value = Payload(values={"text": "temporary" * 1000})
            reference = weakref.ref(value)
            canonical_fingerprint(value)
            del value
            self.assertIsNone(reference())
        finally:
            if enabled:
                gc.enable()

    def test_refresh_keeps_exact_cassette_digest_and_snapshot_contract(self) -> None:
        cassette = demo_cassette()
        with TemporaryDirectory() as directory:
            state = ConversationController.fresh(Path(directory), cassette)
            controller = ConversationController(
                state, cassette, lambda _: None, input_limits=ActiveInputLimits()
            )
            controller.refresh_memory(None, cassette)
            self.assertEqual(
                controller.state.cassette_sha256, digest(canonical_bytes(cassette))
            )
            encoded = canonical_bytes(controller.state)
            self.assertEqual(
                json.loads(encoded)["cassette_sha256"],
                canonical_fingerprint(cassette).sha256,
            )
            self.assertEqual(
                ConversationState.model_validate_json(encoded), controller.state
            )
