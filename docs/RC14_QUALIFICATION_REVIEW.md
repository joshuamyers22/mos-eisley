# rc.14 qualification evidence review

Disposition as of 2026-11-04: signed distribution and offline qualification pass;
the snapshot installed live workflow is evidenced through integration and fresh
tests. Full both-store live qualification remains incomplete. The original live
controller stopped with exit 1 at a host assertion after planned cancellation;
SQLite made zero calls. Publication approval has not been submitted. GitHub's
release-by-tag endpoint returned 404 during this review.

## Frozen identity and candidate gate

The owner requested merged source `11fe46514e7962731023538fc50789c8b9d7fd45`.
Version-matching immutable tag `v0.1.0-rc.14` targets candidate
`ec3211e23c4a3e2b20837114e707bc8ebcbe625a` (epoch 2), with annotated tag object
`f6cf41ac138dd3b1020864510ca4b21440bdae53`. [PR #359](https://github.com/joshuamyers22/mos-eisley/pull/359)
merged normally after all 17 checks, as
`0c1bcfdaa09ddf862bb5ef33fb7dbc7afe0fdc2b`; its tree equals the candidate tree.
The candidate is preserved in main's history. Main's current SDK-2 dependencies
and runtime export were retained; no earlier dependency snapshot was substituted.

One combined `make check` passed: 3,929 source tests (17 skips, 86% coverage),
2,916 installed-wheel tests (13 skips), lint, formatting, types, export and builds.
Elapsed 5,100.757 monotonic / 5,100.747 wall seconds was below both four-hour
ceilings. All 866 frozen non-Markdown inputs remain unchanged. Log SHA256:
`78afbf400779601a1b677b175ee426ad25be8e96933ab5caf8dc363243a56058`.

The first expanded fake terminal fixture omitted required thinking metadata and
failed strict validation. Its corrected fixture passes the real parser and
focused tests; the original failed log remains retained. This is fixture repair,
not relaxation of native protocol validation.

## Protected signed qualification

[Protected release run 41699667393, attempt 1](https://github.com/joshuamyers22/mos-eisley/actions/runs/41699667393)
passed all four native builds, secret scanning, protected preparation and all four
signed qualification jobs. The operator approved preparation only after checking
the exact tag/source/run/environment. Signing keys stayed in protected custody;
no tag or asset was retargeted and no administrative bypass was used.

Independent receipt reconstruction admitted 54 reports and 71 prepared assets:

| Check | Actual evidence |
|---|---|
| Signed installation | Four targets: macOS arm64/x86_64, Linux arm64/x86_64 |
| Installed offline acceptance | Four matrices, both storage backends; cold resume, terminal/diff and recovery |
| Actual predecessor journeys | 40 total: rc.1/2/3/5/7 cross-epoch refusal and rc.9/10/11/12/13 same-epoch journeys on all four targets |
| rc.7 downgrade refusal | Refusal before pointer/state changes; readable retained backups and continued candidate operation |
| Offline native diagnostics | Four matrices, each with silence, output wait, exit wait, inherited pipe, valid-result wait and invalid-result wait; replay leaves failure/event receipts unchanged |
| Generated formula | Two actual macOS journeys |

The ModelReview rejection corpus in these reports is explicitly exact-candidate
source evidence, not the installed binary's complete live review path. Snapshot's
fresh live evidence below exercises that installed path.

Signed receipt review SHA256:
`e5db0ffd036cbd646c6724dde30a549376eb5a9107c0cf26e9492df689d4bb3b`.
Signed release metadata SHA256:
`7c74c6668ef707b4ffd12a69db12d95e633d9a710ec2b9fb8de6f06203948d3d`.
Actual rc.13 predecessor release `430907808` is pinned to source
`8c7690733af1bbc4861911d2c0a2a516961985da`; all ten predecessors' enrolled
metadata/checksum bindings were verified. The reports required zero provider calls.

## Installed live evidence and stopped boundary

The actual signed macOS arm64 executable SHA256 is
`9f2651de14244fd0d46bf620b35797118c83d1a9ab3315e8d3790e2b4c931405`.
All 418 installed runtime Python files match frozen source. The worker image is
`sha256:a0e21a0c251972e3e87f05a6406269f1804c6e879863d6598e2f6326c67f5c9a`.
Its build succeeded; the first host verifier expected normalized package-version
spelling rather than the literal project version. The corrected verifier checked
the same image, source labels, all runtime hashes and native version; no rebuild
or silent substitution occurred. Actual signed guardian/owned-worker removal and
invalid lease checks passed before inference. The deliberately broken baseline
fails its actual tests as intended; that baseline is not described as passing.

Fresh native readiness passed for pinned Codex 0.163.0 and Claude 2.1.283, using
client-owned subscription credentials. The campaign kept exact role/model/effort
bindings, 120-second deadlines, 8,192 reported output-token limits, one-hour
grants, zero correction cycles and the declared stop rules. No API fallback,
model substitution, automatic retry, grant renewal or response repair occurred.

Snapshot completed chat, queued steering, unavailable inspection without dispatch,
cold resume without replay, contextual follow-up, provider-diverse plan review,
creator plan approval, implementation, candidate tests, implementation review,
creator approval of the exact accepted candidate before integration, source-only
integration, fresh integrated tests and post-coding cold resume. Protected tests
and the sentinel were preserved. Six installed ModelReview validation receipts
are valid, subject-bound and issue-free; both judges accepted and both creator
approvals match their subjects/judges. All four actual coding containers are
independently absent.

Claude's plan and implementation critics completed in 38.285s and 40.511s.
Valid terminal results appeared at 38.010s and 40.263s, with EOF at 38.277s and
40.502s. Neither reproduced the historical timeout or invalid ModelReview boundary.
These two observations do not establish a general latency percentile or repair
missing historical native content.

The final planned owned cancellation consumed snapshot slot 14 and retained its
uncertainty: 14 reservations/dispatches, 13 native and usage completions. Resume
correctly exited 2 before conversation opening or dispatch. The host assertion
expected older, unredacted missing-completion wording; the CLI intentionally
reported a redacted missing-artifact error instead. This is RC14-HARNESS-01.

A read-only post-stop check traced the refusal to the exact saved-usage guard:
missing `completion.json` for cancelled slot 14 (`chat-0004`). Fingerprints and
counts did not change. A separate corrected harness checks exit 2, no opened or
running conversation, the redacted boundary, and that exact read-only guard. Its
offline controls reject unrelated missing artifacts, absent guard failure and
wrong exit/opened-conversation cases. The original harness, stopped controller,
ledgers and failed output remain unchanged; its exit 1 is not relabeled a pass.

SQLite has zero reservations, dispatches and completions. Its untouched grant
expired during the audit. No continuation, renewal, retry or further inference
followed the global stop. Full both-store acceptance remains open.

## Evidence retention and next admissible work

Private evidence is under the frozen candidate's `.work/`; no raw native content,
authorization grants or credentials are copied into this tracked review.

| Evidence record | SHA256 |
|---|---|
| `rc14-live-closeout-review.json` | `15ac6053b01b26ce51968bbf3fe752868b3001a1be345e66c9e41e7ece09e130` |
| `rc14-stop-boundary-review.json` | `b1252ae4fb95e6254efd440d47ced52c95a75c39cf22adedff95a7e71389e832` |
| `refusal-harness-correction-review.json` | `1090087545937ed77f20242c88c7fa6360297f8c949e972ffea759971ec695da` |
| `rc14-sqlite-harness-review.json` | `0c25da4abbf73641145b08f3f5040ccc39704cbb6a223266c3b17338e05179b7` |

The read-only closeout rechecked all 54 signed report hashes, frozen inputs,
installed files, original harness bindings, review/approval artifacts, removed
containers and all nine historical evidence roots. Original rc.14 scope bytes
also remained unchanged. It made zero new grants and zero provider calls.

A fresh SQLite-only controller is prepared and checked offline. It refuses absent
explicit new authority, creates no snapshot scope, and leaves the stopped original
scope untouched. Proposed limits: at most 14 native calls (28 task total including
snapshot), the same 120-second/8,192-token profile, one-hour grant, 45-minute wall
and monotonic ceilings, 600-second coding wall, zero corrections/retries/renewals,
and global stop on the first unplanned failure. No fresh scope or grant exists.
New owner authorization is required because the original grant expired and the
[qualification contract](RC14_QUALIFICATION_WORK_NOTE.md#budget-and-stop-rules)
forbids renewal and requires stopping globally. Do not repeat snapshot or reopen
any historical uncertain slot. No candidate runtime change is indicated by the
host assertion defect. Review combined evidence after SQLite before publication.

This owner-directed operator review is not an independent human security or
release attestation. Ordinary engineering receipts confer no evaluation
eligibility. Stable v1, general subscription reliability and broader launch gates
remain separate.
