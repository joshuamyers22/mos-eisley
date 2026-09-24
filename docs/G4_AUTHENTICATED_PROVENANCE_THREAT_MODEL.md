# Threat Model: G4 authenticated custody and VCS/E2 provenance

## Scope and ownership

- System/version: Mos Eisley from `2f02080d62b4b0b1e26d264a52adba47c248151f`.
- Owner/reviewer: Joshua Myers; implementation and adversarial self-review by Codex.
- Date/review trigger: 2026-09-24; repeat for any policy, signature domain, Git argv,
  binding replay, path-scope or final-record schema change.
- In scope: enrolled Ed25519 roles, exact creator/reviewer/child/VCS artifacts,
  read-only Git object reconstruction, bounded child ancestry/diff evidence and final
  immutable provenance record.
- Out of scope: private-key generation/storage, physical identity, external time,
  actual child/provider dispatch, correction, final acceptance and Git writes.

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner/boundary |
|---|---|---|---|
| Creator approval and tests | private review evidence | exact approved plan/test/interface/rubric/base identities | creator / signed creator artifact |
| Frozen reviewer package | private blind oracle | exact package bytes and reference linkage | reviewer / signed custody artifact |
| Child assignment/result | private task/evidence | exact scope, budget, child and commit/diff lineage | creator + child / separate signatures |
| Git repository | source integrity | exact commit/tree/blob and clean-worktree reconstruction | owner / fixed read-only broker |
| Final provenance record | private governance evidence | canonical replay and no overwrite | owner / mode-0600 artifact |

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| Signature or role replay | attacker has another valid artifact/key | fabricated custody | artifact-specific domains, exact policy/scope hashes and enrolled-role checks | signature/role substitution regressions | policy/key custody external |
| Single operator mislabeled independent | schema-2 operation | false assurance | shared operator only with explicit self-review risk and no independence claim | single-operator fixture and distinct-child rejection | no second human review |
| Git alias/config/hook executes | hostile local repository config | host effect or false output | absolute executable, fixed argv, no shell, minimal environment, hook/diff/attribute/fsmonitor overrides, bounds | malicious fsmonitor fixture never executes | Git binary and OS trusted |
| Replacement ref, dirty tree or untracked source substitutes bytes | mutable local repository | wrong code attested | no replacement objects, exact/final HEAD, raw blob replay, full inventory and clean status | dirty/untracked/wrong-HEAD regressions | same-UID race-and-restore remains possible |
| Cosmetic or unrelated child satisfies E2 | misleading signed assignment/result | false delegation claim | distinct child key, positive budgets, meaningful flag, exact owned paths, ancestry and actual full patch | disposable three-commit Git fixture | meaningfulness remains human-reviewed |
| Child edits creator tests | incomplete or overlapping scope | oracle weakening | signed complete sorted test inventory, disjoint owned paths, actual changed-path subset | overlap/out-of-owned regressions | completeness is an accountable signed claim |
| Malicious or oversized input | untrusted artifact bytes | denial or parser ambiguity | 8/32 MB caps, canonical JSON and duplicate-key rejection, bounded Git output/time | duplicate/noncanonical regressions | large valid repos may be rejected |
| Provenance mistaken for permission | downstream ignores boundary | unauthorized effects | every dispatch/write/network/provider/correction/acceptance field false | full-record/CLI assertions and existing launch gate suite | downstream must re-enforce |

## Decisions

- Single-operator human custody is permitted only under ADR-0005 semantics; the child
  identity/key remains distinct.
- Git executable/objects, local host and same-UID filesystem remain trusted. The
  record authenticates enrolled keys and bytes, not people or chronology.
- No private signing key is accepted by the production CLI.
- Recovery is fail-closed: discard the incomplete output, restore a clean exact
  revision and create new signed artifacts; records are never overwritten.
