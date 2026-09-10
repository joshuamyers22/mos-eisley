# Milestone 44 adversarial review: evaluation conformance receipts

## Disposition

Accepted as authenticated, one-assignment observer evidence for a successful
brokered OpenAI conformance probe. Rejected as provider authorship, billing proof,
failure-send proof, batch conformance, live-result conversion, grading input, or
routing evidence.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A synthetic artifact is called credentialed | Require an explicit credentialed-exchange attestation and a policy-enrolled Ed25519 observer signature | A trusted observer can lie or collude |
| A signed artifact is moved to another route or sample | Pre-pin plan, batch, sample, candidate, evaluation request, and serialized provider request | Policy creation and distribution remain trusted |
| A nearby spending scope is substituted | Pre-pin spend-policy, ledger, and ledger-entry identities | Ledger rollback or cloning remains locally undetectable |
| A strict artifact is fabricated without its source state | Reopen the independently anchored authorization, audit chain, and ledger at derivation and authentication | Same-UID fabrication of all local sources remains possible; the observer is the external trust claim |
| The audit's authorization is passed as its own trust anchor | Reject paths in the audit tree plus symlink and hard-link aliases | Independent-copy custody remains an operator responsibility |
| Old evidence is replayed | Enforce policy validity and a bounded observation age against explicit UTC timestamps | Host and observer clock integrity remain trusted |
| A signature is replayed across protocols | Use a distinct domain separator and bind the exact canonical observation hash | Ed25519 key custody remains external |
| A provider failure is labeled as a credentialed exchange | Accept only completed, response-received, settled artifacts with token usage and a provider request ID | Failed outcomes do not prove whether a network send occurred |
| One probe is treated as a live batch | Fix complete-batch conformance, conversion, grading, scoring, quality, promotion, and activation to false | Repeated credentialed execution and a separate reviewed converter remain future work |
| Sensitive response metadata leaks in automation output | Emit hashes and denial flags only | The private source artifacts intentionally retain critique and request metadata |

## Verification scope

Fixture tests cover exact success, route/artifact/policy substitution, audit and
ledger reverification, stale observations, untrusted and tampered signatures,
failure rejection, literal denial flags, explicit CLI attestation, input overwrite,
and audit-anchor separation. Keys and provider artifacts are synthetic; no paid
request is made.
