"""Atomic group admission across rejection, processes and abrupt termination."""

import multiprocessing
import sqlite3
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mos_eisley.core.models import digest
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement, SpendLedger


def entry(index: int, amount: int = 30) -> LedgerEntry:
    return LedgerEntry(
        entry_id=digest(str(index).encode()),
        reservation_sha256="a" * 64,
        reserved_microusd=amount,
    )


def compete_batch(arguments: tuple[str, int]) -> bool:
    path, index = arguments
    ledger = SpendLedger(Path(path))
    try:
        ledger.reserve_many((entry(index * 2), entry(index * 2 + 1)))
    except (ValueError, sqlite3.Error):
        return False
    return True


class BatchLedgerTests(TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.sqlite"
        self.ledger = SpendLedger.create(self.path, 100)

    def test_group_is_fully_held_and_settles_independently(self) -> None:
        self.ledger.reserve_many((entry(1), entry(2), entry(3)))
        self.assertEqual(SpendLedger(self.path).snapshot().charged_microusd, 90)
        self.ledger.settle(
            LedgerSettlement(
                entry_id=entry(1).entry_id,
                reservation_sha256="a" * 64,
                status="settled",
                charged_microusd=5,
            )
        )
        self.assertEqual(self.ledger.snapshot().charged_microusd, 65)
        self.assertEqual(self.ledger.snapshot().unresolved_entries, 2)

    def test_aggregate_overflow_does_not_leave_an_affordable_prefix(self) -> None:
        with self.assertRaises(ValueError):
            self.ledger.reserve_many((entry(1, 60), entry(2, 60)))
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_late_duplicate_rolls_back_new_prefix(self) -> None:
        self.ledger.reserve(entry(1))
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.reserve_many((entry(2), entry(1)))
        self.assertIsNone(self.ledger.entry_status(entry(2).entry_id))
        self.assertEqual(self.ledger.snapshot().charged_microusd, 30)
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.reserve_many((entry(3), entry(3)))
        self.assertIsNone(self.ledger.entry_status(entry(3).entry_id))

    def test_invalid_late_entry_and_batch_sizes_reject_before_mutation(self) -> None:
        for entries in (
            (),
            tuple(entry(i, 0) for i in range(65)),
            (entry(1), entry(2).model_copy(update={"reserved_microusd": -1})),
        ):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                self.ledger.reserve_many(entries)
        self.assertEqual(self.ledger.snapshot().entries, 0)

    def test_unresolved_slot_limit_counts_the_whole_group(self) -> None:
        self.ledger.reserve(entry(1))
        with self.assertRaises(ValueError):
            self.ledger.reserve_many((entry(2), entry(3)), max_unresolved_entries=2)
        self.assertEqual(self.ledger.snapshot().entries, 1)
        self.ledger.reserve_many((entry(2), entry(3)), max_unresolved_entries=3)
        self.assertEqual(self.ledger.snapshot().entries, 3)

    def test_group_replay_and_violation_never_admit_more_entries(self) -> None:
        self.ledger.reserve_many((entry(1), entry(2)))
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.reserve_many((entry(1, 10), entry(2, 10)))
        self.ledger.settle(
            LedgerSettlement(
                entry_id=entry(1).entry_id,
                reservation_sha256="a" * 64,
                status="violation",
                charged_microusd=30,
            )
        )
        with self.assertRaisesRegex(ValueError, "blocked"):
            self.ledger.reserve_many((entry(3, 1), entry(4, 1)))
        self.assertEqual(self.ledger.snapshot().entries, 2)

    def test_competing_processes_cannot_split_or_overspend_groups(self) -> None:
        with ProcessPoolExecutor(
            max_workers=3, mp_context=multiprocessing.get_context("spawn")
        ) as pool:
            results = list(
                pool.map(compete_batch, [(str(self.path), i) for i in range(6)])
            )
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.ledger.snapshot().charged_microusd, 60)
        self.assertEqual(self.ledger.snapshot().entries, 2)

    def test_commit_survives_abrupt_exit(self) -> None:
        script = """
import os, sys
from pathlib import Path
from mos_eisley.run.spend_ledger import LedgerEntry, SpendLedger
SpendLedger(Path(sys.argv[1])).reserve_many(tuple(LedgerEntry(
    entry_id=str(i)*64, reservation_sha256='a'*64, reserved_microusd=30
) for i in (1,2,3)))
os._exit(23)
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.path)],
            timeout=10,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(SpendLedger(self.path).snapshot().charged_microusd, 90)
        self.assertEqual(self.ledger.snapshot().entries, 3)

    def test_mid_insert_database_abort_rolls_back_every_entry(self) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TRIGGER fail_second BEFORE INSERT ON entries "
                "WHEN (SELECT COUNT(*) FROM entries) = 1 "
                "BEGIN SELECT RAISE(ABORT, 'fixture failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.reserve_many((entry(1), entry(2)))
        self.assertEqual(SpendLedger(self.path).snapshot().entries, 0)
