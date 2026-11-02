# rc.13 installed live-workflow qualification: RC13-SUB-01

- Status: stopped at the declared failure rule; full installed live acceptance
  remains incomplete. Reviewed 2026-11-02 UTC.
- Owner Joshua Myers; operator Codex. This was the owner's newly authorized
  full subscription campaign, separate from the earlier successful one-call
  diagnostic. Author/operator overlap is disclosed.
- Frozen application: `8c7690733af1bbc4861911d2c0a2a516961985da`, rc.13,
  storage epoch 2, actual signed macOS arm64 installation.
- Contract: [fresh installed campaign work note](RC13_INSTALLED_LIVE_WORK_NOTE.md).
  [Signed qualification and public inventory](RC13_QUALIFICATION_REVIEW.md)
  remain passed and unchanged.

## Preparation and authority

The fresh private signed installation matched native SHA256
`ac451013db692d8b8b11171120a6afcf0c12033a1cb9ede03c4d713b8c1270c7`;
all 416 installed runtime Python files matched frozen source. Updates were
disabled. All 50 signed reports and 67 immutable public asset identities were
rechecked before new grants. Fresh installed readiness confirmed Codex 0.163.0
and Claude Code 2.1.283, preserving actual HOME and existing CODEX_HOME with
API keys absent.

A fresh exact-source immutable worker image was built:
`sha256:95ddc54fb9b002ddf286bba5e6a5b9a7b2f2a0026a7cb1f87b05ebc480174332`.
Its version and all 416 runtime file hashes matched the candidate. Preparation
retains the failed final image-ID-file write and the verifier's incorrect
normalized-version expectation; correcting those host record/expectation issues
changed no image or application bytes and dispatched no provider call.

The actual signed guardian's unpaid probe verified its bound execution receipt,
rejected a 306-second lease and `--all` container identity before arming, and
proved exact container removal. Its unimplemented synthetic baseline correctly
failed three tests; this was not relabeled as passing code. No host Python/Node
was available on that signed guardian's child PATH.

The single fresh campaign began at `2026-11-01T23:30:50.891327Z`. It retained
the established profile: Sol/medium for chat, creator and child; Terra/medium
and Sonnet 5/high for independent critics; Astra/medium for judge. Limits were
14 invocations/store, 28 total, one-hour grants, 90-minute wall/monotonic ceilings,
60-second native deadlines, 128,000 canonical input bytes, 16,000 text output
bytes, 8,192 reported output tokens, 600-second coding walls and zero correction
cycles. No API fallback, model substitution, deadline increase, grant renewal,
response repair, retry or failed-session replay was authorized or performed.
Native billing/internal retries remain unverified.

## Results before the global stop

| Case | Snapshot | SQLite |
|---|---|---|
| Fresh signed installation/readiness and workspace preparation | Passed | Passed |
| Chat, queued steering, unavailable inspection without dispatch | Passed | Not run |
| Cold resume without native/Git replay | Passed | Not run |
| Contextual follow-up after resume | Passed | Not run |
| Both plan critics and judge | Accepted | Not run |
| Creator approval of exact plan and adjudication | Passed before child dispatch | Not run |
| Candidate implementation tests | 3 passed, no errors/failures/skips | Not run |
| OpenAI implementation critic | Accepted | Not run |
| Claude implementation critic | Native output-phase deadline | Not run |
| Implementation judge and creator approval | Not reached | Not run |
| Integration and fresh integrated-tree tests | Not reached | Not run |
| Post-coding resume and planned cancellation/refusal | Not reached | Not run |

The candidate execution receipt binds `tests/test_adder.py` and the fresh creator
test `tests/test_mos_add.py` to the exact frozen source/test package. It reports
exit 0, three tests, zero failures/errors/skips, unchanged files and 231 output
bytes. These passing candidate tests do not supply missing implementation
adjudication, creator approval, integration or post-integration evidence.

Snapshot reserved and dispatched 11 calls; 10 completed. The eleventh was the
Sonnet/high implementation critic, coding call 08, and remains uncertain.
SQLite reserved/dispatched zero calls. The first unplanned failure stopped the
whole campaign, preserving the unused 17-call capacity. Neither of the planned
controlled-cancellation cases was reached; this uncertainty is an unplanned
failure and does not satisfy those cases.

## Bounded redacted progress

The native failure is `native_process` / `deadline`, configured for 60 seconds,
with adapter elapsed 60,221 ms and pre-cleanup progress elapsed 60,002 ms.
Its strict schema-1 receipt records:

| Observation | Value |
|---|---|
| Phase at deadline | `output` |
| Local stdin drain completed | Yes |
| Stdout bytes observed | 10,627 |
| First / last stdout read | 425 / 59,058 ms |
| Stdout EOF | No |
| Stderr bytes / EOF | 0 / No |
| Leader exited before cleanup | No |
| Owned cleanup completed | Yes |

Thus this fresh attempt was not silent or waiting for local stdin drain: stdout
was still being observed near the deadline, while stream completion and leader
exit had not occurred. Counts and timings do not identify event contents, a
completed final response, native internal retries, or the reason the client had
not finished. No partial output is reconstructed. This receipt does not backfill
the historical rc.12 timeout's missing progress or establish the same cause.

## Cleanup and preservation audit

Read-only audit verified both live worker containers were bound to their actual
leases, removed once and independently absent. The campaign launcher is absent.
The native receipt reports completed cleanup. Both synthetic workspaces retain
their original Git HEAD, clean status, source, protected tests and sentinel;
integration-started/applied-commit/completion records are absent.

All 862 candidate input hashes, native binary and frozen harness hashes are
unchanged. Every prior campaign's file fingerprints and recorded Git state
remain identical: rc.9, both rc.10 attempts, rc.11, rc.12 and the earlier rc.13
one-call diagnostic. The rc.12 uncertain call stays closed and unchanged. No new
scope was created after the stop and no session was resumed for a retry.

Private records are under this worktree's `.work/rc13-live/`, with immutable
harness/provenance records under `.work/`. The stopped campaign contains 123
retained files outside nested Git internals, with aggregate SHA256
`f9390c382ef2b45e2771f0c9323ea60342e17f783088484d00de2e68e6f73311`.
`stopped-campaign-review.json` binds the clamped native request hash, test receipt,
failure progress, cleanup and preservation results. No prompts, grants,
credentials, raw native output or model responses enter Git. These are ordinary
engineering receipts; no prospective sampling registry, custodian mapping,
label store or outcome store was read and no evaluation eligibility is claimed.

The next blocker is Claude's output-phase completion under the admitted
60-second profile. Investigate that boundary before another separately
authorized campaign; do not resume this stopped scope, spend its unused capacity,
widen its timeout or reinterpret the earlier one-call success as full acceptance.
The signed four-platform offline qualification remains passed. Full installed
live-workflow, stable/v1 launch and other distribution/platform admissions remain
open.
