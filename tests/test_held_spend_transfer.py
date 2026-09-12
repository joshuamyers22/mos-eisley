"""An allowance moves to an exact request with no released-capacity interval."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement, SpendLedger


class HeldTransferTests(TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.sqlite"
        self.ledger = SpendLedger.create(self.path, 100)
        self.source = LedgerEntry(
            entry_id="a" * 64, reservation_sha256="b" * 64, reserved_microusd=100
        )
        self.target = LedgerEntry(
            entry_id="c" * 64, reservation_sha256="d" * 64, reserved_microusd=100
        )
        self.ledger.reserve(self.source)

    def test_transfer_preserves_exposure_and_settles_only_the_request(self) -> None:
        self.ledger.transfer_held(self.source, self.target)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 100)
        self.assertEqual(self.ledger.snapshot().unresolved_entries, 1)
        self.assertEqual(self.ledger.snapshot().entries, 2)
        self.ledger.settle(
            LedgerSettlement(
                entry_id=self.target.entry_id,
                reservation_sha256=self.target.reservation_sha256,
                status="settled",
                charged_microusd=20,
            )
        )
        self.assertEqual(self.ledger.snapshot().charged_microusd, 20)
        source = self.ledger.entry_status(self.source.entry_id)
        assert source is not None
        self.assertEqual((source.status, source.charged_microusd), ("settled", 0))

    def test_wrong_hash_amount_identity_or_absent_source_never_moves_funds(
        self,
    ) -> None:
        for source, target in (
            (
                self.source.model_copy(update={"reservation_sha256": "e" * 64}),
                self.target,
            ),
            (self.source.model_copy(update={"entry_id": "e" * 64}), self.target),
            (self.source, self.target.model_copy(update={"reserved_microusd": 99})),
            (self.source, self.target.model_copy(update={"reserved_microusd": 101})),
            (self.source, self.source),
        ):
            with (
                self.subTest(source=source, target=target),
                self.assertRaises(ValueError),
            ):
                self.ledger.transfer_held(source, target)
        self.assertEqual(self.ledger.snapshot().entries, 1)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 100)

    def test_duplicate_destination_rolls_back_source_retirement(self) -> None:
        self.ledger.reserve(self.target.model_copy(update={"reserved_microusd": 0}))
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.transfer_held(self.source, self.target)
        with self.ledger.guard_held(self.source):
            pass
        self.assertEqual(self.ledger.snapshot().charged_microusd, 100)

    def test_late_update_failure_rolls_back_destination_insert(self) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TRIGGER fail_update BEFORE UPDATE ON entries "
                "BEGIN SELECT RAISE(ABORT, 'fixture failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.transfer_held(self.source, self.target)
        self.assertIsNone(self.ledger.entry_status(self.target.entry_id))
        with self.ledger.guard_held(self.source):
            pass

    def test_concurrent_transfer_and_new_admission_never_observe_free_capacity(
        self,
    ) -> None:
        def attempt(index: int) -> bool:
            ledger = SpendLedger(self.path)
            try:
                if index == 0:
                    ledger.transfer_held(self.source, self.target)
                else:
                    ledger.reserve(
                        LedgerEntry(
                            entry_id=str(index) * 64,
                            reservation_sha256="f" * 64,
                            reserved_microusd=1,
                        )
                    )
            except (ValueError, sqlite3.Error):
                return False
            return True

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        self.assertEqual(results, [True, False, False, False])
        self.assertEqual(self.ledger.snapshot().charged_microusd, 100)

    def test_replay_uncertainty_and_violations_cannot_transfer(self) -> None:
        for status in ("settled", "uncertain", "violation"):
            with self.subTest(status=status), TemporaryDirectory() as directory:
                ledger = SpendLedger.create(Path(directory) / "ledger.sqlite", 100)
                ledger.reserve(self.source)
                ledger.settle(
                    LedgerSettlement.model_validate(
                        {
                            "entry_id": self.source.entry_id,
                            "reservation_sha256": self.source.reservation_sha256,
                            "status": status,
                            "charged_microusd": 100,
                        }
                    )
                )
                with self.assertRaises(ValueError):
                    ledger.transfer_held(self.source, self.target)
        self.ledger.transfer_held(self.source, self.target)
        with self.assertRaises(ValueError):
            self.ledger.transfer_held(self.source, self.target)
