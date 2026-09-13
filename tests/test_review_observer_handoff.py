"""Offline observer previews require independently pinned inputs and no signing keys."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from unittest.mock import patch

from test_review_campaign_runner import CampaignRunnerFixture

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.review_campaign import (
    CampaignAttemptSubmission,
    CampaignEvidenceSubmission,
    review_campaign_evidence,
)
from mos_eisley.run.review_campaign_observation import (
    CampaignObservationPreview,
    decode_probe_completion,
    preview_campaign_observation,
)
from mos_eisley.run.review_conformance_observation import sign_review_probe_observation
from mos_eisley.run.store import private_write


class ObserverHandoffTests(CampaignRunnerFixture):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        with patch.object(self, "observe", return_value=None):
            runner = self.runner()
            await runner.run()
        completion = runner.last_completion
        assert completion is not None
        self.completion = completion
        self.completion_path = self.root / "completion.json"
        self.completion_raw = canonical_bytes(completion)
        private_write(self.completion_path, self.completion_raw)
        self.output = self.root / "unsigned-preview.json"

    def arguments(self) -> list[str]:
        args = [
            "review-campaign-observation-preview",
            "--campaign-dir",
            str(self.sealed_directory),
            "--expected-seal-sha256",
            self.seal_sha,
            "--completion",
            str(self.completion_path),
            "--expected-completion-sha256",
            digest(self.completion_raw),
        ]
        for path in self.fixtures[0].lifecycles:
            args.extend(("--lifecycle-directory", str(path)))
        return args

    def preview(self) -> CampaignObservationPreview:
        return preview_campaign_observation(
            self.sealed_directory,
            self.seal_sha,
            self.completion,
            lifecycle_directories=tuple(self.fixtures[0].lifecycles),
            now=datetime.now(UTC),
        )

    def test_cli_preview_is_read_only_unsigned_and_does_not_load_credentials(self):
        before = [f.base.ledger.path.read_bytes() for f in self.fixtures]
        out = io.StringIO()
        with (
            patch("mos_eisley.providers.openai_live.AsyncOpenAI") as sdk,
            patch(
                "mos_eisley.run.review_conformance_observation.sign_review_probe_observation"
            ) as sign,
            redirect_stdout(out),
        ):
            code = main(self.arguments())
        self.assertEqual(code, 0)
        report = json.loads(out.getvalue())
        self.assertTrue(report["requires_independent_attestation"])
        self.assertFalse(report["observer_authenticated"])
        self.assertFalse(report["signature_created"])
        self.assertNotIn("unsigned_observation", report)
        self.assertEqual(
            before, [f.base.ledger.path.read_bytes() for f in self.fixtures]
        )
        sdk.assert_not_called()
        sign.assert_not_called()
        self.assertEqual([f.key_loader.call_count for f in self.fixtures], [4, 0, 0])
        self.assertFalse(self.output.exists())

    def test_explicit_private_output_contains_an_unsigned_wrapper(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                main([*self.arguments(), "--output", str(self.output), "--show"]), 0
            )
        stored = CampaignObservationPreview.model_validate_json(
            self.output.read_bytes()
        )
        self.assertEqual(
            json.loads(out.getvalue())["observation_sha256"], stored.observation_sha256
        )
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertFalse(stored.observer_authenticated)
        self.assertTrue(stored.requires_independent_attestation)

    def test_independently_signed_preview_passes_fresh_partial_campaign_review(self):
        preview = self.preview()
        fixture = self.fixtures[0]
        signed = sign_review_probe_observation(
            preview.unsigned_observation, "observer", fixture.observer_key
        )
        submission = CampaignAttemptSubmission(
            start=self.completion.start,
            judge=self.completion.judge,
            authorizations=self.completion.authorizations,
            signed_observation=signed,
            expected_result_sha256=self.completion.expected_result_sha256,
            lifecycle_directories=tuple(str(path) for path in fixture.lifecycles),
        )
        reviewed = review_campaign_evidence(
            self.sealed_directory,
            self.seal_sha,
            CampaignEvidenceSubmission(
                seal_sha256=self.seal_sha, attempts=(submission, None, None)
            ),
            now=datetime.now(UTC),
        )
        self.assertEqual(reviewed.status, "incomplete")
        self.assertEqual(reviewed.qualifying_attempts, 1)

    def test_changed_completion_pin_fails_before_evidence_access(self):
        self.completion_path.write_bytes(self.completion_raw + b" ")
        with (
            patch(
                "mos_eisley.review_observer_cli.preview_campaign_observation"
            ) as preview,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(self.arguments()), 2)
        preview.assert_not_called()

    def test_wrong_committed_slot_rejects_the_completion(self):
        self.completion = self.completion.model_copy(update={"attempt_index": 1})
        with self.assertRaisesRegex(ValueError, "committed slot"):
            self.preview()

    def test_wrong_result_pin_cannot_prepare_an_observation(self):
        self.completion = self.completion.model_copy(
            update={"expected_result_sha256": "f" * 64}
        )
        with self.assertRaises(ValueError):
            self.preview()

    def test_invalid_phase_signature_fails_before_runtime_collection(self):
        first, judge = self.completion.authorizations
        first = first.model_copy(update={"public_key_sha256": "f" * 64})
        self.completion = self.completion.model_copy(
            update={"authorizations": (first, judge)}
        )
        with (
            patch(
                "mos_eisley.run.review_campaign_observation.collect_review_runtime_exchange"
            ) as collect,
            self.assertRaises(ValueError),
        ):
            self.preview()
        collect.assert_not_called()

    def test_lifecycle_paths_must_be_independently_selected_and_match(self):
        paths = self.fixtures[0].lifecycles
        for selected in ((paths[0],), (paths[1], paths[0])):
            with self.assertRaises(ValueError):
                preview_campaign_observation(
                    self.sealed_directory,
                    self.seal_sha,
                    self.completion,
                    lifecycle_directories=selected,
                    now=datetime.now(UTC),
                )

    def test_runtime_result_substitution_prevents_preview(self):
        path = self.fixtures[0].critic_directory() / "runtime-generation-end.json"
        raw = json.loads(path.read_bytes())
        raw["result_sha256"] = "f" * 64
        path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            self.preview()

    def test_output_cannot_overwrite_or_modify_evidence_directories(self):
        private_write(self.output, b"retained")
        paths = (
            self.output,
            self.sealed_directory / "new-preview.json",
            self.fixtures[0].directory / "new-preview.json",
        )
        for path in paths:
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(main([*self.arguments(), "--output", str(path)]), 2)
        self.assertEqual(self.output.read_bytes(), b"retained")
        self.assertFalse(paths[1].exists())
        self.assertFalse(paths[2].exists())

    def test_completion_decoder_rejects_duplicate_keys_byte_limits_and_naive_time(self):
        naive = self.completion.model_dump(mode="json")
        naive["start"]["started_at"] = "2026-09-13T00:00:00"
        for raw in (
            b'{"attempt_index":0,"attempt_index":0}',
            b" " * 8_000_001,
            json.dumps(naive).encode(),
        ):
            with self.assertRaises(ValueError):
                decode_probe_completion(raw)
