# rc.10 signed qualification review

- Status: signed distribution qualification passed; installed live-workflow
  qualification incomplete (RC10-SUB-01). Assessment closed on 2026-10-29 UTC.
- Accountable owner: Joshua Myers; technical operator: Codex. Owner/operator
  overlap is disclosed; this is not independent security approval.
- Frozen application source: `9ffd540674cc322857c05f09bcaf8dc816b3ff64`.
- Version: `0.1.0-rc.10`, storage epoch 2; immutable tag `v0.1.0-rc.10`,
  annotated tag object `5dc883633713c1836ca8f837968d5c396db4116a`.
- [Immutable release 428076837](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.10)
  published at `2026-10-29T15:52:23Z`, with 47 assets. This publication preceded
  the additional rc.9 predecessor review and the fresh live campaign.

## Objective, guidance and authority

Complete the owner's exact-source signed qualification request, preserving frozen
source, enrolled signing custody, immutable releases, state and usage ledgers.
Use the production template's bounded verification/work-note/threat-model
approach selected in the [qualification work note](RC10_SIGNED_QUALIFICATION_WORK_NOTE.md),
repository AGENTS/CONTRIBUTING, and the existing signed release/install/upgrade
contracts. The acceptance rubric and stopping rules were declared before dispatch.
Original rc.9 failures remain historical evidence; no expired scope was renewed.

The protected owner gate completed publication while remaining qualification was
pending. The operator's duplicate preparation approval returned HTTP 422 because
no deployment remained pending; it was not retried. The operator submitted no
successful publication approval. Record the observed protected publication rather
than claim it was withheld until this review. Receipt fields denying publication
authority remain unchanged: engineering evidence does not grant approval.

## Source integration and protected execution

