"""Conformance ceremony policy preparation is exact, local, and no-send."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.evaluation_conformance import (
    EvaluationConformancePolicy,
    prepare_evaluation_conformance_policy,
    trusted_evaluation_conformance_observer,
    validate_evaluation_conformance_preflight,
)
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
from mos_eisley.run.store import private_write
from tests.test_openai_conformance import conformance_inputs


class EvaluationConformancePreflightTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.batch, self.spend_policy = conformance_inputs()
        self.ledger = SpendLedger.create(self.root / "ledger.sqlite", 20_000)
        self.audit_directory = self.root / "audit"
        self.now = datetime.now(UTC)
        self.observer = trusted_evaluation_conformance_observer(
            "observer-a",
            Ed25519PrivateKey.generate().public_key().public_bytes_raw(),
        )

    def policy(self) -> EvaluationConformancePolicy:
        return prepare_evaluation_conformance_policy(
            self.batch,
            self.batch.requests[0].sample_id,
            self.spend_policy,
            self.ledger,
            self.audit_directory,
            "openai-probe-1",
            self.now - timedelta(minutes=5),
            self.now + timedelta(minutes=30),
            120,
            (self.observer,),
            ("2.54.0",),
        )

    def test_preparation_pins_exact_run_without_reserving_or_creating_audit(
        self,
    ) -> None:
        policy = self.policy()

        self.assertEqual(policy.batch_sha256, self.batch.batch_sha256)
        self.assertEqual(policy.sample_id, self.batch.requests[0].sample_id)
        self.assertEqual(policy.spend_policy_sha256, self.spend_policy.policy_sha256)
        self.assertEqual(policy.ledger_id, self.ledger.policy.ledger_id)
        self.assertFalse(self.audit_directory.exists())
        self.assertIsNone(self.ledger.entry_status(policy.ledger_entry_id))
        self.assertFalse(policy.batch_conversion_authorized)
        self.assertFalse(policy.scoring_authorized)
        self.assertFalse(policy.promotion_authorized)

    def test_preflight_accepts_only_current_exact_fresh_run(self) -> None:
        policy = self.policy()
        authorization = validate_evaluation_conformance_preflight(
            self.batch,
            self.batch.requests[0].sample_id,
            self.spend_policy,
            self.ledger,
            self.audit_directory,
            policy,
            "2.54.0",
            self.now,
        )
        self.assertEqual(authorization.ledger_entry_id, policy.ledger_entry_id)

        for sdk_version, at in (
            ("2.55.0", self.now),
            ("2.54.0", policy.valid_until + timedelta(seconds=1)),
        ):
            with self.assertRaisesRegex(ValueError, "prepared policy"):
                validate_evaluation_conformance_preflight(
                    self.batch,
                    self.batch.requests[0].sample_id,
                    self.spend_policy,
                    self.ledger,
                    self.audit_directory,
                    policy,
                    sdk_version,
                    at,
                )

        with self.assertRaisesRegex(ValueError, "prepared policy"):
            validate_evaluation_conformance_preflight(
                self.batch,
                self.batch.requests[0].sample_id,
                self.spend_policy,
                self.ledger,
                self.root / "other-audit",
                policy,
                "2.54.0",
                self.now,
            )

    def test_extended_window_and_existing_ledger_identity_fail_closed(self) -> None:
        policy = self.policy()
        extended = policy.model_copy(
            update={"valid_until": self.spend_policy.valid_until + timedelta(seconds=1)}
        )
        with self.assertRaisesRegex(ValueError, "prepared policy"):
            validate_evaluation_conformance_preflight(
                self.batch,
                self.batch.requests[0].sample_id,
                self.spend_policy,
                self.ledger,
                self.audit_directory,
                extended,
                "2.54.0",
                self.now,
            )

        self.ledger.reserve(
            LedgerEntry(
                entry_id=policy.ledger_entry_id,
                reservation_sha256="a" * 64,
                reserved_microusd=1,
            )
        )
        with self.assertRaisesRegex(ValueError, "prepared policy"):
            validate_evaluation_conformance_preflight(
                self.batch,
                self.batch.requests[0].sample_id,
                self.spend_policy,
                self.ledger,
                self.audit_directory,
                policy,
                "2.54.0",
                self.now,
            )

    def test_prepare_cli_never_reads_credentials_or_dispatches(self) -> None:
        batch_path = self.root / "batch.json"
        spend_policy_path = self.root / "spend-policy.json"
        observer_path = self.root / "observer.json"
        output_path = self.root / "conformance-policy.json"
        private_write(batch_path, canonical_bytes(self.batch))
        private_write(spend_policy_path, canonical_bytes(self.spend_policy))
        private_write(observer_path, canonical_bytes(self.observer))
        options = [
            "eval-prepare-brokered-conformance-policy",
            "--batch",
            str(batch_path),
            "--sample-id",
            self.batch.requests[0].sample_id,
            "--spend-policy",
            str(spend_policy_path),
            "--spend-ledger",
            str(self.ledger.path),
            "--audit-dir",
            str(self.audit_directory),
            "--policy-id",
            "openai-probe-1",
            "--valid-from",
            (self.now - timedelta(minutes=5)).isoformat(),
            "--valid-until",
            (self.now + timedelta(minutes=30)).isoformat(),
            "--max-observation-age-seconds",
            "120",
            "--observer",
            str(observer_path),
            "--sdk-version",
            "2.54.0",
            "--output",
            str(output_path),
        ]
        with (
            patch("mos_eisley.cli._openai_api_key") as credential,
            patch("mos_eisley.cli.run_isolated_broker") as dispatch,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            self.assertEqual(main(options), 0)

        credential.assert_not_called()
        dispatch.assert_not_called()
        event = json.loads(stdout.getvalue())
        self.assertFalse(event["credential_accessed"])
        self.assertFalse(event["provider_request_sent"])
        self.assertFalse(event["spend_reserved"])
        policy = EvaluationConformancePolicy.model_validate_json(
            output_path.read_bytes()
        )
        self.assertEqual(event["policy_sha256"], policy.policy_sha256)
        self.assertFalse(self.audit_directory.exists())
        self.assertIsNone(self.ledger.entry_status(policy.ledger_entry_id))

    def test_prepare_cli_rejects_output_overlap_without_writes(self) -> None:
        batch_path = self.root / "batch.json"
        private_write(batch_path, canonical_bytes(self.batch))
        with (
            patch("mos_eisley.cli.read_bounded") as read,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(
                main(
                    [
                        "eval-prepare-brokered-conformance-policy",
                        "--batch",
                        str(batch_path),
                        "--sample-id",
                        self.batch.requests[0].sample_id,
                        "--spend-policy",
                        str(self.root / "missing-spend-policy"),
                        "--spend-ledger",
                        str(self.ledger.path),
                        "--audit-dir",
                        str(self.audit_directory),
                        "--policy-id",
                        "openai-probe-1",
                        "--valid-from",
                        self.now.isoformat(),
                        "--valid-until",
                        (self.now + timedelta(minutes=1)).isoformat(),
                        "--max-observation-age-seconds",
                        "120",
                        "--observer",
                        str(self.root / "missing-observer"),
                        "--sdk-version",
                        "2.54.0",
                        "--output",
                        str(self.audit_directory / "policy.json"),
                    ]
                ),
                2,
            )
        read.assert_not_called()
        self.assertFalse(self.audit_directory.exists())
