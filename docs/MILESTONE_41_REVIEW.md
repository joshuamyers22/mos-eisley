# Milestone 41 adversarial review: aggregate billing evidence

## Disposition

Accepted as authenticated corroboration that complete, exclusive OpenAI organization
usage and cost aggregates match one locally settled publication. Rejected as an exact
request-level provider receipt, invoice-finality proof, or authority to change spend.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A local settlement is presented as external billing evidence | Require distinct usage and cost evidence digests plus an independent billing-auditor signature | The evidence bytes are separately retained and not parsed by Mos Eisley |
| A daily cost bucket is attributed to a response ID it does not contain | Require an attested exclusive one-request scope, but fix exact request-cost attribution to false | The auditor can lie about isolation; the documented API remains aggregate |
| Partial pagination makes totals appear to match | Completeness is a literal signed attestation and policy requirement | No collector independently verifies every page or `has_more` value yet |
| An open or mutable reporting bucket is treated as final | Evidence retrieval must occur after both the one-minute usage bucket and one-day cost bucket close | Later provider adjustments and invoice treatment remain possible |
| A different publication is paired with valid billing evidence | Reauthenticate the complete conformance source and private publication, then bind transaction, outcome, ledger, route, usage, and cost | Trusted local stores and parsers remain in the trust base |
| Local and external totals differ by a small amount and are rounded into success | Require exact integer token and microusd equality with no tolerance | Upstream rounding may prevent reconciliation rather than produce false success |
| The conformance observer certifies their own billing claim | Reject billing-auditor identity or public-key overlap with every enrolled conformance observer | Organizational collusion and key custody remain external |
| Project or API-key identifiers leak into portable evidence | Persist only caller-supplied SHA-256 identifiers | Low-entropy or already-known identifiers may still be guessable |
| Evidence or signed metadata is edited | Domain-separated Ed25519 verification binds canonical metadata and both evidence digests | OpenAI does not sign the retained export through this workflow |
| A matching daily aggregate is called a final invoice | Every artifact fixes provider authorship, exact request attribution, and invoice finality to false | Credits, taxes, adjustments, and invoice disputes remain external |
| Reconciliation refunds exposure or permits another request | Ledger mutation, automatic release, and retry are literal false in policy, observation, receipt, and CLI output | Manual financial handling remains an operator responsibility |
| Billing evidence becomes a quality or routing signal | Quality, promotion, and routing activation remain literal false | The repeated blinded empirical study is still required |

## Follow-on requirement

Run separately authorized credentialed conformance through the exact production path.
Then collect complete official Admin API evidence in an isolated credential-owning
process and compare its strict parsed output with this signed contract. Do not claim
request-level billing attribution unless a documented provider field supports it.
