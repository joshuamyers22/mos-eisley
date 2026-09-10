"""Strict runtime revalidation without a complete state JSON buffer."""

import gc
import json
import weakref
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from test_conversation_streamed_inputs import recording_with_arguments

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_review import REVIEW_PROMPT, review_summary
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    ConversationEntry,
    ConversationState,
    WorkingConversationState,
    validate_runtime_state,
)
from mos_eisley.core.models import ReviewResult, Verdict, canonical_bytes, digest
from mos_eisley.core.protocol import ToolCallBlock


class NativeValidationTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        memories = MemoryStore(self.root / "memory", self.root)
        memories.change("user", "set", text='user é🪐\n"\\')
        memories.change("project", "set", text="project\tcontext")
        self.cassette = recording_with_arguments()
        self.state = ConversationController.fresh(
            self.root, self.cassette, memories.load()
        ).model_copy(
            update={
                "retained_cassette": self.cassette,
                "entries": (ConversationEntry(text='queued é🪐\n"\\'),),
            }
        )

    def test_native_validation_matches_json_for_full_and_working_state(self) -> None:
        working = WorkingConversationState.model_validate(dict(self.state))
        for state in (self.state, working):
            with self.subTest(kind=type(state).__name__):
                expected = type(state).model_validate_json(state.model_dump_json())
                actual = validate_runtime_state(state)
                self.assertIs(type(actual), type(state))
                self.assertEqual(actual, expected)
                self.assertEqual(canonical_bytes(actual), canonical_bytes(expected))
                self.assertIsNot(actual.memory, state.memory)
                self.assertIsNot(actual.retained_cassette, state.retained_cassette)
                self.assertIsNot(actual.entries[0], state.entries[0])

    def test_runtime_validation_does_not_encode_complete_state_json(self) -> None:
        expected = canonical_bytes(self.state)
        with patch.object(
            ConversationState,
            "model_dump_json",
            side_effect=AssertionError("complete state JSON buffer"),
        ):
            actual = validate_runtime_state(self.state)
            working = validate_runtime_state(
                WorkingConversationState.model_validate(dict(self.state))
            )
        self.assertEqual(canonical_bytes(actual), expected)
        self.assertEqual(canonical_bytes(working), expected)

    def test_legacy_json_decodes_before_native_validation(self) -> None:
        body = self.state.model_dump(mode="json")
        body.pop("schema_version")
        body.pop("revision")
        body["entries"][0].pop("status")
        body["memory"]["user"]["document"]["updated_at"] = body["memory"]["user"][
            "document"
        ]["updated_at"].replace("Z", "+00:00")
        loaded = ConversationState.model_validate_json(json.dumps(body, indent=2))
        self.assertEqual(
            canonical_bytes(validate_runtime_state(loaded)), canonical_bytes(self.state)
        )
        assert loaded.memory is not None and loaded.memory.user is not None
        self.assertEqual(
            loaded.memory.user.document.updated_at.utcoffset(), timedelta(0)
        )
        assert loaded.retained_cassette is not None
        self.assertIsInstance(loaded.retained_cassette.exchanges, tuple)

    def test_nested_recording_schema_is_checked_even_with_matching_digest(self) -> None:
        exchange = self.cassette.exchanges[0]
        assert exchange.response is not None
        invalid = self.cassette.model_copy(
            update={
                "exchanges": (
                    exchange.model_copy(
                        update={
                            "response": exchange.response.model_copy(
                                update={
                                    "usage": exchange.response.usage.model_copy(
                                        update={"input": -1}
                                    )
                                }
                            )
                        }
                    ),
                )
            }
        )
        state = self.state.model_copy(
            update={
                "retained_cassette": invalid,
                "cassette_sha256": digest(canonical_bytes(invalid)),
            }
        )
        with self.assertRaises(ValueError):
            validate_runtime_state(state)

    def test_nested_recording_mutation_is_detached_and_rechecked(self) -> None:
        actual = validate_runtime_state(self.state)
        response = self.cassette.exchanges[0].response
        assert response is not None
        block = response.turn.blocks[0]
        assert isinstance(block, ToolCallBlock)
        block.args["value"] = ["changed", {"nested": True}]
        self.assertNotEqual(actual.retained_cassette, self.cassette)
        with self.assertRaisesRegex(ValueError, "retained recording"):
            validate_runtime_state(self.state)
        self.assertEqual(validate_runtime_state(actual), actual)

    def test_native_runtime_types_are_strict(self) -> None:
        for update in ({"revision": True}, {"entries": list(self.state.entries)}):
            with self.subTest(field=next(iter(update))), self.assertRaises(ValueError):
                validate_runtime_state(self.state.model_copy(update=update))

    def test_nested_memory_schema_and_integrity_are_rechecked(self) -> None:
        memory = self.state.memory
        assert memory is not None and memory.user is not None
        document = memory.user.document.model_copy(update={"revision": -1})
        snapshot = memory.user.model_copy(
            update={"document": document, "sha256": digest(canonical_bytes(document))}
        )
        invalid = self.state.model_copy(
            update={"memory": memory.model_copy(update={"user": snapshot})}
        )
        with self.assertRaises(ValueError):
            validate_runtime_state(invalid)

    def test_global_progress_and_steering_constraints_still_apply(self) -> None:
        for update in (
            {"exchanges_consumed": 1},
            {
                "entries": (
                    self.state.entries[0].model_copy(update={"steering_for": 0}),
                )
            },
            {"memory_disabled": True},
        ):
            with self.subTest(field=next(iter(update))), self.assertRaises(ValueError):
                validate_runtime_state(self.state.model_copy(update=update))

    def review_state(self, result: ReviewResult) -> WorkingConversationState:
        entry = ArchivedConversationEntry(
            text=REVIEW_PROMPT,
            status="completed",
            answer=review_summary(result),
            artifact_refs={
                "review_packet": "a" * 64,
                "review_result": digest(canonical_bytes(result)),
            },
            source_sha256="b" * 64,
            review_brief_id=result.verdict.brief_id,
            review_result=result,
        )
        return WorkingConversationState.model_validate(
            {**dict(self.state), "entries": (entry,)}
        )

    def test_excluded_review_cache_is_preserved_and_revalidated(self) -> None:
        result = ReviewResult(
            critics=(),
            verdict=Verdict(
                brief_id="c" * 64, decision="accept", rationale="Recorded."
            ),
        )
        state = self.review_state(result)
        actual = validate_runtime_state(state)
        self.assertEqual(actual.entries[0].review_result, result)
        self.assertIsNot(actual.entries[0].review_result, result)
        self.assertEqual(canonical_bytes(actual), canonical_bytes(state))
        with self.assertRaises(ValueError):
            ConversationState.model_validate_json(actual.model_dump_json())

    def test_excluded_review_cache_cannot_bypass_nested_schema(self) -> None:
        result = ReviewResult(
            critics=(),
            verdict=Verdict(
                brief_id="c" * 64, decision="accept", rationale="Recorded."
            ),
        )
        result = result.model_copy(
            update={"verdict": result.verdict.model_copy(update={"schema_version": 2})}
        )
        # The cached value has a matching hash and summary but an invalid schema.
        state = self.review_state(result)
        with self.assertRaises(ValueError):
            validate_runtime_state(state)

    def test_validation_does_not_retain_source_model(self) -> None:
        source = self.state.model_copy()
        reference = weakref.ref(source)
        enabled = gc.isenabled()
        gc.disable()
        try:
            actual = validate_runtime_state(source)
            del source
            self.assertIsNone(reference())
            self.assertEqual(actual, self.state)
        finally:
            if enabled:
                gc.enable()
