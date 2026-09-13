# Reconstruct and verify final review verdicts

`reconstruct_review_result` converts retained critic and judge evidence into a
`RetainedReviewResult` without making provider calls, changing spending or writing
files. The caller supplies the trusted envelope, reviewer, ledger and exact
evidence-bound judge approval. Reconstruction first verifies the complete critic
evidence, findings, approval and judge transfer chain.

The judge's retained model request must match both its approved hash and the same
pure projection used by the live reviewer. Shared response verification checks the
bounded completion receipt, raw broker response, canonical model response and
broker outcome. Received responses require settled spending; all results require
terminal accounting. Missing, changed or partial artifacts raise an error instead
of manufacturing an acceptance or a completed failure result.

A fully recorded failed or cancelled judge attempt yields `infrastructure_error`.
A received response with invalid JSON, excessive JSON nesting, duplicate keys,
omitted required fields, unsupported blocks or exceeded decoder budgets also yields
`infrastructure_error`.
The pure judge decoder is shared with model review. Duplicate or unknown upheld
finding IDs fail through the pipeline's shared verdict helper, and the resulting
failure contains no accepted judge decision or upheld findings.

For valid decisions, the same deterministic verdict rules apply in both paths:
upheld blockers reject; other blocking medium/high findings require revision;
low-impact findings and preferences do not block acceptance. Finding order comes
from the verified request, not the judge's ID order. Original critic contributions,
the exact judge request and valid judge decision remain in the result.

`retain_review_result` reconstructs and exclusively writes private
`review-result.json`. The record binds the trusted approval, completion and outcome
hashes to the complete review result. Retain its canonical SHA-256 independently.
`verify_retained_review_result` requires that expected hash and reconstructs the
whole chain again; changing a cached verdict and recomputing its hash is insufficient.
Subsequent critic or judge evidence changes invalidate the saved result.

Historical verification works after grant expiry and never restores grant or
spending authority. Invalid judge output preserves actual settled cost; failed or
cancelled exchanges preserve conservative exposure. A local result-write failure
can be retried using the existing evidence without another provider attempt.
Existing result files are never overwritten. Rollback preserves evidence and all
spending; it does not automatically repair records or release reservations.

Tests cover accept/revise/reject semantics, nonblocking preferences, invalid and
duplicate decisions, cancellation, uncertain accounting, missing/substituted judge
artifacts, raw/canonical disagreement, forged cached verdicts, changed critic
evidence, expiry and local storage failure. Real Docker smoke saves and verifies a
synthetic final result and confirms unchanged accounting and exact cleanup.

These are trusted-host integrity checks, not external provider authentication or
fresh permission to act on the result. Current guidance admission and authorized
credentialed conformance remain required before live terminal activation. This
library adds no CLI, paid validation, retry or automatic execution. See
[critic evidence](REVIEW_RESPONSE_EVIDENCE.md),
[judge transfer](DEFERRED_JUDGE_RESERVATION.md) and [roadmap](ROADMAP.md).
