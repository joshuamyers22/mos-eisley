# Threat Model: review response-envelope budget correction

## Scope and ownership

- System/version: G2 canonical model-review and brokered OpenAI boundary
- Owner and reviewers: Josh Myers; implementation support by Codex
- Date and review trigger: 2026-09-20; final qualification failure Q-004
- In scope / out of scope: local response budgeting, parsing, retention and request
  identity are in scope; provider payload changes, credentials, dispatch, old campaign
  mutation and launch authority are out of scope

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Visible critic/judge JSON | Private repository review | Strict bounded parse and exact evidence lineage | Josh Myers |
| Opaque encrypted reasoning | Private provider state | Bounded retention without treating it as answer text | Josh Myers |
| Model request and preview hashes | Authorization and spend boundary | Both output limits must remain exact and immutable | Josh Myers |
| Spend reservation | Financial | Token ceiling and no-retry rule must not expand | Josh Myers |

- Actors and capabilities: provider controls response shape within transport bounds;
  operator selects a reviewed budget; trusted host retains and verifies artifacts
- Entry points and trust boundaries: provider JSON to canonical adapter; canonical
  response to broker; broker evidence to model reviewer and retained-evidence verifier
- Data flows and external dependencies: OpenAI response shapes are exercised only by
  captured/synthetic offline fixtures during this correction

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Envelope increase silently weakens answer bound | One byte limit is reused for both concepts | Oversized model prose is accepted | Enforce an 8,000-byte UTF-8 visible-answer cap separately from total canonical bytes | Focused exact/over-limit tests | JSON complexity remains bounded by contracts and token ceiling |
| Opaque reasoning amplifies memory/disk use | Provider returns large encrypted content | Denial of service or retained-data growth | Explicit 64,000-byte envelope policy capped by model registry and broker wire limit | Budget and broker boundary tests | Provider may exceed the envelope and fail closed |
| New limit is absent from request identity | Parser-only configuration changes after approval | Substituted evidence or stale approval | Put both limits in `ModelRequest`; serialize both reviewed launch settings explicitly | Request hash/profile tests | Trusted composition root must supply the reviewed policy |
| Token or spend cap rises with byte cap | Limits are changed together for convenience | Unapproved cost | Keep `max_output_tokens` and spending policy unchanged; regression assertions | Spend/config tests | Invoice finality remains external |
| Old failed response is reclassified | New code is applied retroactively | Audit corruption and unauthorized continuation | Preserve completion receipts and qualification decision; no migration or replay-to-success path | Qualification docs and evidence verifier | Owner controls private files |
| Correction triggers live access | Test or setup reads Keychain/provider | Unauthorized transfer/spend | Synthetic fixtures only; no live command or private campaign script | Test inventory and zero-provider work-note record | Developer machine remains trusted |

## Decisions

- Accepted risks with owner and expiry: bounded opaque reasoning remains retained with
  the canonical response; Josh Myers must reassess the envelope before any future live
  qualification
- Required tests and monitoring: visible-answer and canonical-envelope exact bounds,
  broker request identity, completion receipts, evidence reconstruction, no retry
- Incident and recovery dependencies: `REVIEW_RESPONSE_BUDGET_INCIDENT.md`; rollback is
  a normal code revert because no stored artifact is migrated
