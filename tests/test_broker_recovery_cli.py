"""Recovery status CLI requires independent expected identity and is read-only."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.broker_audit import AssignmentAuthorization, BrokerAudit
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
from mos_eisley.run.store import private_write


def authorization(ledger: SpendLedger) -> AssignmentAuthorization:
    return AssignmentAuthorization(
        plan_sha256="a" * 64,
        batch_sha256="b" * 64,
        sample_id="c" * 64,
        candidate_id="d" * 64,
        evaluation_request_sha256="e" * 64,
        provider_request_sha256="f" * 64,
        spend_policy_sha256="1" * 64,
        ledger_id=ledger.policy.ledger_id,
        ledger_entry_id="2" * 64,
    )


class BrokerRecoveryCLITests(TestCase):
    def test_reports_exact_held_state_without_mutation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = SpendLedger.create(root / "ledger.sqlite", 100)
            expected = authorization(ledger)
            audit = BrokerAudit(root / "audit", expected)
            audit.admit()
            ledger.reserve(
                LedgerEntry(
                    entry_id=expected.ledger_entry_id,
                    reservation_sha256="3" * 64,
                    reserved_microusd=40,
                )
            )
            trusted = root / "trusted-authorization.json"
            private_write(trusted, canonical_bytes(expected))
            before = {
                path.name: digest(path.read_bytes())
                for path in (root / "audit").iterdir()
            }
            snapshot = ledger.snapshot()

            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(
                    main(
                        [
                            "broker-audit-status",
                            "--audit-dir",
                            str(root / "audit"),
                            "--expected-authorization",
                            str(trusted),
                            "--spend-ledger",
                            str(ledger.path),
                        ]
                    ),
                    0,
                )
            event = json.loads(output.getvalue())
            self.assertEqual(event["type"], "broker.audit.status")
            self.assertEqual(
                (event["phase"], event["ledger_status"]), ("admitted", "held")
            )
            self.assertFalse(event["retry_permitted"])
            self.assertEqual(ledger.snapshot(), snapshot)
            self.assertEqual(
                {
                    path.name: digest(path.read_bytes())
                    for path in (root / "audit").iterdir()
                },
                before,
            )

    def test_rejects_self_attestation_and_wrong_ledger(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = SpendLedger.create(root / "ledger.sqlite", 100)
            expected = authorization(ledger)
            audit = BrokerAudit(root / "audit", expected)
            other_root = root / "other"
            other_root.mkdir()
            other = SpendLedger.create(other_root / "ledger.sqlite", 100)
            for expected_path, ledger_path in (
                (audit.directory / "authorization.json", ledger.path),
                (root / "trusted.json", other.path),
            ):
                if not expected_path.exists():
                    private_write(expected_path, canonical_bytes(expected))
                with (
                    redirect_stderr(io.StringIO()),
                    self.subTest(expected=expected_path, ledger=ledger_path),
                ):
                    self.assertEqual(
                        main(
                            [
                                "broker-audit-status",
                                "--audit-dir",
                                str(audit.directory),
                                "--expected-authorization",
                                str(expected_path),
                                "--spend-ledger",
                                str(ledger_path),
                            ]
                        ),
                        2,
                    )
