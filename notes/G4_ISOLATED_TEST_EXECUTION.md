# Work Note: G4 isolated reviewer-test execution and counts

- Status: complete
- Owner: Joshua Myers; implementation by Codex
- Started (UTC): 2026-09-24T04:21:11Z
- Last updated (UTC): 2026-09-24T10:34:28Z
- Review or delete by: retain as G4 delivery evidence
- Related issue/incident/ADR: roadmap G4; Phase L2

## Objective and completion evidence

- Intended outcome: immutable isolated execution/count receipts plus validated
  known-good and known-bad controls for the frozen reviewer package.
- Required invariants: exact current binding/package/tree, generated direct-import
  adapter only, no host execution fallback, bounded offline container, exact counts,
  private immutable records and no downstream authority.
- Evidence that will show completion: focused real-worker and hostile tests, static
  checks, full source suite, export/build and installed-wheel smoke.

## Context retrieved

- `AGENTS.md`; Python, verification and adversarial-review guides and templates
- `docs/ROADMAP.md`; `docs/mos-eisley-plan.md` §26.2/§26.4
- G4 reviewer-package and implementation-binding contracts/threat models/tests
- existing `OfflineContainer`, bounded process and cleanup tests

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-24 04:21 | decision | Use immutable no-mount container stdin protocol and a clean child interpreter; never execute on host in the product path | threat and architecture records | Implement contracts and worker |
| 2026-09-24 04:21 | decision | Require exact counts for every run and assertion-only known-bad failure paired with a clean known-good receipt | G4 plan §26.2 | Add hostile and real-worker regressions |
| 2026-09-24 05:10 | finding | Repository-relative lifecycle defaults could write beneath reviewed inputs | source review | Require explicit disjoint lifecycle root |
| 2026-09-24 05:25 | finding | Already imported packages could shadow same-name materialized implementation | same-name fixture | Add clean `python -I` child with exact path precedence |
| 2026-09-24 05:40 | finding | Distinct binding hashes did not necessarily mean distinct implementation trees | control review | Require distinct tree digests |
| 2026-09-24 06:00 | verification | Focused package/binding/execution suite, Ruff, Pyright and CLI help pass | 25 tests; zero static findings | Run full gates |
| 2026-09-24 10:34 | verification | Source, local fixture, export/build and installed-wheel evidence reconciled | 2,456 source; 48 localhost; 1,787 wheel | Close slice |

## Handoff

- Current state: immutable request/job/receipt/control contracts, worker/child, CLI,
  hostile regressions and documentation are complete and verified.
- Next smallest safe action: begin the separate authenticated-custody and trusted
  VCS/E2 G4 slice; do not infer candidate/correction authority from these records.
- Blocker and required authority/input: none for offline implementation.
- Checks already run: focused 25/25; full static gates; 2,456 source tests reconciled
  with 48/48 local fixture rerun; export/build; 1,787 installed-wheel smoke.

## Close and promote

- Outcome and verification: offline isolated execution/count and paired-control slice
  complete; no live/provider call and no candidate or correction authority granted.
- Durable fact promoted to `PROJECT_MEMORY.md`: yes,
  `delivery.g4.isolated-test-execution`.
- Decision promoted to ADR/documentation: contract, threat model, verification and
  architecture review updated; no ADR because established container authority did
  not change.
- Regression test: `tests/test_reviewer_test_execution.py`.
- Temporary artifacts removed: build/smoke used managed temporary directories; no
  retained execution receipt or live artifact was created.
