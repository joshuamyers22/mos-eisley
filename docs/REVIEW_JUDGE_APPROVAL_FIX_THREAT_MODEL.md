# Threat Model: formal judge approval and unused allowance cleanup

## Scope and ownership

- System/version: brokered review controller schema 2 and spend-ledger terminal cleanup.
- Owner and reviewers: Joshua Myers; accountable review required before live use.
- Date and review trigger: 2026-09-22; formal campaign judge deadline expiry with an unused held allowance.
- In scope / out of scope: timing contracts, terminal transitions, deferred source accounting and inspection are in scope; credentials, provider behavior, historical ledger repair and campaign quality are out of scope.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Controller authorization/start | authorization metadata | Exact canonical binding and exclusive expiry | Joshua Myers |
| Active execution budget | availability and safety limit | Must pause only at the formal human gate and never exceed the envelope wall | Joshua Myers |
| Spend ledger entries | financial integrity | Atomic, exact and conservative state transitions | Joshua Myers |
| Private review artifacts | confidential operational evidence | Bounded, non-symlinked and tamper-evident | Joshua Myers |

- Actors and capabilities: accountable operator, trusted host, untrusted model content, failing provider/worker, local process crash, and a caller attempting replay or contract substitution.
- Entry points and trust boundaries: critic approval, controller start, judge approval, ledger retirement/transfer, terminal artifact write, and read-only inspection.
- Data flows and external dependencies: canonical previews flow from host to approval UI; only approved hashes reach the controller; ledger mutations precede dispatch; provider calls remain behind existing broker/container boundaries.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Substitute grace onto a standard review | Caller constructs schema 2 manually | Longer unauthorized approval wall | Exact 600-second validator plus formal-scope preview validator | Contract and preview tests | Process-local host remains trusted |
| Configure an unbounded grace | Caller controls model input | Denial of service or stale authorization | Literal schema, field cap, exact constant and envelope expiry clipping | Model validation and timing tests | Host scheduling can still consume the fixed grace |
| Retire a critic or dispatched request | Caller passes the wrong ledger entry | Under-report exposure | Exact canonical entry match; retirement accepts only held source shape; controller exposes only its judge allowance | Ledger negative tests and transfer tests | Privileged direct ledger callers remain trusted code |
| Release ambiguous provider exposure | Cancellation/crash during dispatch | Financial undercount | Transfer moves exposure first; destination/uncertain holds never retire; crash remains conservative | Cancellation, transfer and inspection suites | Historical unused holds need explicit governed repair |
| Replay retirement or transfer | Duplicate terminal/issue attempt | Double use or corrupted totals | Serialized transaction, idempotent exact zero settlement, one-use controller phase | Ledger/controller replay tests | Storage availability can prevent terminal record creation |
| Hide a transfer by losing its record | Crash after ledger transfer | Incomplete attribution | Atomic retirement reports whether it changed the source; only that transaction writes the schema-2 terminal cleanup marker, while a pre-retired source without a transfer record remains incomplete | Inspection tests | Target identity cannot be reconstructed without retained record |
| Inject terminal content or approval | Model controls findings/labels | Misleading operator or implicit approval | Sanitized output, escaped structured preview, exact typed hash | Approval-flow tests | Human may still approve poor content |
| Compromise dependency or credential boundary | Host environment compromised | Unauthorized calls/data exposure | No new dependency or credential access; existing pinned build and late credential callback unchanged | Diff and build audit | Outside this slice |

## Decisions

- Accepted risks with owner and expiry: a hard process crash may retain an unused allowance conservatively; Joshua Myers, review at G2 qualification closure. No automatic historical repair is authorized.
- Required tests and monitoring: controller timing, schema substitution, terminal decline/cancel/failure, exact ledger retirement, transfer crash attribution, inspection completeness and full repository gate.
- Incident and recovery dependencies: use the retained start/preview/result pins and read-only inspector; never infer retry or ledger repair authority from a terminal record.
