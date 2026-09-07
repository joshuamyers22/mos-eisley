# Milestone 51 adversarial review: conformance request boundary

## Disposition

Accepted as a hardening of the already fixture-tested, separately authorized OpenAI
conformance path. Rejected as evidence that credentialed conformance completed, that
OpenAI honored a request, that billing was reconciled, or that any route is ready for
scoring, promotion, or activation.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| The ceremony hashes one request but the spending controller adds a service tier after authorization | Put literal `service_tier: default` in the deterministic builder and test that the generation request reaches the transport unchanged | The SDK and remote service still serialize and interpret the request inside their own trust boundaries |
| Streaming or background behavior changes when provider defaults evolve | Put literal false values for both controls in the authorized request | OpenAI behavior and availability remain external |
| A caller requests storage or automatic truncation and the controller silently weakens it | Reject any non-false storage value and any truncation mode other than `disabled` before token counting or reservation | Generic callers may omit controls, in which case the controller still supplies its fixed safe values |
| Generation-only controls contaminate the token-count request or change its meaning | Strip output, storage, tier, streaming, background, and include controls from the count request; test the exact count and generation shapes through the installed SDK | The provider's token counter can still differ from generation accounting; an overage is retained as a violation |
| The returned service tier differs from the requested tier | Continue requiring literal `default`; retain the full reservation and block the shared ledger on mismatch | The Responses API may report a tier selected by provider behavior; local evidence cannot establish the remote cause |
| A signature over a hash is presented as informed human review of cleartext | Document that the signer must independently render or inspect the deterministic request from the blinded inputs and trusted builder | The signed schema does not embed a second human-readable request projection |

## Verification scope

Tests cover explicit request controls, exact controller-to-transport generation
equality, exact reservation hashing, generation-only field removal from input-token
counting, installed-SDK serialization, and pre-provider rejection of conflicting
values. Provider and Docker behavior remains synthetic in these tests. The prior live
synthetic canary proves only its separately fixed request path and does not satisfy
this credentialed blinded-conformance milestone.
