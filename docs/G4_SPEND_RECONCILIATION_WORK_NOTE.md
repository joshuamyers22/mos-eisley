# Work Note: G4 review spend reconciliation

- Status: closed for the exact integrated review ledger
- Owner: Joshua Myers
- Started (UTC): 2026-09-27
- Review or delete by: after G4 closeout
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/WORK_NOTE.md`, and `templates/THREAT_MODEL.md`

## Objective and completion evidence

Close two conservative Anthropic holds for the integrated G4 review of commit
`f54e815987c1e51941abf4c2f2138a7268dcf0a7`, using Joshua's exact
signature and the private Claude Console Usage export. Retain the original
failed-call receipts and claims. The review record and G4 acceptance decision
are outside this adjustment.

## Observations

- The two failed exchanges each retained a 104,960 micro-USD hold. The first
  has no provider response or diagnostic; the second failed at token counting
  with HTTP 401. These are historical observations, not proof of no billing.
- Joshua confirmed that the Console Usage export covers all API keys in the
  relevant workspace for the complete UTC day. Its SHA-256 is pinned in the
  private authority. The 12:00 Sonnet bucket is absent. The complete 13:00 and
  15:00 Sonnet buckets match the two successful retained receipts exactly.
- The Console Cost export is a daily total and does not attribute the failed
  calls. It is supplementary and is not the release basis.

## Invariants and checks

- The ledger transition requires the exact uncertain entry, reservation,
  previous amount, evidence hash, and signed authority hash. Exact replay is a
  no-op; a conflicting replay fails.
- The private broker verifies the signed creator authority, source commit,
  claims, receipts, Console Usage hash, and successful token totals before
  applying either adjustment. It makes no provider call.
- Completion requires both entries settled at zero, no unresolved ledger
  entries, unchanged original receipts, and successful replay of the signed
  single-operator and one-human formal review records.

## Handoff

Joshua signed the exact private authority (artifact SHA-256
`c0ea3b2e5bb6f843da1d3e93be30c1505e146dcf7754d4fbc156c9fc50ae5947`).
The guarded apply settled both failed-call entries at zero. The ledger now has
zero unresolved entries and 38,942 micro-USD charged across the review.
The original failed receipts remain in place. The exact integrated review and
the signed one-human formal exception both replay after the adjustment; G4
acceptance remains unauthorized. The private authority and Console export
remain outside Git.

Verification: focused ledger tests passed (15 tests), private tamper check
rejected a modified authority, and both G4 status replays passed. `make check`
completed lint, formatting, type checking, the full source test suite (87%
coverage), export verification, and build. The installed-package smoke step was
interrupted after a prolonged run, so the combined `make check` did not finish.
