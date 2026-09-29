# Threat model: initial-child creator acceptance

- Owner: Joshua Myers. Target: integrated commit `d7237f5` only.
- Boundary: records a narrow qualification decision; it grants no runtime action.
- Selected guidance: `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md` and
  `templates/WORK_NOTE.md`.

| Asset | Integrity need | Owner |
|---|---|---|
| Plan, child, Git, candidate and final suites | Exact signed source and passing evidence | G4 controller |
| Two-provider review and formal exception | Accepted live-audited result, explicit one-human limit | Joshua Myers |
| Initial and review spending | Settled exact entries, retained failed-call audit | Joshua Myers |
| Signed G3 applicability decision | No empirical or broader workflow claim substitution | Joshua Myers |
| Creator acceptance signature | Accountable exact owner decision | Joshua Myers |

| Abuse case | Control | Residual risk |
|---|---|---|
| Accept a changed source or weaker review | Bound digests and full read-only replay | Compromised host or owner key |
| Treat two path claims as full G4 acceptance | Explicit false combined-workflow and full-milestone fields | Readers may overstate scope |
| Misstate G3 or human independence | Signed ADR-0011 and ADR-0010, explicit false fields | One-human concentration remains |
| Hide a failed call or spend | Separate signed disposition and settled ledger replays | Console invoice for count-only call was not checked |
| Reuse signature for merge, release or spending | Domain-separated body, all authority flags false | Downstream users must enforce own gates |
| Sign without reviewing exact terms | Signer prints full document, canonical body and confirmation ID | Owner can still make an error |

Historical receipts and private provider responses remain unchanged. Any
broader qualification or deployment requires its own reviewed authority.
