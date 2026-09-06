# Milestone 35 adversarial review: dispatch authority consumption

## Disposition

Accepted as independent, short-lived, at-most-once authorization for future broker-
grant issuance. Rejected as a bearer capability or permission to call a provider.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Runtime preparation self-approves dispatch | Dispatch signer identities and keys must be disjoint from runtime-preparation authorities | Organizational independence and collusion remain external |
| A valid signature is rebound to another request | The signature covers exact admission, preparation, route, request hashes, controls, default, ledger, and reservation | Signer custody and judgment remain trusted |
| A decision targets an attacker-chosen claim store | The signed policy pins the complete pre-created claim-store policy | Whole-database copying/rollback needs an external monotonic witness |
| Control or default changes between derivation and consumption | Both control anchors and the default pointer are reverified and read-locked through claim commit | They can advance after the local commit and before a future network send |
| Spend settles while authority is consumed | The exact held entry is reverified and read-locked through claim commit | Future bearer issuance and transport need exclusive settlement ownership |
| Admission is substituted or removed | Full admission provenance is recomputed and its exact stored record is guarded | Same-UID database replacement remains a trusted boundary |
| One admission is authorized more than once | Unique decision, signed-decision, admission, and ledger identities make consumption at-most-once | Cloned stores can fork local history |
| A failed claim insert burns spend or changes admission | Injected database failure rolls back the claim and leaves both earlier records unchanged and held | Earlier runtime authority remains consumed by design |
| The consumed claim is mistaken for a bearer | Types, store policy, claim, status, and CLI events deny grant issuance, direct dispatch, send, retry, and release | A separate exchange must mint the first bearer capability |

## Follow-on requirement

Exchange one exact consumed claim for an ephemeral single-use broker capability under
fresh control, default, admission, and spend guards. Then add a pre-reserved provider
transport with a durable before-send marker and conservative outcome settlement. No
path may infer retry or budget release from a missing response.

