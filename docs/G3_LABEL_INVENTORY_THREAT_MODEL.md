# Threat Model: G3 label inventory and context-policy seal

## Scope and ownership

- System/version: schema-1 G3 context-study contracts
- Owner and reviewers: Josh Myers; independent statistical/data review required
- Date and review trigger: 2026-09-21; revisit for schema, custody, rubric, sampling,
  signer or holdout-access changes
- In scope: offline signature verification, metadata eligibility, policy-arm sealing
- Out of scope: grader recruitment, physical independence, private case custody,
  provider execution, result scoring, promotion and routing activation

## Assets, actors, and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Private cases and held-out sessions | High | Must remain outside inventory/seal inputs | Josh Myers |
| Ground-truth label claims | High | Exact rubric/case binding and two valid signatures | Study owner and graders |
| Trust policy and public keys | High integrity | Independently distributed and reviewed | Josh Myers |
| Eligibility inventory and policy seal | Private | Deterministic, content addressed, mode 0600 | Josh Myers |

- Actors and capabilities: study owner authors policy; enrolled graders sign opaque
  label metadata; local operator runs offline verification; future executor is separate.
- Entry points and trust boundaries: bounded JSON files enter the CLI; Ed25519 verifies
  claims against a separately supplied trust policy; only aggregate metadata crosses
  into the policy seal.
- Data flows and external dependencies: local files and cryptography library only;
  no network, provider, session-store or holdout-dataset access.

## Abuse cases and controls

| Abuse case | Preconditions | Impact | Prevent/detect/respond controls | Evidence | Residual risk |
|---|---|---|---|---|---|
| One person impersonates two graders | Operator controls enrolled keys | False independence | Distinct IDs/keys required; accountable trust-policy review | Negative tests | Key separation cannot prove physical independence |
| Label or case is changed after grading | Mutable source | Wrong ground truth | Sign canonical claim bound to case/rubric digests | Tamper test | Digest does not prove source quality or custody |
| Held-out session leaks into inventory | Broad input contract | Tuning/leakage | Strict extra-forbid metadata schema; opaque case/group digests; no dataset/session CLI argument | Schema and CLI inspection | A signer or custodian can learn information outside this software |
| Selective labels disappear | Operator omits hard/unlabeled cases | Biased study | Catalog is content addressed; exclusions retained; probabilities required | Missing-probability tests | Completeness of the upstream sampling frame needs independent audit |
| Ablation is dropped after results | Mutable arm family | Biased comparison | Exactly one named ablation per target component, including unavailable arms | Policy tests | Implementation hashes need human source review |
| Outcome family or cost scope narrows | Post-hoc policy change | False savings claim | Fixed metric tuple, full cost rule, baseline-retention rule | Contract validation | Statistical adequacy still needs independent review |
| Seal is treated as execution authority | Operator misuse | Unauthorized study/spend | Literal false authority fields and no provider path | CLI round trip | External software can ignore the artifact |
| Replay, duplicate or substituted catalog/inventory | Reused or fabricated files | Stale or false eligibility | Content digests bind catalog, trust policy, inventory and seal; sealing replays every signature and eligibility decision | Provenance tests | No freshness/custody service exists yet |

## Decisions

- Accepted risks with owner and expiry: physical identity, upstream sampling-frame
  completeness and holdout custody remain owner-controlled claims until the empirical
  study receives independent review.
- Required tests and monitoring: signature/tamper, distinct-key, disagreement,
  unknown-probability, cross-split group, missing-label-class, arm-completeness,
  provenance and private-output tests.
- Incident and recovery dependencies: reject and replace the affected catalog,
  inventory and seal; never edit an existing receipt or reuse a consumed holdout.
