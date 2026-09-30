# G4 ETag initial-child call: uncertain spend

- Date: 2026-09-29 UTC. Owner: Joshua Myers. Status: local spend hold
  reconciled on 2026-09-30 UTC.
- Scope: one signed, one-use OpenAI initial-child attempt for a distinct HTTP
  `If-None-Match` task. This record follows the incident-review template and
  the [G4 spend reconciliation threat model](G4_SPEND_RECONCILIATION_THREAT_MODEL.md).
- Impact: the broker reported `broker response unavailable`. The production
  run retained no provider response or child receipt, and no source write,
  test run, Git integration, or G4 acceptance followed. Actual provider charge
  was not established by the broker. The shared ledger initially retained the
  full 49,750 micro-USD hold and blocked another live grant.

| Time (UTC) | Evidence or event | Decision or action |
|---|---|---|
| 2026-09-29 21:43 | One-use claim consumed; broker response unavailable; spend receipt and ledger entry `uncertain` | Do not retry the spent grant or claim. Preserve the historical receipt and hold. |
| 2026-09-29 21:56 | Owner downloaded OpenAI Usage Activity CSV after the failure, with no API-key filters and the only associated project selected | Compare provider activity with exact local settled receipts; do not treat an open UTC-day bucket as final. |
| 2026-09-29 22:06 | The September 29 Terra row showed six requests, 21,438 input tokens, and 7,554 output tokens, exactly matching six pinned settled local calls | Treat this as provisional evidence of no additional reported activity. Leave the ledger unchanged. |
| 2026-09-30 00:04 | Owner downloaded a second Usage Activity CSV after the UTC day closed, for the same organization and sole associated project, with no API-key filters | Verify the closed-day Terra row still has exactly six requests, 21,438 input tokens, and 7,554 output tokens; pin the export digest privately. |
| 2026-09-30 00:14 | Owner-signed exact zero-charge disposition verified; transactional ledger reconciliation applied | Settle the ETag entry at zero micro-USD. Read-only replay confirms zero unresolved shared-ledger entries; retain the original uncertain receipt. |

The broker's unavailable response does not establish whether the provider
received, completed, or charged the call. The closed-day Usage export showed
no additional Terra activity beyond the six locally settled calls. Joshua
signed a disposition binding the exact failed entry, reservation, receipt,
consumed claim, scoped export, local receipts, prior hold, and zero amount.
The disposition artifact SHA-256 is
`f886f19cb0decbeb40f4a2d13478ed66305209903e07de0365669beecabe331f`.
The shared ledger now records this entry as `settled` at zero micro-USD with
zero unresolved entries. The original uncertain receipt remains historical.

This local adjustment relies on the owner's export-scope attestation and the
closed-day Usage activity match. Usage activity is not a final provider Costs
record, and a later posting remains possible. Any new provider evidence must
be reviewed and corrected under separate authority. The target remains at its
approved base, and this attempt supplies no initial-child proposal or G4
qualification evidence.

## Recovery and verification

1. Preserve the signed disposition, exact private Usage export, ledger
   reconciliation row, consumed claim, and original uncertain receipt.
2. If later provider activity or Costs evidence changes the attribution or
   charge, investigate it and obtain separate authority for a correction.
3. Do not retry the spent grant or claim. Reconciliation grants no provider
   call or G4 acceptance.

Private evidence, signing keys, the Usage CSV, and task-local reconciliation
scripts remain outside Git. The reconciled entry no longer blocks the shared
ledger; any new live work still needs its own exact authority.
