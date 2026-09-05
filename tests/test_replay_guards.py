"""Regression cases from the first milestone's adversarial review."""

import asyncio
import io
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import JudgeDecision, ReviewPolicy, canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.recorded import Cassette, RecordedReviewer
from mos_eisley.review.pipeline import review
from mos_eisley.run.store import ArtifactHash, Manifest, load_run, save_run


class ReplayGuardTests(TestCase):
    def test_manifest_cannot_select_arbitrary_files(self) -> None:
        brief, cassette = demo_inputs()
        result = asyncio.run(
            review(
                brief,
                tuple(r.critic for r in cassette.critics),
                RecordedReviewer(cassette),
                ReviewPolicy(),
            )
        )
        with TemporaryDirectory() as directory:
            path = save_run(Path(directory), brief, cassette, ReviewPolicy(), result)
            manifest_path = path / "manifest.json"
            manifest = Manifest.model_validate_json(manifest_path.read_bytes())
            bad = manifest.model_copy(
                update={
                    "artifacts": (ArtifactHash(name="../../private", sha256="0" * 64),)
                }
            )
            manifest_path.write_bytes(canonical_bytes(bad))
            with self.assertRaisesRegex(ValueError, "artifact set"):
                load_run(path)

    def test_replay_compares_result_even_when_digests_match(self) -> None:
        brief, cassette = demo_inputs()
        result = asyncio.run(
            review(
                brief,
                tuple(r.critic for r in cassette.critics),
                RecordedReviewer(cassette),
                ReviewPolicy(),
            )
        )
        with TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            path = save_run(Path(directory), brief, cassette, ReviewPolicy(), result)
            changed = result.model_copy(
                update={
                    "verdict": result.verdict.model_copy(
                        update={"rationale": "changed"}
                    )
                }
            )
            payload = canonical_bytes(changed)
            (path / "result.json").write_bytes(payload)
            manifest_path = path / "manifest.json"
            manifest = Manifest.model_validate_json(manifest_path.read_bytes())
            artifacts = tuple(
                a.model_copy(update={"sha256": digest(payload)})
                if a.name == "result.json"
                else a
                for a in manifest.artifacts
            )
            manifest_path.write_bytes(
                canonical_bytes(manifest.model_copy(update={"artifacts": artifacts}))
            )
            self.assertEqual(main(["replay", str(path)]), 2)

    def test_writer_never_marks_unreplayable_oversize_run_complete(self) -> None:
        brief, cassette = demo_inputs()
        result = asyncio.run(
            review(
                brief,
                tuple(r.critic for r in cassette.critics),
                RecordedReviewer(cassette),
                ReviewPolicy(),
            )
        )
        with TemporaryDirectory() as directory:
            root = Path(directory) / "runs"
            with (
                patch("mos_eisley.run.store.MAX_ARTIFACT_BYTES", 100),
                self.assertRaisesRegex(ValueError, "replay byte limit"),
            ):
                save_run(root, brief, cassette, ReviewPolicy(), result)
            self.assertFalse(root.exists())

    def test_duplicate_cassette_ids_rejected(self) -> None:
        _, cassette = demo_inputs()
        duplicate = cassette.model_copy(
            update={"critics": (cassette.critics[0], cassette.critics[0])}
        )
        with self.assertRaises(ValidationError):
            Cassette.model_validate_json(canonical_bytes(duplicate))

    def test_duplicate_upheld_ids_rejected(self) -> None:
        brief, cassette = demo_inputs()
        assert cassette.judge_response is not None
        finding_id = cassette.judge_response.upheld[0]
        cassette = cassette.model_copy(
            update={
                "judge_response": JudgeDecision(
                    upheld=(finding_id, finding_id), rationale="duplicate"
                )
            }
        )
        result = asyncio.run(
            review(
                brief,
                tuple(r.critic for r in cassette.critics),
                RecordedReviewer(cassette),
                ReviewPolicy(),
            )
        )
        self.assertEqual(result.verdict.decision, "infrastructure_error")
