"""Durable request journal, canonical run storage, and CLI replay."""

import asyncio
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mos_eisley.cli import main
from mos_eisley.core.agent import run_agent
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import JournalEvent
from mos_eisley.core.registry import fixture_registry
from mos_eisley.demo_agent import agent_demo_inputs
from mos_eisley.providers.agent_recorded import RecordedAgentClient
from mos_eisley.run.agent_store import (
    AgentManifest,
    begin_agent_run,
    load_agent_run,
)
from mos_eisley.run.journal import JsonlJournal
from mos_eisley.tools.fixture import FixtureDispatcher


class AgentStoreTests(TestCase):
    def test_roundtrip_permissions_and_single_completion(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()
        with TemporaryDirectory() as directory:
            session = begin_agent_run(Path(directory), config, fixtures, cassette)
            client = RecordedAgentClient(cassette)
            result = asyncio.run(
                run_agent(
                    config,
                    fixture_registry(),
                    client,
                    FixtureDispatcher(fixtures),
                    session.journal,
                )
            )
            session.complete(result)
            loaded = load_agent_run(session.path)
            self.assertEqual(loaded[:3], (config, fixtures, cassette))
            self.assertEqual(loaded[4], result)
            self.assertEqual(len(loaded[3]), 5)
            self.assertEqual(session.path.stat().st_mode & 0o777, 0o700)
            for path in session.path.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "already complete"):
                session.complete(result)

    def test_abort_leaves_unreplayable_partial_journal(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()
        with TemporaryDirectory() as directory:
            session = begin_agent_run(Path(directory), config, fixtures, cassette)
            session.journal.record(
                JournalEvent(
                    type="model.request.started",
                    request_id="model-0001",
                    sequence=0,
                    payload_sha256="0" * 64,
                )
            )
            session.abort()
            self.assertTrue((session.path / "requests.jsonl").is_file())
            self.assertFalse((session.path / "manifest.json").exists())
            with self.assertRaisesRegex(ValueError, "already aborted"):
                session.complete(
                    asyncio.run(
                        run_agent(
                            config,
                            fixture_registry(),
                            RecordedAgentClient(cassette),
                            FixtureDispatcher(fixtures),
                        )
                    )
                )
            with self.assertRaises(OSError):
                load_agent_run(session.path)

    def test_tamper_and_moved_manifest_are_rejected(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()
        with TemporaryDirectory() as directory:
            session = begin_agent_run(Path(directory), config, fixtures, cassette)
            result = asyncio.run(
                run_agent(
                    config,
                    fixture_registry(),
                    RecordedAgentClient(cassette),
                    FixtureDispatcher(fixtures),
                    session.journal,
                )
            )
            session.complete(result)
            journal = session.path / "requests.jsonl"
            original = journal.read_bytes()
            journal.write_bytes(original + b"{}\n")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                load_agent_run(session.path)
            journal.write_bytes(original)
            manifest_path = session.path / "manifest.json"
            manifest = AgentManifest.model_validate_json(manifest_path.read_bytes())
            manifest_path.write_bytes(
                canonical_bytes(manifest.model_copy(update={"run_id": "different"}))
            )
            with self.assertRaisesRegex(ValueError, "identity"):
                load_agent_run(session.path)

    def test_journal_rejects_existing_closed_and_out_of_order_writes(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "journal"
            event = JournalEvent(
                type="model.request.started",
                request_id="model-0001",
                sequence=0,
                payload_sha256="0" * 64,
            )
            with JsonlJournal(path) as journal:
                journal.record(event)
                with self.assertRaisesRegex(ValueError, "contiguous"):
                    journal.record(event)
            with self.assertRaisesRegex(ValueError, "closed"):
                journal.record(event.model_copy(update={"sequence": 1}))
            with self.assertRaises(FileExistsError):
                JsonlJournal(path)


class AgentCliTests(TestCase):
    def test_agent_demo_replay_and_models(self) -> None:
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["agent-demo", "--output", directory, "--json"]), 0)
            completed = json.loads(out.getvalue())
            self.assertEqual(completed["type"], "agent.completed")
            self.assertEqual((completed["requests"], completed["tools"]), (2, 1))
            out.seek(0)
            out.truncate(0)
            self.assertEqual(main(["agent-replay", completed["path"]]), 0)
            replayed = json.loads(out.getvalue())
            self.assertEqual(replayed["type"], "agent.replay.verified")
            out.seek(0)
            out.truncate(0)
            self.assertEqual(main(["models"]), 0)
            models = tuple(json.loads(line) for line in out.getvalue().splitlines())
            self.assertEqual(
                tuple(model["provider"] for model in models), ("fixture", "openai")
            )
            self.assertEqual(models[1]["verification"], "documented")

    def test_agent_replay_rejects_modified_run_without_echoing_content(self) -> None:
        with (
            TemporaryDirectory() as directory,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as errors,
        ):
            self.assertEqual(main(["agent-demo", "--output", directory]), 0)
            run = next(path for path in Path(directory).iterdir() if path.is_dir())
            (run / "result.json").write_text("sensitive modified content")
            self.assertEqual(main(["agent-replay", str(run)]), 2)
            self.assertNotIn("sensitive", errors.getvalue())

    def test_agent_replay_accepts_pre_provider_schema_one_result(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()
        with TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            session = begin_agent_run(Path(directory), config, fixtures, cassette)
            result = asyncio.run(
                run_agent(
                    config,
                    fixture_registry(),
                    RecordedAgentClient(cassette),
                    FixtureDispatcher(fixtures),
                    session.journal,
                )
            )
            session.complete(result)
            result_path = session.path / "result.json"
            legacy = result.model_dump(mode="json")
            legacy.pop("responses")
            payload = json.dumps(
                legacy, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode()
            result_path.write_bytes(payload)
            manifest_path = session.path / "manifest.json"
            manifest = AgentManifest.model_validate_json(manifest_path.read_bytes())
            artifacts = tuple(
                artifact.model_copy(update={"sha256": digest(payload)})
                if artifact.name == "result.json"
                else artifact
                for artifact in manifest.artifacts
            )
            manifest_path.write_bytes(
                canonical_bytes(manifest.model_copy(update={"artifacts": artifacts}))
            )
            self.assertEqual(main(["agent-replay", str(session.path)]), 0)
