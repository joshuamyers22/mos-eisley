# Brokered review conformance probe

`BrokeredReviewConformanceProbe` connects the guided review controller, independent
phase signatures, local approval and the credentialed OpenAI transport. It is a
paid-capable library entry point. Constructing it previews the selected review;
calling and awaiting `run()` can count and generate only after both required forms
of approval for that phase. This increment adds no live CLI and records no live
provider conformance result.

## Host composition

The caller supplies a `PreparedReviewEnvelope`, its `ModelReviewer`, explicit
`ReviewPolicy`, asynchronous `ReviewApprovalUI`, distinct critic `OfflineContainer`
instances and a judge container. Every container must select the same immutable
image. The default quorum is preserved; an OpenAI-only probe requires an explicitly
selected policy permitting one provider. Fixtures select their own smaller quorum.

The remaining dependencies are trusted host callbacks:

- `authority_policy()` selects the current independently enrolled authority policy.
- `load_authorization(scope)` asynchronously obtains the authorizer's signature for
  the exact critic or judge scope. It must not automatically sign for the observer.
- `load_api_key()` synchronously returns the host credential after admission. The
  probe does not search environment variables or select a key store itself.

`controller.preview` provides the exact initial preview. After execution, the host
can retain `controller.start`, `judge_preview` and `approval_ui.authorizations`
independently. The existing controller retains its broker, model, spending and
verdict artifacts. Those artifacts do not authorize another run.

## Dispatch checks

The [signed approval adapter](REVIEW_CONFORMANCE_AUTHORIZATION.md) now keeps frozen,
process-local approvals and exposes `approved_phase()` for current verification.
Each provider operation must match the exact canonical payload derived from that
approved preview. Token-count payloads use the same projection as the spending
controller, and generation includes the approved limits and default service tier.
Canonical comparison distinguishes JSON booleans from numerically equal integers.

Before reading the key, the probe checks the independent signature, local approval,
current authority policy, installed OpenAI SDK version, selected worker images,
guidance, active controller phase, exact payload and expiry. It repeats those checks
after key loading and after each provider await. Authorization or guidance changes
detected after counting block generation; changes detected after generation invalidate
the answer while preserving conservative spending. These are moment-of-use checks,
not atomic revocation at the remote provider.

Each transport consumes one token-count attempt and then, only after successful
counting, one generation attempt. Errors and cancellation do not reset consumption.
The existing envelope reservation and broker claims prevent reissuing the same
approved run through a new probe object. Each operation is bounded by the earliest
signed expiry, controller deadline and 60-second maximum. The controller also
preserves its shared monotonic deadline and awaits worker cleanup on cancellation.

The probe uses the existing `EphemeralOpenAITransport`: short-lived SDK clients,
`https://api.openai.com/v1`, zero automatic retries, bounded HTTP responses, disabled
redirects and ignored proxy environment settings. Credentials stay in the host and
are absent from worker input and retained review records. Generation requests
disable provider storage and truncation. A separate key lookup occurs for each
count and generation operation; loaders must be short, trusted local operations.

## Evidence and launch status

The returned `RetainedReviewResult` proves the controller's local reconstruction
against its saved artifacts. It does not independently authenticate provider
authorship, actual runtime execution or billing, nor certify repeated conformance.
An [independent observer format](REVIEW_CONFORMANCE_OBSERVATION.md) now authenticates
one successful probe's provenance. Independent runtime evidence collection,
review-specific repeated-probe acceptance and authorized live runs remain required.
An authorization signature is permission, not proof of a call.

`review-launch-preview` continues to report live launch unavailable. No credentialed
probe was run as part of this implementation; all provider responses in validation
are synthetic.

## Verification

`tests/test_review_conformance_probe.py` exercises both approvals, exact payloads,
late revocation, expiry, guidance and image changes, provider failure, one-use
execution and repeated cancellation. A mocked HTTP exchange exercises the real SDK,
endpoint and retry settings, request flags and closure of all bounded clients.
`tools/smoke_review_probe.py` repeats the successful flow and repeated cancellation
with real Docker workers and checks every removal receipt. Both test paths use only
synthetic credentials and provider responses.
