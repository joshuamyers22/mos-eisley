# G4 candidate run after signed post-deadline integration

The original G4 candidate gate binds an authenticated provenance record to a
single source revision and a policy that must still be current at dispatch.
After a separately signed post-deadline integration, neither the historical
provenance nor its expired policy can authorize a test on the new commit.

`reviewer_candidate_carryforward.py` provides a separate, offline one-use route.
It replays the complete historical custody, candidate, correction and child chain;
the signed integration grant, VCS record, private claim, original checkout and
detached commit; and a new immutable binding plus read-only Git reconstruction
for the integrated revision. Its creator-signed approval uses a separate Ed25519
domain and the integration's renewed, same-roster trust policy. It binds the
exact historical provenance, signed integration, new binding, known controls,
candidate request, repository, revision and pinned image for at most 24 hours.

Admission also builds the exact isolated job and checks the persistent private
claim store. Dispatch replays admission, exclusively consumes the approval in
that store, runs the frozen reviewer package in the existing immutable,
network-disabled, no-mount container, verifies collection and outcome counts,
and replays Git afterward. A failure after the claim spends the approval. Receipt
verification checks the same claim and current inputs without requiring the
approval window to remain open.

The resulting receipt is candidate-test evidence for this carry-forward route.
It does not authorize a provider call, source write, final suite, review or
acceptance. The existing final-suite gate consumes the original candidate
receipt type; a separate extension and creator approval are needed before this
carry-forward receipt can feed that gate. Single-operator custody remains
disclosed and cannot satisfy formal independent review.

See [the threat model](G4_CARRYFORWARD_CANDIDATE_THREAT_MODEL.md).
