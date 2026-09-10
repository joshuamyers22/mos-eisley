# Independent skill runtime dispatch authority

Mos Eisley can independently authorize and durably consume one admitted skill-runtime
request. The result is eligibility to issue one future request-bound broker grant. It
is deliberately not that grant, is not a bearer capability, contains no prompt or
credential, opens no network connection, and sends nothing.

## Authority and exact binding

A pre-created dispatch-claim-store policy pins the admission store, routing-control
anchor, skill-control anchor, default store, and spend ledger. The signed dispatch
policy schema version 2 pins that store policy, the runtime-preparation authority
policy, and the complete pre-created broker-grant-store policy. Its Ed25519 identities
and keys must be disjoint from runtime-preparation authorities.

The short-lived decision binds:

- the exact stored admission, prepared request, signed runtime decision, and runtime
  request;
- the selected route plus normalized provider-request and broker-request hashes;
- the spend ledger, existing entry, and worst-case reservation; and
- the exact routing-control entry, skill-control entry, and default pointer.

The maximum decision lifetime is 60 seconds. Signature verification is
domain-separated and command-line paths never accept a private key.

## Consumption boundary

Before consumption, Mos Eisley reconstructs the complete routing and skill evidence
graphs and verifies the exact stored admission and held reservation. At the local
commit point it holds read guards on both controls, the current default pointer, the
held spend entry, and the immutable admission record. A private rollback-journal
SQLite store then inserts one claim with unique constraints on the dispatch decision,
signed decision, admission, and ledger entry.

A replay fails closed. A stale control, changed default, settled reservation, wrong
store policy, expired decision, invalid signature, or database error creates no
claim. Database failure does not change the admission or spend hold.

```console
mos skill-runtime-dispatch-claim-store-create \
  --path private/runtime-dispatch-claims.sqlite \
  --dispatch-claim-store-policy trusted/dispatch-claim-store-policy.json \
  --admission-store private/runtime-admissions.sqlite \
  --routing-control-anchor private/routing-control.sqlite \
  --skill-control-anchor private/skill-control.sqlite \
  --default-store private/skill-default.sqlite \
  --spend-ledger private/spend.sqlite

mos eval-derive-skill-runtime-dispatch \
  --dispatch-claim-store-policy trusted/dispatch-claim-store-policy.json \
  --dispatch-authority-policy trusted/dispatch-authority-policy.json \
  --issued-at 2026-09-06T12:00:00+00:00 \
  --valid-until 2026-09-06T12:00:30+00:00 \
  --output private/dispatch-decision.json \
  ...the exact runtime, admission, routing, skill, and spending sources...

# Sign dispatch-decision.json outside the CLI with an enrolled independent key.

mos eval-consume-skill-runtime-dispatch \
  --signed-dispatch-decision private/signed-dispatch-decision.json \
  --dispatch-claim-store private/runtime-dispatch-claims.sqlite \
  --output private/dispatch-claim.json \
  ...the exact runtime, admission, routing, skill, and spending sources...
```

The read-only status command reports absent/consumed and the current ledger state.
All artifacts and events structurally record that no broker grant was issued, direct
provider dispatch remains unauthorized, no request was sent, and neither retry nor
automatic budget release is permitted.

## Deliberate limits

The consumed claim is not accepted by any transport. A guarded
[ephemeral broker-grant exchange](SKILL_RUNTIME_BROKER_GRANT.md) can now consume it
into one memory-only bearer, but redemption still does not send. The provider-owning
[pre-reserved transaction](SKILL_RUNTIME_PROVIDER_TRANSACTION.md) can now burn that
bearer into a durable before-send marker, exclusively settle the existing reservation,
and treat timeout, cancellation, crash, and lost response conservatively without
automatic retry or release.

Local clock integrity, authority-policy distribution, key custody, same-UID access,
database copying/rollback, and organizational independence remain trusted boundaries.
