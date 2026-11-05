# rc.16 preview discovery work note

Status: source implementation and focused verification complete; full gate/CI pending. Owner: Joshua Myers; implementation/operator: Codex.
Started 2026-11-05 UTC; review by 2026-11-12 or before candidate signing.

## Objective, requirements and bounds

Resolve [R15-01](V1_PRODUCTION_READINESS_RC15.md) in a new rc.16 candidate:
read the actual bounded GitHub preview inventory and continue to authenticate
selected release metadata without changing installed state during discovery.
Product authority: plan §28; adopted Python engineering/agentic verification,
adversarial review and work-note guides, verification-loop and threat-model
framework at template pin 8879be48. Read current README/brief/memory, release
implementation/fixtures and protected qualification workflow before implementation.

Invariants: unchanged publisher key, TLS/endpoint/redirect policy, ten-release
selection, 128 KiB signed metadata cap, request/read deadlines, explicit install
confirmation, epoch-2 refusal and private-state/ledger preservation. Inventory
gets a separate 2 MiB cap (over twice the observed 914,579 bytes); it remains
untrusted hints. Oversize/invalid/unavailable inventory must fail closed. No
pagination, credential-bearing request, automatic retry or fallback origin.

Material release-boundary change: two evidence passes plus one correction pass;
three-hour engineering ceiling excluding combined checks. Zero provider calls,
new grants, private keys, security-setting changes, signing or publication.
No restricted evaluation-store access or evaluation eligibility claim. Historical
rc.15/readiness/live evidence and all campaign roots remain unchanged. Start from
readiness PR #366's head; resolve its dependency before candidate merge/signing.

Rubric: old-cap regression fails before fix and passes after; finite byte/record/
endpoint/deadline controls and signature/channel/epoch checks remain effective;
actual retained public feed passes offline and one fresh public lookup verifies
enrolled metadata; version/lock project metadata agree without dependency churn;
actual rc.15 predecessor is pinned for future protected qualification. Full
repository gate and normal CI precede release approval. Retain every first failure and diagnose offline before dependent work;
accountable owner review remains required.

## Threat and verification plan

Untrusted feed can amplify allocations, misdirect URLs, disguise drafts/stable
releases, supply malformed/deep JSON or unauthenticated metadata. Keep fixed
trusted URLs, finite read/record bounds and strict semantic tags; translate JSON
parse failures into ReleaseError. Fetch selected metadata under its smaller cap;
existing enrolled signature/channel/epoch validation remains authoritative.
Tests use synthetic data and real downloader with substituted transport, not a
mocked release_metadata success. Exact historical public bytes remain ignored
engineering fixtures. No source/API inventory is treated as signed publication.

## Evidence and handoff

[Candidate correction and affected-qualification runbook](RC16_PREVIEW_DISCOVERY.md)
records the change and rollout boundary. Signed/public candidate qualification,
actual installed discovery/notice/upgrade/restart and owner acceptance remain
separate gates; this source change cannot alter already published old clients.

| Pass | Evidence / result |
|---|---|
| Reproducer and focused correction | Original oversized-feed test fails at the old cap. Separate 2 MiB inventory cap and controlled JSON-error translation pass nine actual-downloader tests. Three distribution cases prove discovery through notification/confirmed fixture upgrade, tampered signature refusal and invalid-feed failure; full distribution suite passes 45 tests. |
| Boundary/workflow review | Existing downloader, redirects, signature/channel/epoch parser and installer AST/bytes unchanged; external lock records/runtime export identical. Actual rc.15 predecessor/source/release pinned in protected workflow and qualifier; all 18 publication/workflow tests pass. |
| Independent evidence source | Exact historical 914,579-byte public feed replays offline and selects genuine rc.15 metadata; one fresh bounded source lookup verifies enrolled signature, exact source and metadata hash. No provider or installed-state action. |
| Focused validation | Version/lock consistency, unchanged trust/install/live paths, byte-identical dated assessments, links/anchors and whitespace pass. Combined gate has passed lint/format/types and is still running source tests; no final gate result is asserted yet. |

First failures remain in ignored logs. The initial new-test run contains the
intended old-cap failure plus tests referencing the not-yet-added cap. One
post-fix deep-JSON assertion demanded an overly specific error label even when
production already returned ReleaseError; the fixture now checks the actual
controlled-refusal contract and includes deeper nesting. Initial distribution
fixtures assumed `notify` was present without a valid cached release; the established
optional field is now checked without weakening the original cached-result test.
The first direct type invocation selected the host environment and reported
missing third-party imports; the project interpreter exposed two test-only issues
(an untyped empty dict and private-helper access). Typed fixtures and public
endpoint/deadline tests correct them; actual `uv run` type checking passes with
zero errors. None of these errors was relabeled a first-attempt pass or used to
weaken product signature/resource controls.

The 2 MiB cap is deliberately separate and finite. A larger future inventory
still reports unavailable; this fix does not promise discovery across all release
history or remove GitHub availability/rate limits. Its unsigned hints cannot
replace final enrolled signature/channel/platform/epoch validation.

Implementation review is the operator's assessment, not independent human release
approval. Owner review, #366 dependency resolution, required CI and new protected
signed/public acceptance are still required before publishing rc.16. No tag,
release, grant, key, uncertain ledger, old campaign root or security setting changed.



## Retained evidence bindings

Ignored `.work/` records are ordinary engineering evidence, not sampling artifacts.
The initial failed logs are preserved alongside passing focused results. The
combined `.work/make-check.log`, `gate-inputs.json` and eventual `gate-result.json`
retain full-gate exit/duration/input identity independently from this note.

| Record | SHA256 |
|---|---|
| `before-fix.log` | `18481f5f5ac74e6c74d3912c42cf627fcc0c5ce16b37754dacf51787e7da2c4e` |
| `after-fix.log` | `8ffd8405b6568a7daa3b33964c8f77551123dfb4bda9259b14a0bf9d76271be6` |
| `discovery-tests-final.log` | `ca76ae23d74a4f8311220fb98bf9133410292fe2127b0b3238e002043c23db77` |
| `publication-tests.log` | `590dec7680ea2ecfab500b9ceac0c94db6098c713cabc86380547573c4f82f57` |
| `public-discovery-review.json` | `5cbdb046edbbe070ed13d7a4c19db32c6e22841b40138ff7657b47d97e1e5f15` |

A broad attempt to restore the preexisting notification assertion also changed
one legacy-epoch test. Its failed focused run exposed the mistake; the entire
preexisting test prefix is now restored byte-for-byte, with only the three new
cases inserted. The full-gate attempt was explicitly interrupted after 322.980
seconds when its input snapshot became invalid (exit -2, inputs unchanged=false).
`make-check-attempt-1.log`, `gate-attempt-1.json` and
`gate-inputs-attempt-1.json` preserve that attempt. The restored 45-case suite
passes. A new combined run uses a fresh frozen input set; the interrupted run is
not counted as a passing gate.

Passing restored distribution-suite log SHA256:
`d34bfd203228e2701b4951255bed2975ad72a4d9e55bffefff9f257de00cd695`.
