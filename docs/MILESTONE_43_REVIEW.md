# Milestone 43 adversarial review: failure-preserving broker assembly

## Disposition

Accepted as exact-coverage, non-scoreable composition of broker outcomes. Rejected as
live execution provenance, credentialed conformance, grading input, or evidence for
automatic routing.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Only successful broker responses are retained | Add a failure compiler for terminal `failed` and `cancelled` audit states | Rejection before admission is not an attempted assignment and has no terminal outcome |
| Caller cancellation is mislabeled as timeout | Persist `cancelled` separately; only an expired broker deadline records `timeout` | Higher-level cancellation intent is not authenticated |
| Failure cost is fabricated or erased | Bind the exact ledger state; absent reservations yield null cost, while held/uncertain/violation states retain recorded exposure | Provider invoice truth remains external |
| A legacy failure without timing becomes empirical latency | Require schema-3 error classification and latency to mint failure evidence; keep older records recovery-readable only | Host monotonic-clock correctness remains trusted |
| Failed cases are omitted from a result set | Require every blinded batch sample exactly once and restore batch order | A batch itself does not prove a complete plan split without the existing labeled-side lineage checks |
| One execution artifact is replayed under several samples | Require unique sample, authorization, artifact, outcome, ledger-entry, provider-request, and successful-response identities | Local artifacts are not provider-signed |
| Artifacts from separate spending scopes are mixed | Require a single shared ledger identity across the assembled batch | Database rollback or cloning remains outside local detection |
| The failure compiler trusts its audit's own authorization copy or an alias | Require an independently supplied authorization outside the audit tree, reject hard links to the audit anchor, and reject output inside the audit directory | Same-UID operator control and independent-copy custody remain trusted |
| The assembled object is relabeled as live score input | Use a distinct strict schema that fails `RawResultSet` parsing and fixes conformance proof, live issuance, grading, scoring, and promotion to false | A future converter requires its own authenticated live policy and review |
| A terminal failure permits another paid attempt or releases exposure | Artifact and set contracts fix retry and automatic budget release to false | Manual investigation remains an operator responsibility |

## Verification status

Fixture tests cover provider error, true deadline, cancellation, pre-reservation
failure, conservative uncertain spend, exact coverage, canonical ordering, omission,
route substitution, trust-anchor separation, audit-output separation, and strict
incompatibility with scoreable raw results. No provider or paid request was made.
