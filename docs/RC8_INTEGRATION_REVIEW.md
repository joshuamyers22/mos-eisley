# rc.8 integration technical review

- Date: 2026-10-23
- Scope: review/platform `8cef1b4` combined with main `f31b4dd` and startup
  diagnostics `d3b5357`, versioned as rc.8 in `release/review-platform-preview`
- Context: same implementing agent; no independent review or release approval
- Guidance: adversarial review playbook, code/architecture review template,
  credential threat model and bounded verification loop
- Exclusions: real credentials, provider inference, sampling stores, owner sessions,
  Apple signing/notarization, general WSL2 support and stable launch

## Outcome and remaining gates

The source merge is conflict-free. Focused combined checks passed 134 tests with
no skips, including the four review fixtures that failed the earlier startup
branch wheel gate. This does not establish why that historical gate failed.
Lint/format, strict typing and five native-report validator tests passed.
Fourteen publication tests passed after correcting a candidate workflow defect.
The complete source (3,874 tests) and installed-wheel (2,851 tests) gates passed
with 17/13 skips and 86% coverage; audit then blocked on setuptools 84.0.0.
The isolated 84.1.0 security correction clears the direct 54-package audit; fresh
fixed-lock wheel checks also passed (2,851 tests, 13 skips), with a clean audit of
54 packages. Exact final-head CI remains required; results are recorded in the [work note](RC8_REVIEW_PREVIEW_WORK_NOTE.md).

## Trust and request traces

Optional credential transport runs only through trusted-host composition; current
CLI credential routes remain default. `network_credentials.py` checks actual OS
owner and exact reference/service/operation, native expiry and generation.
`credential_network.py` freezes endpoint policy, pins the full DNS answer set and
TLS hostname, uses no proxy/retry path, attaches the secret at socket write, and
rechecks dispatch authority and expiry after native resolution. Debug logging and
echo/error paths are covered by real local HTTP/TLS fixtures. This is local
synthetic boundary evidence, not new-provider live qualification.

Scoped review reconstructs exact canonical source bytes and checks owner,
workspace, complete scope and original brief through `review_source.py`.
Conversation preflight rechecks packet/configuration/campaign identity without
reserving funds or resolving credentials. The paid-capable child retains the
existing signed admission and separate interactive approvals, rechecks source
before credential use and before publication, and preserves consumed attempts
on cancellation. Recorded paths retain their prior contract.

Managed-worktree admission validates owner-controlled regular metadata pointers,
canonical paths, reciprocal `.git`/admin/common bindings, and retained device/inode
identities. It neither changes Git metadata nor grants integration authority.
Freshness/permission/helper-suppression tests include real Git repositories;
same-owner hostile mutation remains outside the documented trust boundary.

Ranked resume works over already admitted bounded metadata, preserves exact-name
ambiguity and locked selection, and adds no transcript reads. Session recovery
and `mos exec` retain the shared controller, workspace and spending checks. Startup
capture persists process status before output decoding/assertions and never sends
model text or retries; its metadata-only process fixtures reject inference.

## Findings and disposition

| ID | Evidence and consequence | Severity | Disposition and verification |
|---|---|---|---|
| R8-01 | Initial rc.7 upgrade step reused rc.5 output names, potentially overwriting its evidence. New immutable-predecessor regression failed on the collision. | High for release evidence | Corrected to separate rc.7 acquisition/output paths; all 14 publication tests pass. Full and tagged qualification remain required. |
| R8-02 | Native platform note still said pending after run `39881254556` passed; latest-download docs still named rc.3. | Medium documentation | Closed exact-candidate native evidence and identify published rc.7 separately from unpublished rc.8. Broader WSL2/release limits retained. |
| R8-07 | Historical CI selected the old harness checkout's obsolete signed metadata, which failed the unchanged artifact-source guard. | High provenance | Preserve current reviewed signed metadata before selecting the legacy harness. A metadata-source/dataflow regression and all 65 affected checks pass; expected pins/signatures/archives remain unchanged. Native CI repeats on the correction. |
| R8-06 | The mandatory audit reports GHSA-xmj3-9gf7-h52w in locked setuptools 84.0.0. | Blocking supply chain | Upgrade only setuptools to the upstream-fixed 84.1.0; direct audit of 54 packages is clean. 64 affected package tests and 2,851 fresh installed-wheel tests pass, with final static/export/build and audit checks. Application source is unchanged. |
| R8-05 | Actual rc.7 rejects new recovery journals in both stores, while release metadata still claimed epoch 1. | High rollback safety | Stop the original gate; propose epoch 2, preserve signed legacy epoch identity and forbid cross-epoch activation rollback. Four new boundary regressions and 64 focused checks pass. Native signed forward/refusal/backup evidence and accountable disposition remain required. |
| R8-04 | Native installer smoke omitted new exec/recovery entry points despite wheel coverage. | Medium qualification | Add real recorded frozen exec plus cold resume for snapshot/SQLite, including one terminal result and committed recovery metadata. Source CLI sanity and affected static checks pass; four native jobs remain required. |
| R8-03 | rc.7 Intel signed qualification took 36m15s with four predecessors; adding a fifth risks its 45-minute ceiling. | Medium delivery | Allow 75 minutes, keeping all platform, signature, state and upgrade checks. This changes CI allowance only. |

No change to product credentials, spending, default activation, study policy or
review quorum is justified or included. Exact combined checks, native artifacts,
real-predecessor upgrade/rollback evidence and accountable release disposition are
required before advertising the candidate as qualified or published.
