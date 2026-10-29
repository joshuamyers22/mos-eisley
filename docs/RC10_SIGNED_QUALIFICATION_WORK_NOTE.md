# rc.10 exact-source signed qualification

- Status: active; signed and bounded subscription qualification authorized,
  publication withheld.
- Accountable owner: Joshua Myers. Technical operator: Codex; no independent
  security-review claim. Started 2026-10-28.
- Frozen release source: `9ffd540674cc322857c05f09bcaf8dc816b3ff64`.
- Last updated: 2026-10-29 UTC.
- Version/tag: `0.1.0-rc.10` / `v0.1.0-rc.10`; storage epoch 2.
- Integration branch: `fix/watchdog-release-integration`. The frozen source and
  dependency set remain unchanged; main retains its separate SDK/HTTP migration.

## Objective, authority and boundaries

The owner requested completion of signed rc.10 qualification from exact
`9ffd540`. Establish protected main ancestry, build/sign through the existing
protected release workflow, and qualify the exact native bytes on Linux/macOS,
arm64/x86_64. Run signed install, native guardian, both-store installed acceptance
and actual-predecessor upgrade/recovery checks, including published rc.9 and
rc.7's cross-epoch downgrade refusal. Review all source/version/signature/hash
bindings before handing off a publication decision.

The request refers to the outlined sequence, including necessary protected
integration/signing and a fresh installed subscription coding campaign on both
stores. The owner's earlier subscription selection remains applicable; expired
rc.9 authorizations are not reused or renewed. Publication remains withheld.
Preserve immutable rc.9 and earlier releases,
failed qualification evidence, publisher custody, user state and original usage
ledgers. Qualification receipts grant no provider, sampling or release authority.
Signed installation/upgrade checks use zero provider calls. Only after those
gates pass, run the separate fresh bounded subscription campaign below.
Conversational live review's separate frozen launcher remains outside this scope.

Guidance: repository AGENTS/CONTRIBUTING, bounded verification guide/loop,
work-note and threat-model templates, release-readiness checklist, publisher
operation runbook, rc.9 prepublication review, watchdog repair and fixture notes.
Risk: release integrity and data preservation; owner instruction supplies signing
authority beyond agent self-review, not independent security approval.

## Acceptance rubric

| Boundary | Required evidence |
|---|---|
| Frozen source | Exact annotated tag, version/epoch and source SHA; immutable existing releases untouched |
| Main ancestry | Reviewed merge preserving main dependencies; required CI passes before merge |
| Protected custody | Signing only in `application-release`; no local key export or secret logging |
| Native bytes | All four exact-source builds and enrolled-key signed installation receipts |
| Guardian regression | Actual frozen readiness, EOF/deadline cleanup and invalid invocation refusal; no host Python fallback |
| Installed acceptance | Snapshot/SQLite exec, cold resume, terminal/diff and recovery on all four native targets |
| Predecessors | Actual signed historical bytes; rc.9 same-epoch upgrade/rollback and rc.7 cross-epoch refusal with state preserved |
| Installed subscription coding | Fresh scopes on both stores, exact admitted clients/model profile, real provider-diverse review, source-only integration, cold resume and owned cancellation without replay |
| Evidence review | Signature, source, metadata/archive/bootstrap hashes, receipt scope and complete inventory verified |
| Publication boundary | Separate publish approval withheld pending evidence/owner review |

## Budget and stopping rules

One complete combined local integration gate after prerequisite controls are
frozen and its required integration CI round. Preserve protected release attempt
1's ancestry refusal; retry failed preparation only after verified main ancestry,
without changing the tag or native bytes. Its explicit new attempt pin is a
separate bounded control batch with a full gate/required CI, run in parallel with
the corrected protected preparation. Separate four-target rc.9 predecessor checks if
the frozen workflow does not include rc.9. Bound each local/CI gate to four hours,
the protected run to six hours and this sequence to twelve hours excluding owner
approval wait. Existing workflow job timeouts remain authoritative. No changes to
the frozen source, test suppression or evidence replacement. Stop on a new
unexplained gate, signature, source, state-preservation or native failure; retain
the failed evidence and make any correction separately reviewable. Reconnect
read-only monitoring after network failures without rerunning successful jobs.

The signed macOS arm64 guardian may additionally run one unpaid offline worker
against the retained synthetic brief and immutable image, with fresh cleanup
directories and no reuse of the failed session. This establishes the signed
helper/worker boundary, not live coding success.

For installed live qualification, retain the accepted experimental subscription
profile and exact client selection from the rc.9 subscription record. Run
this campaign on macOS arm64, the owner-native-client host used for rc.9; the
four-target signed installation scope does not imply four-target live inference.
Check current installed status for Codex 0.163.0 and Claude Code 2.1.283 before use;
credentials stay native-owned. Use Sol `gpt-6-sol`/medium for chat, creator and
child, Terra `gpt-5.6-terra`/medium for the OpenAI critic, Sonnet
`claude-sonnet-5`/high for the Anthropic critic and Astra `gpt-6-astra`/medium for
the judge. No silent model/client substitution or API fallback.

