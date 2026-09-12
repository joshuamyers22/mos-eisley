# Brokered critic and judge controller

`BrokeredReviewController` composes an existing prepared spending envelope,
canonical reviewer and explicit review policy. It checks the roster, exact critic
projections, request budgets and per-call deadlines before admitting work. The
controller approval hash binds the envelope, review policy and whole-review time
limit. It does not obtain credentials, select a provider, enable live terminal
review or automatically approve a preview.

Call `run_critics` with that separately approved hash, one host transport and one
distinct isolated-container instance per critic. An instance permits only one
active exchange; reusing it in the fan-out rejects before reservation. It reserves
the complete critic/judge
envelope once, writes a private start record and runs the critics concurrently.
All children complete broker cleanup before findings are reconstructed. Complete
recorded failures cannot vote but may coexist with a valid quorum; missing or
inconsistent evidence blocks the judge. The default two-provider quorum remains
unchanged. OpenAI-only synthetic fixtures explicitly select a one-provider policy.

Successful critic execution returns `ControllerJudgePreview` and pauses in
`awaiting_judge`. The preview contains the exact verified evidence, judge request
and underlying evidence authorization. The host must separately approve its whole
SHA-256 before calling `run_judge`. The controller rechecks the saved start and
preview, critic evidence, spending and current guidance before issuing the judge.
It reconstructs and privately retains the final result using the same strict
decoder and verdict rules as the lower-level verifier. A completed workflow may
contain an `infrastructure_error`; completion never means code acceptance.

One monotonic deadline covers critics, the judge approval pause and judge execution,
and cannot outlive the envelope's absolute expiry. Per-call deadlines remain bounded
by the review policy and the broker's 60-second maximum. These deadlines initiate
cancellation; bounded broker/container cleanup is still awaited afterward. Repeated
caller cancellation cannot detach the controller's children. Cancel an active
coroutine and await it; `cancel()` stops only a prepared or awaiting-approval
controller. Every cancellation preserves existing holds and uncertain spending.

The private `controller-start.json`, `controller-judge-preview.json` and
`controller-terminal.json` records supplement existing envelope, audit, response and
result artifacts. Exclusive writes reject repeats. A duplicate controller that
cannot reserve the envelope never writes into the winning controller's records.
Wrong approval hashes and wrong transport counts leave a prepared/paused controller
unchanged; once an attempt starts, failures and cancellation consume that phase.
No controller transition retries providers or releases budget.

This first controller is process-local. Durable records support inspection and the
existing lower-level evidence verifiers; they are not serialized controller handles
or permission to restart an interrupted phase. After a final-result write succeeds
but terminal-record storage fails, inspect/verify the existing result without
dispatching again. Crash resume and a user-facing live launch/approval flow remain
separate work. Stored policy paths never select current guidance automatically.

The implementing owner is Codex; Josh Myers remains the project decision owner.
Acceptance uses synthetic providers under existing whole-envelope limits and a
zero-dollar paid-provider budget. Tests cover exact approvals, concurrency, failed
quorum, invalid judges, stale guidance, tampered records, deadline expiry during
the approval pause, repeated cancellation, duplicate starts, storage failure and
final-result reconstruction. Source and installed-wheel checks use the same tests.
`make container` also runs `tools/smoke_review_controller.py`: complete synthetic
review, repeated cancellation and judge failure through real concurrent Docker
workers, with every cleanup receipt verified.
Rollback preserves spending and all retained evidence. See
[guidance admission](REVIEW_GUIDANCE_ADMISSION.md),
[verdict evidence](REVIEW_VERDICT_EVIDENCE.md) and [roadmap](ROADMAP.md).
