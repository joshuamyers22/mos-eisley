# rc.11 execution-receipt qualification review

- Status: signed distribution qualification passed; installed live-workflow
  qualification incomplete at plan review (RC11-SUB-01). Reviewed 2026-10-30 UTC.
- Accountable owner: Joshua Myers; technical operator: Codex. Owner/operator
  overlap is disclosed; this is not independent security approval.
- Frozen source: `4d927cea23ff18f6aa9d231f7c342ee8e2420c84`, version
  `0.1.0-rc.11`, storage epoch 2. Annotated tag object:
  `235f03df11c7cb991bb3d45c748cc89193fd27f8`.
- [Immutable release 429106203](https://github.com/joshuamyers22/mos-eisley/releases/tag/v0.1.0-rc.11)
  published through the owner gate at `2026-10-30T14:06:47Z`, before the fresh
  live campaign. All 55 public asset sizes and digests match the qualified set;
  GitHub's immutable-release attestation verified. Publication does not establish
  full live acceptance.

## Objective, authority and verification contract

The owner requested test execution receipts in a new candidate and repetition of
affected qualification. The [implementation work note](EXECUTION_RECEIPT_WORK_NOTE.md)
declares the production-template guides, invariants, ceilings and stopping rules.
The change exposes selected test files, test/failure/error/skip counts, runner
exit/success, post-run file integrity and combined output size to live reviewers,
bound to exact source/test/output hashes. Missing or contradictory receipts refuse
before review or integration. Combined output remains capped at 32,000 bytes.
Recorded handoffs retain their four-field verification and epoch-2 wire format.

Frozen rc.10 and its [two failed live campaigns](RC10_AUTH_REFRESH_QUALIFICATION_WORK_NOTE.md)
remain unchanged. Native credentials stay client-owned. No API fallback, model
substitution, credit purchase, failed-session replay, authorization renewal,
acceptance waiver or response repair was used. Ordinary engineering evidence is
not prospective evaluation evidence; no sampling stores were consulted.

## Source and protected release provenance

[PR #342](https://github.com/joshuamyers22/mos-eisley/pull/342) merged normally as
`fe24394dd8edf481256be6403756cc53dd542305`, after all 17 checks passed on exact
integration head `12aab0ec576ed9e1f57c851b39a3ba7602181e16`. The normal source
merge preserves `4d927ce` in main history and retains main's newer dependencies;
the release keeps its frozen dependency set. Exact non-Markdown manifests match
the full-gate inputs: 856 candidate files and 857 integration files. Local tag,
version, checkout and main ancestry checks passed before pushing the new tag.

| Gate | Source tests | Installed-wheel tests |
|---|---|---|
| Frozen candidate full `make check` | 3,892; 17 skips | 2,867; 13 skips |
| Main integration full `make check` | 3,894; 17 skips | 2,879; 13 skips |
| Required PR CI | 3,894; 17 skips | 2,879; 13 skips |

Both local full gates passed at 86% coverage, including lint/format, strict
Pyright, export verification and build. Earlier sandbox-denied full checks and
pre-report-digest-fix interruptions remain nonpassing records; they were not
relabeled as passing.

[Protected release run 40981608060](https://github.com/joshuamyers22/mos-eisley/actions/runs/40981608060),
attempt 1, builds and signs this exact source/tag. All four standalone builds,
secret scanning, protected preparation's full `make check audit`, and all four
signed qualification jobs passed. The owner approved preparation before the
operator's one-shot review helper finished its fresh state check; the helper
refused the advanced job before creating a payload or sending an approval.
The operator submitted no preparation or publication approval. The owner's
separate protected publication completed before live qualification.

## Signed and installed acceptance

| Scope | Result |
|---|---|
| Four macOS/Linux arm64/x86_64 targets | Signed source/version/epoch, native installation, tamper refusal and guardian boundaries pass |
| Installed matrices on all four targets | Both storage backends, execution, cold resume, terminal/diff and recovery pass without inference |
| Actual rc.1/2/3/5/7 predecessors | Twenty upgrade/refusal journeys pass, including rc.7 cross-epoch downgrade refusal and retained old-readable backups |
| Actual rc.9 and rc.10 predecessors | Eight same-epoch upgrade/rollback journeys pass; candidate-written state remains readable by the corresponding old epoch-2 reader |
| Generated Homebrew formula | Both macOS journeys pass; no separate public tap update is implied |
| Independent evidence review | All 38 reports, seven immutable predecessor identities, enrolled-key metadata and 55 candidate assets match |

An additional macOS arm64 check installed the signed binary with no host
Python/Node on its child PATH. A host-orchestrated offline worker using that
actual signed native guardian emitted a concrete receipt and removed its exact
container. Invalid 306-second leases and `--all` container identities refused
before readiness. The unimplemented baseline correctly reported three failing
tests; this is execution/cleanup evidence, not successful coding.

The fresh offline image is
`sha256:e3543e68d9dfdc9a198d02a4669d243d9093d41704116afcc35f9af011735661`.
Its installed Python sources match the frozen candidate. Unpaid local proofs
also ran three passing candidate tests and verified actual signed rc.10 passive
resume of new recorded handoffs on snapshot and SQLite without changing storage
or replaying work. All signed/unpaid qualification used zero provider calls.

## Fresh installed subscription campaign: RC11-SUB-01

The exact signed macOS arm64 installation checked both supported, signed-in
native clients immediately before fresh authorization. The campaign started at
`2026-10-30T18:10:16.282670+00:00`, with Codex 0.163.0 and Claude Code 2.1.283.
The declared profile remained Sol/medium for chat, creator and child;
Terra/medium and Sonnet/high for independent critics; Astra/medium for judge.
The ceiling was 14 invocations per store, 28 total, one-hour scopes, 90 minutes
overall, 60-second native deadlines and zero correction cycles. Native billing
and internal retries remain unverified; these are not dollar caps.

Snapshot chat, linked queued steering, inspection refusal, passive cold resume
without replay, and contextual follow-up passed. The real baseline worker ran
three tests on two frozen files, with three expected failures, zero errors/skips,
exit 1, unchanged files and 1,367 combined output bytes. Both critics and the
judge received the same hash-bound plan packet containing this execution receipt.
Both critics accepted. The judge requested revision because the creator's plan
placed independent implementation review after integration. The actual gate
requires review of the tested candidate before integration.

This is a distinct plan-ordering defect, not missing receipt data or a native
authentication failure. Source inspection finds conflicting author guidance in
[conversation_planning.py](../src/mos_eisley/conversation_planning.py), which places
independent review after integration, versus the pre-integration requirement in
[conversation_live_coding.py](../src/mos_eisley/conversation_live_coding.py).
That conflict is the next bounded implementation correction; its causal extent
beyond this observed creator plan is not established by this run.

The controller stopped globally at this first unplanned failure. Snapshot retains
seven reservations, seven native dispatches and seven completions; SQLite retains
zero. The coding operation is conservatively marked uncertain and is not replayed.
No coding child, implementation review, integration, post-coding resume,
deliberate cancellation or SQLite live cases were reached. No post-failure resume
was attempted, and no uncertain-resume refusal claim is made.

Read-only closeout confirmed unchanged workspace head/status/files, protected
tests and sentinel, all original rc.9 files, both original rc.10 campaigns, and
the frozen campaign scripts. The single live baseline guardian armed, matched
its exact lease and removed its container; Docker independently confirmed that
container absent. The unused 21-call capacity remains unused.

## Identity and retained review records

| Artifact | SHA256 |
|---|---|
| Signed release.json | `3b123164bf2c8db3d7262529d8c6830e8de4b0354c7a18dc707b833ad0769d9b` |
| Bootstrap checksum manifest | `d158a82651eeac738805a1414fca90f3adfa62baab3521b9114b6d411dd95340` |
| Linux arm64 archive | `e4b8c35504f54eb53806cdd6a55e9a5cde19b7335d7f53220273275239bd3549` |
| Linux x86_64 archive | `d363d050256fe1e5057b85bfd18b0f8ff4d46eb2fabbf4cc6b5f02bc0e157f13` |
| macOS arm64 archive | `5947e12aedecd26491642bed2aed420c6ad2ca0fcddd222f1cd571603d8bdabe` |
| macOS x86_64 archive | `192924d398ef91e0356cffecf58be92e68d052b06c732ff3892f0b4aba5e7f68` |
| Installed macOS arm64 binary | `8c52e15c658da99408bf71166863e11b0ca191a6b59826b4b2a0ad529aecc18b` |
| 38-report independent review | `5c52643d3d42b300cc4a4e78eff2b3237feac9d7da3c3b683d6e2c57ef45c4eb` |
| Signed offline-worker review | `ea7085a23f79b915d7fd01cea923ab1bdb5d35cf9ddeb98074923431f610331a` |
| Stopped live-campaign review | `23ceac075da011d8a10513a1a802631ba99252259e36f8b0b94badb5e9ec4fde` |

Private evidence is retained in the integration worktree's `.work/rc11-evidence/`.
No raw provider payloads, transcripts, authorization capabilities or credentials
are committed. Disposable post-stop audit helpers initially used Python rather
than JSON tuple decoding and an incorrect retained-snapshot path; their failures
remain separate logs. Corrected read-only review passed without changing product
code, campaign inputs, outcomes, authority or usage.

## Disposition and remaining work

Execution-receipt delivery and repeated signed distribution qualification are
complete. Fresh full live acceptance is incomplete. Correct creator plan ordering
to require candidate tests and implementation approval before integration, then
select a new immutable candidate and separately bound fresh qualification. Do
not retarget rc.11 or reuse its stopped campaign.

No broad v1 readiness, four-target live inference, native Windows, general WSL2,
stable release, public online bootstrap replay or separate conversational
`/review` qualification is claimed. Existing project-plan and operational gates
remain open. This closeout changes documentation only; relative links, evidence
identities and `git diff --check` are its applicable validation.
