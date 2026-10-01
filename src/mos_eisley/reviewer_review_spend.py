"""Check fresh allowance or replay one exact retained review reservation."""

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.openai_spend import SpendReservation
from mos_eisley.run.spend_ledger import SpendLedger


def verify_review_reservation(
    ledger: SpendLedger, entry_id: str, reservation: SpendReservation
) -> None:
    """Metadata replay cannot require an already consumed hold to remain unused.

    This does not reserve funds or authorize another send. Dispatch still calls
    the transactional ledger.reserve, which rejects duplicate IDs and overruns.
    Existing held/uncertain/violation entries remain metadata, not passing audits.
    """
    entry = ledger.entry_status(entry_id)
    if entry is not None:
        if (
            entry.reservation_sha256 != digest(canonical_bytes(reservation))
            or entry.reserved_microusd != reservation.reserved_microusd
        ):
            raise ValueError("review reservation differs from retained ledger entry")
        return
    snapshot = ledger.snapshot()
    if snapshot.blocked or reservation.reserved_microusd > snapshot.available_microusd:
        raise ValueError("shared review spending allowance is unavailable")
