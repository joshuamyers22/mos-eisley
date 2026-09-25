# G4 independent-review gate threat model

## Scope and ownership

- System/version: offline G4 signed implementation-review record, schema 1.
- Owner: Joshua Myers. Date: 2026-09-24. Trigger: new external critic/judge trust boundary.
- In scope: exact Git/plan/test lineage, role signatures, quorum, adjudication and replay.
- Out of scope: provider dispatch, raw provider identity proof, human independence,
  key custody, release approval, live spending and time attestation.

## Assets, actors and boundaries

| Asset | Sensitivity | Integrity/availability need | Owner |
|---|---|---|---|
| Approved plan, source patch and test receipts | Private source/evidence | Exact bytes and current Git replay | Project owner |
| Creator, critic and judge keys | Signing authority | Distinct custody, no key in CLI or repo | External custodians |
| Review record | Private result | Canonical, complete, non-overwriting | Project owner |

An untrusted artifact supplier can submit arbitrary JSON and files. An enrolled
critic or judge can sign an incorrect assessment. A same-UID host operator can
alter local files, clocks and stores. The verifier trusts only the configured
provenance policy and separately enrolled keys; it does not infer real provider
independence from different key labels.

## Abuse cases and controls

| Abuse case | Impact | Control/evidence | Residual risk |
|---|---|---|---|
| Substitute plan, source, tests or receipt | Wrong code accepted | Rebuild full subject from approved plan hash, trusted Git diff and complete final-suite replay | Compromised VCS/host trust root |
| Forge or reuse creator/child/critic key | False independent review | Domain-separated Ed25519 signatures; distinct roster IDs and keys; role disjointness | Colluding custodians or stolen keys |
| Hide failed critic or bypass quorum | Unsupported accept | Exact full roster, signed statuses, two completed critics from two families | Families are enrolled claims, not independently proven |
| Change critic findings before judge | Misadjudication | Judge signs ordered critic artifact hashes; deterministic finding-ID adjudication | Judge can reject a real finding with false rationale |
| Fabricate code evidence | False finding | Exact diff citation catalog and quote validation | Quote presence does not prove the claim |
| Replay an old positive decision | Stale acceptance | Current final-suite/Git/plan reconstruction and exact subject comparison | Same-UID compromise may alter local trust inputs |
| Embed credentials or exfiltrate data | Confidentiality loss | No network, key, provider or tool access in this gate; private mode-0600 output | External signers/providers require separate data policy |
| Oversized/malformed input or dependency failure | Denial of service or a positive verdict outside the approved request budget | Bounded regular-file reads, canonical JSON, bounded Git output, exact critic/judge request-size checks and no fallback | Review of >256 KB diff needs a separately designed protocol |
| Treat attestation as release | Unsafe deployment | `acceptance_authorized=false` and `independent_human_review_proven=false` | Operators must preserve downstream gates |

## Decisions

- No live call or release authority is implied by signed review evidence.
- No bypass for a large/binary/non-UTF-8 review subject; stop and design an
  independently reviewed larger-artifact protocol if needed.
- Production acceptance requires accountable external review and any applicable
  G3 quality gate. This agent's implementation is not that approval.
