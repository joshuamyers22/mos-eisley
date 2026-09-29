# G4 correction integration architecture review

- Scope: new offline integration broker and tests on `feat/production-template-guidance`.
- Reviewer: Codex self-review; not independent production approval.
- North star: an exact signed child proposal becomes one replayable detached commit
  without mutating the user's original checkout or implying acceptance.
- Runtime: Python 3.12+, trusted fixed-argv Git, private same-UID controller store.

## Dependency and critical path

The write broker consumes the already claimed correction admission and signed
child-dispatch receipt. Its separate creator signature names the complete receipt
and exact changed paths. The prior candidate/custody/control/binding/Git chain
is replayed before the claim. Only then may the trusted broker create a private
detached worktree, write existing owned files, stage those paths and make a local
commit. Read-only replay checks original and integrated repositories; an external
enrolled VCS signer attests the record. Final tests and review remain downstream.

## Findings and disposition

| Severity | Evidence/consequence | Disposition |
|---|---|---|
| High | A proposal receipt deliberately denies repository writes | Added separate creator-signed exact integration approval |
| High | An approval-digest claim permits another approval for the same cycle | Claim keyed by task/cycle, spent before worktree creation |
| High | Checkout can trigger hooks, filters or unsafe tree entries | Disable hooks/config-dependent helpers and reject attributes, links and submodules; hook and attribute regressions |
| High | A local commit alone could hide extra changes or branch movement | Verify exact parent, paths, bytes, patch, clean worktree and unchanged original HEAD; replay source provenance |
| High | Unbound files in the original checkout could change during integration while HEAD and bound-source replay still pass | Added full original-checkout clean-status check after commit and during signed-record replay; regression mutates an unbound README |
| Medium/open | Trusted Git, host, local clock and signer custody remain outside cryptographic proof | Keep production activation gated; no hostile-host claim |
| Medium/open | A failed write can leave a partial detached worktree | Preserve claim/worktree for inspection; no automatic retry or deletion |

## Verdict

The offline bounded write/integration path is suitable for fixture testing after
the documented checks. Production release remains blocked on the measured provider
broker, independent review, final whole-suite gates and accountable owner approval.
