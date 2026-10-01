# Agentic Verification Loop: G3 owner statistical-review assignment

## Objective and authority

- Requirement: G3 study governance in `docs/mos-eisley-plan.md`,
  `docs/G3_CONTEXT_STUDY.md`, and the approved owner direction recorded in
  ADR-0008.
- Outcome: Joshua Myers may perform the G3 statistical-method review while his
  study-owner overlap is disclosed and all separate empirical gates remain.
- Invariants: do not claim a review has happened; do not assert independent human
  judgment from the owner; preserve two-grader labels, holdout custody, G5/G6
  promotion, provider/spending and execution gates.
- Risk class: material study governance and inference integrity.
- Implementation owner: Codex under Joshua Myers's direction.
- Accountable approver: Joshua Myers approved the role assignment; any future
  statistical report needs his actual signed review and its own evidence.
- Starting revision/state: `8c2bc1d7`, clean dedicated worktree.
- Selected guide: `docs/AGENTIC_VERIFICATION_GUIDE.md` and this repository's
  `templates/AGENTIC_VERIFICATION_LOOP.md`; ADR-0008 uses `templates/ADR.md`.

## Rubric and stopping rules

| Dimension | Severity | Evidence | Pass threshold |
|---|---|---|---|
| Exact role change | Blocking | Plan, ADR and G3 guide | Joshua may review G3 method with owner overlap disclosed |
| No false approval | Blocking | Cross-document inspection | Review, cohort seal and live authority remain pending |
| Other role boundaries | Blocking | Threat model and roadmap | Graders, resolver, holdout and G5/G6 gates unaffected |
| Traceability | High | Historical record addendum and memory | Earlier separate-person rule is explicitly superseded for future G3 statistical review |

- Maximum passes: two evidence-changing passes and one combined repository gate.
- Compute/spend ceiling: local checks only; no provider calls.
- Pass rule: all blocking rubric rows, `git diff --check`, applicable link checks,
  and `make check` pass.
- Stop rule: stop after the pass rule and a distinct cross-document review.
- Escalation trigger: a method, grader, holdout or promotion rule would need a
  broader exception.

## Iterations and findings

| # | Slice | New evidence | Finding | Disposition |
|---:|---|---|---|---|
| 1 | Add ADR and align plan, G3 guide, threat model, roadmap, historical addendum and memory | Compared prior G3 role language with the owner's new assignment and existing single-operator ADR pattern | G3-R-001: several keys or owner signatures could be presented as independent human judgment | Explicitly disclose owner overlap, require a real method review record, and deny independent-owner claims |
| 2 | Cross-document review | Confirmed the G3 exception leaves distinct label-grader and later promotion roles intact | No additional blocking finding | Keep exception scoped to G3 statistical methods |

## Exit

- Rubric result: pass; the role exception, pending-review boundary, and unchanged
  grader/holdout/promotion gates are explicit across the plan and G3 records.
- Full quality gate: `make check` passed on 2026-09-27 (Ruff, Pyright, source
  tests with coverage, export verification, sdist/wheel build, and installed-wheel
  smoke test; the packaged test run reported 1,894 tests, OK).
- Remaining uncertainty: no real G3 statistical review, signed label catalog,
  approved sample/spend plan or empirical cohort seal exists.
- Durable decision: ADR-0008; G3 implementation history remains unchanged.
