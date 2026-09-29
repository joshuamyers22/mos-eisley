# Threat Model: G3 applicability decision for one G4 correction run

- System: exact G4 integrated commit `f54e815`; one-human owner decision.
- Selected guide: `templates/THREAT_MODEL.md`.
- Scope: quality-claim interpretation only; no study, provider call, or release.

| Asset | Integrity need | Owner |
|---|---|---|
| Approved task plan and integrated Git revision | Exact task and correction-only scope | G4 controller |
| Final suites and signed review | Replayable exact-run quality evidence | G4 controller |
| G3 applicability decision | Narrow, accountable, non-transferable scope | Joshua Myers |

| Abuse case | Control | Residual risk |
|---|---|---|
| Relabel one task as representative G3 utility | Explicit false G3-study and broader-claim fields | Readers may still overstate the result |
| Reuse determination for a changed commit or plan | Exact source, subject, plan, suite, review and ADR digests | Compromised host or owner key |
| Hide failed provider calls or uncertain spending | Replay of live audits and signed reconciliation | Console export scope depends on owner attestation |
| Treat model agreement as independent human review | ADR-0008 verifier retains false independence fields | Concentrated human authority |
| Turn scope decision into G4 acceptance | Separate owner decision remains mandatory; signed record denies acceptance | Downstream misuse of a non-authorizing artifact |

The decision is a scoped applicability finding, not a substitute for G3
empirical evidence whenever context, routing, savings or broader quality is
claimed. A future claim must reopen the G3 study rather than reuse this record.
