# PR integration work note — 2026-09-29

- Status: complete
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

## Merge inventory

| PRs | Final disposition |
|---|---|
| #233, #235, #238 | Merged directly into `main`. |
| #242, #244, #245 | Merged into their feature base branches; those commits reached `main` through #241 and #243. |
| #240, #241, #243 | Merged into `main` in G2, G3, G4 order after conflict resolution and fresh required checks. |
| #234, #236, #237, #239 | Merged into `main` after repaired checks; #236 handled direct SDK callback errors, and #237/#239 repaired the runtime export. |

## Integration progress

- PRs #233, #235, and #238 merged into `main` with passing GitHub checks.
- PR #242 merged into its G3 base; #244 and #245 merged into their G4 base.
  Their commits are ancestors of the final integrated `main`.
- G2 PR #240 was reconciled with the new `main`. The integration retains
  the later Anthropic structured-output and signed-campaign controls, restores
  G2 mixed-provider credential and signed-scope checks, and keeps the exact G2
  qualification contract. Focused mixed, acceptance, launch, and broker tests
  passed. The combined `make check` passed 2,376 source and 1,761 installed-wheel
  tests. PR #240 merged after its fresh GitHub checks.
- The G3 branch merged G2 with mixed-provider and owner-role
  gates retained. Focused launch, reviewer, broker, and readiness tests passed.
  A direct SDK callback exception is reduced to a coarse readiness failure so
  the OpenAI dependency update cannot expose private error text.
- The G4 branch merged that G3/G2 integration. Its two document
  conflicts retained G3 study deferral, exact G2 qualification, and current G4
  correction status. Its combined `make check` passed 2,599 source and 1,910
  installed-wheel tests before publication.
- PR #234 merged after its required checks. PR #236's SDK callback fix passed
  its focused readiness tests under OpenAI 3.19.2. PRs #237 and #239 repaired
  stale runtime exports. The combined dependency batch passed 2,599 source
  tests, 1,910 installed-wheel tests, export verification, and a production
  dependency audit with no known vulnerabilities in 50 packages.
- The first integrated G3/G4 pushes exposed merge conflicts and historical
  `generic-api-key` scan findings on API-key parameters and Ed25519 signing-key
  type annotations. No credential value was present in those findings. G3 and
  G4 include the pinned setup-uv update across all jobs and exact-fingerprint
  exceptions. Their fresh GitHub checks passed before merge.

## Final verification

- GitHub marked all 13 original PRs merged and reported no open PRs after #239.
- The `main` tree at `888c669` was byte-for-byte identical to the locally
  verified combined dependency tree. This note changes documentation only.
- ADR-0011's study deferral remains in the integrated roadmap. No study,
  live provider call, production deployment, or release was performed.
