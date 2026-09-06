"""Aggregate admission remains bounded across processes and interrupted runs."""

import io
import json
import multiprocessing
import sqlite3
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing, redirect_stderr, redirect_stdout
from multiprocessing.synchronize import Barrier
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import digest
from mos_eisley.run.spend_ledger import (
    LedgerEntry,
    LedgerSettlement,
    Outcome,
    SpendLedger,
)


def entry(index: int, amount: int) -> LedgerEntry:
    return LedgerEntry(
        entry_id=digest(str(index).encode()),
        reservation_sha256="a" * 64,
        reserved_microusd=amount,
    )


_barrier: Barrier | None = None


def initialize_worker(barrier: Barrier) -> None:
    global _barrier
    _barrier = barrier


def compete(arguments: tuple[str, int]) -> bool:
    path, index = arguments
    if _barrier is None:
        raise RuntimeError("worker barrier was not initialized")
    _barrier.wait(timeout=10)
    try:
        SpendLedger(Path(path)).reserve(entry(index, 30))
    except (ValueError, sqlite3.Error):
        return False
    return True


class LedgerTests(TestCase):
    def test_admission_and_settlement_release_only_known_savings(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spend.sqlite"
            ledger = SpendLedger.create(path, 100)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            ledger.reserve(entry(1, 100))
            with self.assertRaises(ValueError):
                ledger.reserve(entry(2, 1))
            self.assertEqual(ledger.snapshot().charged_microusd, 100)
            ledger.settle(
                LedgerSettlement(
                    entry_id=entry(1, 100).entry_id,
                    reservation_sha256="a" * 64,
                    status="settled",
                    charged_microusd=40,
                )
            )
            ledger.reserve(entry(2, 60))
            snapshot = SpendLedger(path).snapshot()
            self.assertEqual(snapshot.charged_microusd, 100)
            self.assertEqual(snapshot.available_microusd, 0)
            self.assertEqual(snapshot.unresolved_entries, 1)
            self.assertEqual(snapshot.entries, 2)

    def test_uncertainty_retains_and_violation_blocks_remaining_budget(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = SpendLedger.create(Path(directory) / "spend.sqlite", 100)
            cases: tuple[tuple[int, Outcome], ...] = (
                (1, "uncertain"),
                (2, "violation"),
            )
            for index, status in cases:
                reserved = entry(index, 20)
                ledger.reserve(reserved)
                ledger.settle(
                    LedgerSettlement(
                        entry_id=reserved.entry_id,
                        reservation_sha256="a" * 64,
                        status=status,
                        charged_microusd=20,
                    )
                )
            snapshot = ledger.snapshot()
            self.assertEqual(snapshot.available_microusd, 60)
            self.assertTrue(snapshot.blocked)
            self.assertEqual(snapshot.unresolved_entries, 2)
            with self.assertRaisesRegex(ValueError, "blocked"):
                ledger.reserve(entry(3, 1))

    def test_duplicate_mismatched_and_invalid_settlements_do_not_release(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = SpendLedger.create(Path(directory) / "spend.sqlite", 100)
            reserved = entry(1, 50)
            ledger.reserve(reserved)
            with self.assertRaises(sqlite3.IntegrityError):
                ledger.reserve(reserved)
            settlement = LedgerSettlement(
                entry_id=reserved.entry_id,
                reservation_sha256="a" * 64,
                status="settled",
                charged_microusd=10,
            )
            for update in (
                {"entry_id": "b" * 64},
                {"reservation_sha256": "b" * 64},
                {"charged_microusd": 51},
                {"status": "uncertain"},
            ):
                with self.subTest(update=update), self.assertRaises(ValueError):
                    ledger.settle(settlement.model_copy(update=update))
                self.assertEqual(ledger.snapshot().charged_microusd, 50)
            ledger.settle(settlement)
            with self.assertRaises(ValueError):
                ledger.settle(settlement)
            with self.assertRaises(sqlite3.IntegrityError):
                ledger.reserve(reserved)
            self.assertEqual(ledger.snapshot().charged_microusd, 10)

    def test_missing_corrupt_existing_or_changed_ledger_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spend.sqlite"
            with self.assertRaises(sqlite3.Error):
                SpendLedger(path)
            self.assertFalse(path.exists())
            for amount in (True, 0, -1, 1_000_000_000_001):
                with self.subTest(amount=amount), self.assertRaises(ValidationError):
                    SpendLedger.create(path, amount)
            ledger = SpendLedger.create(path, 100)
            with self.assertRaises(FileExistsError):
                SpendLedger.create(path, 200)
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("UPDATE ledger_policy SET ceiling = 200")
            with self.assertRaisesRegex(ValueError, "changed"):
                ledger.reserve(entry(1, 1))
            corrupt = Path(directory) / "corrupt.sqlite"
            corrupt.write_bytes(b"not a database")
            with self.assertRaises(sqlite3.Error):
                SpendLedger(corrupt)
            self.assertEqual(corrupt.read_bytes(), b"not a database")

    def test_concurrent_processes_cannot_overspend(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spend.sqlite"
            ledger = SpendLedger.create(path, 100)
            context = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(
                max_workers=4,
                mp_context=context,
                initializer=initialize_worker,
                initargs=(context.Barrier(4),),
            ) as workers:
                admitted = list(
                    workers.map(compete, [(str(path), i) for i in range(12)])
                )
            self.assertLessEqual(sum(admitted), 3)
            self.assertGreater(sum(admitted), 0)
            snapshot = ledger.snapshot()
            self.assertEqual(snapshot.charged_microusd, sum(admitted) * 30)
            self.assertLessEqual(snapshot.charged_microusd, 100)

    def test_committed_reservation_survives_abrupt_process_exit(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spend.sqlite"
            ledger = SpendLedger.create(path, 100)
            script = """
import os, sys
from pathlib import Path
from mos_eisley.run.spend_ledger import SpendLedger, LedgerEntry
SpendLedger(Path(sys.argv[1])).reserve(LedgerEntry(
    entry_id='a'*64, reservation_sha256='b'*64, reserved_microusd=100))
os._exit(23)
"""
            completed = subprocess.run(
                [sys.executable, "-c", script, str(path)],
                timeout=10,
                check=False,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 23, completed.stderr)
            self.assertEqual(ledger.snapshot().charged_microusd, 100)
            with self.assertRaises(ValueError):
                ledger.reserve(entry(2, 1))

    def test_locked_database_cannot_admit(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spend.sqlite"
            ledger = SpendLedger.create(path, 100)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                with self.assertRaises(sqlite3.OperationalError):
                    ledger.reserve(entry(1, 1))
            self.assertEqual(ledger.snapshot().entries, 0)

    def test_entry_status_is_read_only_and_exact(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = SpendLedger.create(Path(directory) / "spend.sqlite", 100)
            self.assertIsNone(ledger.entry_status("a" * 64))
            item = entry(1, 20)
            ledger.reserve(item)
            status = ledger.entry_status(item.entry_id)
            assert status is not None
            self.assertEqual(status.status, "held")
            self.assertEqual(status.charged_microusd, 20)
            self.assertEqual(ledger.snapshot().entries, 1)

    def test_held_guard_requires_exact_unsettled_reservation(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = SpendLedger.create(Path(directory) / "spend.sqlite", 100)
            item = entry(1, 20)
            ledger.reserve(item)
            with ledger.guard_held(item) as status:
                self.assertEqual(status.status, "held")
            for changed in (
                item.model_copy(update={"reservation_sha256": "b" * 64}),
                item.model_copy(update={"reserved_microusd": 19}),
            ):
                with (
                    self.subTest(changed=changed),
                    self.assertRaisesRegex(ValueError, "exact held"),
                    ledger.guard_held(changed),
                ):
                    pass
            ledger.settle(
                LedgerSettlement(
                    entry_id=item.entry_id,
                    reservation_sha256=item.reservation_sha256,
                    status="settled",
                    charged_microusd=10,
                )
            )
            with (
                self.assertRaisesRegex(ValueError, "exact held"),
                ledger.guard_held(item),
            ):
                pass

    def test_unexpected_journal_or_missing_policy_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spend.sqlite"
            ledger = SpendLedger.create(path, 100)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
            with self.assertRaisesRegex(ValueError, "journaling"):
                ledger.reserve(entry(1, 10))
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("DELETE FROM ledger_policy")
            with self.assertRaisesRegex(ValueError, "policy"):
                SpendLedger(path)

    def test_cli_creation_inspection_and_no_implicit_reset(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spend.sqlite"
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(
                    main(
                        ["spend-ledger-create", str(path), "--ceiling-microusd", "100"]
                    ),
                    0,
                )
            created = json.loads(output.getvalue())
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["spend-ledger-status", str(path)]), 0)
            self.assertEqual(json.loads(output.getvalue()), created)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(
                        ["spend-ledger-create", str(path), "--ceiling-microusd", "200"]
                    ),
                    2,
                )
            self.assertEqual(SpendLedger(path).policy.ceiling_microusd, 100)
