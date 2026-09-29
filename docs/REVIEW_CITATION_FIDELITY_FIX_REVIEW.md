# Adversarial review: content-bound review citations

## Review metadata

- Repository: Mos Eisley Memory Selection
- Remote: `https://github.com/joshuamyers22/mos-eisley.git`
- Branch and starting commit: `feat/production-template-guidance` at
  `768519f599c5162aa9270f62959b741a2e2a182c`
- Reviewer and date: Joshua Myers, 2026-09-20
- Scope: critic citation models, unified-diff unit derivation, reviewer projection,
  pipeline/evidence validation, production preview preparation, tests and docs
- Requirement: accept exact multiline code from one diff view without admitting
  invented, stale, normalized or cross-hunk evidence
- Independence: owner self-review; no independent reviewer is claimed
- Ceiling: four iterations, zero provider calls and USD 0

## Executive verdict

- Overall grade: approve
- Release recommendation: approve for offline integration; no live authority follows
- Highest risk: a derived-view or versioning error could admit unsupported evidence
- Strongest property: every schema-2 unit ID is recomputed from the frozen diff and
  binds the exact view, locator and text
- Recommended first improvement: none required for this bounded correction

## Verification evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Formatting | `uv run --frozen ruff format --check .` | Passed | Complete repository |
| Lint | `uv run --frozen ruff check .` | Passed | Complete repository |
| Static typing | `uv run --frozen pyright` | Passed | Zero errors |
| Focused tests | selected model/citation tests | 12 passed | Includes v1/v2 prompt isolation |
| Review regression | `PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -p 'test_review*.py'` | 366 passed | No skips reported |
| Unit/integration/coverage | `make test` | 2,462 passed, 4 skipped, 89% | No provider or credential access |
| Build/package | `make verify-export build smoke` | Passed; 1,843 wheel tests | Required network retry only for package-index access |
| Production-like contracts | `make container` | Passed | Build, isolation, controller, approvals, conformance, probe, runtime, campaign and launch |

## Architecture map

```text
launch/evidence adapters -> review pipeline -> citation policy -> core models
model reviewer adapter ------------------------^              -> frozen brief
```

- Domain policy: `review/citations.py` derives and validates bounded citation units.
- Application use cases: the review pipeline and evidence reconstruction invoke the
  same validator before a finding can reach the judge.
- Infrastructure adapter: the model reviewer projects compact descriptors and validates
  the catalog before prompting.
- Delivery/composition: production launch preview opts into schema 2; no live CLI or
  transport authority was added.
- External systems: none used by citation derivation or validation.

## Findings

### Resolved high: schema-1 prompt exposed the schema-2 response field

- Location: `src/mos_eisley/providers/model_reviewer.py`
- Principle: compatibility boundary / interface segregation
- Evidence: the shared response JSON schema initially retained optional `source_unit`
  when constructing a schema-1 critic prompt.
- Failure mode: a legacy critic could return a field its contract does not admit.
- Correction: remove `source_unit` from schema-1 prompt schemas and assert its absence;
  assert its presence in schema 2.
- Acceptance: focused prompt and citation tests plus every broader gate passed.

No critical, high, medium or low findings remain open in the reviewed scope.

## Clean-code and architecture result

- The parser and validator form one deterministic policy module with bounded hunk
  growth and fail-closed malformed-input behavior.
- Models express versioned wire contracts; adapters do not duplicate validation rules.
- Tests cover exact behavior rather than normalization and preserve schema-1 canonical
  serialization and prompt behavior.
- The official OpenAI citation-formatting guide informed the use of explicit stable
  citable units; local validation remains authoritative.

## Improvement plan

| Priority | Change | Finding addressed | Owner | Verification | Status |
|---:|---|---|---|---|---|
| 1 | Isolate schema-2 response fields from schema-1 prompts | Compatibility leak | Joshua Myers | Prompt-schema assertions and full gates | Complete |

## Final challenge result

The hardest rule is derived-view fidelity; it is infrastructure-independent and
tested directly. The citation policy owns the only semantic reconstruction. No broad
exception converts malformed diffs into valid evidence. The second pass added prompt
compatibility evidence, found no new issue, and met the verification loop's stop rule.
