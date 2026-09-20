# Work Note: positive citation and post-result observation fix

- Status: closed
- Owner: Joshua Myers
- Started (UTC): 2026-09-20
- Last updated (UTC): 2026-09-20
- Review or delete by: close after verification and promote durable facts
- Related issue/incident/ADR: ADR-0006; final live read-only review retest

## Objective and completion evidence

- Intended outcome: prove a positive schema-2 `source_unit` citation through the
  retained brokered review path and construct post-result runtime observations with
  the correct phase authorization for every exchange.
- Required invariants: all critics use the critic-phase authorization; the judge uses
  the judge-phase authorization; exact request/lifecycle ordering is preserved;
  fabricated citations still fail closed; no live provider or credential access.
- Evidence that will show completion: a positive retained-result regression, a
  two-critic authorization-mapping regression, malformed-shape rejection, and the
  project quality gates.

## Context retrieved

- `AGENTS.md`
- `docs/PYTHON_ENGINEERING_GUIDE.md`
- `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`
- `docs/adr/ADR-0006-review-citation-contract.md`
- `docs/LIVE_READ_ONLY_REVIEW_QUALIFICATION_VERIFICATION.md`
- `src/mos_eisley/run/review_runtime_evidence.py`
- `src/mos_eisley/run/review_campaign_observation.py`
- `tests/test_review_runtime_evidence.py`
- `tests/test_review_citations.py`

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-20 | observation | A completed review has one authorization per phase, not one per exchange. The failed private construction zipped three exchanges against two authorizations, assigning the judge authorization to critic two. | campaign observation already uses an index conditional; runtime test covers only one critic | centralize the mapping and add a two-critic regression |
| 2026-09-20 | observation | Schema-2 exact citation validation has a pure positive test, but the retained broker/conformance path only exercises an empty critique. | citation and conformance tests | add a deterministic positive retained-path test |
| 2026-09-20 | implementation | Added one grouped collector that validates complete critic/judge shape and phase order, reuses the critic authorization for every critic, and delegates every exact record check to the existing single-exchange collector. | runtime evidence, campaign observation and conformance probe diffs | run focused and broad regressions |
| 2026-09-20 | verification | Positive multiline postimage evidence survived critic validation, judge uphold and retained reconstruction; two critics mapped to one critic-phase authorization and the judge mapped to the judge-phase authorization. | 36 focused tests; 371 broad review tests | complete package/container gates and adversarial review |
| 2026-09-20 | verification | The unrestricted complete gate passed 2,467 source-checkout tests and 1,848 installed-wheel tests; export verification, sdist/wheel builds and 89% coverage also passed. The production-like container gate passed. | `make check`; `make container` | close and promote the durable record |

## Handoff

- Current state: implementation, focused regressions, complete package gate,
  production-like container gate and adversarial review all pass.
- Next smallest safe action: commit the correction if requested. Any new live test
  still requires separate exact authorization.
- Blocker and required authority/input: none.
- Checks already run: Ruff lint and format, Pyright, 36 focused tests, 371 broad
  review tests, `make container`, and unrestricted `make check` pass. The complete
  gate ran 2,467 source-checkout tests and 1,848 installed-wheel tests, verified
  exports and both distributions, and reported 89% coverage. `git diff --check`
  passes.

## Close and promote

- Outcome and verification: grouped post-result observation construction now obeys
  phase cardinality, and a positive schema-2 postimage citation survives the full
  retained path; all scoped and release gates pass.
- Durable fact promoted to `PROJECT_MEMORY.md`: `delivery.next.live-review` records
  the offline corrections and preserves the historical retest's nonqualifying state.
- Decision promoted to ADR/documentation: existing ADR-0006 remains authoritative.
- Regression test, issue, or improvement-plan link: runtime-evidence and
  conformance-probe regressions plus
  `docs/REVIEW_CITATION_OBSERVATION_FIX_VERIFICATION.md`.
- Temporary artifacts removed: `make check` removed its temporary wheel environment;
  no live or credential artifacts were created.
