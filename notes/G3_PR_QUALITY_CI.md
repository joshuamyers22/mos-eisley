# Work Note: G3 PR quality CI

- Status: active
- Owner: repository maintainer
- Started (UTC): 2026-09-28 16:38
- Last updated (UTC): 2026-09-28 16:40
- Review or delete by: PR #241 closure
- Related issue: [PR #241](https://github.com/joshuamyers22/mos-eisley/pull/241)

## Objective and completion evidence

- Intended outcome: make the required `quality` check report the complete source
  and installed-wheel gates without a combined-job timeout.
- Required invariants: keep every `make check` component and `make audit` in CI;
  keep `quality` failed when either suite fails or is skipped; change no G3
  sampling, source-enrollment, label, or production-outcome authority.
- Evidence that will show completion: workflow parse, focused dependency-gate
  inspection, local test failure disposition, and a green new-head PR CI run.
- Risk class: material CI gate; no runtime or study protocol change.
- Resource ceiling: one workflow revision and one new-head CI run; stop if an
  actual test failure requires separate diagnosis.

## Context retrieved

Selected `docs/AGENTIC_VERIFICATION_GUIDE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md`, and `templates/WORK_NOTE.md` under
`AGENTS.md`. Read `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, the G3
roadmap and execution-view verification, `.github/workflows/ci.yml`, `Makefile`,
and `tools/smoke_package.py`.

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-28 16:39 | observation | Old `quality` job reached its 75-minute timeout during installed-wheel smoke after 2,540 source tests passed in 54m32s; `make audit` never ran. | [run attempt 1](https://github.com/joshuamyers22/mos-eisley/actions/runs/36433710537) | Split independent gates. |
| 2026-09-28 16:40 | decision | Run source checks and installed-wheel smoke in separate 90-minute jobs; retain `quality` as a fail-closed dependency gate for both. | `.github/workflows/ci.yml` | Verify and publish. |
| 2026-09-28 16:41 | verification | Workflow YAML parses with four jobs; `git diff --check`, Ruff and Pyright pass. The old rerun was cancelled because it retained the known timeout. | Local checks and [old run](https://github.com/joshuamyers22/mos-eisley/actions/runs/36433710537) | Finish full gate. |
| 2026-09-28 17:12 | error | Local `make check` stopped after 2,540 tests with 32 errors and 4 skips. It did not reach package smoke. The previous GitHub source suite passed on the same product code. | Local test summary; old run | Capture a local rerun log and compare new-head CI. |

## Handoff

- Current state: workflow change under verification; local test errors are under
  diagnosis.
- Next smallest safe action: push and inspect the new PR CI while capturing the
  local rerun's error summary.
- Blocker and required authority/input: none for this CI correction.
- Checks already run: previous CI source suite passed; local `make check` failed
  with 32 errors; the full local test rerun is in progress.
