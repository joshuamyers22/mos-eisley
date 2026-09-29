# Threat Model: citation and observation completion

## Scope and ownership

- System/version: Mos Eisley schema-2 review and runtime observation construction
- Owner and reviewers: Joshua Myers
- Date and review trigger: 2026-09-20; final live retest retained-result follow-up
- In scope / out of scope: offline retained citation and runtime evidence composition
  are in scope; new live dispatch, credentials, spending, and attestation are out.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Retained critic finding | untrusted model output | exact frozen-source binding | review pipeline |
| Phase authorization | signed local authority | exact critic/judge separation | Joshua Myers |
| Runtime evidence | private host records | exact request, worker, cleanup, and phase binding | observation builder |

- Actors and capabilities: an untrusted critic can invent citations; a caller can
  provide reordered, missing, or surplus request/lifecycle records.
- Entry points and trust boundaries: critic response parsing, retained reconstruction,
  runtime evidence collection, and unsigned observation proposal construction.
- Data flows and external dependencies: deterministic local files and signed records;
  no new network or dependency.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Judge authorization assigned to a critic | multiple critics and flattened positional zip | observation construction fails or binds the wrong approved phase | semantic grouping maps every critic to authorization 0 and judge to authorization 1 | two-critic regression | caller can still select the wrong evidence directory, which existing exact request/cleanup checks reject |
| Missing or surplus lifecycle path | incomplete or mixed run evidence | silent truncation could omit an exchange | exact cardinality validation before collection | shape regressions | local files may disappear and then fail closed |
| Fabricated positive `source_unit` | malicious/errant critic | unsupported finding reaches judge | existing catalog recomputation and exact substring validation remain unchanged | citation adversarial suite plus positive retained test | model relevance remains advisory |
| Historical schema-1 drift | shared response type changes | replay incompatibility | preserve schema-1 projection and tests | full review suite | schema 1 retains its known expressiveness limit |
| Observation mistaken for attestation | successful local collection | false conformance claim | helper returns local `ReviewObservedExchange` only; independent signature remains separate | observation contract tests | operator interpretation risk remains documented |

## Decisions

- Accepted risks with owner and expiry: local collection proves record consistency,
  not provider conformance; Joshua Myers owns this standing limitation.
- Required tests and monitoring: positive retained citation, multi-critic phase mapping,
  malformed shape rejection and runtime tamper cases pass. The unrestricted full
  package gate and production-like container gate pass.
- Incident and recovery dependencies: never edit a sealed run; correct orchestration
  code and create a new observation proposal from independently selected evidence.
