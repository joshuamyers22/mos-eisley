# ADR-0017: Session-owned operation recovery journal

- Status: implemented within the user-authorized §31.4 scope; release review separate
- Date and owner: 2026-10-21, Joshua Myers

## Context and options

Existing sessions already persist consumed attempts, admissions, queued steering,
child records and budgets. Resume marks running turns interrupted, but lacks an
explicit ordered operation journal and terminal cursor. Keeping recovery in the
sandbox would tie durable intent to disposable execution. A second transcript store
would add competing commit and owner boundaries.

## Decision and consequences

Add a bounded nested version-1 metadata journal to the existing verified session.
Commit dispatch decisions/reservations and terminal outcomes/cursors atomically
with their authoritative records. Treat an entire admitted turn or child operation
as the recovery unit; no intermediate paid/tool effect is automatically replayable.
Unclosed operations become uncertain, and aggregate exposure remains in the existing
ledger. Revalidate workspace/capabilities before dispatch and freeze the container
recipe for replacement execution. Detailed behavior is in `SESSION_RECOVERY.md`.

Legacy records remain readable without synthesizing absent history. Old binaries
reject journal-bearing sessions, so downgrade needs a matching reader and backup.
The metadata consumes existing bounded header capacity. Same-UID host/storage and
trusted Docker daemon compromise remain outside this integrity contract. Rollback
can revert this coherent change while retaining compatible session readers.

## Verification

Require dispatch/result transaction and acknowledgement fault injection, abrupt
process loss, preserved steering/spend, owner isolation, recipe drift refusal and
source/installed-package checks. Reconsider the recovery unit if partial tool-loop
continuation is introduced; that requires its own effect and idempotency contract.
