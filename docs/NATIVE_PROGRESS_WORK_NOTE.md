# Bounded native failure progress receipts

- Status: implementation and local full verification complete; accountable review
  and exact installed delivery remain pending. Owner Joshua Myers; operator Codex.
  Started and reviewed 2026-10-31 UTC.
- Base: main `a4b296203178fcecd733cc2118b3f994ded767b8`. Related finding:
  RC12-SUB-01; [diagnosis PR #346](https://github.com/joshuamyers22/mos-eisley/pull/346).
- Requirement: complete bounded, redacted diagnostics before another fresh call.
  This task authorizes implementation and offline verification, not inference.

## Guidance and completion contract

Selected repository Python engineering guide, bounded verification guide/loop,
work-note and threat-model templates. Context: shared native runner, Claude
failure receipts, subscription authority/usage, native fixtures and installed-wheel
smoke registration. No evaluation/sampling stores are consulted.

Blocking rubric: distinguish observed input/output/exit phases and stream EOF
without retaining content; fixed schema/constant state and saturating counters;
preserve timeout, output ceilings, process-group cleanup, cancellation and one-use
uncertain ledgers; preserve immutable rc.12 and all old campaign records.

The additive version-1 progress object is restricted to bounded numeric values,
booleans and a fixed input/output/exit phase. It records per-stream byte counts,
first/last monotonic read times and EOF, input drain, pre-cleanup leader exit and
cleanup completion. No prompts, output, stderr, arbitrary event fields, paths,
PIDs, arguments, environment, provider identities or credentials enter it.
No native-event parser or changed provider protocol is introduced.

## Threat boundary and limits

Native output is untrusted. Only byte counts/times/EOF are observed; never parse
or copy native text into diagnostics. A strict immutable extra-forbidden model
defines the serialized schema. Counters and milliseconds saturate at 1,000,000.
This is metadata, not a provider result or billing/cleanup attestation. An observed
leader exit does not imply pipe EOF or process-group absence. Cleanup completion
means the existing owned-group stop routine returned successfully.

Keep private receipt creation and no-overwrite behavior. Missing diagnostics
on older/synthetic errors remain valid; no old receipt is rewritten. Cancellation
must propagate and leave usage uncertain. No new authorization, inference,
deadline widening, release tag, published asset or automatic retry is allowed.

## Bounded verification

One implementation batch, focused privacy/process/receipt/authority regressions,
static checks and one full `make check` within four hours before PR publication.
Required CI precedes normal merge. Stop on privacy, cleanup, authority or quality
failure; correct affected checks without repeating successful gates unnecessarily.
Use synthetic subprocesses only: silent timeout, output then hang, exited leader
with a descendant holding a pipe, output overflow, exchange/start/cleanup faults,
cancellation and clean control. Confirm saved receipts contain no sentinels and
replay remains refused. Full installed-wheel coverage must include the new tests.

## Result and handoff

Implementation and 84 affected offline tests passed; Ruff/format and strict
Pyright passed. Installed-wheel smoke explicitly includes the new progress
tests. Initial fixture corrections retained the actual assertions: this Mac
buffered a 128-KB write, so the generic-runner backpressure fixture now uses
2 MB of synthetic input; the inherited-pipe child deliberately ignores SIGTERM
and requires existing SIGKILL escalation. A terminating child could make the
second group signal return EPERM on this host; diagnostics truthfully recorded
`cleanup`/completion false, with no change to production stop semantics. The
original failed focused record remains private.

One complete `make check` passed in 4,800.929 seconds, exit 0, with all 860
non-Markdown input names/content hashes unchanged. Source passed 3,909 tests
in 2,797.003 seconds (17 skips) at 86% coverage; installed-wheel smoke passed
2,893 tests in 1,943.407 seconds (13 skips). Lint/format, strict Pyright,
export verification and build passed in that same gate. Full log SHA256:
`ae5d154002d3999eecdaa764853be2a197f5c4711f03c74379eee3c4b39b06dc`.

The earlier diagnosis PR #346 passed all 13 checks and merged normally as
`dd031815874c72418d8de67500b24ed9703778bf`. This implementation fast-forwarded
over that documentation-only merge after checking every intervening path was
Markdown; its tested 860 application inputs remain identical. No passed gate
was repeated for that documentation update. A fresh
installed candidate and a separately bounded native call remain subsequent work;
this batch cannot resolve the historical Claude internal cause.
