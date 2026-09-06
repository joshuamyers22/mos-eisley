# Ephemeral skill runtime broker grant

Mos Eisley can now exchange one exact consumed dispatch-authority claim for one
short-lived, request-bound bearer. Issuance remains provider-independent: it reads no
credential, exposes no request body, opens no network connection, and sends nothing.

## Pinned and durable issuance

Dispatch-authority policy schema version 2 pins a pre-created broker-grant-store
policy. That store policy pins the dispatch-claim store, admission store, routing and
skill control anchors, default store, and spend ledger. A different issuance store
cannot accept the signed authority.

Before issuance, Mos Eisley reconstructs the complete routing and skill lineages,
signed runtime preparation, exact admission, signed dispatch decision, and consumed
claim. The commit holds read guards on:

- the latest routing activation control;
- the latest skill release control;
- the current skill default pointer;
- the exact held spend reservation;
- the exact stored broker admission; and
- the exact stored consumed dispatch claim.

The private rollback-journal store uniquely records the dispatch decision, dispatch
claim, admission, ledger entry, and a domain-separated hash of the random 256-bit
capability. It never stores the bearer secret or request body. If the durable commit
succeeds but the in-memory bearer is lost, another bearer cannot be minted.

## Memory-only bearer

The bearer lives in a `SkillRuntimeBrokerCapability` object for at most 30 seconds and
is capped by the signed dispatch decision's remaining lifetime. Its representation
redacts the secret, and ordinary callers cannot reconstruct the object to reset its
latches. The object delivers one `BrokerClaim` containing only the secret,
broker-request hash, and issuance hash. Module-private state is not a security boundary
against malicious code already running inside the trusted host process.

Verification and durable-commit time count against the capability lifetime. If the
window expires after the issuance record commits, no bearer is returned and durable
uniqueness prevents replacement.

Redemption checks all three fields with a generic failure, burns the capability under
a process-local lock before returning, and returns only the durable issuance metadata.
It does not return request bytes or invoke a transport. Malformed or substituted
claims do not consume the valid bearer; a valid claim can succeed only once.

The CLI intentionally cannot issue or export the bearer because process exit would
destroy its fail-closed state or require persisting the secret. It can create and
inspect the hash-only durable store:

```console
mos skill-runtime-broker-grant-store-create \
  --path private/runtime-broker-grants.sqlite \
  --broker-grant-store-policy trusted/broker-grant-store-policy.json \
  --dispatch-claim-store private/runtime-dispatch-claims.sqlite \
  --admission-store private/runtime-admissions.sqlite \
  --routing-control-anchor private/routing-control.sqlite \
  --skill-control-anchor private/skill-control.sqlite \
  --default-store private/skill-default.sqlite \
  --spend-ledger private/spend.sqlite

mos skill-runtime-broker-grant-status \
  --signed-dispatch-decision private/signed-dispatch-decision.json \
  --dispatch-authority-policy trusted/dispatch-authority-policy.json \
  --broker-grant-store private/runtime-broker-grants.sqlite \
  --spend-ledger private/spend.sqlite
```

Status reports only absent/issued and the ledger state. It cannot recover a bearer and
always denies direct provider dispatch, send, retry, and automatic budget release.

## Deliberate limits

Redemption is not a provider-send event. The next provider-owning transaction must
accept the exact issuance and prepared request, recheck current controls and held
spend, durably record intent before the first operation that might transfer data,
consume the already reserved amount without reserving again, and conservatively
settle response, rejection, cancellation, timeout, crash, and lost-response states.
No missing outcome may authorize retry or budget release.

Capability delivery still requires a private authenticated channel. Process memory,
same-UID inspection, clock integrity, database rollback/cloning, and host compromise
remain trusted boundaries.
