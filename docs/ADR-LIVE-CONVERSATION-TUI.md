# ADR: Live text turns in saved terminal conversations

- Status: proposed
- Date and owner: 2026-10-01, Joshua Myers

## Context and options

The TUI controller already saves queued turns, cancellation, context admission and
resumption, but ordinary answers use a finite recorded cassette. A separate live
screen would duplicate those controls. Extending the recorded mode without a saved
provider identity could send a resumed preview to a provider unexpectedly.

## Decision and consequences

Add an explicit `openai_live_conversation` mode. Each live launch requires transfer
opt-in, a current reviewed price policy, an existing shared ledger, and private
artifacts. Save the model, effort, policy hash, ledger ID and artifact root as the
session identity. One submitted turn runs through the existing OpenAI adapter and
spending controller with no tools or retries. The recorded preview stays the
default. A changed or expired policy starts a new live session; in-place policy
renewal would require a separate explicit migration design.

The controller still carries a demo cassette fingerprint for compatibility with
the existing schema, but never dispatches a recorded exchange in live mode. A
future schema version can remove that compatibility field. The current 16-message
session limit also remains.

## Verification

Offline tests must show three contextual live turns beyond the recording length,
saved identity checks, cancellation without replay, and a reservation/receipt
through the adapter and ledger. Full repository `make check` and accountable owner
review are required before treating the feature as release-ready.
