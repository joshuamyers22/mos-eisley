"""Settled runtime responses publish atomically without reasoning disclosure."""

import io
import json
import sqlite3
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import TestCase

from pydantic import JsonValue, ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import ReasoningBlock, TextBlock, Turn
from mos_eisley.run.skill_runtime_response import (
    PublishedSkillRuntimeResult,
    SkillRuntimeResponseStore,
    SkillRuntimeResponseStorePolicy,
    publish_skill_runtime_response,
)
from mos_eisley.run.store import private_write
from tests import test_skill_runtime_provider as provider_module


class SkillRuntimeResponsePublicationTests(TestCase):
    def setUp(self) -> None:
        self.provider = provider_module.SkillRuntimeProviderTransactionTests()
        self.provider.setUp()
        self.addCleanup(self.provider.doCleanups)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = SkillRuntimeResponseStore.create(
            self.root / "runtime-responses.sqlite",
            self.provider.grant.dispatch.response_policy,
            self.provider.store,
        )
        self.publish_at = self.provider.now + timedelta(seconds=1)

    def response(
        self,
        *,
        output: list[dict[str, JsonValue]] | None = None,
        response_id: str = "resp_skill_runtime_1",
    ) -> dict[str, JsonValue]:
        return {
            "id": response_id,
            "status": "completed",
            "model": self.provider.runtime.spend_policy.model,
            "service_tier": "default",
            "output": cast(
                JsonValue,
                output
                if output is not None
                else [
                    {
                        "type": "reasoning",
                        "id": "reasoning_1",
                        "summary": [
                            {"type": "summary_text", "text": "private summary"}
                        ],
                        "encrypted_content": "private-encrypted-reasoning",
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Published answer."}
                        ],
                    },
                ],
            ),
            "usage": {
                "input_tokens": 12,
                "output_tokens": 7,
                "input_tokens_details": {
                    "cached_tokens": 0,
                    "cache_write_tokens": 0,
                },
                "output_tokens_details": {"reasoning_tokens": 3},
            },
            "incomplete_details": None,
        }

    def execute(self, response: dict[str, JsonValue] | None = None):
        transport = provider_module.FakeProviderTransport(response or self.response())
        return self.provider.execute(transport)

    def publish(self, response: dict[str, JsonValue] | None = None):
        capability, reply = self.execute(response)
        prepared = self.provider.grant.dispatch.admission_fixture.prepared
        publication, result = publish_skill_runtime_response(
            prepared,
            capability.issuance,
            reply,
            self.provider.grant.store,
            self.provider.store,
            self.provider.runtime.ledger,
            self.store,
            self.publish_at,
        )
        return capability, reply, publication, result

    def test_atomically_retains_response_and_publishes_text_only(self) -> None:
        capability, reply, publication, result = self.publish()

        self.assertEqual(
            publication.raw_response_sha256, reply.outcome.provider_response_sha256
        )
        self.assertEqual(publication.result_sha256, result.result_sha256)
        self.assertEqual(result.issuance_sha256, capability.issuance.issuance_sha256)
        self.assertEqual(result.provider_request_id, "resp_skill_runtime_1")
        self.assertEqual(result.stop_reason, "end_turn")
        self.assertEqual(result.usage.input, 12)
        self.assertEqual(result.usage.output, 7)
        self.assertEqual(
            result.charged_microusd,
            self.provider.runtime.spend_policy.cost(12, 7),
        )
        self.assertEqual(
            result.assistant,
            Turn(role="assistant", blocks=(TextBlock(text="Published answer."),)),
        )
        self.assertTrue(result.reasoning_omitted_from_publication)
        self.assertFalse(result.provider_credential_added_to_publication)
        self.assertNotIn(b"private summary", canonical_bytes(result))
        self.assertNotIn(b"private-encrypted-reasoning", canonical_bytes(result))
        self.assertIn(b"private-encrypted-reasoning", self.store.path.read_bytes())
        loaded = self.store.load(publication.publication_id)
        self.assertEqual(loaded, (publication, result))
        self.assertEqual(self.store.status().publications, 1)

    def test_replay_cannot_publish_the_same_outcome_twice(self) -> None:
        capability, reply, publication, result = self.publish()
        prepared = self.provider.grant.dispatch.admission_fixture.prepared
        with self.assertRaisesRegex(ValueError, "already published"):
            publish_skill_runtime_response(
                prepared,
                capability.issuance,
                reply,
                self.provider.grant.store,
                self.provider.store,
                self.provider.runtime.ledger,
                self.store,
                self.publish_at,
            )
        self.assertEqual(
            self.store.load(publication.publication_id), (publication, result)
        )

    def test_response_substitution_is_rejected_before_publication(self) -> None:
        capability, reply = self.execute()
        changed = reply.model_copy(
            update={"response": {**reply.response, "id": "resp_substituted"}}
        )
        with self.assertRaisesRegex(ValueError, "provenance is incomplete"):
            publish_skill_runtime_response(
                self.provider.grant.dispatch.admission_fixture.prepared,
                capability.issuance,
                changed,
                self.provider.grant.store,
                self.provider.store,
                self.provider.runtime.ledger,
                self.store,
                self.publish_at,
            )
        self.assertEqual(self.store.status().publications, 0)

    def test_tool_output_is_not_publishable_even_after_settlement(self) -> None:
        response = self.response(
            output=[
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "unexpected",
                    "arguments": "{}",
                }
            ]
        )
        capability, reply = self.execute(response)
        with self.assertRaisesRegex(ValueError, "not publishable|unauthorized tools"):
            publish_skill_runtime_response(
                self.provider.grant.dispatch.admission_fixture.prepared,
                capability.issuance,
                reply,
                self.provider.grant.store,
                self.provider.store,
                self.provider.runtime.ledger,
                self.store,
                self.publish_at,
            )
        self.assertEqual(self.store.status().publications, 0)

    def test_reasoning_only_response_is_not_publishable(self) -> None:
        response = self.response(
            output=[
                {
                    "type": "reasoning",
                    "id": "reasoning_1",
                    "summary": [],
                    "encrypted_content": "opaque",
                }
            ]
        )
        capability, reply = self.execute(response)
        with self.assertRaisesRegex(ValueError, "no publishable text"):
            publish_skill_runtime_response(
                self.provider.grant.dispatch.admission_fixture.prepared,
                capability.issuance,
                reply,
                self.provider.grant.store,
                self.provider.store,
                self.provider.runtime.ledger,
                self.store,
                self.publish_at,
            )

    def test_store_failure_is_atomic_and_does_not_change_settled_spend(self) -> None:
        capability, reply = self.execute()
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_publication BEFORE INSERT ON publications "
                "BEGIN SELECT RAISE(ABORT, 'simulated publication failure'); END"
            )
            connection.commit()
        ledger_before = self.provider.runtime.ledger.snapshot()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated publication"):
            publish_skill_runtime_response(
                self.provider.grant.dispatch.admission_fixture.prepared,
                capability.issuance,
                reply,
                self.provider.grant.store,
                self.provider.store,
                self.provider.runtime.ledger,
                self.store,
                self.publish_at,
            )
        self.assertEqual(self.provider.runtime.ledger.snapshot(), ledger_before)
        self.assertEqual(self.store.status().publications, 0)

    def test_published_result_schema_rejects_reasoning_blocks(self) -> None:
        _, _, _, result = self.publish()
        changed = result.model_dump(mode="json")
        changed["assistant"] = Turn(
            role="assistant",
            blocks=(
                ReasoningBlock(
                    provider="openai",
                    visible="private",
                    opaque={"encrypted_content": "private"},
                ),
            ),
        ).model_dump(mode="json")
        with self.assertRaises(ValidationError):
            PublishedSkillRuntimeResult.model_validate(changed)

    def test_store_policy_substitution_is_rejected(self) -> None:
        changed_policy = self.provider.grant.dispatch.response_policy.model_copy(
            update={"store_id": "e" * 64}
        )
        with self.assertRaisesRegex(ValueError, "does not match transaction"):
            SkillRuntimeResponseStore.create(
                self.root / "other-responses.sqlite",
                changed_policy,
                self.provider.store,
            )

    def test_store_policy_rejects_incoherent_retention_limits(self) -> None:
        with self.assertRaisesRegex(
            ValidationError, "per-response limit exceeds total retention"
        ):
            SkillRuntimeResponseStorePolicy(
                store_id="e" * 64,
                provider_transaction_store_id=self.provider.store.policy.store_id,
                max_raw_response_bytes=2048,
                max_total_raw_response_bytes=1024,
            )

    def test_cli_exposes_verified_result_without_private_reasoning(self) -> None:
        policy_path = self.root / "response-policy.json"
        private_write(
            policy_path,
            canonical_bytes(self.provider.grant.dispatch.response_policy),
        )
        cli_store_path = self.root / "cli-runtime-responses.sqlite"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-response-store-create",
                        "--path",
                        str(cli_store_path),
                        "--response-store-policy",
                        str(policy_path),
                        "--provider-transaction-store",
                        str(self.provider.store.path),
                    ]
                ),
                0,
            )
        self.assertEqual(
            json.loads(stdout.getvalue())["type"],
            "evaluation.skill_runtime.response_store_created",
        )

        capability, reply = self.execute()
        cli_store = SkillRuntimeResponseStore(cli_store_path)
        publication, _ = publish_skill_runtime_response(
            self.provider.grant.dispatch.admission_fixture.prepared,
            capability.issuance,
            reply,
            self.provider.grant.store,
            self.provider.store,
            self.provider.runtime.ledger,
            cli_store,
            self.publish_at,
        )
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-response-store-status",
                        "--response-store",
                        str(cli_store_path),
                    ]
                ),
                0,
            )
        status = json.loads(stdout.getvalue())
        self.assertEqual(status["publications"], 1)
        self.assertFalse(status["raw_response_export_authorized"])

        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(
                main(
                    [
                        "skill-runtime-response-result",
                        "--response-store",
                        str(cli_store_path),
                        "--publication-id",
                        publication.publication_id,
                    ]
                ),
                0,
            )
        output = stdout.getvalue()
        event = json.loads(output)
        self.assertEqual(
            event["result"]["assistant"]["blocks"],
            [{"kind": "text", "text": "Published answer."}],
        )
        self.assertNotIn("private summary", output)
        self.assertNotIn("private-encrypted-reasoning", output)

    def test_stored_result_tampering_is_detected_before_read(self) -> None:
        _, _, publication, _ = self.publish()
        with sqlite3.connect(self.store.path) as connection:
            connection.execute(
                "UPDATE publications SET provider_request_id = ?",
                ("resp_tampered",),
            )
            connection.commit()
        with self.assertRaisesRegex(ValueError, "record is invalid"):
            self.store.load(publication.publication_id)
