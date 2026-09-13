# Review conformance acceptance

`evaluate_review_conformance` now evaluates one fixed tranche of three precommitted
review probes. All three must have fresh, independently authenticated observations,
verified runtime evidence and fully explained settled ledger entries. The evaluator
is read-only and grants no provider dispatch, retry or live review activation.

## Commit one exact tranche

The host selects and independently retains `ReviewAcceptancePolicy` before any of
the three attempts starts. The policy fixes:

- Three ordered slots, each pinning the complete critic preview, observation policy
  and independent authority policy.
- The exact critic roster identities and role profiles, judge role profile, review
  quorum policy and controller duration.
- The installed SDK version, immutable worker image, commitment time, validity
  window and maximum observation age.

Role profiles bind provider, model, effort, system-prompt hash and token/response-byte
limits. `review_role_profile` derives these fields from a tool-free canonical request.
The judge profile can be projected with an empty finding set before execution;
acceptance checks the actual evidence-derived judge request against it. Full request,
guidance and spending bindings remain pinned separately in each committed preview
and its independently authenticated phase authorizations.

Three is the minimum fixed tranche size for this review-specific criterion. All
slots must pass; this is not a pool from which to select favorable results. A missing,
declined, failed or unproven attempt cannot be replaced silently. A different tranche
requires a separately retained policy and fresh exact approvals. That is not automatic
retry authority or a disposition of an earlier failure.

The OpenAI-only evaluator preserves the explicitly selected review policy. It rejects
a profile that cannot meet that policy, including two-provider quorum. Acceptance of
an explicitly selected one-provider experiment does not establish conformance for
the default two-provider review policy or for other models, effort levels or images.

## Fresh verification

Supply one `ReviewAttemptEvidence` for each slot in commitment order. These are
trusted caller-selected contexts and paths: previews, controller start, both phase
authorizations, signed observation, independent final-result pin, reviewer, ledger
and every worker lifecycle directory. Do not populate them from a saved acceptance
report. Supply `None` for a slot with no qualifying evidence; retain all three slots.

For every supplied attempt, the evaluator authenticates the observer again and
reconstructs the full local review result and spending chain. It then rereads the
runtime records and cleanup receipts and compares them with the signed exchange
pins. SDK/image/role/quorum changes, altered signatures, tampered evidence or missing
cleanup fail verification. Serial execution must follow commitment order, with each
later controller start following the preceding observation time.

Controller and signed-observation identities must be distinct. Every provider response
ID and worker-cleanup evidence pin must also be distinct across the whole tranche.
Duplicating or rewrapping an earlier response therefore cannot add another success.
These identifiers remain observer-supported local evidence, not cryptographic proof
of provider authorship.

When all slots qualify, each participating ledger must contain exactly the distinct
entries attributable to those attempts, including retired judge allowances. Its
total charge must equal their reconstructed charges. Blocked, unresolved or additional
entries reject acceptance, even when an unexplained entry was settled to zero.
Use dedicated tranche ledgers; one shared ledger or separate dedicated ledgers are
supported. Conflicting filesystem paths for the same ledger identity are rejected.

## Results and limits

`status: "accepted"` requires all three slots and complete ledger accounting.
`status: "incomplete"` reports how many supplied slots independently qualified when
one or more slots is `None`. Malformed, mismatched or corrupt supplied evidence raises
an error instead of being silently omitted. Neither result creates reservations or
loads credentials. Historical reports are not execution authority; callers must
reevaluate against current trusted inputs and the policy's validity window.

Acceptance covers this exact tranche and profile. It does not prove commitment
custody, honest host measurements, remote provider authorship, reconciled billing,
quality, or completeness of attempts outside the committed tranche. Independent
observers must still inspect actual runtime and supporting evidence. The evaluator
does not turn successful fixtures or the older evaluation-calibration conformance
gate into live review conformance.

Live launch remains unavailable. An operator ceremony for independently retained
commitments and evidence, explicitly authorized live attempts, and a separately
reviewed launch-admission decision remain outstanding. No live tranche was executed
or accepted during this implementation.

## Validation

Tests build three distinct synthetic probes after committing their exact slots,
collect runtime and cleanup evidence, independently sign fixture observations and
exercise the real evaluator. They cover complete/incomplete tranches, omitted or
repeated slots, late commitments, profile changes, response duplication, runtime
tampering, wrong cleanup, ledger contamination and expiry. No cached success receipt
is substituted for fresh verification.
