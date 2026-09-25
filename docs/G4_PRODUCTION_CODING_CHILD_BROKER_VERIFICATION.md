# G4 production coding-child broker verification

- Starting revision: `b692e6468e28d0d162f19e2d7b003098d0617681`, clean worktree.
- Requirement: [G4 roadmap](ROADMAP.md), [plan §14.2.1](mos-eisley-plan.md#1421-creator-led-coding-delegation), and existing [offline dispatch](G4_CORRECTION_CHILD_DISPATCH.md).
- Objective: separately signed provider authorization with one-call isolated broker,
  conservative aggregate reservation, provider-usage settlement, enrolled-child
  proposal signature and replayable evidence.
- Non-goals: live call this turn, provider invoice reconciliation, repository/Git
  write, whole-suite result, critic quorum or final acceptance.
- Risk: high. Owner: Joshua Myers. Agent implementation is not independent approval.
- Selected pinned guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
  `templates/THREAT_MODEL.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`,
  `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`, `templates/WORK_NOTE.md`.
  OpenAI Docs informed the stateless, tool-free Responses request; no credential
  tool was available and no provider credential was read.

## Rubric and bounded loop

| Dimension | Severity | Pass evidence |
|---|---|---|
| Exact separate authority and replay denial | Blocker | Read-only offer preview, creator signature, exact offer/request/policy/ledger/image binding; cross-instance duplicate negative |
| Bounded provider exposure | Blocker | Full reservation before call; measured usage settlement or retained uncertain hold |
| Child identity and scope | Blocker | Enrolled key, parsed proposal, existing-owned-path and offline-container validation |
| No ambient authority | Blocker | Tool-free stateless request, no host write, no CLI/live activation |
| Delivery | Material | Focused negatives, typing/lint, whole suite, wheel build |

Budget: two implementation/verification passes, no external spend; stop if owner
approval or live data is needed. Pass 1 established signed request/spend/child
composition and focused fake-transport tests. Pass 2 added durable audit/response
replay and duplicate-instance checks. No agent self-review is independent release
approval.

## Checks and findings

| Check | Result |
|---|---|
| Focused broker tests | `uv run --frozen python -m unittest discover -s tests -p 'test_reviewer_coding_broker.py' -q`: 7 passed; fake transport only |
| Existing correction regressions | `uv run --frozen python -m unittest discover -s tests -p 'test_reviewer_correction.py' -q`: 6 passed; exact-offer preview equals dispatch offer |
| Ruff and Pyright | `ruff check .`, `ruff format --check .`, `pyright`: passed on final source; zero typing errors |
| Combined gate | Permissioned `make check`: 2,487 source tests passed, four skipped; 88% branch-inclusive coverage; locked export, wheel build and 1,834 installed-wheel smoke tests passed |
| Affected post-gate packaging check | Added the broker test to `tools/smoke_package.py`; permissioned `make smoke` passed 1,841 installed-wheel tests |
| Whitespace | `git diff --check`: passed |

No live provider request was made. The provider-side response and usage remain
trust assumptions, not an independently reconciled bill. Final whole-suite,
critic quorum, renewed correction chain, G3 production quality and accountable
launch review remain open.

The initial sandboxed `make check` attempt was interrupted before completion
because prior runs of the localhost MCP fixture had hit sandbox bind denials;
it is not counted as a pass. The later permissioned complete gate is the passing
result above. No separate production Docker image rebuild or live OpenAI exercise
is claimed by this code/packaging verification.
