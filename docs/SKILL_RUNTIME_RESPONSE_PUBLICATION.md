# Skill runtime response publication

Mos Eisley can now turn one successfully settled skill-runtime provider transaction
into one durable, content-verified publication. The private store retains the exact
canonical provider response for verification while its read surface exposes only a
text-only assistant result and hash-linked publication manifest.

## Exact lineage and atomic publication

Provider-transaction policy schema version 2 pins the complete response-store policy
before a capability can be issued. That response policy pins the transaction-store
identity, capacity, per-response and aggregate retention limits, result size limits,
and literal denials for reasoning publication, provider-credential publication,
provider retry, and automatic budget release.

Publication accepts only an exact finished transaction whose outcome is
`response_received` and whose existing ledger entry is settled. It reverifies the
stored intent/outcome pair, issuance, prepared request, route, request and response
hashes, ledger identity, usage, model, provider request ID, stop reason, and charged
cost. A substituted response or locally invented result fails before commit.

One private rollback-journal SQLite transaction stores:

- the exact canonical raw provider response;
- the reasoning-free assistant result;
- the publication manifest; and
- the exact provider intent and outcome needed to reverify both.

Every later status or result read validates canonical encodings, row indexes, content
hashes, full lineage, and the published text against a fresh parse of the retained raw
response. A corrupt or substituted row fails closed. Publication IDs, transactions,
outcomes, provider request IDs, and result hashes are unique, so replay cannot create
a second publication.

## Reasoning and credential boundary

OpenAI reasoning blocks, including encrypted content, may be present in the private
raw response because dropping them would weaken response integrity. They are omitted
from the published assistant turn, whose schema accepts only text blocks. Provider
credentials are never accepted or added by this module. Published model text is
untrusted and may itself contain sensitive material, so callers still need an
output-content policy. Tool calls and reasoning-only responses are not publishable.

The store has no raw-response load or CLI export operation. Its CLI can create a
pinned store, report verified publication counts, and return one verified
reasoning-free result:

```console
mos skill-runtime-response-store-create \
  --path private/runtime-responses.sqlite \
  --response-store-policy trusted/response-store-policy.json \
  --provider-transaction-store private/runtime-provider-transactions.sqlite

mos skill-runtime-response-store-status \
  --response-store private/runtime-responses.sqlite

mos skill-runtime-response-result \
  --response-store private/runtime-responses.sqlite \
  --publication-id PUBLICATION_SHA256
```

## Deliberate limits

Private filesystem permissions and Python module boundaries do not contain malicious
same-UID or same-process code. The owner can copy or roll back both SQLite databases,
so cross-host uniqueness and monotonicity require an external witness. Retention and
deletion policy, hardware durability, provider-side receipt, invoice reconciliation,
and credentialed OpenAI conformance remain external or future work. A settled and
published result proves consistency with local authenticated inputs and retained
provider bytes; it does not prove that the provider authored those bytes independently
of the trusted transport.
