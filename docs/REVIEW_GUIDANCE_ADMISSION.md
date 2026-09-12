# Current guidance checks for brokered review

`ReviewGuidanceAdmission` binds an explicitly selected workspace, guidance store,
prepared critic/judge rubric and current owner-policy file/hash. Construction
revalidates that exact selection and freezes the prepared bytes. Pass it as
`guidance=` when preparing a brokered review call. Guidance grants no transfer,
spending, provider or machine authority; existing explicit approvals still apply.

The request must use the exact derived guided brief. The approval commits the
prepared guidance hash, and issuance retains private `guidance-review.json` beside
the request and spending audit. All critics in a spending envelope must share the
same guidance admission hash, including whether guidance is selected. Deferred
judge preparation automatically inherits that selection; the evidence-bound judge
path preserves the same restriction and verifies it in retained transfer lineage.

Current checks run before preview, reservation and grant issuance, before starting
the isolated exchange, before and after token counting and generation, and after
worker acknowledgement/cleanup before returning a model result. Every check uses
the existing guarded local reconstruction, with locks released before provider
awaits. Ordinary guidance writers may complete during a provider call; detected
changes invalidate the answer. Checks describe those instants, not uninterrupted
policy validity, remote cancellation or an atomic revocation boundary at send.

A stale selection before reservation creates no spending entry or audit. Once a
hold or client exists, rejection preserves it and the one-use attempt. Changes
during counting prevent generation; changes during generation retain uncertain
spending. Changes detected after worker cleanup keep already settled actual cost
but prevent a successful model completion. No rejection retries a provider request,
refunds an uncertain charge or refreshes the guidance automatically.

Historical audit verification checks the retained guidance hash, bounded prepared
schema, exact brief projection and judge/critic binding. It never follows a stored
policy path or requires that historical guidance still be current. Current policy
paths and raw policy prose remain host configuration and are absent from provider
payloads and retained guidance. Historical verification cannot authorize new work.

The optional authorization field is omitted for unguided calls, preserving their
existing canonical bytes. Older readers reject guided authorizations; rollback
must preserve an upgraded reader for retained guided evidence. Keep all spending
and audit records when rolling back. The lower-level unguided APIs remain available
for explicit unguided briefs; a future live entry point must select the admission
object whenever project guidance is selected.

The implementing owner is Codex; Josh Myers remains the project decision owner.
Acceptance uses synthetic transports and local guidance fixtures, the existing
quality suite and isolated worker checks, with no paid-provider budget. Tests cover
staleness at each boundary, workspace/policy mismatch, mixed envelopes, judge
inheritance, cancellation, historical reads, tampering and unchanged legacy bytes.
This library slice does not enable live terminal review. Credentialed conformance
and complete live workflow integration remain separate gates. See
[role admission](PROJECT_GUIDANCE_ROLE_ADMISSION.md),
[critic evidence](REVIEW_RESPONSE_EVIDENCE.md) and [roadmap](ROADMAP.md).