[PR #339](https://github.com/joshuamyers22/mos-eisley/pull/339) merged normally as
`fb4a35f50f9789f7d6edb7b30b3695f9f0fe2431`, after all 17 checks passed. Its tree
matches tested integration `b9bc4b20601a7c88af7ec6cdea57a92c11cabf88` and preserves
`9ffd540` in main history. Main retains its separate newer dependencies; the
release remains on the frozen dependency set. The integration full gate passed
3,889 source tests/17 skips, 86% coverage, 2,874 installed-wheel tests/13 skips,
lint/format, strict Pyright and export/build.

[Protected run 40785649978](https://github.com/joshuamyers22/mos-eisley/actions/runs/40785649978)
retains both attempts. Attempt 1 correctly refused preparation at
`2026-10-28T23:24:15Z` because the tag was not yet reachable from main. It created
no signed candidate. After integration and successful local ancestry verification,
only failed jobs were retried. Attempt 2 signed and qualified the same source/tag
through protected custody; all four native builds and signed jobs passed.

The separate actual-rc.9 workflow pins attempt 2, the original protected run,
source/tag/workflow identity, successful preparation and immutable predecessor.
[PR #340](https://github.com/joshuamyers22/mos-eisley/pull/340), host harness
`49cc6429c8283d995cedcd8a1e7050707a94ee2a`, passed its complete local gate and all
13 CI checks, then merged normally as
`3f1394fdeb41920f4bd67a529a82eee06db2ccb6`. Its full gate also passed 3,889
source/2,874 wheel tests, with 17/13 skips and 86% coverage. The only attempt-control
changes were two equality literals; signatures and all state checks stayed strict.

## Signed acceptance results

| Scope | Result and evidence |
|---|---|
| macOS/Linux, arm64/x86_64 | Four enrolled-key signed installations; exact source/version/epoch and archive/bootstrap identities verified |
| Frozen guardian | Native readiness, EOF/deadline exact-container cleanup and invalid invocation refusal pass on all four targets |
| Installed matrix | Snapshot and SQLite, execution, cold resume, terminal/diff and recovery pass on all four targets |
| rc.1/2/3/5/7 predecessors | Twenty actual upgrade/refusal journeys pass; cross-epoch downgrade refuses before state/pointer changes, retained backups remain old-readable, old readers reject new journaled state |
| Actual rc.9 predecessor | Four journeys pass on both stores with same-epoch candidate-written-session rollback; source `f94842a44b9fc5dcf42a7f5880a6683e4fdc0b23`, immutable release `424828190` |
| Generated Homebrew formula | Both macOS journeys pass; no separately published tap update is implied |
| Evidence/public bytes | 34 receipts reviewed: 30 protected-run reports plus four separate rc.9 reports; all 47 public assets match qualified sizes/SHA256; immutable-release attestation verified |

The additional rc.9 reports are retained in
[run 40905969535](https://github.com/joshuamyers22/mos-eisley/actions/runs/40905969535),
not added to the immutable release. Their recorded harness source/hash matches the
qualified host harness. Unpaid signed checks used zero provider calls.

A further actual signed macOS arm64 offline worker passed against the retained
synthetic brief and immutable image
`sha256:11023d7c1443bdb03365e3eb93bd29f59c6da5b5e3333f762e0db33a89ea9763`.
It armed the frozen guardian, returned a lease-bound verification result and
removed the exact real container without host Python/Node on the child PATH.
The deliberately unimplemented baseline's tests failed as expected; this proves
execution/cleanup, not successful coding. Invalid 306-second leases and `--all`
container identities refused before readiness.

## Immutable identity and review records

| Artifact | SHA256 |
|---|---|
| Signed release.json | `d1553b5c4320965efdb0f95366f45391713949e990af890db8a2c65d9bec6e3f` |
| BOOTSTRAP_SHA256SUMS | `86b979b1d479be2d96dfc983ff890db6bed086490094aaf83585345ab1e57be5` |
| Linux arm64 archive | `a79c4ce7d04c39ff5fb3ac5944f3e005116db01921782640e4002bc9bbcabb04` |
| Linux x86_64 archive | `a43580f222126f1ce9ba667fee42b01dec59a1fcc5192a2a843f62ad6dd1a955` |
| macOS arm64 archive | `38e95210edc4689c059d1e92ba1c40c211c3dd299631c39f379563c9b3f7181b` |
| macOS x86_64 archive | `cbb15317561564e13132059adcb14878efbf9631587c07b7e2d374e40e75ba49` |
| Installed macOS arm64 native executable | `0ae37d6b028a8b602a0b3433f2fabc1327aa48acd585e65c179e2640e3fe3ce8` |
| Integration full-gate log | `a95bd3b6d0f863f59d041f7a2bd46f613115b45fcb6fc4c40f5e35c945cedab1` |
| Attempt-2 control full-gate log | `76393cc17a5cab9aa25fc2cd63c8e714f9c7f272dfea5d4dba2378600876a7f1` |
| 34-receipt review | `0d6e216143813b2b7a51710f945a10b77dd09f99ec8fc65bb45771ca739bb12f` |
| Public inventory review | `9c9f6d0ff6ea89190626240b8ae4340659df372deb0fd1b085863a974516f4d3` |
| Signed offline-worker review | `9a956e8fb2b5262da63298057ee3b9368e3887fe0cad177e6237a45ffa1e12f5` |
| Stopped live-campaign closeout review | `10c6010b3255b55487ce70adf0ab4e185bba676e32109915fa3363081acada33` |

Private local evidence is retained under the integration worktree's
`.work/rc10-evidence/`, including original failed attempts, controller logs,
readiness records, signed reports and conservative usage reservations. These are
ordinary engineering records, not prospective evaluation artifacts. No raw
provider responses, transcripts, authorization capabilities or credentials are
included in this document or committed with it.

## Installed live campaign: RC10-SUB-01

Fresh scopes were prepared on macOS arm64 after signed evidence review, using
Codex 0.163.0 and Claude Code 2.1.283. Both native status checks reported supported
and signed in immediately before authorization. The private readiness reader's
initial Claude-schema error occurred before any authorization/inference; the
corrected reader retained that failure and verified the actual client version.
No product contract or native client was changed.

The campaign started at `2026-10-29T19:48:51Z`, bounded to 14 native invocations
per store, 28 total, one-hour scopes, 90 minutes overall, 60-second native
requests and zero correction cycles. It used the declared Sol/Terra/Sonnet/Astra
profile, with no API fallback, extra credits or model substitution. Native billing
and internal retries remain unverified; invocation ceilings are not dollar caps.

Snapshot chat, linked queued steering, inspection refusal, passive cold resume
without replay, and a contextual follow-up recovering the earlier fresh marker
passed. Coding's baseline real worker armed and removed its exact container with
one bound cleanup receipt, advancing beyond rc.9's watchdog failure. The creator
and OpenAI critic completed. The Anthropic critic's native invocation exited 1;
its retained failure records `phase=native_exit`, `diagnostic_hint=authentication`,
`billing_verified=false`. This diagnostic does not establish the specific account
or credential cause, nor a new watchdog defect.

The controller stopped globally on that first unplanned failure. Snapshot usage
retains six reservations/dispatches, five completed calls and one uncertain
operation; SQLite retains zero invocations. No replacement authorization, retry,
usage refund/reset or replay occurred. Read-only closeout confirmed unchanged
workspace Git head/status/files, protected tests/sentinel, and all original rc.9
subscription files. The cleanup receipt is armed/lease-bound and records removal;
Docker independently reports that exact container absent.

End-to-end coding integration, post-coding resume and deliberate cancellation
were not reached. No SQLite live cases ran. A post-failure resume was not attempted
and no uncertain-scope resume-refusal claim is made. RC10-SUB-01 remains open;
full installed live-workflow qualification has not passed.

## Handoff and limits

The next bounded action is native Claude authentication diagnosis without
inference, then a separately declared fresh qualification after readiness is
restored. Preserve the failed scope and usage; it must not be resumed or renewed
as a replacement attempt. A demonstrated product correction would require a new
candidate and affected qualification; immutable rc.10 stays unchanged.

This closes the assessment with a passing signed distribution scope and an
explicit incomplete live scope. No broad v1 readiness, native Windows, general
WSL2, four-target live inference, public online bootstrap replay, or separate
conversational `/review` launcher qualification is claimed. `/inspect` remains
refused on this subscription route. Stable release and other existing project
plan gates remain open. Rollback to rc.9 is qualified within epoch 2; rc.7 and
other epoch-1 readers require retained pre-upgrade copies and refuse new state.

The closeout changes documentation only. Relative links, signed identity/hash
references, retained review-record digests and `git diff --check` passed. Runtime
and test inputs are unchanged; the preceding integration/control full gates
remain their executable validation evidence.
