"""Wrong answers, ambiguous tables, retained lineage, expiry and export integrity."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from pydantic import JsonValue

from mos_eisley.analysis.artifacts import (
    AnalysisArtifact,
    BundleManifest,
    delete_expired,
    export_csv,
    load_artifact,
    save_artifact,
    verify_export,
)
from mos_eisley.analysis.controller import (
    AnalysisConfig,
    AnalysisFailure,
    AnalysisResult,
    run_analysis,
)
from mos_eisley.analysis.demo import AnalysisFixtureClient, fixture_config, run_demo
from mos_eisley.analysis.evidence import (
    AnalysisAnswer,
    AnalysisEvidence,
    CellClaim,
    ToolTrace,
    checked_answer,
    sql_records,
)
from mos_eisley.analysis.fixture_server import REVISION
from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    ToolCallBlock,
    ToolResultBlock,
    Usage,
)
from mos_eisley.core.registry import fixture_registry


def trace(result_id: str = "result-0002", value: JsonValue = 42) -> ToolTrace:
    now = datetime.now(UTC)
    call = ToolCallBlock(
        id="metric-call",
        name="run_metric",
        args={
            "arguments_json": json.dumps({"name": "total", "revision": REVISION}),
        },
    )
    return ToolTrace(
        call=call,
        started_at=now,
        completed_at=now,
        outcome="accepted",
        result_id=result_id,
        response=ToolResultBlock(
            call_id=call.id,
            name=call.name,
            content=json.dumps(
                {
                    "structured_content": {
                        "columns": ["total"],
                        "rows": [[value]],
                        "truncated": False,
                        "revision": REVISION,
                        "submitted_sql": "SELECT 42 AS total",
                        "normalized_sql": "SELECT 42 AS total",
                        "data_snapshot": None,
                    }
                }
            ),
        ),
    )


def answer(value: object = 42, **changes: object) -> AnalysisAnswer:
    return AnalysisAnswer.model_validate(
        {
            "status": "answer",
            "text": "Untrusted prose: the total is 99999.",
            "result_ids": ("result-0002",),
            "claims": (
                CellClaim.model_validate(
                    {
                        "result_id": "result-0002",
                        "row": 0,
                        "column": "total",
                        "value": value,
                    }
                ),
            ),
            **changes,
        }
    )


def artifact() -> AnalysisArtifact:
    item = trace()
    context_call = ToolCallBlock(
        id="analysis-context",
        name="get_semantic_context",
        args={"arguments_json": "{}"},
    )
    context = item.model_copy(
        update={
            "call": context_call,
            "result_id": "result-0001",
            "response": ToolResultBlock(
                call_id=context_call.id,
                name=context_call.name,
                content=json.dumps({"structured_content": {"revision": REVISION}}),
            ),
        }
    )
    traces = (context, item)
    return AnalysisArtifact(
        result=AnalysisResult(
            answer=checked_answer(answer(), traces),
            semantic_revision=REVISION,
            evidence=tuple(
                AnalysisEvidence(
                    result_id=cast(str, t.result_id),
                    tool=t.call.name,
                    result_sha256=digest(
                        canonical_bytes(cast(ToolResultBlock, t.response))
                    ),
                    complete=True,
                )
                for t in traces
            ),
            tool_trace=traces,
            sql_trail=sql_records(traces),
            started_at=item.started_at,
            completed_at=item.completed_at,
            provider="fixture",
            model="tool-reviewer-v1",
            question="What is the total?",
            question_sha256=digest(b"What is the total?"),
            provider_usage=(Usage(input=10, output=10),),
            model_turns=1,
            tool_calls=2,
            input_bytes=10,
            output_bytes=10,
            retention="private",
            value_verification="returned_cells",
        )
    )


class CellValidationTests(TestCase):
    def test_wrong_numeric_values_and_json_type_confusion_rejected(self) -> None:
        for value in (43, "42", 42.0, True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                checked_answer(answer(value), (trace(),))
        result = checked_answer(answer(), (trace(),))
        self.assertNotIn("99999", result.text)
        self.assertIn('column "total": 42', result.text)

    def test_missing_ambiguous_truncated_or_malformed_table_rejected(self) -> None:
        for data in (
            {"columns": ["total", "total"], "rows": [[42, 43]], "truncated": False},
            {"columns": ["total"], "rows": [[42, 43]], "truncated": False},
            {"columns": ["total"], "rows": [], "truncated": False},
            {"columns": ["total"], "rows": [[42]], "truncated": True},
            {"columns": ["total"], "rows": [[42]]},
            {"columns": [None], "rows": [[42]], "truncated": False},
        ):
            item = trace()
            response = cast(ToolResultBlock, item.response).model_copy(
                update={"content": json.dumps({"structured_content": data})}
            )
            with self.subTest(data=data), self.assertRaises(ValueError):
                checked_answer(
                    answer(), (item.model_copy(update={"response": response}),)
                )

    def test_absent_duplicate_and_context_claims_rejected(self) -> None:
        claim = CellClaim(result_id="result-0002", row=0, column="total", value=42)
        for proposal in (
            answer(claims=()),
            answer(result_ids=()),
            answer(claims=(claim, claim)),
            answer(claims=(claim.model_copy(update={"row": 5}),)),
            answer(claims=(claim.model_copy(update={"column": "other"}),)),
            answer(status="clarify"),
        ):
            with self.assertRaises(ValueError):
                checked_answer(proposal, (trace(),))
        item = trace()
        context = item.model_copy(
            update={"call": item.call.model_copy(update={"name": "list_metrics"})}
        )
        with self.assertRaises(ValueError):
            checked_answer(answer(), (context,))

    def test_nonfinite_and_duplicate_source_json_rejected(self) -> None:
        for content in (
            '{"structured_content":{"truncated":false,"columns":["total"],"rows":[[NaN]]}}',
            '{"structured_content":{"truncated":true,"truncated":false,"columns":["total"],"rows":[[42]]}}',
        ):
            item = trace()
            item = item.model_copy(
                update={
                    "response": cast(ToolResultBlock, item.response).model_copy(
                        update={"content": content}
                    )
                }
            )
            with self.assertRaises(ValueError):
                checked_answer(answer(), (item,))

    def test_sql_and_response_lineage_are_rechecked(self) -> None:
        saved = artifact()
        data = saved.model_dump(mode="json")
        result = cast(dict[str, JsonValue], data["result"])
        trail = cast(list[dict[str, JsonValue]], result["sql_trail"])
        trail[0]["submitted_sql"] = "SELECT 999"
        with self.assertRaises(ValueError):
            AnalysisArtifact.model_validate_json(json.dumps(data))
        updates: tuple[dict[str, JsonValue], ...] = (
            {"question": "Another question"},
            {"tool_calls": 3},
            {"value_verification": "not_applicable"},
            {"evidence": []},
        )
        for update in updates:
            result = saved.result.model_dump(mode="json")
            result.update(update)
            with self.assertRaises(ValueError):
                AnalysisResult.model_validate_json(json.dumps(result))


class ArtifactTests(TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.saved = artifact()

    def save(self) -> Path:
        return save_artifact(self.root, self.saved, 3600)

    def test_private_roundtrip_and_export_require_exact_parent(self) -> None:
        path = self.save()
        manifest, loaded = load_artifact(path)
        self.assertEqual(loaded, self.saved)
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        self.assertEqual((path / "result.json").stat().st_mode & 0o777, 0o600)
        exported = export_csv(path, "result-0002", self.root)
        self.assertEqual((exported / "result.csv").read_bytes(), b"total\r\n42\r\n")
        self.assertEqual(
            verify_export(exported, path).parent_sha256, manifest.payload_sha256
        )
        # Identical content hashes can identify identical captured evidence, even
        # when separately packaged. A different captured result must not verify.
        different = self.saved.result.model_dump(mode="json")
        different["question"] = "Other question"
        different["question_sha256"] = digest(b"Other question")
        other_artifact = AnalysisArtifact(
            result=AnalysisResult.model_validate_json(json.dumps(different))
        )
        other = save_artifact(self.root, other_artifact, 3600)
        with self.assertRaises(ValueError):
            verify_export(exported, other)

    def test_export_selects_named_result_not_last_result(self) -> None:
        result = self.saved.result
        later = trace("result-0003", 99)
        later_call = later.call.model_copy(update={"id": "later-call"})
        later = later.model_copy(
            update={
                "call": later_call,
                "response": cast(ToolResultBlock, later.response).model_copy(
                    update={"call_id": later_call.id}
                ),
            }
        )
        traces = (*result.tool_trace, later)
        updated = result.model_copy(
            update={
                "tool_trace": traces,
                "sql_trail": sql_records(traces),
                "tool_calls": 3,
                "completed_at": later.completed_at,
                "evidence": (
                    *result.evidence,
                    AnalysisEvidence(
                        result_id="result-0003",
                        tool="run_metric",
                        complete=True,
                        result_sha256=digest(
                            canonical_bytes(cast(ToolResultBlock, later.response))
                        ),
                    ),
                ),
            }
        )
        path = save_artifact(self.root, AnalysisArtifact(result=updated), 3600)
        exported = export_csv(path, "result-0002", self.root)
        verify_export(exported, path)
        self.assertEqual((exported / "result.csv").read_bytes(), b"total\r\n42\r\n")

    def test_tampered_bytes_rejected(self) -> None:
        path = self.save()
        with (path / "result.json").open("ab") as stream:
            stream.write(b" ")
        with self.assertRaises(ValueError):
            load_artifact(path)

    def test_rehashed_wrong_answer_still_rejected(self) -> None:
        path = self.save()
        result = json.loads((path / "result.json").read_bytes())
        result["result"]["answer"]["claims"][0]["value"] = 999
        payload = json.dumps(result).encode()
        (path / "result.json").write_bytes(payload)
        manifest = BundleManifest.model_validate_json(
            (path / "manifest.json").read_bytes()
        )
        (path / "manifest.json").write_bytes(
            canonical_bytes(
                manifest.model_copy(update={"payload_sha256": digest(payload)})
            )
        )
        with self.assertRaises(ValueError):
            load_artifact(path)

    def test_rehashed_csv_must_match_source(self) -> None:
        path = self.save()
        exported = export_csv(path, "result-0002", self.root)
        payload = b"total\r\n999\r\n"
        (exported / "result.csv").write_bytes(payload)
        exported_manifest = BundleManifest.model_validate_json(
            (exported / "manifest.json").read_bytes()
        )
        (exported / "manifest.json").write_bytes(
            canonical_bytes(
                exported_manifest.model_copy(update={"payload_sha256": digest(payload)})
            )
        )
        with self.assertRaises(ValueError):
            verify_export(exported, path)

    def test_expired_access_export_and_explicit_cleanup(self) -> None:
        path = self.save()
        manifest, _ = load_artifact(path)
        with self.assertRaises(ValueError):
            delete_expired(path)

        class ExpiredClock(datetime):
            @classmethod
            def now(cls, tz: object = None) -> datetime:
                return manifest.expires_at + timedelta(seconds=1)

        with patch("mos_eisley.analysis.artifacts.datetime", ExpiredClock):
            with self.assertRaises(ValueError):
                load_artifact(path)
            with self.assertRaises(ValueError):
                export_csv(path, "result-0002", self.root)
            delete_expired(path)
        self.assertFalse(path.exists())

    def test_symlinks_hardlinks_public_files_and_unexpected_entries_rejected(
        self,
    ) -> None:
        for kind in ("symlink", "hardlink", "public", "extra"):
            path = self.save()
            payload = path / "result.json"
            if kind == "symlink":
                target = self.root / "target.json"
                payload.rename(target)
                payload.symlink_to(target)
            elif kind == "hardlink":
                os.link(payload, self.root / "hardlink.json")
            elif kind == "public":
                payload.chmod(0o644)
            else:
                (path / "extra").write_text("unexpected")
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                load_artifact(path)

    def test_unapproved_retention_and_invalid_destinations_rejected(self) -> None:
        memory = self.saved.model_copy(
            update={
                "result": self.saved.result.model_copy(update={"retention": "memory"})
            }
        )
        with self.assertRaises(ValueError):
            save_artifact(self.root, memory, 3600)
        for ttl in (0, 604801, True):
            with self.assertRaises(ValueError):
                save_artifact(self.root, self.saved, ttl)
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.save()
        self.root.chmod(0o700)
        with self.assertRaises(ValueError):
            export_csv(self.save(), "missing", self.root)

    def test_csv_formula_cells_are_escaped_with_reported_lineage(self) -> None:
        item = trace(value=" =SUM(A1:A2)")
        claim = answer(" =SUM(A1:A2)")
        result = self.saved.result
        traces = (result.tool_trace[0], item)
        updated = result.model_copy(
            update={
                "tool_trace": traces,
                "sql_trail": sql_records(traces),
                "completed_at": item.completed_at,
                "answer": checked_answer(claim, traces),
                "evidence": (
                    result.evidence[0],
                    result.evidence[1].model_copy(
                        update={
                            "result_sha256": digest(
                                canonical_bytes(cast(ToolResultBlock, item.response))
                            )
                        }
                    ),
                ),
            }
        )
        path = save_artifact(self.root, AnalysisArtifact(result=updated), 3600)
        exported = export_csv(path, "result-0002", self.root)
        manifest = verify_export(exported, path)
        self.assertEqual(manifest.escaped_csv_cells, 1)
        self.assertIn(b"' =SUM", (exported / "result.csv").read_bytes())


class EvidenceConversationTests(IsolatedAsyncioTestCase):
    async def test_wrong_claim_cannot_complete_real_mcp_conversation(self) -> None:
        class WrongClient(AnalysisFixtureClient):
            async def complete(self, request: ModelRequest) -> ModelResponse:
                response = await super().complete(request)
                if response.stop_reason == "end_turn":
                    raw = response.model_dump(mode="json")
                    turn = cast(dict[str, JsonValue], raw["turn"])
                    blocks = cast(list[dict[str, JsonValue]], turn["blocks"])
                    proposal = json.loads(cast(str, blocks[0]["text"]))
                    proposal["claims"][0]["value"] = 999
                    blocks[0]["text"] = json.dumps(proposal)
                    response = ModelResponse.model_validate_json(json.dumps(raw))
                return response

        with self.assertRaises(AnalysisFailure):
            await run_analysis(
                AnalysisConfig(
                    provider="fixture",
                    model="tool-reviewer-v1",
                    account="fixture",
                    question="What is the total?",
                ),
                fixture_config(),
                fixture_registry(),
                WrongClient(),
            )

    async def test_real_envelope_preserves_sql_results_and_usage(self) -> None:
        result = await run_demo()
        self.assertEqual(result.schema_version, 2)
        self.assertEqual(result.value_verification, "returned_cells")
        self.assertEqual(result.sql_trail[0].submitted_sql, "SELECT 42 AS total")
        self.assertIsNone(result.sql_trail[0].source_reported_metadata["data_snapshot"])
        self.assertEqual(len(result.provider_usage), 2)
        self.assertEqual(result.tool_trace[1].result_id, "result-0002")


class ArtifactCLITests(TestCase):
    def test_cli_retention_verification_and_export_are_offline(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(
                    [
                        "analysis-demo",
                        "--allow-result-retention",
                        "--result-root",
                        str(root),
                    ]
                )
            self.assertEqual(code, 0)
            path = json.loads(out.getvalue())["artifact_path"]
            for arguments in (
                ["analysis-verify", path],
                [
                    "analysis-export",
                    path,
                    "--result-id",
                    "result-0002",
                    "--result-root",
                    str(root),
                ],
            ):
                out = io.StringIO()
                with (
                    redirect_stdout(out),
                    patch(
                        "mos_eisley.analysis.cli.EphemeralOpenAITransport"
                    ) as provider,
                ):
                    self.assertEqual(main(arguments), 0)
                    provider.assert_not_called()
            exported = json.loads(out.getvalue())["path"]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(["analysis-verify", exported, "--source", path]), 0
                )
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["analysis-verify", exported]), 2)

    def test_no_retention_without_consent(self) -> None:
        with TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["analysis-demo", "--result-root", directory]), 2)
            self.assertEqual(list(Path(directory).iterdir()), [])
