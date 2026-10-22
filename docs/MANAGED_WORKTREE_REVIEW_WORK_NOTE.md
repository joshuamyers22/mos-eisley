# Work note: managed-worktree review

- Status: closed
- Owner: repository maintainer, assisted by Codex
- Started / updated: 2026-10-22
- Review by: next release qualification
- Related: project plan §31.7; production template 8879be48f3b760e65f6bed32f8740314fe92910d

## Objective and completion evidence

Admit Mos-created standard linked worktrees to the existing frozen Git review
reader. Preserve owner-scoped workspace, admin-directory and common-directory
identity, disabled helpers, source revalidation, unchanged checkout, frozen-brief
parity, quorum, budgets, cancellation and read-only review authority. Keep ordinary
schema-1 scopes byte compatible. Linked scopes use an explicit versioned binding.

Risk class: security-sensitive local read boundary. Metadata indirection can
select another repository or run configuration helpers. Validate bounded reciprocal pointers and owner-controlled, non-symlinked
metadata before Git runs; pin identities throughout acquisition. Standard layout
is evidence of topology, not proof that Mos issued a worktree or new authority.
The trust model remains cooperative owner-controlled local metadata, not kernel
containment against concurrent malicious same-owner rewrites.

Non-goals: creating or integrating worktrees during review, changing the diff
panel, credentials, release activation, paid calls, or claiming Linux/WSL2/live
qualification from macOS fixtures. No sampling stores or user catalogs are needed.

Acceptance: real CodingVCS stages; valid detached linked scopes; distinct shared
and local identities; malformed/redirected/linked/unsafe metadata rejected before
process launch; stale replacement and source edits rejected; helpers suppressed;
creator and child checkout/index unchanged; CLI/JSON and persisted scope parity;
existing live authority tests pass. Source and installed-wheel checks must pass.

## Context retrieved

- [Git reader](../src/mos_eisley/git_review.py), CodingVCS and associated tests.
- [Scope contract](GIT_REVIEW_SCOPES.md), [plan](mos-eisley-plan.md#317-direct-review-scope-selection).
- AGENTS.md, engineering and verification guides, threat model and work-note templates.
- [Git worktree layout](https://www.kernel.org/pub/software/scm/git/docs/git-worktree.html).

## Verification budget and stop rules

Three evidence-producing passes: admission implementation; fault/consumer tests;
combined verification and publication. Four hours active engineering plus the
normal sequential full gate. Stop expansion on unsafe topology or an unresolved
identity ambiguity; fail closed rather than follow arbitrary redirects. No paid
providers or production writes. Record failures and final gate results below.

## Observations and attempts

- At entry, CodingVCS created standard linked worktrees while the reader required
  a `.git` directory. No durable Mos issuance registry is present or required for
  read-only owner-controlled admission.

- Admission implemented in a separate bounded metadata module; shared Git config,
  refs and objects remain distinct from worktree-local HEAD/index. The creator
  checkout also must protect its `.git` entry against other writers.
- Initial test fixture errors (missing first session save and treating admin log
  directories as files) were corrected; no production relaxation was needed.
- Focused Git scope/range/worktree batch: 61 tests passed before the final two
  replacement/final-boundary cases. Final managed-worktree suite: 20 passed in
  24.838 seconds. Scoped live connection: 10 passed in 50.250 seconds.
- Ruff/format and strict Pyright passed. The combined sequential `make check -j1`
  completed with exit 0; final source and wheel evidence follows below.
- Full source gate passed: 3,853 tests in 3,010.803 seconds, 17 platform skips,
  86% coverage (84% required). Export verification and source/wheel builds passed.
- Installed-wheel suite passed: 2,831 tests in 2,072.095 seconds, 13 platform skips.
  All 413 packaged Python files match the tested source bytes exactly.
- Qualified wheel: `mos_eisley-0.1.0rc5-py3-none-any.whl`; SHA-256
  `25ccb0d0aede1e7dae35f7158dcefe80984017bf7fe49a306f7c91aa594ea193`.
  Disposable full output remains outside Git at
  `/private/tmp/mos-managed-worktree-check.log`. No code changed after the gate.

## Handoff / completion

Managed-worktree read admission and local macOS source/installed-wheel
qualification are complete. A real CodingVCS stage remains eligible for its
separately authorized exact integration after review; review itself neither edits
nor integrates. Shared consumers retain existing admission, quorum, budgets,
cancellation and read-only authority. Ordinary schema-1 scope bytes remain stable.

The scope contract, project plan, roadmap and evidence-linked project memory now
record this boundary. Native Linux/Windows-hosted WSL2 and exact new live-target/
release qualification remain independent gates. These synthetic/local checks do
not provide accountable production or security approval, or qualify new paid
provider targets. No real credentials, providers or sampling stores were used.
