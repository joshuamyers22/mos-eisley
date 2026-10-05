# G4 initial-child one-human exception: threat model

- Scope: exact `d7237f5` initial-child implementation review and ADR-0010.
- Owner: Joshua Myers. Trigger: one human signer for the formal review gate.
- Selected guidance: `templates/THREAT_MODEL.md`, `templates/WORK_NOTE.md`,
  and the existing G4 one-human exception contract.

| Asset | Integrity need | Owner |
| --- | --- | --- |
| Signed final-suite and Git lineage | Exact replay, no substitution | G4 controller |
| Critic, judge, and spend audits | Retain all calls and failed attempts | Review brokers |
| Owner decision and exception | Exact subject, ADR, and key | Joshua Myers |

| Abuse case | Control | Residual risk |
| --- | --- | --- |
| Reuse acceptance for another commit | Bind revision, subject, record, and ADR digest | Owner can still approve the wrong scoped claim |
| Claim independent human review | Both records retain false independence flags | Readers may mistake provider diversity for human independence |
| Treat model output as external attestation | Replay signed owner observations and private live audits | Provider use does not prove correctness |
| Hide failed Anthropic count or charge | Keep the old blocked ledger and failed claim visible | Provider billing needs separate evidence |
| Alter amendment or sign with another key | Canonical bytes, enrolled creator signature, and no overwrite | Owner key compromise |
| Turn exception into release authority | Explicit denial of acceptance, merge, release, and calls | Downstream process must enforce the denial |

The exception is retrospective and exact-run scoped. The original independent
human review gate remains open.
