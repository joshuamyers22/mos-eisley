# Signed review conformance authorization

The brokered review path now has a library boundary for independently authorized
probe phases. An enrolled authorizer signs one exact critic phase, and later signs
the evidence-derived judge phase separately. The existing local approval prompts
remain required. This implements authorization checks; a credentialed executor and
authenticated observation of review-path conformance remain G2 work.

## Trusted inputs and signed scope

The host selects the authority policy, runtime, exact critic preview and controller
start independently of retained artifacts. An Ed25519 authority identity and key
must be distinct from every enrolled observer. The policy fixes its validity window,
maximum authorization lifetime (at most 600 seconds) and reservation ceiling.

`review_conformance_scope` derives the signed scope from the trusted previews. It
requires guided OpenAI requests and binds:

- The full canonical critic preview and controller authorization hashes.
- The exact phase preview, selected guidance, ledger and ledger policy.
- SDK version, immutable worker image ID, OpenAI Responses endpoint, zero automatic
  retries and disabled provider storage.
- The reservation ceiling and expiry. Critics reserve the complete envelope;
  judge authorization binds the controller start and existing judge allowance,
  with zero additional reservation.

The critic prompt's local approval hash is the controller authorization hash.
The signature also binds the hash of the **complete** critic preview, including
requests and spending. Judge signatures bind the complete judge preview. A critic
signature cannot authorize the later judge request.

`make_review_conformance_authorization` bounds the signed window by both policy
and phase expiry. `sign_review_conformance_authorization` signs its canonical
bytes with a review-specific domain separator. Production signing keys belong to
the independent authorizer; deterministic test keys are fixtures only.
`verify_review_conformance_authorization` checks the selected policy, exact expected
scope, enrolled key, signature and current UTC time. Expiry is exclusive. Evaluation
authorization modes and receipts cannot substitute for this statement.

## Local approval composition

Wrap a `ReviewApprovalUI` with `SignedReviewApprovalUI`, then pass the adapter to
the existing [approval flow](REVIEW_APPROVAL_FLOW.md). The host supplies callbacks
for the current authority policy, runtime and controller start, plus an asynchronous
loader for an independently signed authorization matching the requested scope.
The adapter does not create signatures automatically.

Each phase loads and verifies its signature before asking for local approval, then
rereads policy, runtime, scope and time after the prompt. Missing authorization or
local decline stops that phase. A changed policy, runtime or expired signature fails
closed. Existing controller guidance checks, shared deadlines, one-use reservations
and cancellation cleanup still apply. Declining or failing judge approval preserves
the existing allowance; it does not release money or retry the request.

The adapter's `authorizations` tuple contains signatures whose local approval hash
matched. It is not a dispatch log or evidence that a provider call occurred.

## Remaining execution and evidence boundary

The verifier is read-only and repeatable. Verification does not consume permission,
load credentials, attest runtime configuration or establish provider conformance.
A future credentialed executor must verify again at credential and provider use,
enforce the actual SDK/image and bounded isolated transport, preserve current
guidance checks and controller/ledger one-use rules, and retain attempts and
independently authenticated observations. Trusted runtime callback values are
bindings to check against execution, not runtime attestation by themselves.

The signed statement explicitly grants no automatic retry, automatic budget release
or live review activation, and always reports `conformance_proven: false`.
[Launch preview](REVIEW_LAUNCH_PREVIEW.md) therefore still reports live launch
unavailable. This increment adds no paid CLI or credential access.

## Verification

The focused tests exercise independent keys, scope and policy substitution, invalid
signatures, exclusive expiry, local decline, changes during prompts, current guidance
and separate critic/judge approvals. `tools/smoke_review_conformance.py` repeats the
two-phase flow and rejected critic-signature reuse with real Docker workers,
synthetic provider responses and verified cleanup receipts. Neither proves live
provider conformance.
