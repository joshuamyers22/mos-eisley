# Work note: live session coding release gates

- Status: release packet prepared; financial reconciliation complete. Final
  delivery checks and accountable disposition are recorded in [PR #287](https://github.com/joshuamyers22/mos-eisley/pull/287).
- Owner: Joshua Myers owns operating and release authority; Codex prepares changes
  and verification, without claiming independent human approval.
- Started: 2026-10-05.
- Functional runtime candidate: `44adf471e7386f34fb37479b46eaf0b2302d4291`.
- Starting delivery head: `abefd1f`.
- Guidance: `AGENTS.md`, `AGENTIC_VERIFICATION_GUIDE.md`,
  `ADVERSARIAL_REVIEW_PLAYBOOK.md`, `templates/WORK_NOTE.md` and
  `templates/THREAT_MODEL.md`; GitHub template provenance is recorded in
  `LIVE_SESSION_CODING_WORK_NOTE.md`.

## Objective and invariants

Close the retained cancellation charge using updated provider evidence, prepare
an exact-candidate spending/integration/cancellation review, run the combined
local gate and GitHub candidate CI, prepare the PR, and verify the release build
for the supported existing-source `pure_python_v1` scope before normal use.

Keep the original $10 ledger and all historical receipts. No further provider
dispatch, inferred refund, reset or credential publication is authorized by a
financial evidence gap. Keys and raw synthetic model packets remain private.
Publish only code, documentation and safe evidence digests. Preserve protected
tests, exact review identity and one-use integration. Stop merge if CI fails or
accountable release review remains outstanding. Do not substitute the agent's own
assessment for human/domain approval. No wider repository/platform admission or
prospective evaluation claim follows from these gates.

## Current evidence

The [functional qualification record](LIVE_SESSION_CODING_QUALIFICATION_WORK_NOTE.md)
binds all four passing cases, 132 ledger entries and total exposure $2.466033,
including one $0.113 uncertain cancellation allowance. Its earlier reconciled
receipt remains unchanged.

The first refreshed export omitted completed calls and was not used to reduce the
hold. The next complete October 5 export matched every Luna, Terra and Astra total,
and left one unmatched Sol request: 791 input and 973 output tokens, no cache
writes. Joshua explicitly attested that all credential usage is included and
qualification was its only Sol usage. Under the pinned call policy the charge is
22,624 micro-USD. The exact ledger adjustment changed 113,000 to 22,624 micro-USD,
preserved the original uncertain receipt, and replayed as a no-op. All 132 entries
are settled; total spending is **2,375,657 micro-USD ($2.375657)**, with zero
unresolved entries and the original $10 cap unchanged. No provider call occurred.

Private financial evidence SHA-256:
`6ff6b084b4de7a2e059875966cd487b1f556c0d854f0ea8b552afe7d8b7df842`.
Owner authority SHA-256:
`78bd67c5b0f96521b9daddcd1f8bf2fee7a06c068c7c17d4af3fd5fa71401eb0`.
Authority is the authenticated owner-session attestation; the executor integrity
seal is not an independently enrolled human signature. Original functional
evidence, before/after cancellation snapshots and uncertain receipt remain intact.
An additional receipt-to-ledger reconstruction matched every one of the 132
entries, both accountable adjustments and the exact settled total without mutation.
Its SHA-256 is
`d7f90e3bba3e54c36adf7192a0443e32fbba1b5de55e7aa375d63fc7b49f7561`.

The locked runtime dependency audit passed: no known vulnerabilities or adverse
project statuses in 47 packages. Its first attempt was blocked by sandbox DNS;
the network-enabled repeat completed successfully. The combined local `make check`
is running outside the sandbox so native socket, tmux and Git containment checks
can run. Main requires `quality`, `container` and `gitleaks`, enforced for admins;
the approval count is zero, so no protection bypass is planned.

PR #287 is the authoritative closeout record for the final delivery head, complete
local check result, exact-head CI, artifact hashes, accountable disposition and
merge/build verification. This preparation note does not itself assert those gates
passed. The initial delivery build at `61cbb58` verified all 387 runtime source
files in both wheel and source archive against qualified candidate `44adf47`.
Container, secret scanning and native Windows/macOS/Linux storage CI passed on
that head. Later documentation commits preserve the runtime and dependency bytes;
the final PR head still requires its own protected CI checks.

## Review and release handoff

The user authorized this release-gate work, including PR and merge operations.
That authorization does not itself document assessment of a prepared exact-candidate
financial/release review packet. Accountable approval must bind the concrete
candidate, review findings, CI results and operating scope before merge.

The [review packet](LIVE_SESSION_CODING_RELEASE_REVIEW.md) traces spending,
integration, data transfer and cancellation controls and states residual model
reliability and post-integration recovery limits. Financial review is complete
for the exact adjustment above. Before normal use, confirm passing delivery CI and
accountable release acceptance in [PR #287](https://github.com/joshuamyers22/mos-eisley/pull/287).
