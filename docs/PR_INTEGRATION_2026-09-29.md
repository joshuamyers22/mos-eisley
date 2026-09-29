# PR integration work note — 2026-09-29

- Status: active
- Owner and merge authorizer: Joshua Myers
- Implementation: Codex
- Scope: all 13 Mos Eisley PRs open when the owner requested fixes and merges
- Starting `main`: `0ce5c54d601324a0b6a88f20b2b0b812d2ea1c26`
- Selected guidance: `AGENTS.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/WORK_NOTE.md`,
  `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, and the applicable G2/G3/G4 threat models

## Objective and acceptance

Integrate every open PR into `main` without losing either side of overlapping
feature branches. The final commit must contain each intended change, pass the
required repository and GitHub checks, and leave no open PR from this set.
Dependencies are integrated through their base branches before those branches
enter `main`; feature and dependency conflicts are reviewed by affected boundary.

Invariants: no G3/G5 study execution before production; no implicit live
activation, credential access, provider spend, retry, or release tag; no private
keys, prompts, payloads, labels, outcomes, or sampling data in Git; preserve
signed historical evidence and fail-closed spending, authorization, storage, and
containment behavior. Existing exact campaign evidence does not authorize a
new launch or a new artifact. No production deployment is part of this task.

The risk class is high because G2/G4 authorization, spending, dependency versions,
and release workflow all change. Owner direction authorizes the merge work;
the prior domain and signed evidence keep their exact scope. A passing PR check
is necessary but does not certify product production readiness.

## Verification budget and stop rules

- Provider spend: zero; use synthetic and offline fixtures only.
- For each distinct combined code batch: focused affected tests and static checks,
  then `make check` before pushing or merging. Recheck affected gates after fixes.
- Use GitHub PR checks and a final `main` inventory as independent integration
  evidence. Do not treat a canceled check as a pass.
- Stop a merge if a conflict changes authorization, spending, source custody,
  release protection, or study timing without a testable resolution; keep the PR
  open and record the exact blocker for owner review.

## Current integration sequence

| PRs | Planned disposition | Evidence or open gate |
|---|---|---|
| #244, #245 | Merge into their G4 base #243 first | Both local merges were clean; the source-text broker's 4 initial and 12 correction tests, Ruff and Pyright passed. Full combined gate pending. |
| #242 | Merge into its G3/G4 base #241 first | PR checks passed before integration; release approval remains separate. |
| #233, #240 | Integrate Anthropic and G2 owner live-review changes | Both have passing PR checks but overlapping source and docs; review conflicts and preserve the later G2 exact profile. |
| #241, #243 | Integrate G3/G4 development and connected correction into `main` | Both overlap G2/G4; maintain ADR-0011 study deferral and exact G4 evidence limits. |
| #234–#239 | Refresh against integrated `main`, fix lock/export or CI failures, then merge | #236, #237, #239 quality failed; #234 quality canceled. No bypass. |

## Integration progress

- PRs #233, #235, and #238 were merged into `main` with passing GitHub checks.
- PR #242 was marked ready and merged into its G3 base with passing checks.
- GitHub marks #244 and #245 merged into the G4 branch. Their 4 initial broker
  and 12 correction broker tests, Ruff, and Pyright passed. The earlier combined
  `make check` session was interrupted before its final result was captured.
- G2 PR #240 was reconciled with the new `main`. The integration retains
  the later Anthropic structured-output and signed-campaign controls, restores
  G2 mixed-provider credential and signed-scope checks, and keeps the exact G2
  qualification contract. Focused mixed, acceptance, launch, and broker tests
  passed. The combined `make check` passed 2,376 source and 1,761 installed-wheel
  tests, and the branch was pushed for fresh GitHub checks.
- The G3 branch now has a local merge of G2 with mixed-provider and owner-role
  gates retained. Focused launch, reviewer, broker, and readiness tests passed.
  A direct SDK callback exception is reduced to a coarse readiness failure so
  the OpenAI dependency update cannot expose private error text.
- The G4 branch has a local merge of that G3/G2 integration. Its two document
  conflicts retained G3 study deferral, exact G2 qualification, and current G4
  correction status. Its combined `make check` passed 2,599 source and 1,910
  installed-wheel tests before publication.
- PR #234 merged after its required checks. PR #236 still fails its old branch
  test for the direct SDK callback exception; its corrected code is in G3/G4 and
  a repair branch. PRs #237 and #239 failed on stale runtime exports; their
  repaired exports pass the verifier in local repair branches.

## Handoff

PR #240 is queued for auto-merge after fresh GitHub checks. Push the integrated
G3 and G4 heads, wait for required checks, then merge #241 and #243 in order.
Refresh the repaired dependency branches against integrated `main`, run the
combined dependency gate, and merge their PRs after fresh required checks.
