# Work note: dependency PR CI repairs

- Status: active
- Owner: Codex, under the owner's instruction to fix and merge open PRs
- Started: 2026-11-01
- Selected guidance: `templates/WORK_NOTE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`
  and `templates/AGENTIC_VERIFICATION_LOOP.md`.

## Objective and completion evidence

Repair PRs #347, #348, #350 and #351 while retaining their requested dependency
versions and all existing quality gates. This is routine, reversible development
configuration work; it adds no runtime feature or platform support claim.
Completion requires synchronized lock/export versions, one combined `make check`,
and passing GitHub checks before merging. Limit implementation to the observed
failures; investigate new failures rather than bypassing checks. Allow up to three
repair passes and one complete CI cycle per unchanged revision.

## Context retrieved and observations

- `README.md`, `PROJECT_BRIEF.md` and `PROJECT_MEMORY.md` retain the existing
  platform qualification boundaries.
- Failed source jobs for #348, #350 and #351 passed their tests, then failed
  `tools/verify_export.py`: Dependabot changed `requirements.runtime.txt` without
  upgrading `uv.lock`. Repair the lock to the requested version, then regenerate
  and verify the export.
- The #347 WSL2 job failed in Pyright's implicit Node installation. The bootstrap
  installed no Linux Node, and the qualification deliberately restricts PATH.
  Install Ubuntu's `nodejs` package and check `node --version` under that same PATH
  before qualification. Actual Windows-hosted CI remains the acceptance check.

## Verification

- Focused checks: runtime export verification for each dependency branch; existing
  qualification tool tests and static checks for the WSL2 bootstrap branch.
- Combined quality gate and GitHub check results are recorded by the merge commits
  and their associated Actions runs.
- No changes to credentials, spending, platform admission or release authority.
