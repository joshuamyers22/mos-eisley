# Threat model: distinct coupon allocation G4 task

## Scope and ownership

- System: private coupon allocation task and G4 connected initial-to-correction path
- Owner and accountable signer: Joshua Myers
- In scope: task inputs, frozen tests, provenance, offline execution, isolated Git,
  spend boundary, and defect triage
- Out of scope: public release, merge, activation, and unsanctioned provider calls

## Assets and boundaries

| Asset | Integrity need | Owner |
|---|---|---|
| Approved plan, base commit, protected creator tests | Exact hashes and clean Git | Joshua |
| Frozen reviewer package and known controls | No post-freeze oracle or adapter change | Joshua |
| Child and owner signing keys | Distinct role signatures and private files | Joshua |
| Shared spend ledger and provider grant | One exact call, conservative hold, settlement | Joshua |
| Isolated integration and candidate receipts | One-use claims, scoped source, replayable tests | G4 controller |

## Abuse cases and controls

| Abuse case | Control | Remaining limit |
|---|---|---|
| Stale or substituted plan, tests, or Git tree | Creator approval, frozen package, binding and Git replay | Owner must review task meaning |
| Child source outside scope or malformed output | Owned-path validation and contained proposal replay | Valid source can still be wrong |
| Duplicate dispatch or overspend | Private one-use claims, exact live grant and shared ledger | External billing reconciliation remains separate |
| Credential disclosure | Hidden local key prompt and no credential in task files | Owner device custody remains external |
| Misbound reviewer test or false failure | Direct adapter allowlist, known-good/bad controls, exact counts | Oracle correctness still needs human review |
| Manufactured defect or passing result called correction evidence | Two independent authorized assertion reproductions and signed triage | A passing candidate closes this attempt |
| Host write or acceptance from narrow grants | Separate signed Git, test, review, and acceptance gates | G4 completion needs all gates |

## Decisions

The task uses single-operator mode and claims no independent human review.
Joshua must sign each owner gate. A passing candidate, invalid proposal,
collection error, changed evidence, or unresolved ledger entry stops the
correction path. No live call is permitted without an exact, current one-use
grant and local credential entry.
