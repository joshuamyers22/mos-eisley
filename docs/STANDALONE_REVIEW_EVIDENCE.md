# Standalone review evidence

`run.review_standalone_evidence` closes the retention gap for a one-off brokered
review probe that is not already represented by a sealed campaign submission. It
does not run a review. It verifies and writes one private JSON bundle from evidence
the owning host already holds.

## Retained contract

The bundle reuses the validated `CampaignAttempt` and `CampaignAttemptSubmission`
contracts and therefore retains:

- the exact launch configuration and critic preview, including the configured
  visible-text output limit;
- the authority and observation policies;
- the controller start and conditional judge preview;
- both signed phase authorizations;
- the signed post-result observation and expected result hash;
- the spend-ledger path; and
- every critic/judge lifecycle path in exchange order.

The top-level contract fixes provider dispatch, live activation, and retry authority
to `false`. It contains no provider credential and grants no new authority.

## Verify before retention

`retain_standalone_review_evidence` canonicalizes and decodes the bundle with
duplicate-key and size checks, reconstructs the dispatch-refusing reviewer from the
exact configuration and its response limits, authenticates the signed observation,
reconstructs the pinned result from the ledger and run artifacts, and verifies every
approved runtime exchange and cleanup record. A configuration whose response limit
would project different critic or judge requests fails closed. Only after all checks
pass does it exclusively create a mode-0600 file in an existing private
owner-controlled directory.

The output must be an absolute new path outside the review run and worker lifecycle
directories. Existing files are never replaced. Verification failure writes
nothing.

## Offline replay

Read the retained bytes with `decode_standalone_review_evidence`, then call
`verify_standalone_review_evidence` with the historical verification time. Replay
requires the referenced ledger, run directory, and lifecycle directories to remain
available and unchanged. The one-file bundle preserves all authentication inputs;
it intentionally does not duplicate the larger runtime artifacts.

A valid replay proves the retained local result, signatures, exact phase bindings,
runtime records, and cleanup records. It does not prove provider authorship or
billing, authorize a retry, qualify production launch, or reinterpret an immutable
historical verdict.
