# Claude critic qualification latency profile, revision 2

The explicit 120-second native profile passed the separately authorized signed
rc.14 both-store installed qualification on macOS arm64 with Sonnet 5/high through
Claude Code 2.1.283. See the [exact live evidence](RC14_QUALIFICATION_REVIEW.md).
This is scoped historical success, not a general reliability claim or a change
to defaults or old grants. rc.15 signed/offline qualification did not repeat live
inference; see the [current evidence matrix](V1_INSTALLED_ACCEPTANCE_RC15.md).

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

The earlier [validation diagnostic](MODEL_REVIEW_DIAGNOSTICS_WORK_NOTE.md)
completed natively in 39.737 seconds but returned 159 non-JSON bytes. Subsequent
source corrections made the native request envelope explicit and aligned the
advertised review schema with runtime rules. Signed rc.14 then produced valid
bound Claude plan/implementation reviews on both stores. Four critic calls
completed in 38.285/40.511 seconds (snapshot) and 36.338/34.664 seconds (SQLite),
with EOF. The original stopped campaigns and controller assertion failure remain
preserved in their records; a successful later case does not erase them.

Those observations establish neither a percentile nor a success-rate/billing
guarantee. Future invalidated or missing live scopes require reviewed exact
candidate/profile, fresh native readiness and fresh bounded authority. Preserve
the first-unplanned-failure stop rule and every earlier ledger. This guidance
authorizes no call, replacement probe, campaign or stable/public launch.
