# G4 final whole-suite verification

- Starting revision: `4b95a51c5a375e334f968d8adf43fa0c8e22ea26`, clean worktree.
- Requirement: [G4 roadmap](ROADMAP.md), [plan §26.2](mos-eisley-plan.md#262-review-loop-contract), existing authenticated candidate and isolated execution contracts.
- Objective: separately approved, exact final creator/reviewer whole-suite runs with protected creator Git bytes, separate count evidence and non-accepting replay.
- Risk: high. Owner: Joshua Myers. Agent implementation is not independent release approval.
- Selected pinned guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
  `templates/THREAT_MODEL.md`, `templates/WORK_NOTE.md`. The production-template
  survey is pinned in `AGENTS.md`; no live review survey or provider call occurred.

## Bounded rubric

| Dimension | Severity | Pass evidence |
|---|---|---|
| Full exact creator and reviewer suites | Blocker | Protected creator paths/base-final Git bytes; frozen reviewer/candidate identity; separate passing count receipts |
| Separate authority and replay denial | Blocker | Creator signature, two exact requests, image/window and exclusive claim |
| No acceptance escalation | Blocker | False authority flags on approval/receipt and nonpassing result on a failed suite |
| Delivery | Material | Focused regressions, CLI round trip, static gate, source and installed-wheel suites |

Budget: two evidence-changing passes, no external spend; stop if real credentials,
fresh authority or independent judgment becomes necessary. Pass 1 found that
creator tests may directly import implementation, while the reviewer binder must
forbid that; a separate creator job reuses the same isolated child/count engine
  without weakening the reviewer binding. Pass 2 adds current Git, one-use and CLI
  replay checks, plus denial of a test-pattern file disguised as a fixture. No
  agent self-review counts as independent acceptance.

## Checks

| Check | Result |
|---|---|
| Focused final-suite tests | 13 passed, including imported candidate regressions; real clean Python worker, fake Docker transport only |
| Final combined gate | Permissioned `make check`: Ruff, format and Pyright passed; complete source suite passed; 88% branch-inclusive coverage; locked export and wheel build passed; 1,854 installed-wheel tests passed |
| Whitespace | `git diff --check`: passed |

No live provider request, production final candidate run, independent critic/judge
decision, or final acceptance is claimed. The earlier creator-suite digest remains
an approval claim until the new signed exact-package and Git-byte gate is actually
run on a production candidate.

The first sandboxed `make check` completed 2,499 source tests with four skips but
had 31 localhost socket-bind permission errors in MCP fixtures, so it is not
counted as a pass. A permissioned rerun was stopped before completion after an
offline review found a test-pattern file could be disguised as a fixture; the
negative regression and classification denial were added. The final permissioned
combined run above exited zero. No production Docker image rebuild or live G4
exercise is claimed by this source/package check.
