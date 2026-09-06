# One-use skill runtime preparation

Mos Eisley can now prepare one exact OpenAI text request from the current selected
persona without sending it. Preparation reconstructs the prompt from authenticated
installed bytes, binds an empirically selected model route and current skill-health
receipt, and burns a separately signed one-use decision into the shared spending
ledger. It does not create a broker bearer capability, open a provider connection, or
authorize dispatch.

## Transaction and trust boundaries

A runtime-authority policy pins the exact health-authority policy, default-store
policy, routing activation-authority and control-anchor policies, model registry,
spending-ledger identity, and broker-admission store policy. Runtime authority
identities and keys must be independent of every observer, policy signer, selector,
installer, controller, promoter, grader, and resolver in both complete lineages.

The signable runtime decision binds:

- one request identity and exact user input;
- the current default pointer, installed manifest, archive, persona identity, and
  reconstructed instruction body;
- provider, backend, model, reasoning effort, client version, registry, output limit,
  and candidate identity;
- the current skill-health eligibility and routing-preflight digests;
- the exact normalized provider-request and broker-request hashes;
- the reviewed spending policy, ledger identity, deterministic entry identity, and
  reservation digest; and
- a maximum 300-second validity window.

Before the commit point, the preparer reverifies the complete skill health and routing
lineages, both current controls, complete default history, installed archive, model
registry, route membership, signed runtime authority, request bytes, and spend ceilings. It
reserves the spending policy's full allowed input-token count plus the requested output
limit. This deliberately pessimistic policy-ceiling calculation needs no provider
counting call. A future dispatcher must still count and reject an input above the
policy maximum before send.

At commit, the preparer holds verified read locks on both the latest skill release
control and current default pointer, then inserts one immutable entry into the shared
spend ledger. That single insertion is both the one-use authorization burn and the
aggregate budget reservation. There is no false claim of a cross-database atomic
transaction. A failure rolls the insert back; a replay collides with the deterministic
entry ID and fails closed.

```console
mos eval-derive-skill-runtime-preflight \
  --runtime-request private/runtime-request.json \
  --routing-preflight private/routing-preflight.json \
  --health-eligibility private/skill-health-eligibility.json \
  --spend-ledger private/spend.sqlite \
  --output private/runtime-decision.json \
  ...complete skill evidence and policies...

# Sign runtime-decision.json outside Mos Eisley, then:
mos eval-prepare-skill-runtime-request \
  --signed-runtime-decision trusted/signed-runtime-decision.json \
  --output private/prepared-runtime-request.json \
  ...the same exact sources...

mos skill-runtime-preflight-status \
  --signed-runtime-decision trusted/signed-runtime-decision.json \
  --runtime-authority-policy trusted/runtime-authorities.json \
  --spend-ledger private/spend.sqlite
```

Private keys are never accepted by the CLI. The prepared artifact contains the user
input and exact system instructions and is therefore written as private data. Status
inspection never retries, sends, settles, or releases a reservation.

## Deliberate limits

The supplied routing preflight is now reconstructed from its full
calibration/holdout/promotion and signed operational chain during preparation. The
subsequent [guarded broker admission](SKILL_RUNTIME_ADMISSION.md) repeats that
verification and holds both control anchors through its local commit. Neither artifact
authorizes provider dispatch.

The reservation uses the spending policy's maximum input tokens, not a provider count,
so it may hold substantially more budget than the eventual request needs and does not
itself prove that the request fits that token limit. No automatic release exists. The
current `BudgetedOpenAITransport` creates its own reservation and
cannot consume this pre-reserved entry; integrating it directly would double-reserve
and is prohibited until a dedicated settlement path is implemented.

A crash after the ledger commit but before the prepared artifact is written leaves a
held reservation and consumed authorization. Read-only status reports that state with
`retry_permitted: false`. It cannot prove whether some future process sent a request;
dispatch auditing and outcome settlement are future work.

Local database rollback/cloning, external monotonic state, clock integrity, source
retention, credentials, endpoint trust, provider behavior, and actual invoice
reconciliation remain outside this gate. Every decision, preparation, and status fixes
provider dispatch, activation, configuration mutation, automatic rollback, and
automatic budget release to false.
