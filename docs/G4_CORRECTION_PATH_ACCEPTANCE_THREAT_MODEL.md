# Threat Model: final creator decision for one G4 correction path

- Selected guide: `templates/THREAT_MODEL.md`.
- Owner: Joshua Myers. Target: `f54e815` only.
- Boundary: records a narrow qualification decision; no runtime dispatch.

| Asset | Integrity need | Owner |
|---|---|---|
| Task plan, child, Git, suites and review | Exact source and passing evidence | G4 controller |
| Quality-scope decision | No G3 or full-workflow claim substitution | Joshua Myers |
| Final acceptance signature | Accountable exact owner decision | Joshua Myers |

| Abuse case | Control | Residual risk |
|---|---|---|
| Accept a changed commit or weaker review | Signed exact artifact digests and replay | Compromised host or owner key |
| Treat one correction task as full G4 qualification | Explicit false full-workflow and initial-child fields | Readers may overstate the result |
| Turn decision into release authority | Explicit false merge, release, activation and provider fields | Downstream process must enforce its own gate |
| Hide failed calls or spend | Replayed provider audits and signed reconciliation | Billing export scope relies on owner attestation |
| Sign without seeing scope | Signer prints this document and canonical body; exact confirmation ID | Owner can still approve mistakenly |

The signed record remains private, immutable and replayable. Any broader
qualification or deployment requires separate evidence and owner authority.
