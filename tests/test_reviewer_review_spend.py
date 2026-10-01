"""Reservation replay does not restore funds or authorize duplicate sends."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.openai_spend import SpendReservation
from mos_eisley.reviewer_review_spend import verify_review_reservation
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement, SpendLedger


class ReviewReservationTests(unittest.TestCase):
    def test_conflicts_fresh_exhaustion_and_duplicate_send_are_rejected(self) -> None:
        reservation = SpendReservation(
            policy_sha256=digest(b"policy"),
            request_sha256=digest(b"request"),
            input_tokens=1,
            max_output_tokens=1,
            reserved_microusd=10,
        )
        entry = LedgerEntry(
            entry_id=digest(b"one call"),
            reservation_sha256=digest(canonical_bytes(reservation)),
            reserved_microusd=10,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = SpendLedger.create(root / "ledger.sqlite", 100)
            ledger.reserve(entry)
            ledger.settle(
                LedgerSettlement(
                    entry_id=entry.entry_id,
                    reservation_sha256=entry.reservation_sha256,
                    status="settled",
                    charged_microusd=3,
                )
            )
            verify_review_reservation(ledger, entry.entry_id, reservation)
            with self.assertRaises(sqlite3.IntegrityError):
                ledger.reserve(entry)
            with self.assertRaises(ValueError):
                verify_review_reservation(
                    ledger,
                    entry.entry_id,
                    reservation.model_copy(
                        update={"request_sha256": digest(b"other request")}
                    ),
                )
            mismatch = SpendLedger.create(root / "mismatch.sqlite", 100)
            mismatch.reserve(entry.model_copy(update={"reserved_microusd": 11}))
            with self.assertRaises(ValueError):
                verify_review_reservation(mismatch, entry.entry_id, reservation)
            exhausted = SpendLedger.create(root / "exhausted.sqlite", 9)
            with self.assertRaises(ValueError):
                verify_review_reservation(exhausted, entry.entry_id, reservation)
            self.assertEqual(exhausted.snapshot().entries, 0)


if __name__ == "__main__":
    unittest.main()
