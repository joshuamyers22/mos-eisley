# Threat model: real initial-child G3 applicability

## Scope and ownership

- System: exact G4 initial-child commit `d7237f5` and its private evidence.
- Owner and reviewer: Joshua Myers, sole human signer.
- Trigger: G3 applicability is the next gate before a separate G4 creator decision.
- Selected guidance: `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`,
  `templates/WORK_NOTE.md` and `templates/ADR.md`.

## Assets and boundaries

| Asset | Boundary |
|---|---|
| Approved task plan, signed child/final receipts | Private owner files and pinned Git source |
| Critic, judge and formal exception evidence | Private owner files and exact replay |
| Failed count and successful review spending | Separate private SQLite ledgers and signed disposition |
| Applicability decision | ADR hash plus Joshua's domain-separated Ed25519 signature |

## Abuse cases and controls

| Abuse case | Control | Residual risk |
|---|---|---|
| Reuse correction-path decision | Exact initial source/subject/child/ADR identities | Owner can still misunderstand the narrow claim |
| Invent a G3 study pass from one task | Explicit false study, representative-quality and savings fields | No representative study exists |
| Hide failed count or confuse ledgers | Exact signed disposition, retained historical claim and separate settled review ledger | Console invoice for failed count was not checked |
| Treat model diversity as human independence | Explicit independent-human-review false flag and ADR-0010 scope | One-human concentration remains |
| Reuse signature for acceptance or provider use | Domain-separated decision; acceptance and dispatch fields false | Compromised owner or host |
| Substitute plan, commit or audit | Exact hashes, signed lineage and final-suite replay | Trusted-host compromise |

## Recovery

Stop on any missing receipt, changed hash, unresolved spend or failed replay.
Keep historical artifacts immutable. A changed claim or source requires a new
scope decision. Any broader G3 claim requires the actual sealed empirical study.
