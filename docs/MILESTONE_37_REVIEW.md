# Milestone 37 adversarial review: provider-owning transaction

## Disposition

Accepted as an at-most-once local provider invocation with a durable send boundary and
conservative pre-reserved settlement. Rejected as proof of provider receipt, external
billing finality, or safe retry after any committed intent.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| The same grant is sent through different transaction stores | Grant-policy schema 2 pins one complete transaction-store policy, whose identity is checked against the grant store | Owner-controlled store cloning or rollback needs an external witness |
| Request, route, model, or reservation is substituted | Execution recomputes both request hashes and checks every issuance, preparation, spend, route, and ledger relationship before redemption | A compromised trusted process can replace code or transport behavior |
| Control/default changes race the send decision | Both latest controls, current default, exact issuance, and exact held spend stay read-locked through bearer burn and intent commit | Controls can advance after irrevocable intent commits |
| Intent persistence fails | Bearer is already consumed, transport is never invoked, and spend remains held with no retry path | Manual reconciliation may establish that no send occurred, but cannot recreate authority |
| Process dies after intent but before/during send | The fsynced marker reports an ambiguous boundary; retry and automatic release are structurally false | Local state cannot prove whether the provider received bytes |
| Transport silently retries | Execution requires OpenAI identity and a declared zero retry count; the production SDK client uses `max_retries=0` | A malicious or defective trusted transport can lie about its internals |
| Provider call hangs | Transaction policy caps the enclosing wait at 60 seconds; timeout settles full exposure as uncertain | Cancellation cannot prove remote processing stopped |
| Provider errors, cancellation, or response loss erase exposure | Every post-marker exception settles `uncertain` at the full reservation | Provider billing reconciliation remains external |
| Provider violates model, tier, token, or price assumptions | Full reservation is retained as `violation` and the shared ledger blocks new reservations | Provider-side charge beyond the local ceiling cannot be prevented after transfer |
| Valid response releases excessive budget | Actual cost is recomputed from authenticated local pricing and bounded usage, never provider-supplied currency values | Pricing-source correctness and cache discounts remain operator-reviewed |
| Ledger and outcome stores cannot commit atomically | Ledger commits first; either failure leaves the durable send marker and never grants retry. Recovery rejects a recorded outcome that disagrees with the ledger | Cross-device/database atomicity and hardware failure remain outside SQLite guarantees |
| Durable audit leaks prompt, bearer, credential, or response | Transaction DB stores only lineage, response hash, usage, cost, and status; tests scan raw SQLite bytes | The returned in-memory response and private transport still handle sensitive data |
| Status treats ambiguity as authorization | All absent, before-send, and finished statuses fix retry and automatic release to false | Human reconciliation policy is not yet implemented |

## Follow-on requirement

Add credentialed OpenAI conformance for the exact transaction boundary and a durable,
content-verified response/result publication step. Publication must correlate the
provider response, settled outcome, request identity, and runtime lineage without
weakening ambiguous-state handling or exposing reasoning/credentials unintentionally.
