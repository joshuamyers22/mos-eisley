# RC12-SUB-01 native Claude timeout diagnosis

- Status: bounded offline diagnosis complete; the historical native cause remains
  unobservable. Installed live acceptance remains incomplete.
- Owner Joshua Myers; operator Codex. Reviewed 2026-10-31 UTC.
- Subject: immutable rc.12 `2f75d429c87b3b48c946832ff9c73748abf94efe`,
  Claude Code 2.1.283, Sonnet 5/high, snapshot implementation critic.
- Authority: diagnose the retained failure. Zero new provider invocations,
  authorization scopes, credential-cache reads, retries or session replays.

## Contract and evidence

Selected repository guidance: bounded verification guide/loop, work-note and
incident-review templates. Invariants: preserve the failed call, uncertain usage,
workspace, release and prior campaigns; expose no prompts, native output or
credentials. The bounded checks were retained identity comparison, frozen-source
tracing, four one-second offline synthetic processes and the two existing focused
timeout/receipt tests. Offline fixtures do not establish the historical cause or
qualify a changed deadline.

The [qualification review](RC12_QUALIFICATION_REVIEW.md) records the failed
eleventh native invocation: ten completions, one uncertain call, SQLite zero,
no integration. The failure is `native_process` / `deadline`, with a configured
60 seconds and measured monotonic elapsed time of 60,215 ms.

Both Claude request hashes reconstruct exactly after the subscription wrapper's
existing 16,000-byte text-output clamp. The initial comparison omitted that clamp;
its assertion failed without changing evidence. Correct reconstruction binds
coding call 03 to native slot 6 and call 08 to slot 11.

| Observation | Successful plan critic | Failed implementation critic |
|---|---:|---:|
| Native model/effort | Sonnet 5/high | Sonnet 5/high |
| Serialized transport payload | 6,561 bytes | 7,008 bytes |
| Canonical request after clamp | 6,725 bytes | 7,172 bytes |
| Dispatch-to-terminal receipt file timestamps | 31.862 s | 60.217 s |
| Native completion retained | Yes | No |

File timestamps are approximate wall-clock observations, not monotonic latency
instrumentation. The successful receipt reports 2,895 output tokens; its usage
does not predict the failed call's output or billing. The 447-byte input increase
is within the 128,000-byte admission limits. The source reaches dispatch only
after exact-version/native-sign-in checks and the fresh authority guard pass.
The retained failure is before result parsing, with no output-limit, native-exit,
protocol/schema or cleanup error recorded. A later native auth, quota or retry
condition remains possible because its progress was not retained.

## What the timer actually measures

In [the frozen runner](../src/mos_eisley/providers/codex_subscription.py), process
creation precedes the timeout context. The timer then covers stdin write/drain,
stdout and stderr reads to EOF, and process wait. Authentication preflight and
result parsing occur outside that invocation timer. Claude's measured elapsed
receipt also includes process startup and the final cleanup interval.

Both output readers buffer internally until EOF. A deadline cancels the readers,
stops the owned process group, and raises a controlled error without returning
partial output. [The Claude adapter](../src/mos_eisley/providers/claude_subscription.py)
records only reason/deadline/elapsed metadata for this path. It cannot tell us
whether the historical client was generating, retrying, stalled, finished but
still running, or waiting on an inherited output pipe. A valid native result
could have been emitted without reaching the parser; none is recoverable from
the retained Mos receipts. No unrelated client logs or credential caches were
searched to invent that missing lineage.

## Offline verification

Four synthetic Python processes used the unchanged frozen runner; no Claude
client or inference service was invoked.

| Synthetic case | Observed result |
|---|---|
| Valid Claude event stream, then clean exit | Valid response, exit 0, about 25 ms |
| Silent live process | `deadline`, about 1,006 ms |
| Valid complete event stream, then live process waits | Same `deadline`, about 1,006 ms |
| Valid stream and exited leader; descendant holds pipe | Same `deadline`, about 1,005 ms |

The three error cases expose no raw stdout/stderr through the exception. All
owned fixture processes were absent after cleanup. This demonstrates the
diagnostic ambiguity; it does not choose one case as the real failure.
The existing finite-timeout/no-retry test and controlled-reason/redaction test
passed. An initial test selector used the wrong Codex test class; the Claude
case passed and the corrected Codex selector passed separately. No product or
test source was changed and no full application gate was repeated.

## Disposition

Confirmed proximate cause: the native exchange did not satisfy EOF/exit completion
within its admitted deadline. The underlying Claude/provider/process condition
cannot be determined from the existing receipt. Authentication preflight passed,
the earlier Claude call completed, and request sizes were admitted; those facts
do not prove continued service health during the failed call. No evidence shows
that raising the deadline alone would fix the problem.

The [progress-receipt implementation](NATIVE_PROGRESS_WORK_NOTE.md) now passes
offline source/wheel verification; a new installed artifact and fresh diagnostic
invocation remain pending. It adds bounded, redacted progress metadata on native
failure: input-drained state, first/last output timing, byte counts, stream EOF,
leader exit and cleanup state, without introducing an event parser. It preserves
finite deadlines, output limits, uncertain usage and no-retry
semantics. Do not retain native text, stderr excerpts, request content, auth data
or arbitrary event values. Prove those privacy/failure boundaries offline before
a separately bounded fresh diagnostic invocation. Do not replay slot 11 or
silently widen the frozen campaign's deadline. No runtime fix or new qualified
candidate is claimed by this documentation-only diagnosis.

Private metadata-only records under `.work/claude-timeout-diagnosis/`:

| Record | SHA256 |
|---|---|
| Retained-call comparison | `7cba7aee91a55a506dad8571c0bd090902ca6234efc182ad41551ee3294161d7` |
| Four-case offline probe review | `8b42eb1b63f0fd7f8517d328f12af370d19a43ce7e37eca7124fb733b333e441` |
| Frozen shared native runner | `c74007e885326ce54b2146ba94c1fd75189dc50b2535ad6ec4511372ed22ac0f` |

Ordinary engineering records are not prospective evaluation artifacts; no
sampling registry, custodian mapping, labels or outcome stores were consulted.
