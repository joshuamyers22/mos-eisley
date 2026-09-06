# Milestone 34 adversarial review: routing lineage and broker admission

## Disposition

Accepted as non-sending, one-use broker-readiness evidence. Rejected as provider
dispatch authority.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A caller fabricates a current-looking routing receipt | Runtime preparation and admission recompute the complete routing evidence and signature graph | Retained source authenticity still depends on the enrolled signers |
| Runtime signer overlaps a routing evaluator or controller | Runtime identities and keys are checked against both skill and routing graders, resolvers, promoters, and activation authorities | Organizational collusion remains external |
| Routing or skill control advances during local admission | Read locks on both exact latest anchors span the admission commit | Either control can advance after commit; dispatch must recheck |
| Reservation settles or changes during admission | The exact held ledger entry is read-locked through the admission commit | A later dispatcher needs exclusive settlement ownership |
| Admission accidentally reserves a second time | Admission performs no spend-ledger insert; tests require the snapshot to remain identical | The existing generic transport still double-reserves and remains prohibited |
| One prepared request is admitted repeatedly | Deterministic and unique prepared, decision, and ledger identities fail closed in the pinned store | Copying the same store identity requires an external monotonic witness |
| A different admission store accepts the decision | The signed runtime policy pins the complete pre-created store policy | Same-policy database cloning remains external |
| An admission is mistaken for send permission | Every store policy, record, status, and CLI event structurally denies a grant, dispatch, send, retry, and automatic release | Independent dispatch authority and a capability broker remain future work |

## Follow-on requirement

Implement an independently authorized dispatcher that atomically consumes one admitted
record into one short-lived request-bound capability, rechecks both control planes and
held spend immediately before external transfer, records the ambiguous send boundary,
and conservatively settles every outcome without retry.
