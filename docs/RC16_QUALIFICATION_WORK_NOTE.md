# rc.16 owner review, signing and affected qualification

Status: active. Owner: Joshua Myers; operator: Codex. Started 2026-11-05 UTC.
Review by 2026-11-12 or before publication. Frozen candidate remains
`14eb79d52950f340aba159815222e04e6ea864e3`, version `0.1.0-rc.16`, epoch 2.

## Authority, review and bounds

The owner explicitly requested review and merge of #366 then #367, protected
signing and affected rc.16 qualification. Selected guidance: AGENTS, publisher
preparation/handoff, Python engineering, agentic verification/adversarial guides,
threat-model, verification-loop and work-note templates. Review covers bounded
unsigned discovery, unchanged signed metadata/trust/install boundaries, exact
artifact/source identity and first-failure preservation. This is an owner-directed
operator review; no independent human security attestation or stable approval.

Six-hour operation window, one immutable tag/protected run, one signing approval,
no workflow retry after an unexpected failure and zero provider calls/new grants.
Keep publication pending, protected custody unchanged and all old campaign/state/
ledger/evaluation stores untouched. Receipts are ordinary release engineering
records and confer no evaluation authority. No private key or raw provider output
is accessed. A supplementary qualification harness has its own reviewed identity;
it cannot change frozen runtime source, tag, binaries or published predecessors.

## Completed source review and merges

#366 merged normally as `3344c8f5bfafe0804d5d4dd55314b853f3541a1f` after all
14 head checks. #367 was retargeted to main and merged normally as
`b3a239a5b1bb9ec8efd8898dfd9e5201adda0dbf` after all 18 checks. Its tree equals
the frozen source and preserves that source in main history. Source gate passes
3,960 tests (17 skips), 86% coverage and 2,919 wheel tests (13 skips), exit 0;
all 876 frozen inputs unchanged. Original test/host-interpreter errors and the
interrupted attempt remain preserved in the preparation records.

Annotated tag `v0.1.0-rc.16`, object
`cdcb8240b84de4d909d345e35a08654064763535`, passed metadata/mainline checks and
started [protected run 42102119299](https://github.com/joshuamyers22/mos-eisley/actions/runs/42102119299),
attempt 1. A local tag preflight accidentally used host Python 3.9 without
tomllib and failed before creating any tag; the subsequent absent-tag check also
failed. Project Python 3.12 corrected the invocation; exactly one tag was created
and pushed. Neither failed preflight is a passing check or signing attempt.

## Affected evidence and supplementary harness

The frozen protected workflow repeats four-target signed install, both-store
offline matrices, all twelve actual predecessors including rc.15 and rc.7
cross-epoch refusal, six-case native diagnostics and actual SBOM admission.
Expected base: 62 reports/80 prepared assets; actual counts must be reconstructed.
No general stable, WSL2, cask/manager publication or live-workflow equivalence is
implied. rc.14's live evidence stays historical.

Supplementary real signed-binary discovery needs a separately reviewed four-target
workflow. It must authenticate the exact protected preparation and four signed
jobs before executing any artifact. Use actual untouched publisher-signed rc.15
and rc.16 bootstraps/archives in a private disposable HOME/root, preserve synthetic
state and the old failed-cache bytes through explicit offline installer upgrade,
then force actual native public discovery. Verify enrolled current public metadata,
candidate version, source/artifact hashes, unchanged pointer/sentinel and cleanup.
Old-client refusal is a declared expected case; no fabricated future release or
same-version lookup is called a guided upgrade/restart qualification.

## Verification / handoff

Pending protected and supplementary results. Keep original failures visible and
separate runtime candidate, harness, API observations and actual report identities.
No final publication approval is authorized by this task.


The separate read-only harness is implemented with six passing offline challenges:
real enrolled-style signatures and archive/bootstrap hashes, wrong identity,
signature/archive/bootstrap/manifest substitution, wrong host/harness refusal
before native execution, isolated child environment/deadline/output checks with
no retry, and fixed redacted failure reasons. Explicit harness pyright passes
with zero errors. Initial lint/type findings were an unused import, long fixture
URL and nested fixture contexts; all were corrected before the combined gate.
Workflow YAML and embedded Python compile; native matrix jobs are dispatch-only
and are not credited as executed by PR checks. The combined repository gate for
this separate harness is running with a frozen input snapshot.


Static review before any signed native dispatch caught a harness contract error:
the bootstrap emits a human confirmation, not JSON. The added seventh offline
case reproduced JSONDecodeError. Bounded execution is now separate from the CLI
JSON decoder; all seven harness tests and explicit pyright pass. The first
combined harness gate was interrupted when its input snapshot became invalid,
and its log/result/inputs remain under attempt-1 names; it is not claimed as a
passing gate. A corrected combined gate and exact-head CI are required. Runtime
source/tag and the protected signing run are unchanged; no native qualification
attempt has yet executed through this supplementary workflow.

Original bootstrap-contract regression SHA256: `2a33ec0d225d43727b26fc0471c6ee84747437f6526d3f001e0a4b1c5f1196c6`.
Passing seven-case log SHA256: `582e846322891f296a63a40b9d15eab87592c5ed25fac4581280e05ea8e92873`.
