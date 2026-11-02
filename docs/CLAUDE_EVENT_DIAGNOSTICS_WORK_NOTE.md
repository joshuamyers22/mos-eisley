# Claude output-phase event diagnostics

- Status: active. Owner Joshua Myers; operator Codex. Started 2026-11-02 UTC.
- Authority: add bounded redacted event-state diagnostics, verify offline, run
  one fresh authorized probe, and use its evidence to fix completion handling
  or revise the qualification latency profile before another full campaign.
- Guidance: Python engineering and bounded-verification guides; work-note,
  threat-model and adversarial-review templates. Existing strict protocol and
  authority tests remain authoritative; operator review is not independent
  human security approval.

## Objective, invariants and threats

Distinguish an incomplete Claude turn from an emitted, validated final result
whose stream/process remains open. Observe fixed event categories, capped
counts/times, bounded parsing limitations, terminal-result validation and EOF.
Persist no native text, identifiers, model-supplied strings, paths, arguments,
environment, credentials, prompts or responses in diagnostic receipts or Git.
Keep generic progress schema 1 and existing failure receipt shapes compatible;
write a separate versioned event receipt. Diagnostics grant no completion,
dispatch, retry or billing authority. Strict final parsing, finite output/input
limits, process cleanup and uncertain ledgers remain enforced.

Native stdout is untrusted. Bound line, total inspection bytes, event count,
parser work and all emitted numeric fields. Malformed/oversized/incomplete input
must be visible as an observation limitation; absence of a terminal marker is
not conclusive when inspection is incomplete. Validate at most the first result
prefix with the existing protocol parser, without admitting it early. Data after
that marker still reaches the unchanged final parser and may invalidate a turn.

Preserve frozen rc.13, all stopped campaigns and the earlier one-call diagnostic.
Use an isolated unreleased source candidate; no release tag or asset is changed.
The new probe is host-orchestrated from the reviewed source, not signed installed
qualification. Readiness uses the pinned native client and actual HOME/context;
API keys are absent and no credential cache is read.

## Resource ceiling and stop rules

One coherent implementation batch: focused offline stream/privacy/protocol,
authorization/cancellation and qualifier-observer tests, strict types/lint, then
one full make check within four wall/monotonic hours before PR publication.
No local full gates run concurrently. Later evidence-driven code changes require
affected checks; failures and original logs stay preserved.

After offline verification, exactly one fresh finite probe grant for
critic_anthropic / Sonnet 5/high / Claude Code 2.1.283. Maximum one invocation,
128,000 canonical input bytes, 16,000 text output bytes, 8,192 output tokens,
120-second native ceiling, 180-second outer wall/monotonic ceiling and 20-minute
grant. The new diagnostic window observes whether a valid result occurs before
or after the former 60-second boundary. This changes no closed campaign's
deadline and authorizes no full campaign, renewal, replacement grant, automatic
retry, API fallback, model substitution or response repair. Native billing and
internal retries remain unverified. Stop after this probe regardless of result.

Bind the exact retained synthetic failed rc.13 review packet under a new scope,
workspace and usage root; never resume its original slot. Freeze source/harness
hashes and preserve all historical fingerprints before/after dispatch. A new
120-second probe is diagnostic evidence for one packet, not general reliability.
Choose a completion fix only if supported by validated terminal-state evidence;
otherwise record the observed latency and precisely limited qualification profile.

## Initial observations

RC13-SUB-01 retained drained input, 10,627 stdout bytes through 59,058 ms, open
streams, leader still running and completed cleanup at its 60-second deadline.
No event contents were retained. Source inspection shows final protocol parsing
waits for EOF. An initial inspection noted the coding configuration's nominal
60-second timeout; further tracing found the subscription wrapper replaces it
with the finite grant deadline plus 35 seconds, capped at 300. That initial
outer-timeout finding is corrected; no outer-timeout implementation change is
needed for a newly authorized latency profile.
No new grant or inference has run for this task yet.

## Probe outcome and decision

[The event diagnostic review](CLAUDE_EVENT_DIAGNOSTICS.md) records the single
fresh probe: one reservation/dispatch/completion, 50.205 seconds, thinking
metadata through 48.213 seconds, a validated terminal result at 49.492 seconds
and EOF 179 ms later. No terminal-result/exit stall was reproduced. Inspection
was complete and strict final parsing succeeded; the returned text did not
validate as the coding ModelReview contract. No raw body was retained to infer
its precise schema defect, and no repair/retry followed. All seven historical
campaigns and the frozen 864 source inputs and the probe harness remain unchanged.

Retain completion handling and select the explicit
[120-second qualification profile](CLAUDE_NATIVE_LATENCY_PROFILE.md) for the
next separately admitted attempt; existing admission and outer grant+35 timeout
support it without runtime deadline changes. This is not full workflow
qualification. The artifact-contract issue remains open and no full campaign is
authorized by this one-probe task. The probe authorization is exhausted.

Seven focused event tests plus native-progress, subscription authority/ledger
and qualifier-observer cases passed; source and explicit tool types and
lint/format pass. The final combined batch's full gate and required CI remain
pending before publication/normal merge. No runtime source changed after the
probe; documentation/profile selections add no inference.


## Full gate clock-stop and wheel recovery

The combined gate passed 3,919 source tests (17 skips, 86% coverage), static
checks, export verification and build. During the wheel stage its controller
observed 16,405.281 wall seconds versus 3,810.882 monotonic seconds, exceeding
the declared four-hour wall ceiling after a large clock discrepancy. The
precise environment cause is unestablished. It stopped the owned make group;
the make process, launcher and group were independently confirmed absent.
Original result remains exit 124 (process -15), not a passing invocation.
All 864 input hashes remain unchanged. Original log SHA256:
`b3b5acfbb47dac5416898da84c3cc8c882c98c911fabbc80a8925e184bedeb9b`.

Only the complete unfinished installed-wheel stage is being recovered with
fresh private temporary state, the identical built wheel and 90-minute wall
and monotonic limits. All 417 wheel runtime Python files match source. No
passed source stage or live probe is repeated, and no code/input is changed.


The complete wheel recovery passed 2,906 tests in 2,048.469 seconds (13 skips),
exit 0. Wall/monotonic durations were 2,077.917 / 2,077.902 seconds, within
90 minutes. All 864 inputs, the built wheel and original log remain unchanged;
all 417 runtime Python files in the wheel match source. Recovery log SHA256:
`26ea664a0eb4bb3df3b9184c3a11829645f64e6d1acb15461b9efac1e5e21cdd`.
All required stages now pass after this disclosed unfinished-stage recovery;
the original full invocation remains nonpassing. No source test, live probe,
provider request or grant was repeated for recovery.
