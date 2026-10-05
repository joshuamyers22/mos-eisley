# G4 protected remote storage anchor

Status: prospective design and fail-closed client boundary implemented; remote
service deployment and qualification remain open. Formal independent review is
on hold. Joshua requested protected storage, chose a remote service/store, and
delegated the backend choice on 2026-10-01. No trusted-local exception is assumed.

## Backend and protection boundary

Use an IAM-authenticated admission service backed by **AWS DynamoDB**. DynamoDB
supports atomic conditional transactions; IAM can restrict the underlying
transactional actions. See [transaction semantics](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)
and [transaction IAM controls](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html).
This is the chosen design, not evidence that an existing AWS deployment was found.

The task operator gets only admission-service access for its enrolled owner.
It gets no direct table write/delete/restore, signing-secret access, service-code
update, role-assumption or IAM-management permission that could bypass that
boundary. The service role gets the minimal transactional/read permissions.
Service administration is a distinct protected authority; an administrator
capable of replacing both the service and its trusted signing identity remains
outside the rollback-resistance guarantee. Keeping another restorable task-local
sidecar does not implement this protection.

Deployment requires an actual AWS account, region, deployment role, service
endpoint, protected signing-key custody and owner enrollment. None has been
verified or provisioned in this work. No cloud charges or writes occurred.

## Remote state and atomic admissions

| State | Required behavior |
|---|---|
| Enrolled owner | Bind authenticated service caller to a previously enrolled owner key. Never enroll from a self-asserted request or accept another owner's aggregate scope. |
| Aggregate scope | Pin owner, service identity, ceiling, current epoch, active/revoked status, cumulative held/charged amount and increasing sequence. The scope survives local ledger reset or copying. |
| Grant entry | Atomically create one entry for the exact signed grant digest and reservation hash/amount. Reject a duplicate even after local task state is restored. |
| Count stage | Atomically advance claim to count once, only while the owner/scope/epoch remains current and active. |
| Send stage | Atomically advance count to send once, rechecking current owner, cap, epoch and revocation. Never issue a second permit for a repeated request or nonce. |
| Epoch/control change | Invalidate old bindings, preserving cumulative holds and spent grant identities. A reset does not mint new budget or erase historical effects. |
| Timeout/unavailable state | Stop. An uncertain admission is spent locally and may already be committed remotely; never fall back to a local ledger or silently retry. |
| Reconciliation | Keep full remote exposure conservatively. Any release needs separate authenticated evidence and authority; this client implements no automatic release/reset. |

For a claim, one DynamoDB transaction must conditionally update the aggregate
scope and insert the absent grant. For count/send, condition the scope on current
epoch, active state and enrolled ownership and update the exact grant's prior
stage in the same transaction. Return a service-signed response bound to the
fresh nonce and exact request. Persist the response/admission evidence server-side
so an interrupted client cannot erase it. Disable transparent client retries.
One Region is the authoritative writer; do not infer cross-Region linearization
from regional transaction guarantees.

Revocation is ordered against atomic remote admission. A revocation before send
admission denies generation; a later revocation cannot undo an already admitted
in-flight effect. The service must document that commit boundary and retain
uncertainty rather than promise cancellation of an effect already admitted.

## Implemented client contract

[Protected anchor guard](../src/mos_eisley/run/protected_spend_anchor.py) requires
a separate enrolled-owner signature over the exact grant, ledger policy,
remote service/signing key, owner aggregate scope, epoch, ceiling and time window.
That binding authorizes metadata transfer only, not provider generation or spend.
Existing provider grants remain separately required.

The guard authenticates fresh service receipts, rejects changed nonce/request,
scope/epoch, sequence, window or aggregate amount, and retains the binding plus
claim/count/send audit records. An offline verifier checks the exact retained
stage identities and signatures. RPC admission gets a maximum ten-second
deadline, capped by the remaining original provider authority; a longer anchor
binding cannot extend that authority. The deployed adapter must enforce that
transport timeout with retries disabled. The
[initial-child broker](../src/mos_eisley/reviewer_initial_coding_broker.py) and
[correction-child broker](../src/mos_eisley/reviewer_coding_broker.py) require this
guard before local reservation and wrap both count and generation with remote
admission. Missing protection denies live dispatch before provider contact.

Historical grant and receipt schemas remain readable; their successful replay
does not claim protected-anchor qualification. Accepted dependency/duration
artifacts are unchanged. Old live scripts lacking the new protected binding
will stop; do not bypass this by installing the synthetic test fixture or minting
a local replacement service. Fresh live use needs a qualified remote deployment,
separate exact owner binding and provider authority.

Only digests, owner/scope identifiers, epoch, reservation amounts and nonces
cross this boundary. Prompts, creator/reviewer test bytes, model responses,
provider keys and task outcomes do not enter anchor records.

## Verification and remaining gate

[Synthetic boundary fixtures](../tests/test_protected_spend_anchor.py) demonstrate
the client contract against an enrolled, serialized service fixture kept outside
the disposable ledger. They cover copied/restored ledger replay, new client
instances, remote revocation, epoch change, owner/cap/grant substitution,
concurrent aggregate admission, outage/no retry, response substitution,
retained-audit tampering and missing-anchor denial in both live brokers.
They do not establish real DynamoDB persistence, IAM separation, network
authentication or deployed service behavior.

The remote gate remains open until the selected deployment supplies its exact
identity and proves those conditions with fault receipts, including service
restart, concurrent claims, client-state restoration, stale epoch, foreign owner,
revocation during count and uncertain service replies. The service signer key
must be separately enrolled in a fresh owner binding. Do not mark S1/S2/S4/S5
closed operationally based only on the synthetic fixture.
