# rc.14 qualification evidence review

Disposition as of publication: the owner accepted the completed qualification;
[immutable rc.14 is published](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.14)
as release `434439039`. Signed/offline qualification passes all four
macOS/Linux targets; combined installed live evidence passes both stores on
macOS arm64. The original controller's exit 1 remains preserved and disclosed.
See [owner acceptance and public verification](RC14_PUBLICATION_WORK_NOTE.md).

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

## Installed snapshot evidence and original stopped boundary

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

At the original stop, SQLite had zero reservations, dispatches and completions.
Its untouched grant expired during the audit. No continuation or renewal of that
scope followed; it remains unchanged. The owner subsequently authorized a fresh
SQLite-only scope, as recorded below.

## Fresh SQLite-only qualification and combined review

After the owner approved the concrete SQLite-only proposal, a separate new scope
used at most 14 calls, the same 120-second/8,192-token profile, a one-hour grant,
45-minute wall/monotonic ceilings, 600-second coding wall and zero corrections.
Its native readiness was checked immediately before authorization. No snapshot
scope was repeated and no original grant or uncertain slot was reopened.

The SQLite controller exited 0 in 224.556 monotonic / 224.543 wall seconds. It
completed chat, steering, cold resume, contextual follow-up, provider-diverse plan
review, creator approval, child implementation, candidate tests, implementation
review, exact creator approval before integration, source-only integration and
fresh integrated tests. Both stores' fresh integrated execution receipts report
three tests, exit 0, no failures/errors/skips and unchanged frozen test files.
Post-coding cold resume passed without replay. Planned cancellation removed the
owned native process group; subsequent resume refused before conversation opening
and made zero additional calls. The corrected assertion verified the exact
missing-completion guard without weakening the CLI's redaction.

SQLite's six ModelReview artifacts are valid and subject-bound. Both phase judges
accepted, and creator approvals match their exact subjects and judge hashes.
Its four actual coding workers are independently absent. Claude plan review
completed in 36.338s (valid result 36.123s, EOF 36.330s); implementation review
completed in 34.664s (valid result 34.454s, EOF 34.655s). These are two additional
observations under the qualified profile, not a general latency guarantee.

The final read-only combined reconstruction passed: 28 total dispatches, 26 native
completions and two deliberately cancelled uncertain slots, with 14/13 per store.
It revalidated all twelve ModelReview artifacts, exact approval order, source-only
integration, protected tests/sentinels, fresh integrated tests, eight absent coding
workers, all 54 signed report hashes, installed/source identity and harness hashes.
All nine historical roots and the entire original rc.14 campaign root remain
unchanged, including its unused SQLite grant and failed controller. No further
inference, renewal, repair, model substitution or automatic retry occurred.

The combined evidence closes both-store installed live acceptance for this exact
candidate on macOS arm64. Four-target signed/offline qualification remains a
separate, passed scope. The original aggregate controller remains nonpassing;
RC14-HARNESS-01 is closed by exact offline diagnosis and the successful fresh
SQLite cancellation/refusal check. No runtime change or replacement candidate is
indicated. Owner acceptance and protected publication subsequently completed;
see the publication work note.

## Evidence retention and publication gate

Private evidence is under the frozen candidate's `.work/`; no raw native content,
authorization grants or credentials are copied into this tracked review.

| Evidence record | SHA256 |
|---|---|
| `rc14-live-closeout-review.json` | `15ac6053b01b26ce51968bbf3fe752868b3001a1be345e66c9e41e7ece09e130` |
| `rc14-stop-boundary-review.json` | `b1252ae4fb95e6254efd440d47ced52c95a75c39cf22adedff95a7e71389e832` |
| `refusal-harness-correction-review.json` | `1090087545937ed77f20242c88c7fa6360297f8c949e972ffea759971ec695da` |
| `rc14-sqlite-harness-review.json` | `0c25da4abbf73641145b08f3f5040ccc39704cbb6a223266c3b17338e05179b7` |
| `rc14-sqlite-qualification/subscriptions/summary.json` | `12cd5b0fb7f3662a4bb5431f12a80f68f8727df2c10b2dd3aa10250692e7e88f` |
| `rc14-combined-live-review.json` | `773eb9dd6eb1d29e40d209a7ae6ada8bcad130ba23724b131d891e2a068ac6a5` |

The read-only closeout rechecked all 54 signed report hashes, frozen inputs,
installed files, original harness bindings, review/approval artifacts, removed
containers and all nine historical evidence roots. Original rc.14 scope bytes
also remained unchanged. It made zero new grants and zero provider calls.

The fresh SQLite-only harness refused absent explicit authority during offline
preparation; the owner then authorized exactly that bounded run. The successful
summary and combined reconstruction above supplement the original failed
controller without replacing or modifying it. The [qualification contract](RC14_QUALIFICATION_WORK_NOTE.md#budget-and-stop-rules)
continues to prohibit grant renewal and replay. No additional inference is
needed for this campaign. The owner subsequently accepted
this exact evidence and the protected gate published it, as recorded in the
publication work note.

This owner-directed operator review is not an independent human security or
release attestation. Ordinary engineering receipts confer no evaluation
eligibility. Stable v1, general subscription reliability and broader launch gates
remain separate.
