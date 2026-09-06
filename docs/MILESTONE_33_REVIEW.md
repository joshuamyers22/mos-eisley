# Milestone 33 adversarial review: one-use skill runtime preparation

## Disposition

Accepted as a crash-conservative preparation and spending-admission substrate. It is
not accepted as provider dispatch authority.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Separate claim and budget databases commit only halfway | The deterministic spend-ledger insert is both authority consumption and reservation | Whole-ledger rollback/cloning needs an external witness |
| Default or release control changes during admission | Verified control/default read locks remain held across the ledger commit | They may advance immediately afterward; dispatch must recheck |
| A nearby prompt, model, or effort is substituted | Installed bytes reconstruct the exact `PromptAsset`; complete route equality, registry identity, and no-substitution resolution are required | Routing source chain is signer-attested in this slice |
| Provider counting occurs before authority consumption | Worst-case policy input tokens are reserved locally with no provider call | This can over-reserve significantly |
| Crash after consumption silently permits retry | Read-only status exposes absent/held/settled/uncertain/violation and always denies retry or automatic release | Operator recovery remains manual |
| Existing broker accidentally sends the prepared request | Preparation issues no capability and sets sent/dispatch fields to false; current transport cannot consume the reservation | A new pre-reserved broker settlement path is required |
| A runtime signer self-approves upstream evidence | Runtime authority identity/key must be disjoint from every upstream health, control, promotion, installation, default, and evaluation authority | Organizational identity and collusion remain external |
| Request contents leak through ordinary output | Prepared artifacts use private writes and events emit only digests/amounts | Same-UID access and explicit file sharing remain trusted |

## Follow-on requirement

Implement a request-bound broker that accepts only this prepared artifact, reverifies
the complete routing source chain and latest routing/skill controls under commit guards,
consumes the already-held ledger entry without reserving again, records admission before
send, and conservatively settles response, failure, timeout, and cancellation. No
automatic retry may cross an ambiguous send boundary.
