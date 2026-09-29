# Work Note: review citation fidelity fix

- Status: closed
- Owner: Joshua Myers
- Started (UTC): 2026-09-20
- Last updated (UTC): 2026-09-20
- Review or delete by: completion of the offline correction
- Related issue/incident/ADR: final live-review citation-fidelity failure; `docs/adr/0006-content-bound-review-citations.md`

## Objective and completion evidence

- Intended outcome: accept exact multiline code quoted from one unified-diff view
  while rejecting invented, stale, normalized, or cross-hunk evidence.
- Required invariants: schema-1 request bytes and historical outcomes remain stable;
  no retained live artifact changes; no provider, credential, or network access; new
  citations bind to one deterministic source unit.
- Evidence that will show completion: focused parser/validator/replay tests, affected
  review tests, the full offline quality gate, and production-like container checks.

## Context retrieved

- `src/mos_eisley/core/models.py`, `src/mos_eisley/review/pipeline.py`
- `src/mos_eisley/providers/model_reviewer.py`
- `src/mos_eisley/run/review_evidence.py`, `src/mos_eisley/run/review_launch.py`
- `docs/MODEL_REVIEWER.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`
- OpenAI citation-formatting guide reviewed 2026-09-20

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-20T16:08:35Z | observation | The failed quote is exact postimage code from one diff hunk, but not an exact raw-patch substring because continuation lines retain `+` markers. | Offline retained-shape diagnosis and current raw-substring validator | Add deterministic raw/before/after diff units. |
| 2026-09-20T16:08:35Z | decision | Version critic requests instead of silently changing schema 1. Schema 2 will carry compact, content-bound unit descriptors; evidence may name one unit. | Serialization and replay-path inspection | Implement fail-closed catalog and quote validation. |
| 2026-09-20 | implementation | Added bounded deterministic raw/before/after hunk units, content-bound IDs, schema-2 request projection, exact single-unit evidence validation, and schema-2 production preview preparation. | `src/mos_eisley/review/citations.py`; ADR-0006; focused tests | Run adversarial and compatibility review. |
| 2026-09-20 | adversarial review | Schema-1 response prompts initially exposed the optional schema-2 `source_unit` property even though schema-1 request bytes and validators were unchanged. | Prompt-schema inspection and model-reviewer regression test | Remove the property from schema-1 prompt schemas and rerun gates. |
| 2026-09-20 | verification | The corrected implementation passed 12 focused citation/model tests, 366 review tests, 2,462 source tests with four skips and 89% coverage, 1,843 installed-wheel tests, package/export gates, and the complete container suite. | `docs/REVIEW_CITATION_FIDELITY_FIX_VERIFICATION.md`; `docs/REVIEW_CITATION_FIDELITY_FIX_REVIEW.md` | Close the offline correction without changing live authority. |

## Handoff

- Current state: the offline correction is complete; no live authority exists.
- Next smallest safe action: none within this work item. Any future live qualification
  requires a new owner-directed and separately reviewed plan.
- Blocker and required authority/input: production qualification remains failed and
  unauthorized; this correction does not grant provider or campaign authority.
- Checks already run: 12 focused tests, 366 review tests, 2,462 source tests with four
  skips and 89% coverage, 1,843 installed-wheel tests, package/export gates, and the
  complete container suite.

## Close and promote

- Outcome and verification: schema 2 accepts exact quotes from one content-bound diff
  view and rejects stale, invented, normalized, or cross-hunk evidence; all offline
  and production-like gates passed.
- Durable fact promoted to `PROJECT_MEMORY.md`: schema-2 citation correction and the
  unchanged failed/unauthorized production state.
- Decision promoted to ADR/documentation: `docs/adr/0006-content-bound-review-citations.md`
- Regression test, issue, or improvement-plan link: `tests/test_review_citations.py`;
  `docs/REVIEW_CITATION_FIDELITY_FIX_REVIEW.md`
- Temporary artifacts removed: test/build environments were automatically removed;
  ordinary ignored build outputs remain.
