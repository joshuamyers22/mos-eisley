# rc.10 corrected-preparation predecessor control

- Status: local control gate passed; PR CI and actual rc.9 journeys pending.
  Owner: Joshua Myers; operator: Codex. Date: 2026-10-29.
- Frozen application source/tag remain `9ffd540674cc322857c05f09bcaf8dc816b3ff64`
  / `v0.1.0-rc.10`. No application, dependency, signing-key or artifact change.
- Parent integration: `b9bc4b20601a7c88af7ec6cdea57a92c11cabf88`, PR #339.

## Objective and concrete failure

Protected release run `40785649978`, attempt 1, passed all four native builds
but its preparation was approved before the candidate reached main. The tag
verification guard correctly rejected ancestry at `2026-10-28T23:24:15Z`.
Signing and signed-candidate upload were skipped. Retain that failed attempt;
do not relabel it as passing or change an immutable tag to bypass the guard.

After PR #339's required checks pass and its merge establishes ancestry, verify
the guard locally and rerun only failed preparation/dependents on the same
source/tag. The actual rc.9 predecessor qualification must admit that explicit
attempt 2, rather than the refused attempt 1. This control changes only the
workflow's attempt equality and its source-contract regression from 1 to 2.
Source SHA, tag, workflow ID, run ID, successful-prepare requirement, immutable
rc.9 identity, signatures, archive/bootstrap hashes and all state checks remain.

## Guidance, limits and evidence

Use repository AGENTS/CONTRIBUTING, bounded verification guide/loop, work-note
and threat-model guidance already selected in the
[qualification work note](RC10_SIGNED_QUALIFICATION_WORK_NOTE.md).
The risk is evidence substitution between failed and corrected preparation;
retain strict equality to the selected attempt and record both outcomes.
This host-only qualification control grants no signing, provider or publication
authority. Signing follows the owner's existing exact-candidate request and
protected custody; publication remains withheld.

One full local gate for this two-literal control batch, focused publication
contracts and required PR CI, within the existing four-hour per-gate bound.
Run it in parallel with the main integration/signing sequence. Stop on a new
unexplained failure or any changed source/artifact identity; do not broaden the
attempt predicate or silently start another run. Fresh subscription qualification
retains its separate 28-invocation/90-minute scope after signed native checks.

All 16 focused publication contracts passed. The full control `make check`
passed 3,889 source tests in 2,767.284 seconds (17 skips), 86% coverage,
export/build and 2,874 installed-wheel tests in 1,871.978 seconds (13 skips).
Ruff/format and strict Pyright passed. Both executable/test inputs match the
pre-gate hashes. Gate log SHA256:
`76393cc17a5cab9aa25fc2cd63c8e714f9c7f272dfea5d4dba2378600876a7f1`.

PR #339 merged normally at `fb4a35f50f9789f7d6edb7b30b3695f9f0fe2431`
after all 17 checks passed; its tree matches tested integration `b9bc4b2`.
The frozen source's local main-ancestry guard then passed. The failed-job retry
retained run ID `40785649978` and exact source/tag, advancing to attempt 2.
The enrolled owner approval advanced preparation before the operator's duplicate
approval request was processed; that request found no pending deployment and
was not retried. Preparation then passed, including ancestry verification and
protected signing. Three signed target jobs passed at the latest inspection;
Intel macOS remained in progress. No actual rc.9 upgrade is claimed yet.

The full-gate-tested control branch may run its read-only qualification while
PR CI runs; required CI remains mandatory before merging this control. Review
all actual receipts and signature/hash bindings before starting the fresh native
subscription campaign or considering publication.
