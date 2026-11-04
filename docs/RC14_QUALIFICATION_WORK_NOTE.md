# rc.14 signed and installed live qualification

- Status: signed/offline qualification passes on all four targets; combined
  installed live evidence passes both stores on macOS arm64 after a separately
  authorized SQLite-only run. Original stopped evidence remains unchanged.
  Publication awaits owner review. See [evidence review](RC14_QUALIFICATION_REVIEW.md).
  Owner Joshua Myers; operator Codex.
- Authority: the owner's explicit four-step request: freeze rc.14 incorporating
  merged source `11fe46514e7962731023538fc50789c8b9d7fd45`, protected build/sign,
  four-target signed installation/upgrade/refusal/offline checks, then one fresh
  both-store subscription campaign under the 120-second profile and evidence
  review before publication. This new campaign authority supersedes the exhausted
  one-probe scope; no historical slot is resumed.

## Guidance, invariants and review

Apply Python engineering, bounded verification and adversarial review guides;
work-note, threat-model and verification-loop templates; publisher preparation,
installed acceptance and the revised Claude latency profile. Keep main's current
dependency set and SDK-2 adapter; change project version to rc.14. Pin immutable
published rc.13 release `430907808`, source
`8c7690733af1bbc4861911d2c0a2a516961985da`, as the actual predecessor in addition
to the existing historical journeys. Keep epoch 2, rc.7 cross-epoch refusal,
enrolled-key verification, exact artifact/source bindings and rollback/recovery.

Extend offline signed native fixtures to verify the static envelope instruction
and redacted event-state receipts, including valid-result-with-open-process
refusal. Run the strict ModelReview diagnostic contracts on each target against
the exact source; disclose source-level versus installed-binary evidence.
The fresh installed live campaign must verify the actual binary review path.

Threats: artifact substitution, stale approvals, leaking native content through
diagnostics, review bypass, unbounded dispatch, credential exposure and replay.
Keep signing keys in protected custody and native credentials client-owned.
No private grant, raw provider response or prompt enters Git. Preserve every
closed campaign and diagnostic root; no sampling registry, custodian mapping,
label store or outcome store is read. Ordinary receipts confer no evaluation
eligibility. Operator review is not independent human security review.

## Budget and stop rules

One combined candidate batch: focused contracts, one full `make check` with
four-hour wall and monotonic ceilings, then exact-head required CI and normal
merge before an immutable version-matching tag. Preserve failed logs and recover
only justified unfinished/affected stages; never relabel an interrupted run.
Protected preparation and all four signed qualification jobs must pass before
dependent live dispatch. No tag/asset retargeting, signing-key reads or admin
bypass. Approve protected preparation only for the reviewed exact tag/run;
publication stays withheld until evidence review, with any external publication
reported truthfully. A workflow wait is not authorization to bypass protection.

After fresh signed installation, exact worker-image construction, guardian and
cleanup verification, and native readiness: one fresh campaign, maximum 14
invocations/store, 28 total, one-hour grants, 90-minute wall/monotonic campaign,
120-second native deadlines, 128,000 canonical input bytes, 16,000 text output
bytes, 8,192 reported output tokens, 600-second coding walls, zero corrections.
Retain exact Sol/medium chat/creator/child, Terra/medium and Sonnet/high critics,
Astra/medium judge and pinned native clients. Preserve actual HOME/CODEX_HOME;
strip API keys. No API fallback, credit purchase, model substitution, grant
renewal, automatic retry, response repair or failed-session replay. Stop globally
on the first unplanned signature, provider, protocol, test, review, integration,
deadline or cleanup failure; preserve unused capacity. Native billing and internal
retries remain unverified. A planned cancellation is distinct from an unplanned
failure. Full v1/stable launch and unrelated distribution routes stay separately
gated.

## Preparation evidence (recorded before freeze)

Fresh remote main equals `11fe465`; rc.14 tag is unused. Actual rc.13 release is
immutable, published and pinned to its expected source. Candidate, CI, protected
run, signed reports, fresh campaign and evidence disposition remain pending.

