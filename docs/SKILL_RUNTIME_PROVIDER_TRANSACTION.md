# Skill runtime provider transaction

Mos Eisley can now redeem one ephemeral skill-runtime capability into one
provider-owning, pre-reserved OpenAI transaction. The transaction has no token-count,
reservation, retry, or automatic-release path: preparation already reserved the
worst-case exposure, and execution can only settle that exact ledger entry.

## Durable before-send boundary

Broker-grant policy schema version 2 pins one pre-created provider-transaction-store
policy. That policy pins the grant-store identity, both control anchors, current
default store, spend ledger, transaction capacity, response-publication policy, and a
provider wait of at most 60 seconds. A different local store cannot accept the bearer
lineage.

Before redemption, execution checks the exact prepared request, provider and broker
request hashes, model, spend policy, reservation, issuance, OpenAI provider identity,
and a transport-declared retry count of zero. It then holds read guards on:

- the latest routing control;
- the latest skill release control;
- the current skill default;
- the exact held ledger entry; and
- the exact durable broker-grant issuance.

Under those guards, the in-memory bearer is redeemed and burned. A private
rollback-journal SQLite store then commits the exact send intent using
`synchronous=EXTRA`. The provider transport is not invoked until that commit returns.
If intent commit fails, no request is sent, the bearer stays consumed, and the
reservation stays held. There is deliberately no recovery retry.

The intent store contains hashes and provenance only. It never stores the bearer,
prompt, provider credential, request body, or response body.

## One invocation and conservative settlement

After the marker, execution makes one call with the exact prepared request and fixed
`store=false`, `truncation=disabled`, and `service_tier=default` controls. Its own
timeout bounds how long Mos Eisley waits even if the credential-owning transport has a
longer timeout. The production OpenAI transport declares OpenAI identity and constructs
the official SDK with `max_retries=0`.

Outcomes settle the existing reservation as follows:

| Observed result | Ledger result | Returned result |
| --- | --- | --- |
| Valid model, tier, and bounded usage | `settled` at computed actual cost | Exact response plus hash-only intent/outcome metadata |
| Missing/invalid usage, provider error, timeout, cancellation, or lost response | `uncertain` at the full reserved amount | No provider response |
| Model, tier, token, or price assumption violated | `violation` at the full reserved amount and ledger blocked | No provider response |

The ledger commits before the outcome record. If ledger settlement fails, the durable
before-send marker remains with the reservation held. If outcome commit fails after
ledger settlement, the ledger remains conservatively accounted and recovery reports
the marker without guessing an outcome. Every status has `retry_permitted=false` and
`automatic_budget_release_authorized=false`.

## Read-only recovery CLI

The CLI can create and inspect the metadata store but intentionally cannot import an
API key, redeem a bearer, or send a request:

```console
mos skill-runtime-provider-transaction-store-create \
  --path private/runtime-provider-transactions.sqlite \
  --provider-transaction-store-policy trusted/provider-transaction-policy.json \
  --broker-grant-store private/runtime-broker-grants.sqlite \
  --routing-control-anchor private/routing-control.sqlite \
  --skill-control-anchor private/skill-control.sqlite \
  --default-store private/skill-default.sqlite \
  --spend-ledger private/spend.sqlite

mos skill-runtime-provider-transaction-status \
  --issued-broker-grant private/issued-broker-grant.json \
  --broker-grant-store private/runtime-broker-grants.sqlite \
  --provider-transaction-store private/runtime-provider-transactions.sqlite \
  --spend-ledger private/spend.sqlite
```

Recovery distinguishes absent, durable-before-send, and finished states and
correlates any outcome with the exact ledger state. A missing outcome after the marker
is ambiguous by design, never permission to retry.

## Deliberate limits

Transport declarations and Python module privacy are controls against accidental
composition, not containment of malicious code already running in the trusted host.
Credentials, process memory, same-UID inspection, clocks, database rollback/cloning,
filesystem durability, provider idempotency, and external billing reconciliation
remain trust boundaries. Durable content-verified response/result publication is
implemented as a separately pinned store; credentialed OpenAI conformance remains
future work.
