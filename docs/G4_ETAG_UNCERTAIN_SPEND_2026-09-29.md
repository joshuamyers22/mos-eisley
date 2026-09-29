# G4 ETag initial-child call: uncertain spend

- Date: 2026-09-29 UTC. Owner: Joshua Myers. Status: open.
- Scope: one signed, one-use OpenAI initial-child attempt for a distinct HTTP
  `If-None-Match` task. This record follows the incident-review template and
  the [G4 spend reconciliation threat model](G4_SPEND_RECONCILIATION_THREAT_MODEL.md).
- Impact: the broker reported `broker response unavailable`. The production
  run retained no provider response or child receipt, and no source write,
  test run, Git integration, or G4 acceptance followed. Actual provider charge
  is unknown. The shared ledger conservatively retains the full 49,750
  micro-USD hold and blocks another live grant while this entry is unresolved.

| Time (UTC) | Evidence or event | Decision or action |
|---|---|---|
| 2026-09-29 21:43 | One-use claim consumed; broker response unavailable; spend receipt and ledger entry `uncertain` | Do not retry the spent grant or claim. Preserve the historical receipt and hold. |
| 2026-09-29 21:56 | Owner downloaded OpenAI Usage Activity CSV after the failure, with no API-key filters and the only associated project selected | Compare provider activity with exact local settled receipts; do not treat an open UTC-day bucket as final. |
| 2026-09-29 22:06 | The September 29 Terra row showed six requests, 21,438 input tokens, and 7,554 output tokens, exactly matching six pinned settled local calls | Treat this as provisional evidence of no additional billed request. Leave the ledger unchanged. |

The broker's unavailable response does not establish whether the provider
received, completed, or charged the call. The preliminary Usage CSV was
exported before the September 29 UTC day closed. A later posting remains
possible, so zero-charge reconciliation has **not** been signed or applied.
The target remains at its approved base, and this attempt supplies no
initial-child proposal or qualification evidence.

## Recovery and verification

1. After 2026-09-30 00:00 UTC, the owner downloads a fresh Usage Activity CSV
   for the same organization and project with no API-key filters. Retain its
   exact bytes privately and attest the export scope and download time.
2. Verify the complete September 29 Terra bucket against the six pinned local
   settled receipts. If any additional request or tokens appear, investigate
   their attribution and charge; do not force a zero disposition.
3. If the closed-day bucket still matches exactly, have the enrolled owner sign
   an exact disposition binding the failed entry, reservation, prior hold,
   external evidence digest, and reconciled amount. The trusted host then
   applies the transactional ledger adjustment and verifies zero unresolved
   entries. Retain the original uncertain receipt as historical evidence.
4. Treat any later provider posting as a separate incident and correction.
   Reconciliation grants no provider call, G4 acceptance, or retry.

Private evidence, signing keys, the Usage CSV, and task-local reconciliation
scripts remain outside Git. The pending spend entry is a sequencing blocker for
live work; an unrelated task can be planned and tested offline.
