# rc.13 signed diagnostics qualification review

- Status: signed distribution and offline diagnostics passed; the single fresh
  Claude diagnostic completed. Full installed live-workflow acceptance remains
  incomplete.
- Reviewed 2026-11-01 UTC. Owner Joshua Myers; operator Codex. Author/operator
  overlap is disclosed and does not establish independent human review.
- Selected guidance: the repository bounded-verification guide, work-note and
  threat-model templates. Preserve signatures, finite grants, one-use ledgers,
  redaction and every historical uncertain call. No new campaign or publication
  approval follows from these engineering receipts.

## Exact candidate and delivery

Frozen source `8c7690733af1bbc4861911d2c0a2a516961985da`, version
`0.1.0-rc.13`, storage epoch 2; annotated tag object
`2738bf094b5e071803267870cedfca89b5efe667`.
[PR #353](https://github.com/joshuamyers22/mos-eisley/pull/353) passed all 13
checks on corrected head `01a4af2` and merged normally as `c415765`.
[Integration PR #354](https://github.com/joshuamyers22/mos-eisley/pull/354)
passed all 17 checks on exact head `ec54f12` and merged normally as
`0603949213033ede2c052227deb8f8696de1b14e`. Candidate ancestry in main and
tag/version equality were verified before tag push. Main retains its newer
dependencies and SDK-2 adapter; the release retains rc.12 dependencies and the
compatible SDK-1 adapter.

The [delivery work note](RC13_DELIVERY_WORK_NOTE.md) preserves the original
interrupted candidate full gate and failed wheel retry. Candidate source passed
3,911 tests (17 skips, 86% coverage). After correcting the isolated-wheel helper
registration, its complete wheel stage passed 2,898 tests (13 skips); runtime
wheel bytes stayed unchanged. All required stages passed after that disclosed
recovery; the original interrupted invocation is not reported as passing.
The main integration's combined `make check` passed, exit 0: 3,912 source tests
(17 skips, 86%) and 2,899 isolated-wheel tests (13 skips), with all 862 input
hashes unchanged in 4,985.357 wall seconds.

## Protected signing, installation and upgrades

[Protected Release run 41342968889](https://github.com/joshuamyers22/mos-eisley/actions/runs/41342968889),
attempt 1, built the exact source. Secret scanning, all four native builds,
protected preparation's `make check audit`, container checks and signing passed.
The operator submitted the owner's explicitly authorized preparation/signing
approval after fresh exact-source/tag/run and four-build checks. No operator
publication approval was submitted.

All four signed qualification jobs passed. Strict report review verified:

| Evidence | Passed |
|---|---:|
| Signed native installations | 4 |
| Both-store installed matrices, including cold resume, terminal/diff and recovery | 4 |
| Actual rc.1/2/3/5/7 upgrade/refusal journeys | 20 |
| Actual rc.9/10/11/12 same-epoch upgrade/rollback journeys | 16 |
| Generated macOS formula journeys | 2 |
| Signed offline native-progress matrices | 4 |
| Total reports | 50 |

Each target verified the exact signed source, version, epoch, metadata, archive
and bootstrap identities. The rc.7 cross-epoch downgrade refusal remains intact;
same-epoch journeys retain candidate-written state, cold resume, recovery,
tamper refusal and uninstall checks. The complete offline qualification used
zero provider invocations.

Each progress matrix ran four fake shell clients under private HOME and an empty
child PATH without host Python/Node: silence; observed stdout/stderr followed by
a wait; closed streams with the leader still waiting; and an exited leader whose
descendant retained the pipes. Fixed redacted progress, cleanup, EOF/leader
observations and refusal to replay the failed attempt passed. No fixture output,
client path or credential enters a progress receipt.

The owner separately published [immutable release 430907808](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.13)
at `2026-11-01T22:43:52Z`. All 67 public names, sizes and digests match the
qualified inventory; GitHub immutable attestation verified. Publication occurred
before the diagnostic completed and is recorded as observed, not withheld.

## One fresh bounded Claude diagnostic

The actual signed macOS arm64 build was privately installed with updates disabled.
Its native SHA256 is
`ac451013db692d8b8b11171120a6afcf0c12033a1cb9ede03c4d713b8c1270c7`,
matching the signed qualification report. Fresh installed readiness confirmed
the supported signed-in Claude Code 2.1.283 before creating the new grant.

The separately authorized host controller used the exact frozen candidate source
and existing synthetic implementation-review packet under a new grant/workspace
and usage root. This is a source-orchestrated native diagnostic, not a complete
installed coding workflow or continuation of rc.12. Actual HOME/native credential
selection stayed fixed; API keys were absent. Limits were one invocation,
Sonnet 5/high, 60-second native deadline, 128,000 input bytes, 16,000 text output
bytes, 8,192 reported output tokens, a 20-minute grant and a 120-second outer
wall/monotonic ceiling. Native billing/internal retries remain unverified.

The call completed at `2026-11-01T22:46:33.980716Z` in 55.840 monotonic /
55.841 wall seconds: one reservation, one native dispatch, one native completion
and one completed usage record. The synthetic critic decision was `accept`.
Reported output was 5,426 tokens. No retry, replacement scope, API fallback,
response repair or deadline increase followed. No raw response text is committed.

Progress metadata is attached to controlled failures. This successful call
produced no failure-progress receipt; the four-target offline matrices qualify
that failure path. Success does not reveal the historical timeout's cause or
establish general reliability. All 121 retained rc.12 campaign files outside
nested Git internals have identical names and hashes; the earlier uncertain
slot remains closed, without a completion or replay. Candidate source and
diagnostic harness hashes remained unchanged.

## Evidence and remaining work

Private evidence remains in the candidate worktree's `.work/rc13-evidence/`:
protected run/jobs, signed publication and qualification artifacts,
`receipt-review.json`, public inventory/attestation, private installation proof,
and the one-call `claude-diagnostic/diagnostic-review.json`. SHA256 of the combined
signed report review is
`18df528fcd0deef4676e2e40580400390791497572822a601bb03a9b38991dc6`.
The canonical diagnostic request and response are bound by hashes in that private
review. Prompts, native output, grants and credentials stay out of Git. These are
ordinary engineering receipts; no sampling registry, custodian mapping, label
store or outcome store was read, and no evaluation eligibility is claimed.

The authorized four-step delivery is complete. A subsequently authorized
[fresh installed live-workflow campaign](RC13_INSTALLED_LIVE_QUALIFICATION_REVIEW.md)
stopped at another Claude implementation-critic deadline (RC13-SUB-01), with
11 dispatches, 10 completions, no integration and SQLite zero. Its new progress
receipt records stdout data near the deadline, open streams, a running leader
and completed cleanup. Both campaigns remain closed. The one-call success
does not close either campaign's missing integration or SQLite cases.
Conversational `/review`, npm/tap routes, WSL2/native Windows and stable/public
launch retain their existing independent qualification gates.
