# Agentic Verification Loop: reconcile continuous production plan in PR #241

## Objective and authority

- Requirement: the approved continuous production plan in source commit `f46e3a8`
  and the sealed G3 study package's §9 must be present in the branch proposed for
  merge to `main`.
- Outcome: the PR branch contains plan §26.6, its G5 preregistration and related
  roadmap, routing, review-loop and ADR guidance.
- Invariants: preserve the existing G3 owner-review exception and ADR-0005
  single-operator review decision; do not assert a completed study, eligible
  labels, current live authority or automatic policy learning.
- Risk class: material study and production governance.
- Implementation owner: Codex under Joshua Myers's direction.
- Accountable approval: the continuous plan was previously accepted by Joshua
  Myers; this port remains subject to PR review.
- Starting revision: `07afb982a1bf82677349b2734e63cdfc831bd054`, clean PR branch.
- Selected guide: `docs/AGENTIC_VERIFICATION_GUIDE.md` and
  `templates/AGENTIC_VERIFICATION_LOOP.md`; the imported decision follows
  `templates/ADR.md`.

## Rubric and stopping rules

| Dimension | Severity | Evidence | Pass threshold |
|---|---|---|---|
| Plan completeness | Blocking | Source commit versus PR diff | §26.6 and its linked contracts transfer without weakening entry gates |
| ADR identity | Blocking | ADR filenames and cross-document links | Continuous plan uses unique ADR-0009; existing ADR-0005 keeps its meaning |
| Authority truthfulness | Blocking | Plan, roadmap, G5 protocol and memory | Three levels remain planned, no execution or promotion authority |
| Repository quality | High | Link/diff checks and `make check` | All pass before push |

- Maximum iterations: two evidence-changing passes and one combined repository gate.
- Compute/spend ceiling: local checks only; no provider study calls.
- Pass rule: all blocking rows, link and diff checks, and `make check` pass.
- Stop rule: stop after pass rule and distinct cross-document inspection.
- Escalation trigger: a source decision or existing G3/G4 authority boundary would
  need a substantive change.

## Iterations and findings

| # | Slice | New evidence | Finding | Disposition |
|---:|---|---|---|---|
| 1 | Port accepted source commit `f46e3a8` | Clean cherry-pick of six documentation files onto the PR branch | C-001: imported ADR-0005 number collides with the branch's existing single-operator ADR-0005 | Number the imported ADR-0009 and update links; preserve the accepted decision text |
| 2 | Cross-document review | Exact §26.6 and G5 protocol bytes match `f46e3a8`; changed Markdown links resolve; the plan, roadmap, routing guide, review-loop plan, G5 protocol, ADR and memory retain staged authority | No further blocking finding | Keep the imported program planned and the existing G3/G4 gates intact |

## Exit

- Rubric result: pass. The imported §26.6 and G5 protocol match source commit
  `f46e3a8`; all changed Markdown relative links resolve, ADR numbers are unique,
  and the staged diff passes `git diff --cached --check`.
- Full quality gate: `make check` passed on 2026-09-27 with host permissions:
  Ruff, Pyright, source tests with coverage, export verification, sdist/wheel
  build, and installed-wheel smoke tests (1,894 tests, OK). The first sandboxed
  attempt could not bind localhost fixture sockets and ended with 31 permission
  errors; the complete host-permitted rerun passed.
- Remaining uncertainty: no G3 statistical review, real eligible labels, cohort
  seal or continuous production level has been completed by this port.
- Durable decision: plan §26.6 and ADR-0009 carry the accepted program direction;
  the sealed local study package remains unchanged.
