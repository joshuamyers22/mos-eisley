"""Fixed-prefix evidence assembly authenticates separate fixture signatures."""

import base64
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from test_review_observer_handoff import ObserverHandoffFixture

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.review_campaign import CampaignEvidenceSubmission
from mos_eisley.run.review_campaign_observation import preview_campaign_observation
from mos_eisley.run.review_campaign_runner import CampaignProbeCompletion
from mos_eisley.run.review_campaign_submission import (
    append_campaign_observation,
    decode_signed_observation,
)
from mos_eisley.run.review_conformance_observation import sign_review_probe_observation
from mos_eisley.run.store import private_write


class CampaignSubmissionTests(ObserverHandoffFixture):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.select_completion(self.completion)

    def select_completion(self, completion: CampaignProbeCompletion) -> None:
        self.completion = completion
        index = completion.attempt_index
        self.selected_preview = preview_campaign_observation(
            self.sealed_directory,
            self.seal_sha,
            completion,
            lifecycle_directories=tuple(self.fixtures[index].lifecycles),
            now=datetime.now(UTC),
        )
        self.signed = sign_review_probe_observation(
            self.selected_preview.unsigned_observation,
            "observer",
            self.fixtures[index].observer_key,
        )
        self.completion_path = self.root / f"selected-completion-{index}.json"
        self.preview_path = self.root / f"selected-preview-{index}.json"
        self.signed_path = self.root / f"selected-signed-{index}.json"
        self.output = self.root / f"submission-{index}.json"
        self.completion_raw = canonical_bytes(completion)
        self.preview_raw = canonical_bytes(self.selected_preview)
        self.signed_raw = canonical_bytes(self.signed)
        for path, raw in (
            (self.completion_path, self.completion_raw),
            (self.preview_path, self.preview_raw),
            (self.signed_path, self.signed_raw),
        ):
            private_write(path, raw)

    def append_arguments(self, previous: Path | None = None) -> list[str]:
        args = [
            "review-campaign-evidence-append",
            "--campaign-dir",
            str(self.sealed_directory),
            "--expected-seal-sha256",
            self.seal_sha,
            "--completion",
            str(self.completion_path),
            "--expected-completion-sha256",
            digest(self.completion_raw),
            "--preview",
            str(self.preview_path),
            "--expected-preview-sha256",
            digest(self.preview_raw),
            "--signed-observation",
            str(self.signed_path),
            "--expected-signed-observation-sha256",
            digest(self.signed_raw),
            "--output",
            str(self.output),
        ]
        for path in self.fixtures[self.completion.attempt_index].lifecycles:
            args.extend(("--lifecycle-directory", str(path)))
        if previous is not None:
            args.extend(
                (
                    "--previous-evidence",
                    str(previous),
                    "--expected-previous-evidence-sha256",
                    digest(previous.read_bytes()),
                )
            )
        return args

    def append(self, previous: CampaignEvidenceSubmission | None = None):
        return append_campaign_observation(
            self.sealed_directory,
            self.seal_sha,
            self.completion,
            self.selected_preview,
            self.signed,
            lifecycle_directories=tuple(
                self.fixtures[self.completion.attempt_index].lifecycles
            ),
            previous=previous,
            now=datetime.now(UTC),
        )

    def test_cli_writes_private_verified_prefix_without_credentials_or_mutation(self):
        before = [f.base.ledger.path.read_bytes() for f in self.fixtures]
        out = io.StringIO()
        with (
            patch("mos_eisley.providers.openai_live.AsyncOpenAI") as sdk,
            redirect_stdout(out),
        ):
            self.assertEqual(main(self.append_arguments()), 0)
        sdk.assert_not_called()
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["qualifying_attempts"], 1)
        self.assertEqual(report["submission_sha256"], digest(self.output.read_bytes()))
        self.assertFalse(report["provider_dispatch_authorized"])
        stored = CampaignEvidenceSubmission.model_validate_json(
            self.output.read_bytes()
        )
        self.assertIsNotNone(stored.attempts[0])
        self.assertEqual(stored.attempts[1:], (None, None))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            before, [f.base.ledger.path.read_bytes() for f in self.fixtures]
        )

    async def test_cli_appends_all_three_slots_and_preserves_prior_files(self):
        previous: Path | None = None
        for index in range(3):
            if index:
                probe = self.probes[index]
                result = await probe.run()
                assert (
                    result is not None
                    and probe.controller.start is not None
                    and probe.judge_preview is not None
                )
                authorizations = probe.approval_ui.authorizations
                self.select_completion(
                    CampaignProbeCompletion(
                        seal_sha256=self.seal_sha,
                        attempt_index=index,
                        start=probe.controller.start,
                        judge=probe.judge_preview,
                        authorizations=(authorizations[0], authorizations[1]),
                        expected_result_sha256=digest(canonical_bytes(result)),
                        lifecycle_directories=tuple(
                            str(path) for path in probe.lifecycle_paths
                        ),
                    )
                )
            retained = None if previous is None else previous.read_bytes()
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(self.append_arguments(previous)), 0)
            report = json.loads(out.getvalue())
            self.assertEqual(report["qualifying_attempts"], index + 1)
            self.assertEqual(
                report["status"], "accepted" if index == 2 else "incomplete"
            )
            if previous is not None:
                self.assertEqual(previous.read_bytes(), retained)
            previous = self.output

    def test_replacement_of_an_existing_slot_is_rejected(self):
        previous = self.append().submission
        with self.assertRaisesRegex(ValueError, "next empty slot"):
            self.append(previous)

    def test_skipping_the_first_slot_is_rejected_before_evidence_review(self):
        self.completion = self.completion.model_copy(update={"attempt_index": 1})
        self.selected_preview = self.selected_preview.model_copy(
            update={
                "canonical_completion_sha256": digest(canonical_bytes(self.completion))
            }
        )
        with (
            patch(
                "mos_eisley.run.review_campaign_submission.review_campaign_evidence"
            ) as review,
            self.assertRaisesRegex(ValueError, "next empty slot"),
        ):
            self.append()
        review.assert_not_called()

    def test_mismatched_signed_preview_is_rejected(self):
        changed = self.signed.observation.model_copy(update={"result_sha256": "f" * 64})
        self.signed = sign_review_probe_observation(
            changed, "observer", self.fixtures[0].observer_key
        )
        with self.assertRaisesRegex(ValueError, "selected preview"):
            self.append()

    def test_invalid_independent_signature_is_rejected(self):
        self.signed = self.signed.model_copy(
            update={"signature_base64": base64.b64encode(bytes(64)).decode()}
        )
        with self.assertRaises(ValueError):
            self.append()

    def test_cross_campaign_prior_submission_is_rejected(self):
        previous = CampaignEvidenceSubmission(
            seal_sha256="f" * 64, attempts=(None, None, None)
        )
        with self.assertRaisesRegex(ValueError, "next empty slot"):
            self.append(previous)

    def test_changed_input_hash_fails_before_verification_or_output(self):
        self.signed_path.write_bytes(self.signed_raw + b" ")
        with (
            patch(
                "mos_eisley.review_submission_cli.append_campaign_observation"
            ) as append,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(self.append_arguments()), 2)
        append.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_previous_evidence_requires_a_paired_independent_hash(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(
                main(
                    [
                        *self.append_arguments(),
                        "--previous-evidence",
                        str(self.root / "missing.json"),
                    ]
                ),
                2,
            )
        self.assertFalse(self.output.exists())

    def test_changed_runtime_evidence_is_rejected_even_with_valid_signature(self):
        path = self.fixtures[0].critic_directory() / "runtime-generation-end.json"
        raw = json.loads(path.read_bytes())
        raw["duration_ms"] += 1
        path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            self.append()

    def test_output_cannot_overwrite_existing_submission(self):
        private_write(self.output, b"retained")
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.append_arguments()), 2)
        self.assertEqual(self.output.read_bytes(), b"retained")

    def test_signed_observation_decoder_rejects_duplicate_keys(self):
        with self.assertRaises(ValueError):
            decode_signed_observation(
                b'{"signer_id":"observer","signer_id":"observer"}'
            )
