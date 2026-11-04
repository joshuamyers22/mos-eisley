# Claude critic qualification latency profile, revision 2

Signed rc.14 qualified an explicit 120-second native deadline for Sonnet 5/high
through Claude Code 2.1.283 within the installed macOS arm64 profile below. This
is finite qualification evidence, not a general reliability claim or a change to
existing/default 60-second grants. Future calls require their own current
authorization; no stopped scope is reopened or widened.

The [event diagnostic](CLAUDE_EVENT_DIAGNOSTICS.md) observed a validated terminal
result at 49.492 seconds and EOF 179 ms later, after thinking metadata through
48.213 seconds. Two installed campaigns had previously crossed their 60-second
deadline with no complete admitted response. The evidence supports allowing more
finite latency in a new qualification attempt; it does not establish a percentile,
guarantee success within 120 seconds, or establish that an early-result/exit
workaround is safe. Strict EOF, exit, protocol and artifact validation remain.

| Limit | Revised qualification selection |
|---|---|
| Exact critic route | `anthropic_subscription`, `claude-sonnet-5`, `high` |
| Exact native client | Claude Code 2.1.283, executable/context hash bound |
| Native deadline | 120 seconds in a new immutable authorization |
| Outer subscription role timeout | Existing grant deadline + 35 seconds, hence 155 seconds |
| Canonical input / text output | 128,000 / 16,000 bytes |
| Reported output tokens | 8,192 |
| Correction cycles / retries / response repairs | Zero |
| Coding wall | Existing 600 seconds, independently enforced |
| Full campaign call/global wall ceilings | Existing 14 per store / 28 total / 90 minutes |
| Grant lifetime | At most one hour; expiry still refuses without renewal |

The existing installed `mos subscription authorize --timeout 120` admits this
deadline only through a new explicit grant. When multiple roles share an
authorization they share its native deadline; do not claim a per-role deadline
that the grant does not enforce. The host qualification tool's corresponding
explicit preparation selections are `--inference-timeout-seconds 120` and
`--max-output-tokens 8192`. Preparation alone supplies no live dispatch authority.
Its existing offline tests verify exact 120-second selection while retaining
the global invocation, input/output, coding-wall and correction ceilings.

The profile was subsequently exercised by signed rc.14
`ec3211e23c4a3e2b20837114e707bc8ebcbe625a`: both storage backends completed the
installed macOS arm64 workflow through review, exact creator approval, integration
and fresh tests. Four Claude critic calls returned valid bound artifacts and EOF
in 38.285/40.511 seconds (snapshot) and 36.338/34.664 seconds (SQLite). See
[qualification evidence](RC14_QUALIFICATION_REVIEW.md) and
[publication](RC14_PUBLICATION_WORK_NOTE.md). The original snapshot controller's
host assertion failure is retained; the owner separately authorized a fresh
SQLite-only run, whose controller passed in 224.556 seconds under stricter
45-minute outer bounds. Snapshot was not repeated.

The earlier [validation diagnostic](MODEL_REVIEW_DIAGNOSTICS_WORK_NOTE.md)
completed natively in 39.737 seconds but returned 159 non-JSON bytes. That closed
scope and all other historical uncertainty remain unchanged. rc.14's static
native envelope instructions and strict schema/runtime alignment now have direct
post-fix installed live evidence. No response repair, automatic retry or old
scope renewal supplied that evidence.

This qualifies the stated finite profile; it does not establish percentiles,
production-like load/reliability, default 60-second success or another platform's
native-client behavior. Those remain in the
[fresh v1 assessment](V1_PRODUCTION_READINESS_RC14.md). This document grants no
additional provider call, new campaign or stable launch authority.
