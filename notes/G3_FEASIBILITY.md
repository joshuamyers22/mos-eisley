# Work Note: G3 fixed-matrix feasibility preflight

- Status: closed for the feasibility-preflight slice; G3 study open
- Owner: Josh Myers
- Started (UTC): 2026-09-21
- Last updated (UTC): 2026-09-21
- Review or delete by: G3 utility-study completion or abandonment
- Related issue/incident/ADR: `docs/ROADMAP.md` G3; plan §§18.3, 26.3–26.4

## Objective and completion evidence

- Intended outcome: before any paid fixed-matrix evaluation, produce a deterministic,
  content-addressed report showing whether the preregistered quality targets can fit
  the case, assignment and spend ceilings under the existing statistical design.
- Required invariants: repetitions never count as independent groups; the complete
  comparison family is included; clean and defective evidence are both budgeted;
  exact zero-risk or perfect-rate bounds are reported as unattainable at finite sample;
  current hard caps cannot be expanded; the report grants no execution, promotion or
  routing authority.
- Evidence that will show completion: reference calculation from plan §26.3 reproduces
  1,732 clean groups, 13,856 clean cases and 249,408 clean assignments; smaller
  feasible and spend-infeasible cases pass; malformed/mismatched budgets fail closed;
  focused lint, types and tests pass.

## Context retrieved

- `AGENTS.md`, `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`
- `docs/ROADMAP.md`; `docs/mos-eisley-plan.md` §§6.6–6.7, 18, 26
- `docs/adversarial-review-loop-project-plan.md` L4–L5
- `docs/STATISTICAL_DESIGN.md`, evaluation models/statistics/scoring and tests
- `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`
- production-template `templates/STATISTICAL_ANALYSIS_PLAN.md`, work-note and
  verification-loop templates at `237330dc7f6424dafcb172aa7ca776e755c71610`
- `docs/PRODUCTION_TEMPLATE_G3_SURVEY_2026-09-21.md`

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-21 | observation | G3 planning and labeling may proceed while G2 qualification remains open; live quality or savings claims may not. | Plan §26.4 and roadmap G3 | Keep this slice offline and authority-denying. |
| 2026-09-21 | observation | The existing scorer implements a fixed complete matrix, group-mean Hoeffding bounds and Bonferroni family correction, but has no executable pre-spend feasibility calculation. | `evaluation/statistics.py`; `evaluation/models.py`; plan §26.3 | Add a pure preflight over the existing contracts rather than a new inference method. |
| 2026-09-21 | decision | Use the template statistical-analysis plan in addition to the pinned Python and bounded-verification guidance. Upstream changes since the prior survey do not modify those sources. | G3 template survey | Record the study estimand, caps, best-case assumptions and non-authority explicitly. |
| 2026-09-21 | implementation | The first pure calculation reproduced the plan's 1,732-group clean bound and passed focused lint, typing and 15 evaluation tests. | Focused local checks | Review accounting and artifact integrity before the full gate. |
| 2026-09-21 | observation | The initial route ceilings did not bind their reviewed price/request basis, and assignment spend alone could be mislabeled as total study spend. | Distinct diff and requirement review | Require a cost-basis digest per route and an explicit non-assignment cost ceiling. |
| 2026-09-21 | implementation | The corrected report binds the candidate grid, gate, strata, repetitions, route cost bases, non-assignment ceiling and hard caps; all authority fields remain false. | `evaluation/feasibility.py`; CLI and contract tests | Run focused and repository-wide gates. |
| 2026-09-21 | verification | Sixteen focused evaluation tests pass with 89% affected coverage; full Ruff, formatting and Pyright pass. The source suite passes 2,488 tests with 4 skipped and 89% total coverage; the installed wheel passes 1,855 smoke tests. | `docs/G3_FEASIBILITY_VERIFICATION.md` | Close the slice and hand off study design. |

## Handoff

- Current state: the offline, content-addressed feasibility preflight is implemented;
  it reproduces the reference calculation and rejects designs that exceed data,
  assignment or total-spend ceilings. It grants no study-execution authority.
- Next smallest safe action: draft and seal the baseline/ablation policy and inventory
  eligible independently graded labels without inspecting held-out sessions.
- Blocker and required authority/input: the owner and an independent statistical
  reviewer must choose actual targets, strata, budget and reviewed route price bases;
  G2 completion remains a prerequisite for live quality or savings claims.
- Checks already run: focused Ruff, formatting, Pyright and 16 tests; affected coverage
  89%; full `make check` source suite 2,488 tests, 4 skipped, 89% coverage, export,
  build and 1,855 installed-wheel smoke tests.

## Close and promote

- Outcome and verification: first G3 slice complete; see
  `docs/G3_FEASIBILITY_VERIFICATION.md`
- Durable fact promoted to `PROJECT_MEMORY.md`: `delivery.g3.feasibility`
- Decision promoted to ADR/documentation: `docs/EVALUATION.md` and roadmap updated;
  no ADR needed because the existing inference method and authority model are unchanged
- Regression test, issue, or improvement-plan link: `tests/test_evaluation_feasibility.py`
- Temporary artifacts removed: report tests use temporary directories; build artifacts
  are the repository's normal ignored `make check` outputs
