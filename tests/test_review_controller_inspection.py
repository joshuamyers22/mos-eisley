"""Stopped-run inventory never reauthorizes dispatch or changes retained state."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from test_review_controller import ControllerFixture

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.review_controller import ControllerStart
from mos_eisley.run.review_controller_inspection import inspect_review_controller
from mos_eisley.run.spend_ledger import SpendLedger


class ControllerInspectionTests(ControllerFixture, IsolatedAsyncioTestCase):
    preview_sha256: str | None = None

    async def critics(self):
        preview = await super().critics()
        self.preview_sha256 = preview.sha256
        return preview

    def expected(self):
        expected = self.controller.start
        assert expected is not None
        return expected

    def inspect(self, expected: ControllerStart | None = None):
        return inspect_review_controller(
            self.directory,
            self.expected() if expected is None else expected,
            self.base.ledger,
            expected_judge_preview_sha256=self.preview_sha256,
        )

    def files(self):
        return {
            str(p.relative_to(self.base.root)): p.read_bytes()
            for p in self.base.root.rglob("*")
            if p.is_file()
        }

    async def test_paused_review_inventory_preserves_all_bytes_and_holds(self):
        await self.critics()
        before = self.files()
        state = self.inspect()
        self.assertEqual(state.recorded_phase, "judge_preview")
        self.assertEqual(state.identified_charged_microusd, 365)
        self.assertTrue(state.spending_inventory_complete)
        self.assertEqual([c.audit for c in state.critics], ["verified", "verified"])
        self.assertEqual(
            [c.completion for c in state.critics], ["verified", "verified"]
        )
        self.assertIsNone(state.judge)
        self.assertFalse(state.retry_permitted)
        self.assertFalse(state.resume_authorized)
        self.assertFalse(state.verdict_verified)
        self.assertEqual(before, self.files())

    async def test_finished_run_reports_records_without_claiming_verified_verdict(self):
        preview = await self.critics()
        await self.finish(preview.sha256)
        state = self.inspect()
        self.assertEqual(state.recorded_phase, "finished")
        self.assertEqual(state.identified_charged_microusd, 60)
        self.assertEqual(state.ledger_charged_microusd, 60)
        self.assertTrue(state.spending_inventory_complete)
        self.assertTrue(state.result_present)
        self.assertFalse(state.verdict_verified)
        self.assertNotIn("Fixture", state.model_dump_json())
        self.assertNotIn("accept", state.model_dump_json())

    async def test_crash_after_transfer_before_record_exposes_unknown_attribution(self):
        preview = await self.critics()
        from mos_eisley.run.store import private_write

        def fail_transfer(path: Path, data: bytes):
            if path.name == "judge-transfer.json":
                raise OSError("fixture disk failure")
            private_write(path, data)

        with (
            patch(
                "mos_eisley.run.review_broker.private_write", side_effect=fail_transfer
            ),
            self.assertRaises(OSError),
        ):
            await self.finish(preview.sha256)
        state = self.inspect()
        self.assertEqual(state.recorded_phase, "failed")
        self.assertFalse(state.spending_inventory_complete)
        self.assertEqual(state.identified_charged_microusd, 40)
        self.assertEqual(state.ledger_charged_microusd, 365)
        self.assertIsNone(state.judge)

    async def test_failed_judge_keeps_uncertain_exposure(self):
        preview = await self.critics()
        from mos_eisley.core.ports import ProviderError

        self.judge.error = ProviderError("SECRET diagnostic")
        await self.finish(preview.sha256)
        state = self.inspect()
        assert state.judge is not None and state.judge.ledger is not None
        self.assertEqual(state.judge.ledger.status, "uncertain")
        self.assertEqual(state.identified_charged_microusd, 365)
        self.assertNotIn("SECRET", state.model_dump_json())

    async def test_cancelled_pause_retains_judge_hold(self):
        await self.critics()
        self.controller.cancel()
        state = self.inspect()
        self.assertEqual(state.recorded_phase, "cancelled")
        self.assertEqual(state.identified_charged_microusd, 365)

    async def test_pre_dispatch_failure_reports_partial_audit_and_held_spend(self):
        with (
            patch.object(
                self.envelope.critics[0],
                "_issue_reserved",
                side_effect=OSError("fixture"),
            ),
            self.assertRaises(OSError),
        ):
            await self.critics()
        state = self.inspect()
        self.assertEqual(state.recorded_phase, "failed")
        self.assertEqual([c.audit for c in state.critics], ["absent", "absent"])
        self.assertEqual(state.identified_charged_microusd, 975)

    async def test_missing_completion_is_not_inferred_from_settled_spending(self):
        await self.critics()
        path = (
            self.directory
            / self.calls[0].authorization.ledger_entry_id
            / "model-completion.json"
        )
        path.unlink()
        state = self.inspect()
        self.assertEqual(state.critics[0].audit, "verified")
        self.assertEqual(state.critics[0].completion, "absent")

    async def test_missing_terminal_does_not_infer_finished_from_result(self):
        preview = await self.critics()
        await self.finish(preview.sha256)
        (self.directory / "controller-terminal.json").unlink()
        state = self.inspect()
        self.assertEqual(state.recorded_phase, "judge_transfer")
        self.assertTrue(state.result_present)

    async def test_expected_start_mismatch_rejected(self):
        await self.critics()
        expected = self.expected().model_copy(
            update={"started_at": self.expected().started_at - timedelta(seconds=1)}
        )
        with self.assertRaisesRegex(ValueError, "start mismatch"):
            self.inspect(expected)

    async def test_wrong_ledger_rejected(self):
        await self.critics()
        other = SpendLedger.create(self.base.root / "other.sqlite", 1000)
        with self.assertRaisesRegex(ValueError, "ledger mismatch"):
            inspect_review_controller(self.directory, self.expected(), other)

    async def test_mutated_request_and_completion_and_result_rejected(self):
        preview = await self.critics()
        await self.finish(preview.sha256)
        for path in (
            self.directory
            / self.calls[0].authorization.ledger_entry_id
            / "model-request.json",
            self.directory
            / self.calls[0].authorization.ledger_entry_id
            / "model-completion.json",
            self.directory / "review-result.json",
        ):
            original = path.read_bytes()
            with self.subTest(path=path.name):
                path.write_bytes(b"{}")
                with self.assertRaises(ValueError):
                    self.inspect()
                path.write_bytes(original)

    async def test_partial_request_tampering_is_rejected_without_outcome(self):
        await self.critics()
        child = self.directory / self.calls[0].authorization.ledger_entry_id
        (child / "outcome.json").unlink()
        (child / "model-request.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "artifact mismatch"):
            self.inspect()

    async def test_dangling_artifact_symlink_is_not_missing(self):
        await self.critics()
        (self.directory / "controller-terminal.json").symlink_to(
            self.base.root / "missing"
        )
        with self.assertRaises((OSError, ValueError)):
            self.inspect()

    async def test_cli_is_metadata_only_and_does_not_load_credentials(self):
        await self.critics()
        trusted = self.base.root / "expected-start.json"
        trusted.write_bytes(canonical_bytes(self.expected()))
        before = self.files()
        output = io.StringIO()
        with (
            redirect_stdout(output),
            patch(
                "mos_eisley.cli._openai_api_key",
                side_effect=AssertionError("credential access"),
            ),
        ):
            self.assertEqual(
                main(
                    [
                        "review-controller-status",
                        "--review-dir",
                        str(self.directory),
                        "--expected-start",
                        str(trusted),
                        "--spend-ledger",
                        str(self.base.ledger.path),
                    ]
                ),
                0,
            )
        state = json.loads(output.getvalue())
        self.assertEqual(state["type"], "review.controller.status")
        self.assertFalse(state["retry_permitted"])
        self.assertEqual(before, self.files())

    async def test_cli_rejects_self_attestation_and_hardlink_alias(self):
        await self.critics()
        saved = self.directory / "controller-start.json"
        alias = self.base.root / "alias.json"
        os.link(saved, alias)
        for expected in (saved, alias):
            with (
                self.subTest(expected=expected),
                redirect_stderr(io.StringIO()) as error,
            ):
                self.assertEqual(
                    main(
                        [
                            "review-controller-status",
                            "--review-dir",
                            str(self.directory),
                            "--expected-start",
                            str(expected),
                            "--spend-ledger",
                            str(self.base.ledger.path),
                        ]
                    ),
                    2,
                )
                self.assertIn("input or artifact validation failed", error.getvalue())

    async def test_expired_deadline_is_information_only(self):
        await self.critics()
        with patch("mos_eisley.run.review_controller_inspection.datetime") as clock:
            clock.now.return_value = self.expected().expires_at + timedelta(seconds=1)
            state = self.inspect()
        self.assertTrue(state.deadline_expired)
        self.assertFalse(state.retry_permitted)
        self.assertEqual(state.identified_charged_microusd, 365)

    async def test_tampered_preview_and_transfer_are_rejected(self):
        preview = await self.critics()
        await self.finish(preview.sha256)
        for filename, field in (
            ("controller-judge-preview.json", "controller_sha256"),
            ("judge-transfer.json", "envelope_sha256"),
        ):
            path = self.directory / filename
            original = path.read_bytes()
            record = json.loads(original)
            record[field] = "f" * 64
            with self.subTest(filename=filename):
                path.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    self.inspect()
                path.write_bytes(original)

    async def test_finished_record_with_missing_result_is_rejected(self):
        preview = await self.critics()
        await self.finish(preview.sha256)
        (self.directory / "review-result.json").unlink()
        with self.assertRaisesRegex(ValueError, "terminal mismatch"):
            self.inspect()

    async def test_call_directory_symlink_is_rejected(self):
        await self.critics()
        child = self.directory / self.calls[0].authorization.ledger_entry_id
        saved = self.base.root / "moved-call"
        child.rename(saved)
        child.symlink_to(saved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "directory must not be a symlink"):
            self.inspect()

    async def test_missing_start_is_rejected_without_creating_it(self):
        await self.critics()
        path = self.directory / "controller-start.json"
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.inspect()
        self.assertFalse(path.exists())

    async def test_judge_transfer_requires_an_independent_preview_pin(self):
        preview = await self.critics()
        await self.finish(preview.sha256)
        with self.assertRaisesRegex(ValueError, "independent preview pin"):
            inspect_review_controller(self.directory, self.expected(), self.base.ledger)
        with self.assertRaisesRegex(ValueError, "independent pin"):
            inspect_review_controller(
                self.directory,
                self.expected(),
                self.base.ledger,
                expected_judge_preview_sha256="f" * 64,
            )
