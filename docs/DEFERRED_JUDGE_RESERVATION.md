# Bind the judge allowance to its approved request

`PreparedJudgeTransfer` connects a reserved review envelope to the exact judge
request once its findings are available. The caller supplies the existing envelope,
reviewer and `JudgeRequest`. Preparation verifies the retained envelope and expiry,
requires terminal critic spending states, and projects the request through the same
pure reviewer method used for actual adjudication. It verifies the original brief,
model, pricing policy and full output cap against the judge allowance.

The existing allowance supplies capacity for this preview. It is not charged again,
and the preview performs no provider operations or artifact writes. This matters
when a ledger has enough already-held judge funds but too little unreserved capacity
for a second reservation. A `PreparedReviewCall` using allowance capacity cannot use
its ordinary single-call issuer; the envelope transfer path is required.

The new confirmation hash binds the original envelope, exact source allowance and
complete judge-call authorization. The aggregate envelope approval is insufficient:
its judge allowance explicitly authorized spending capacity without a data transfer.
Trusted user/admin policy must separately approve the actual judge request, including
its findings, instructions, model, token counting and generation. As elsewhere, a
content hash is not authentication and must not be automatically echoed or accepted
from model output.

Issuance calls `SpendLedger.transfer_held` in a serialized transaction. The exact
source must still be held, the destination must be new, and the amounts must match.
The old allowance is recorded as settled with zero charged while the new exact
request reservation carries the same full amount. This is a transfer of exposure,
not a refund: the ledger total never changes. Other reservations cannot observe a
free-capacity interval, and a duplicate destination or failed update rolls back
both changes. A pricing violation blocks the transfer.

After transfer, private `judge-transfer.json` links the parent allowance to the
request authorization. The broker's audit uses the fixed `judge/` child directory
and existing pre-reserved controller. The grant expires within both the call and
envelope lifetimes. The consumed source allowance prevents a second transfer, even
from another preview for the same findings or from an alternate proposed request.
The returned model client preserves exact request matching, one-use dispatch and
awaited worker cleanup.

A crash, storage failure or expiry after accounting transfer leaves the destination
fully held. A cancellation or ambiguous provider outcome retains that full amount.
Successful settlement retains actual cost even if the judge's answer later fails
JSON or evidence checks. There is no automatic retry, refund, repair or allowance
release. Source records are retained; rollback must preserve both their lineage and
all destination exposure.

`verify_judge_transfer` checks the expected transfer record, original envelope hash,
ledger identity, retired source, exact destination reservation and completed child
broker audit. Missing or changed artifacts fail closed. A host response receipt is
not proof of a valid judge answer, accepted citations or provider-authenticated data.

This boundary verifies request and spending lineage. Terminal critic ledger states
only establish terminal accounting status; they do not establish completed worker
cleanup, critique validity, finding provenance or quorum. The caller must still use the review pipeline's
citation, deduplication, provider-diversity and quorum rules. Persisted response/finding
verification and current guidance admission remain required for the live product,
along with authorized credentialed conformance. This library enables no live CLI.

Tests cover no-double-reservation previews, exact findings/brief/policy binding,
separate confirmation, atomic transfer, competing admissions, late-write rollback,
replay, expiry, interrupted issuance, cancellation and audit tampering. Real Docker
smoke runs two synthetic critics and a judge from one reserved envelope, checks
actual settlement and transfer lineage, rejects replay and confirms exact cleanup.
See the [combined envelope](REVIEW_SPENDING_ENVELOPE.md),
[single-call admission](REVIEW_BROKER_ADMISSION.md) and [roadmap](ROADMAP.md).
