# Threat Model: G4 review spend reconciliation

## Scope and ownership

- System/version: exact integrated G4 review for `f54e815`.
- Owner and reviewer: Joshua Myers; one-human authority is explicit.
- Date and trigger: 2026-09-27; two failed Anthropic calls left uncertain holds.
- Scope: existing ledger entries and private Console Usage evidence only.

## Assets and boundaries

| Asset | Need | Boundary |
|---|---|---|
| Review ledger | Exact and durable balances | Private SQLite file |
| Failed call claims | Immutable historical audit | Private claim directories |
| Console Usage CSV | Full-day usage attribution | Joshua's local download and private copy |
| Owner signature | Accountable release authority | Enrolled Ed25519 key, used locally |

## Abuse cases and controls

| Abuse case | Control | Residual risk |
|---|---|---|
| Clear an unrelated hold | Exact entry, reservation, ledger, amount, and source pin | Owner or host compromise |
| Forge or edit billing export | SHA-256 pin, exact bucket checks, private copy, owner attestation of all-key scope | Console export completeness depends on owner selection |
| Double release or conflicting replay | Transactional unique reconciliation row and idempotent exact replay | SQLite/host corruption |
| Replace historical failure evidence | Receipt and outcome digests in signed body; old files never overwritten | Host compromise |
| Use signature for a provider call or G4 acceptance | Domain-separated authority expressly denies both | Misuse outside this broker |
| Incomplete two-entry transition | Replay requires both exact settled entries; rerun finishes an interrupted apply | Temporary partial ledger state |

## Decisions and recovery

The private signer prints the complete canonical authority before signing.
The adjustment is zero for each failed call because provider-side hourly usage
has no unaccounted Sonnet tokens in either relevant bucket. If the Console
export scope is later found incomplete, retain the signed artifact and audit,
raise an incident, and make a separately authorized correction. No automatic
new provider call or G4 acceptance follows this reconciliation.
