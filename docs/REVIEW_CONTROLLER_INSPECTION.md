# Inspecting saved brokered reviews

`review-controller-status` inventories the durable records and spending of a
stopped [brokered review controller](BROKERED_REVIEW_CONTROLLER.md). It makes no
provider calls, loads no credentials, changes no artifacts or ledger entries, and
never authorizes retry or process restart.

```sh
mos-eisley review-controller-status \
  --review-dir /private/reviews/run-123 \
  --expected-start /private/approvals/run-123-start.json \
  --expected-judge-preview-sha256 "$REVIEW_PREVIEW_SHA256" \
  --spend-ledger /private/spending.sqlite
```

The trusted host must independently retain the exact `ControllerStart` record
from the owning controller’s `start` property after reservation succeeds. Supply
that record separately from the review
directory; pointing at the inspected run's own start record, including a hardlink
alias, is rejected. Copying an untrusted run's start record elsewhere does not
establish trust. The API takes the independently trusted `ControllerStart` value
explicitly. Missing or mismatched start/envelope records fail validation. The
inspector uses the caller-selected directory and ledger, never a saved path to
select another workspace or spending scope.

After a judge transfer, also supply `--expected-judge-preview-sha256`, independently
retained from the preview returned to the owning host by `run_critics`. The API
accepts this as `expected_judge_preview_sha256`. It is optional before transfer;
when supplied it must match. A saved start alone does not pin the later concrete
judge request. The preview pin establishes inspection identity, not dispatch
approval, and must never be populated automatically from the inspected directory.

Output is one `review.controller.status` JSON object containing:

- `recorded_phase`: the latest retained stage (`started`, `judge_preview`,
  `judge_transfer`, `finished`, `failed`, or `cancelled`). This describes records,
  not whether a process is running or whether a provider call is still active.
- Each critic's and any identified judge's reservation, ledger status, audit
  completeness, and model-completion verification status. A complete broker audit
  alone cannot establish a complete model exchange or a valid review decision.
- The original judge allowance, identified charged exposure, total ledger charged
  exposure, and `spending_inventory_complete`. The ledger total can include other
  reviews. An allowance retired before its transfer record was saved is flagged
  as incomplete attribution; the inspector cannot identify its target by guessing
  among other ledger entries. Held and uncertain exposure remains charged.
- Whether a result artifact exists, its digest, and whether the saved absolute
  deadline has elapsed. Result bytes, request/response bodies and diagnostic prose
  are never printed.

`verdict_verified`, `retry_permitted`, and `resume_authorized` are always false.
A recorded `finished` phase means the terminal record binds the saved result; it
is not a fresh semantic verdict verification. Use
[retained final verdict verification](REVIEW_VERDICT_EVIDENCE.md) with the pinned
reviewer configuration, judge authorization, and result digest for that claim.
Missing completion records remain missing even when spending is settled. A result
saved before a crash does not imply a terminal `finished` record exists.

Present request hashes, audit chains, completed model exchanges, judge transfer
bindings and terminal result bindings are checked. Partial artifacts are reported
without manufacturing missing records. Invalid present bindings are rejected.
Historical guidance checks do not reload current project policy or grant current
permission. Files are bounded, and artifact symlinks and special files are rejected.

Inspect a stopped run whose trusted directory and ledger are not being modified.
The reads span multiple files and ledger queries, so the output is not an atomic
snapshot of an active run. This command adds no lock acquisition, repair, hold
release, new grant, implicit approval, or live launch flow.
