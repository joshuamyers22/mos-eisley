# G4 one-human formal review exception: threat model

- System/version: exact `f54e815` G4 carry-forward review; exception schema 1.
- Owner: Joshua Myers. Trigger: owner request for one human operator.
- Scope: governance evidence only. No provider call, Git integration, or release.
- Selected guide: `templates/THREAT_MODEL.md`.

| Asset | Integrity need | Owner |
|---|---|---|
| Final-suite receipt and integrated Git tree | Exact replay and no substitution | G4 controller |
| Critic, judge, and spending audits | Retain failed calls and settled charges | G4 review broker |
| Owner-signed decision and exception | Bind exact subject, record, and ADR | Joshua Myers |

| Abuse case | Control | Residual risk |
|---|---|---|
| Reuse a passing review for another commit | Exception checks full revision, subject hash, record hash, and ADR hash | Owner may still approve the wrong scoped change |
| Claim independent human review from one signer | Both records retain false independence flags; original gate remains unmet | Readers may overlook the exception wording |
| Treat model output as a signed external assessment | Exception only accepts owner-attested observations; private verifier replays retained live audits | Provider operation does not prove correctness |
| Hide failed provider calls or cost | Existing audit and ledger verification remain required and unresolved holds remain visible | Uncertain holds may need later reconciliation |
| Sign with another key or alter the amendment | Enrolled creator signature, domain separation, canonical artifact, and no overwrite | Compromised owner key can still approve |
| Turn review evidence into release authority | Exception and review record both deny acceptance, merge, release, and new calls | A separate downstream process must honor the denial |

The exception is retrospective and exact-run scoped. The signed artifact is required
before this alternative formal implementation-review requirement can pass. Future
commits retain the original independent-review contract unless separately amended.
