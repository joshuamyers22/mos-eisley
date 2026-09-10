# Milestone 36 adversarial review: ephemeral broker capability

## Disposition

Accepted as a request-bound, single-redemption, memory-only broker capability.
Rejected as evidence that a provider request was sent or safely settled.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A consumed dispatch claim mints multiple bearers | A pinned grant store uniquely consumes the dispatch decision, claim, admission, and ledger entry | Cloned or rolled-back stores need an external monotonic witness |
| An attacker substitutes an issuance store | Dispatch-authority policy schema 2 signs the complete pre-created grant-store policy digest | Policy distribution remains trusted |
| Control, default, admission, claim, or spend changes during issuance | Full revalidation precedes read guards held on all six sources through the durable commit | Controls can advance after issuance and must be rechecked before send |
| The durable record leaks the bearer | It stores only a domain-separated capability hash; regression tests scan the SQLite bytes for the secret | Same-process memory and private IPC remain sensitive |
| A bearer is logged through object inspection | The capability representation is fixed and redacted | A caller can still mishandle the explicitly delivered `BrokerClaim` |
| A copied bearer is redeemed repeatedly | Exact capability, request, and issuance hashes are compared and a lock burns valid redemption before return | Process restart cannot restore bearer state, deliberately preventing retry |
| A caller reconstructs the capability object to reset its latch | Construction requires issuer-private state; only the explicitly delivered claim crosses the intended private channel | Python module privacy does not contain malicious code in the trusted host process |
| Malformed input burns the legitimate bearer | Malformed and mismatched claims fail before the redemption latch changes | Repeated invalid attempts are not rate-limited locally |
| Commit succeeds but bearer delivery is lost | Durable uniqueness prevents reissuance; status reports issued without recovering the secret | Operator cannot distinguish delivered, redeemed, or lost without the future send audit |
| Verification or commit stalls through capability expiry | Monotonic elapsed time is deducted before returning; an expired committed issuance returns no bearer and cannot be retried | Clock and monotonic-source integrity remain host assumptions |
| The grant path silently reserves again | Every issuance guard checks the existing held entry and ledger snapshots remain unchanged | Provider transport must support pre-reserved settlement ownership |
| Redemption is mistaken for provider transfer | It returns only issuance metadata; no request bytes, credential, transport, socket, or provider call is reachable | Durable before-send and outcome settlement remain future work |

## Follow-on requirement

Build a provider-owning pre-reserved transaction that consumes the redeemed issuance,
records an fsynced before-send boundary, performs at most one exact request, and
settles the existing reservation conservatively. Cancellation, timeout, crash, or a
lost response must remain charged/uncertain and never imply retry.
