# Milestone 40 adversarial review: publication-history witness

## Disposition

Accepted as a portable signed commitment that detects rollback or divergence when a
trusted verifier supplies a separately retained checkpoint. Rejected as proof of
external retention, newest-checkpoint delivery, provider behavior, or global
monotonicity.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A checkpoint hashes unvalidated database rows | The response store fully reverifies canonical raw response, result, manifest, transaction, and ledger lineage before computing history | Trusted parser/code and local source databases remain in the trust base |
| Deletion, reordering, or replacement preserves a plausible row count | A domain-separated rolling digest commits ordered publication-manifest hashes, not count alone | Collision resistance depends on SHA-256 |
| SQLite maintenance renumbers implicit row IDs | Response-store policy schema 2 persists and validates a gap-free explicit publication sequence; history never depends on `rowid` | Existing schema-1 response stores require explicit migration rather than silent reinterpretation |
| Legitimate later publications invalidate every checkpoint | Verification requires the signed history to be an exact prefix and separately returns the current head | A checkpoint does not summarize records committed after its count |
| An empty checkpoint creates a meaningless witness | Policy requires a positive minimum publication count before derivation or verification | Policy authors choose whether the minimum is operationally sufficient |
| Checkpoint or signature bytes are edited | Strict canonical contracts and an Ed25519 signature bind policy, store, history, and witness time | Key custody and witness enrollment remain external |
| A stale checkpoint is replayed forever | Policy validity and maximum checkpoint age are checked against explicit UTC verification time | Host clock and trusted timestamping remain external |
| Hashing exports private response or assistant content | History contains only policy, count, rolling digest, and latest manifest identifiers; CLI regression tests scan output | Traffic patterns and publication counts remain observable to checkpoint holders |
| Local storage is described as an external witness | Checkpoint and verified result fix external-retention proof to false and documentation requires separate retention | The software cannot prove the operator actually transmitted or retained the signed copy |
| An attacker suppresses the newest signed checkpoint | Every artifact fixes latest-external-checkpoint proof to false | The verifier must obtain the newest checkpoint from a trusted external channel |
| Checkpoint verification authorizes retry or budget release | Both authorities are structurally false | Ambiguous provider settlement still requires separate reconciliation |

## Follow-on requirement

Configure and test an actual owner-approved external retention channel that enforces
latest-checkpoint delivery and access isolation. Separately reconcile provider billing
or receipts before financial-finality claims, and run credentialed conformance only
with explicit authorization.
