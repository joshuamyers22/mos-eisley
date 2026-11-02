# Claude critic qualification latency profile, revision 2

Use an explicit 120-second native deadline for the next separately authorized
Sonnet 5/high qualification attempt through Claude Code 2.1.283. This is a
revised qualification selection, not a claim of general reliability or a change
to existing/default 60-second grants. No stopped scope is reopened or widened.

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

Full installed qualification remains open. Before another campaign, resolve and
verify the probe's invalid `ModelReview` artifact boundary, review the exact
candidate/profile, refresh native readiness and obtain fresh bounded campaign
authority. Any newly authorized campaign must retain the first-unplanned-failure
stop rule and every earlier ledger unchanged. This task authorizes no further
provider call, replacement probe, new full campaign or stable/public launch.
