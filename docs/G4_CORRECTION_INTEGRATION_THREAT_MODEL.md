# G4 correction integration threat model

## Scope and ownership

- System/version: offline G4 isolated correction integration, schema 1.
- Owner/reviewer: Josh Myers; Codex self-review is not independent release approval.
- Date/trigger: 2026-09-24; new repository/VCS write boundary.
- In scope: exact one-use creator grant, private detached worktree, Git commit and
  replayable VCS record. Out of scope: provider child, network, final suites,
  branch merge/push and acceptance.

## Assets, actors and boundaries

| Asset | Sensitivity and owner | Required property |
|---|---|---|
| Original checkout/branch | User-owned source | No write, move or history change |
| Frozen creator/reviewer tests | Creator/reviewer-owned | No child replacement or test weakening |
| Signed proposal/grant | Creator/child | Exact bytes, scope, deadline and one-use binding |
| Private integration store | Controller-owned | Exclusive claim and isolated worktree custody |
| Git objects/metadata | Trusted broker-owned | Only new detached worktree and commit writes |

Child output is untrusted. Creator and VCS signatures are checked against the
enrolled policy. Git executable, same-UID process, private store, local clock and
filesystem are trusted operational dependencies, not proven by a signature.

## Abuse cases and controls

| Abuse case | Impact | Control and evidence | Residual risk |
|---|---|---|---|
| Reuse cycle or substitute proposal | Unapproved write | Separate signed receipt-bound grant; task/cycle O_EXCL claim; no-link private-store open | Same-UID store tampering |
| Write original checkout or extra files | User-data corruption | New outside-repo worktree; no-follow owned-path writes; exact staged/final diff and original HEAD replay | Interrupted attempt leaves isolated partial state |
| Hook/filter or submodule execution | Arbitrary code | Fixed Git options; reject attributes, symlinks and submodules; hook regression | Trusted Git/config and host still required |
| Changed tests or source during operation | False evidence | Preflight chain, byte checks, clean trees and post-commit source replay | Concurrent same-UID races are not a hostile-host guarantee |
| Forge a successful integration receipt | False promotion | Enrolled VCS signature; reread commit, parent, tree, patch and blobs | VCS key custody external |
| Oversized or malicious tree | Exhaustion or unsafe checkout | 2,048-file/32-MB ceiling, canonical paths, no aliases | Large legitimate repositories unsupported |
| Network/provider or acceptance by implication | Unauthorized spend/result | No provider adapter; authority fields remain false | Future gates must not treat commit as acceptance |

## Decisions

- An interrupted claim/worktree is retained for manual inspection; no automatic
  retry, deletion or merge.
- Production activation requires accountable review, trusted key/host custody,
  measured broker spend and the remaining G4 final gates.
- Regression suite covers exact integration, one-use replay, bad grant, linked
  store, dirty original/worktree, unsafe attributes and disabled hooks.
