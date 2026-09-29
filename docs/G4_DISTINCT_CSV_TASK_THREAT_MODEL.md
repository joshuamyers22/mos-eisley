# Threat model: distinct CSV G4 task

## Scope and ownership

- System/version: bounded CSV task setup and connected G4 authority chain
- Owner and reviewer: Joshua Myers, disclosed single-operator mode
- Date and trigger: 2026-09-28, new task after two passing initial candidates
- In scope: task bytes, source/test custody, child proposal, spending, isolated
  integration and candidate execution
- Out of scope: production activation, merge, release and G4 acceptance

## Assets, actors and boundaries

| Asset | Sensitivity | Integrity need | Owner |
|---|---|---|---|
| Plan, protected tests and frozen reviewer package | Private task evidence | Exact bytes and collection | Joshua |
| Child key and owner signing key | Signing authority | Owner-only custody and separate roles | Joshua |
| Provider key and spend ledger | Credential and money | One exact call, bounded hold and settlement | Joshua |
| Original and isolated Git trees | Source integrity | Approved base, owned path and clean replay | Joshua |

The provider returns untrusted source text. The enrolled child broker validates
and signs only an owned-file proposal. Creator, custody, dispatch, live-call,
integration, candidate, correction, final-suite, review and acceptance gates
remain separate. The reviewer adapter exposes only the declared parser symbol.

## Abuse cases and controls

| Abuse case | Impact | Control | Residual risk |
|---|---|---|---|
| Changed plan, tests, package or Git base | False result | Hash-bound signatures, clean Git and replay | Same human owns approvals |
| Malformed proposal or extra path | Unsafe integration | Canonical source validation and owned-path check | Semantic defects still possible |
| Duplicate or unauthorized provider call | Excess spend | Exact one-use grant, claim and shared-ledger hold | Provider billing may differ |
| Credential or source escape | Disclosure or mutation | Hidden key prompt, tool-free provider call, no-network worker, private files | Host operator retains access |
| Known-control or candidate collection failure | False defect | Exact counts, zero-error controls, receipt replay | Tests cover a bounded dialect |
| Manufactured implementation failure | Invalid qualification | Freeze plan/tests before child, stop on passing candidate, require two matching independent receipts and signed triage | Real tasks may simply pass |

## Decisions and recovery

Joshua's signatures are required at each authority boundary. A failed
diagnostic does not become a candidate receipt. Stop on stale source, invalid
signature, missing collection, unresolved ledger entry, exhausted allowance or
passing candidate. Retain signed evidence and do not reuse a consumed claim;
prepare a fresh task or grant after a terminal failure. No private key, provider
response or raw transcript belongs in the tracked work note.
