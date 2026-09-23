# Threat Model: reassessed formal cleanup boundary

## Scope and ownership

- System/version: brokered controller terminal cleanup and read-only controller inspection after `2ed7f11`.
- Owner and reviewers: Joshua Myers; accountable review remains required before another live campaign.
- Date and review trigger: 2026-09-23; accepted three-slot evidence with three rejecting code verdicts.
- In scope / out of scope: standard/formal cleanup selection and attribution are in scope; provider behavior, historical ledger repair, retry, routing, and launch activation are out of scope.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Standard controller artifacts | authorization metadata | Preserve schema-1 bytes and conservative hold behavior | Joshua Myers |
| Formal controller artifacts | authorization/accounting evidence | Bind fixed grace and cleanup marker to exact formal controller | Joshua Myers |
| Spend ledger source/destination entries | financial integrity | Never release dispatched or uncertain exposure | Joshua Myers |
| Inspector result | operational evidence | Distinguish controller cleanup from missing transfer attribution | Joshua Myers |

- Actors and capabilities: trusted controller/inspector, accountable operator, untrusted model findings, storage failure, and callers supplying mismatched retained artifacts.
- Entry points and trust boundaries: terminal transition, held-source retirement, transfer, terminal record, and stopped-run inspection.
- Data flows and external dependencies: only local canonical artifacts and SQLite state; this correction adds no network, credential, provider, or dependency access.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Standard run triggers formal cleanup | Schema-1 controller owns a reserved envelope | Compatibility and accounting drift | Gate retirement on schema-2 formal authorization | Standard decline/cancel/failure regressions | Standard unused hold remains conservative |
| Standard artifact claims formal retirement | Settled-zero source plus injected schema-2 terminal | False complete attribution | Inspector requires formal controller schema before accepting cleanup marker | Tampered standard-marker regression | Trusted-host artifact forgery remains outside the model |
| Cleanup releases a transferred/uncertain call | Wrong ledger entry or ambiguous state | Understated exposure | Exact source identity; only held source can retire; settled-zero transfer source is no-op; destination remains charged | Ledger transfer/idempotence and completed-judge tests | Storage failure can leave conservative incomplete attribution |
| Formal human pause becomes unbounded | Malformed authorization or stale envelope | Stale dispatch | Exact 600-second schema validator, start/envelope clipping, fixed operation caps | Contract and paused-clock tests | Host scheduling can consume the bounded grace |
| Correlated reviewers drive unsafe scope expansion | Same model repeats an unsupported interpretation | Regression disguised as remediation | Requirement trace plus executable counterexample before accepting a finding | Reassessment disposition and regressions | Single-provider campaign is not independent judgment |

## Decisions

- Accepted risks with owner and expiry: standard unused allowances remain conservatively held as before; Joshua Myers, revisit only through a separate governed design.
- Required tests and monitoring: standard/formal cancellation, post-transfer terminal completion, missing-transfer inspection, shared-ledger accounting, timing/grace clipping, and full repository gate.
- Incident and recovery dependencies: preserve retained campaign artifacts; do not repair historical ledgers or infer retry/live authority.
- Verification result: the focused regressions and full `make check` passed from source and the installed wheel; no live access was used.
