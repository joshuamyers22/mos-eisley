# Threat Model: G4 bounded correction-cycle evidence gate

## Scope and ownership

- System/version: offline G4 correction schema 1 and worker observation schema 2.
- Owner/reviewers: Joshua Myers; implementation and self-review by Codex.
- Date/review trigger: 2026-09-24; revisit before production child dispatch.
- In scope: failed candidate evidence, signed triage and creator approval, one-use
  cycle claim, aggregate allowance, renewed-chain completion.
- Out of scope: real model/child dispatch, credential custody, provider usage,
  actual spending settlement, final acceptance.

## Assets, actors and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Frozen reviewer package and failed-test identities | private | exact and bounded | controller |
| Candidate claims and correction-cycle store | private | one-use, durable, no overwrite | controller |
| Judge/creator signatures and trust policies | authority-bearing | exact role, domain and current window | human operator |
| Git source and corrected binding | source integrity | clean exact revision and lineage | repository owner |

Actors are the creator, judge, coding child, controller and potentially hostile
reviewer test code. Signed artifacts cross into the controller; the isolated
worker returns count/ID evidence; the controller reads Git through the existing
fixed-argv broker. Same-UID host processes, store selection, local time, trusted
Git/Docker/image and physical key custody remain outside this software proof.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Control/evidence | Residual risk |
|---|---|---|---|---|
| Fake or stale failure | altered receipt or source | needless correction | claim replay, current Git, two distinct runs and exact failed IDs | trusted worker/container |
| Oracle/test defect relabeled as code defect | wrong adjudication | wrong repair | signed full-ID disposition, clause/citation/violation hashes; deny non-code routes | semantic review remains human |
| Forged judge or creator | key substitution | false cycle | enrolled key, domain-separated signature, exact policy/window | physical key custody |
| Replay or extra cycle | duplicate task/cycle | unbounded repair | `O_EXCL` private claim, persisted completion, schema cap two | alternate store or same-UID attacker |
| Budget reset | new revision/task state | excess allocation | fixed signed task ceiling, carried reservations and deadline | actual usage needs external ledger |
| Scope/test mutation | changed package or child grant | weakened oracle | renewed creator/custody/Git chain, exact reviewer test bytes and adapter/static inputs | creator-test blobs and arbitrary dynamic Python semantics are not compared here |
| Host escape/data exfiltration | hostile tests | secrets or writes | existing no-mount, no-network container and no host fallback | Docker/image integrity |
| Partial claim/completion write | crash | unavailable cycle | fsync and fail-closed existing file | operator recovery needs inspection |
| Critic artifact substitution | forged critic hash | false judge context | judge signs critic hash | critic quorum/authenticity not yet verified here |

## Decisions

- No production correction dispatch or acceptance is enabled by this slice.
- Failures with errors, mismatched IDs, non-implementation dispositions, stale
  provenance, changed tests or exhausted allowances stop the cycle.
- Required before production: accountable owner review, actual signer custody,
  authenticated critic/judge evidence, measured aggregate spend, final whole-suite
  and independent implementation review. Clean wheel smoke passed for this slice.