Preparation checks: the first expanded terminal fixture omitted required thinking
metadata, and strict protocol validation correctly refused it. The corrected
fixture is now checked by the real parser before the six installed CLI wait
cases. Five focused offline progress/review-contract cases, 17 publication
contracts and 42 distribution cases pass; the changed tool's strict types pass.
Initial failed fixture/type logs remain private. A final event-receipt replay
immutability assertion joins the combined gate. Expected signed inventory is
54 reports and 71 assets, pending actual review: four each signed installation,
both-store matrix and offline progress; 40 historical/actual upgrade journeys;
and two macOS formula journeys. No provider invocation has run for rc.14.

## Candidate gate and technical review

The combined `make check` exits 0 in 5,100.757 monotonic / 5,100.747 wall
seconds, within both four-hour ceilings. Source: 3,929 tests in 2,966.067s,
17 skips, 86% coverage. Installed wheel: 2,916 tests in 2,072.842s, 13 skips.
Lint, formatting, types, export verification and both builds pass. All 866
frozen inputs are unchanged. Full log SHA256:
`78afbf400779601a1b677b175ee426ad25be8e96933ab5caf8dc363243a56058`.
Every non-project dependency lock entry and runtime export matches `11fe465`;
no older SDK-1 dependency set is substituted.

Technical review traced the pinned rc.13 workflow/upgrade admission, signed
installation identity checks, fake native clients, fixed system-prompt assertion,
event-state validation, exclusive receipts and unchanged failure/replay gates.
No blocking finding remains. The six fixtures explicitly distinguish valid
terminal-result observation from actual EOF/process completion; malformed results
stay invalid. Review-contract checks disclose their exact-source scope rather
than claiming the installed binary's complete coding path. That path remains
for fresh live qualification. Owner-directed operator review does not establish
an independent reviewer attestation.

Private preparation compiled the new inert live harness, verified chunked packet
parsing using `TextBlock.kind`, fixed the prior harness's unreachable attribute
defect in the new copy only, and bound the intended 120-second/8192-token limits.
All nine historical evidence roots remain separate. Actual source/image/native
bindings, signed installation, fresh readiness and grants remain pending. The
pinned client versions and Docker are available; no new inference has run.

## Final disposition of the original campaign

Candidate `ec3211e` merged in PR #359 after all 17 checks; immutable rc.14 tag and
protected run 41699667393 passed all four signed jobs. The actual review admitted
54 reports and 71 prepared assets. Snapshot completed the installed workflow
through exact creator approval, integration and fresh tests, including two valid
Claude reviews under 120 seconds. Its planned cancellation correctly refused
resume without replay, but a host assertion expected older error wording and
stopped the original controller. That exit 1 and all original bytes are retained.
The corrected assertion passes bounded offline positive/negative checks.

Closeout independently rechecked source, installed files, signed report hashes,
review/approval bindings, worker removal and all nine older roots without grants
or provider calls. SQLite remains zero calls and its untouched grant expired.
Full both-store qualification is incomplete. A fresh SQLite-only continuation is
prepared with at most 14 calls, the same native profile, a one-hour grant and
45-minute wall/monotonic ceilings; it requires explicit new owner authority. No
snapshot repetition, scope reopening, renewal or retry is authorized by this
record. Publication approval was not submitted; release-by-tag returned 404.
See the evidence review for hashes, limitations and the final disposition.

## Separately authorized SQLite completion

The owner approved the prepared SQLite-only proposal. One fresh scope completed
with controller exit 0 in 224.556 monotonic / 224.543 wall seconds, within both
45-minute limits: 14 dispatches, 13 completions, one planned owned cancellation
and fail-closed resume without replay. Chat, steering, contextual cold resume,
plan and implementation reviews, exact creator approval before integration,
source-only integration, fresh tests and post-coding cold resume passed. Each
store's fresh integrated execution receipt has three tests, exit 0 and no
failures/errors/skips. Both SQLite Claude reviews returned valid bound artifacts
in 36.338s and 34.664s. All four new coding workers are independently absent.

Read-only combined review verifies 28 task dispatches, 26 completions and two
planned uncertain cancellations; all twelve ModelReview artifacts and exact
approval subjects/order; eight removed workers; source/native/harness identity;
54 signed reports; all nine older roots and the original rc.14 root unchanged.
No original scope was resumed and snapshot was not repeated. Combined both-store
installed live acceptance is complete for this exact macOS arm64 candidate.
Original controller exit 1 remains historical evidence, disclosed separately
from the successful SQLite controller. No further inference or runtime change is
needed. Accountable owner publication review and the protected gate remain.
