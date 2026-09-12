# Combined critic and judge spending allowance

`PreparedReviewEnvelope` groups one to eight already prepared critic calls and a
spend-only allowance for a future judge. Preview binds each exact critic approval,
one brief and ledger, unique critic IDs, a caller-supplied aggregate ceiling, the
private artifact directory, judge spending policy and expiry. It performs no writes,
provider operations or reservations. This spending boundary does not establish
provider diversity, evidence validity or pipeline quorum.

The judge's request cannot be frozen before critic findings exist. Its
`DeferredJudgeAllowance` therefore commits to conservative schema-2 pricing and the
full input/output token ceilings, with `transfer_authorized` fixed to false. This
reserves capacity; it grants no judge token count, request or broker issuance.

Explicit `approved_envelope_sha256` confirmation covers all selected critic transfers
and the complete maximum allowance. The content hash is not authentication: trusted
host code must obtain user/admin approval and must not automatically echo the preview
hash or accept model-supplied approval. `SpendLedger.reserve_many` admits all critic
entries and the judge allowance in one serialized transaction. An insufficient total,
late duplicate, invalid entry, admission-slot limit or database failure rolls back
the entire new group. Existing reservations remain intact. The bounded ledger API
accepts one to 64 entries; the review envelope uses at most nine. Existing single
reservation callers use the same transaction logic and retain their behavior.

Successful reservation creates a private directory containing `envelope.json`.
An artifact failure after the database commit conservatively retains every hold.
Repeating the reservation cannot issue another group. The returned
`ReservedReviewEnvelope` uses the approved absolute directory and fixed child paths;
reconstructing a host handle cannot redirect or repeat a critic issuance. It rechecks
the retained envelope, expiry, the exact critic hold and the still-held judge
allowance before creating a child broker audit. The existing pre-reserved controller
then consumes that critic's allowance without reserving twice.

Known critic savings become available after settlement; the other critic and judge
holds remain charged. Cancellation or ambiguous outcomes retain the affected full
allowance. A pricing violation blocks later provider operations even for another
already-issued pre-reserved critic: the controller checks the shared blocked state
before token counting and again before generation. These checks cannot recall
operations already in flight. No retry, refund, top-up or automatic release is added.

Tests exercise concurrent process admission, late-insert rollback, abrupt process
exit after commit, exact capacity/slot boundaries, duplicate approval and critic
identity, different ledger paths, changed briefs, artifact failure/tampering, expiry,
exclusive issuance, cancellation and cross-critic pricing violations. Real Docker
smoke reserves two critics and a judge together, executes one synthetic critic,
checks the other holds remain charged, rejects reissuance and confirms exact cleanup.
All provider fixtures are synthetic; these are not live quality or diversity claims.

The next boundary must approve the actual judge request and atomically move its
existing allowance to the exact request reservation, while retaining critic/finding
lineage and never opening a spending gap or charging twice. The current allowance
cannot be passed directly to `PreReservedOpenAITransport`: its hash describes a
spending commitment, not a request-specific reservation. That dispatch remains
unimplemented. Guidance admission, retained response/evidence verification and
credentialed conformance also remain required before live terminal review.

See [single-call admission](REVIEW_BROKER_ADMISSION.md), the
[brokered client](BROKERED_MODEL_CLIENT.md) and [roadmap](ROADMAP.md). The existing CLI,
research artifact contracts and SQLite schema remain compatible. Rollback removes
the envelope API and preserves outstanding holds; it must not erase reserved funds.
