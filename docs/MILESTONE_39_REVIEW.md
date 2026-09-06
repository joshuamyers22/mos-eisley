# Milestone 39 adversarial review: runtime conformance attestation

## Disposition

Accepted as authenticated metadata proving that one enrolled observer signed a claim
about one exact locally verified runtime publication. Rejected as independent proof of
credential use, provider authorship, billing finality, transport behavior, or model
quality.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A generic conformance receipt is attached to another runtime result | Policy pins the response store; observation binds exact publication, result, transaction, route, and provider request identities; authentication reloads and reverifies the private publication | Trusted local code and response store remain in the trust base |
| An obsolete or arbitrary SDK is described as conformant | Policy contains a canonical allowlist of accepted SDK versions and authentication rejects all others | Version approval and dependency provenance remain operator decisions |
| An unsigned observation is mistaken for evidence | Only an authenticated artifact verifies an enrolled Ed25519 signature; derive output is explicitly signable metadata | Artifact consumers must require the authenticated schema |
| Observation or signature bytes are edited | Domain-separated signature verification covers strict canonical observation bytes | Key custody and observer identity remain external |
| A stale observation is replayed indefinitely | Policy validity and a bounded observation age are checked against an explicit UTC authentication time | Host clock correctness and external timestamping remain trusted |
| Merely deriving metadata claims a live exchange | CLI requires an explicit credentialed-exchange attestation before creating output | A dishonest operator can still attest falsely |
| Attestation leaks provider response or secrets | Observation and authenticated output contain hashes and transport metadata only; CLI tests scan for assistant text, reasoning, and key material | The separate private response and redacted transport evidence have their own retention boundaries |
| A signature is presented as provider proof or billing evidence | Both observation and authenticated artifact structurally fix authorship proof and billing reconciliation to false | Provider-signed receipts and invoice ingestion are not implemented |
| One conformance call is used as quality evidence | Quality, promotion, and routing activation are structurally false | Repeated blinded empirical evaluation remains required |
| The conformance command silently incurs cost | This milestone sends nothing; the existing paid-capable lifecycle remains separately authorized and was not invoked | A future operator-run exchange transfers data and may incur provider charges |

## Follow-on requirement

Perform a separately authorized credentialed OpenAI run through the exact transaction,
publication, and attestation path and retain redacted transport evidence. Then add an
external billing or provider-receipt reconciliation source before claiming financial
finality; model quality still requires the pre-registered repeated evaluation suite.
