# G4 independent-review gate verification

- Starting revision: `9d5626f`, clean worktree; branch `feat/g4-independent-review-gate`.
- Requirement: [G4 roadmap](ROADMAP.md), [plan §26.4](mos-eisley-plan.md#264-delivery-order-and-accountable-gates), and [final-suite contract](G4_FINAL_WHOLE_SUITES.md).
- Objective: exact post-suite subject reconstruction and authenticated, quorum-bound independent critic/judge evidence with no release authority.
- Risk: high. Owner: Joshua Myers. Agent implementation is not independent acceptance.
- Selected pinned guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, `templates/WORK_NOTE.md`. The template survey is pinned in `AGENTS.md`; no live review or provider call occurred.

## Bounded rubric

| Dimension | Severity | Pass evidence |
|---|---|---|
| Exact plan, Git and final-suite subject | Blocker | Recompute from signed approvals, protected test receipts and current Git; stale/tampered inputs denied |
| Authenticated multi-family review | Blocker | Distinct creator/critic/judge roles and signatures; two completed provider-family claims; all critic hashes signed by judge |
| Citation and verdict fidelity | Blocker | Exact-source citation validation, shared deterministic adjudication, non-accepting upheld blockers |
| No authority escalation | Blocker | No signing keys, provider or write calls in CLI; false release/human-independence flags |
| Delivery | Material | Focused negative tests, static checks, source and installed-wheel gate |

Budget: two evidence-changing passes, no external spend. Stop if external key custody,
live provider evidence or accountable independent review is needed. Pass 1 added
the signed exact-subject gate, citation and quorum regressions. Pass 2 added an
upheld-blocker verdict regression and made failed critic claims explicitly false.

## Checks

| Check | Result |
|---|---|
| Focused review tests | 8 dedicated tests passed on final code; exact subject, signatures, quorum, citation, blocker verdict, replay and CLI paths covered |
| First sandboxed `make check` | Ruff, format and Pyright passed; source suite ran 2,513 tests with four skips but 31 unrelated localhost MCP fixture `socket.bind` permission errors. Not a pass. |
| Permissioned `make check` through build | Ruff, format and Pyright passed; 2,513 source tests passed with four skips and 88% branch-inclusive coverage; locked export and wheel build passed. Its superseded wheel smoke was interrupted after the new test was added to the explicit allowlist. |
| Final installed-wheel smoke | Permissioned `make smoke`: 1,867 tests passed from the built wheel, including the new G4 test file |
| Whitespace | `git diff --check` passed |

No production G4 candidate, critic/judge provider call, independent human review,
release acceptance or live spend is claimed. Signatures and provider-family labels
are a trust-policy assertion, not reconstruction of G2 raw broker evidence.
The owner must review the code and arrange actual external reviewer/provider
evidence before any production G4 decision. The agent's fixture reviews are not
independent acceptance.

## Judge-request budget correction, 2026-09-25

- Trigger: offline adversarial source review found that `assess_independent_review`
  bounded each critic request but omitted the shared pipeline's judge-request
  `max_request_bytes` check. A signed record could therefore pass despite a
  judge request outside its creator-signed review policy.
- Correction: reconstruct the deduplicated `JudgeRequest` once, reject it when
  its canonical bytes exceed the signed limit, and pass that same request to
  `judge_verdict`. The public record schema and authority scope did not change.
- Regression: a case with valid creator, critic and judge signatures, valid
  citations and a critic request within the limit failed before correction
  (`ValueError` not raised), then passed after correction by rejecting its
  oversized judge request. The normal accepting case remains covered.
- Verification: focused regression passed; Ruff, formatting and Pyright passed.
  The first sandboxed `make check` ran 2,514 source tests with four skips but
  failed 31 localhost `socket.bind` fixtures with `Operation not permitted`;
  it was not a pass. The permissioned `make check` exited zero, including source
  tests, locked export, wheel build and 1,868 installed-wheel smoke tests.
  Branch-inclusive coverage is 88%; `git diff --check` passed.
- Authority: this correction made no live G4 call and grants no provider,
  repository-write or release authority. The user reports accountable approval
  secured; no external approval artifact was supplied to or verified by this
  offline correction.