Create fresh one-hour authorizations, 14 native invocations per store, 28 total,
within a fresh 90-minute campaign ceiling. Keep 60-second native deadlines,
8,192 native-reported output tokens, 16,000-byte text, 128,000-byte canonical input,
600-second coding walls and zero correction cycles. Native billing/retries remain
unverified; these are invocation limits, not dollar caps. Use the retained image
`sha256:11023d7c1443bdb03365e3eb93bd29f59c6da5b5e3333f762e0db33a89ea9763`.
Stop globally on the first unplanned admission, output, protocol, provider, test,
integration or cleanup failure. Preserve original outputs and unused capacity;
no replacement scopes, outcome repair or expired-scope replay. Inspection and
separate conversational live review remain outside this experimental route.
The planned 14 calls per store are three chat turns (including queued steering
and a context-only follow-up after cold resume), ten coding-role calls and one
deliberately cancelled chat call. Per-role chat admission is four; the shared
14-call limit remains authoritative. The extra context turn supplies distinct
resume evidence within the existing 28-invocation ceiling, not retry capacity.

## Observations and attempts

- Frozen branch is clean and pushed at `9ffd540`; its full local gate passed
  3,887 source tests/17 skips and 2,862 installed-wheel tests/13 skips, with 86%
  coverage. Local native guardian evidence remains unsigned and is not promoted
  to exact-tag signed evidence.
- Current main is `dd3713b`. A normal three-way integration automatically retains
  main's dependency set; the lock diff changes only the project version. The only
  merge conflict was the memory index, resolved by retaining main's entries and
  adding the two candidate evidence rows.
- `application-release` still requires the enrolled owner and restricted tag
  deployment policy. Exact rc.10 tag lookup returned 404 before creation.
- The frozen workflow already requires all four signed installed matrices and
  rc.1/rc.2/rc.3/rc.5/rc.7 upgrade checks. Its omitted actual rc.9 predecessor
  requires separately bound four-target evidence without changing `9ffd540`.
- Exact annotated rc.10 tag started protected release run `40785649978`, source
  `9ffd540`; all four native builds and gitleaks passed. Tag object:
  `5dc883633713c1836ca8f837968d5c396db4116a`. The active immutable-tag ruleset
  blocks updates/deletion of `refs/tags/v*` with no bypass actors. The current
  GitHub operator is the enrolled owner `joshuamyers22`.
- The early integration gate was deliberately interrupted (exit 130) to include
  the required rc.9 predecessor workflow in this same frozen validation batch.
  Its partial log is retained, not counted as a passing gate. The new manual
  read-only workflow pins the original protected run/source and published rc.9
  identity, verifies successful preparation before artifact download, checks out
  and records its own exact host-harness revision and retains written reports.
  A source contract regression
  guards evidence substitution and fail-open configuration.
- Focused source inspection found the historical harness's predecessor choices
  stop at rc.7. Its host-only allowlist now additionally pins published rc.9 to
  `f94842a`; no verification or upgrade logic changes. The existing signed-source
  admission test exercises correct source/version and wrong-source/version
  refusal for every allowlisted predecessor, including rc.9. A second early
  integration gate was interrupted to include this prerequisite; both partial
  logs are retained. The frozen application's source, dependencies and tag
  remain unchanged.
- Fresh frozen-lock audit passed for 54 runtime packages, with no known
  vulnerabilities or adverse project statuses. No dependency version changed.
- Final combined integration `make check` passed: 3,889 source tests in
  2,814.266 seconds (17 skips), 86% coverage, export/build, and 2,874 installed-wheel
  tests in 1,940.745 seconds (13 skips). Ruff/format and strict Pyright passed.
  All 15 executable/test inputs match their pre-gate hashes. The log's first/final
  writes bound the completed gate to 4,815.623 seconds, within the four-hour ceiling.
  Gate log SHA256: `a95bd3b6d0f863f59d041f7a2bd46f613115b45fcb6fc4c40f5e35c945cedab1`.
- The completed local gate ended at `2026-10-29T00:37:25Z`; fresh monitoring after
  the approval/monitoring gap observed that pass. It was not rerun or relabeled.
  No subscription authority or inference was started during the gap.
- Fresh protected-state inspection found attempt 1 had received owner approval
  before main ancestry was established. `prepare` job `123162500267` stopped at
  `Verify release tag` with `release tag commit is not reachable from main` at
  `2026-10-28T23:24:15Z`. Quality/signing/artifact steps were skipped; no signed
  publication candidate was created. Preserve that failed log and approval
  history. The main integration is the concrete correction for this gate.
- The original predecessor workflow's attempt-1 pin remains a strict historical
  control. A separately qualified control revision must pin the corrected attempt
  before the actual rc.9 journey can run; do not remove or weaken the attempt check.

## Handoff

Local integration validation is complete; protected main PR/CI/merge are next.
Exact-tag signing retries only after ancestry verifies. Signed qualification and
the separately pinned rc.9 upgrade remain pending.
Fresh subscription qualification follows successful signed native checks.
No rc.10 publication or fresh subscription inference has occurred.
