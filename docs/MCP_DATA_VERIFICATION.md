# MCP data connection verification — 2026-09-09

Objective: make the data-mcp server usable through Mos Eisley's explicit CLI and
canonical agent port, including writes on both source backends and Ana Lite's
analysis profile. Work started from main `950cb88` in an isolated worktree.
The external server revision tested was data-mcp `2019983`.

Blocking checks: operator grants control dispatch; unapproved tools cannot execute;
input constraints survive lowering; environment values are explicitly selected;
uncertain writes are never automatically retried; protocol failures are bounded
and diagnostics do not disclose raw values. Paid provider integration, production
source access and hostile-process isolation are outside this slice.

## Evidence and dispositions

| Check | Evidence | Result |
|---|---|---|
| Real data path | `tests/test_mcp_data_integration.py` | Parquet create/append/replace/query; promoted semantic context/list/revision-bound metric; analysis write denial passed |
| Database persistence | Same test, disposable PostgreSQL 17 | INSERT/UPDATE commits remained visible in a new MCP session; DELETE and empty SELECT passed; unique schema removed |
| Canonical agent | `tests/test_mcp.py` | Two-turn fixture model used a real stdio MCP dispatcher through `run_agent` |
| Capabilities and schemas | Same tests | Explicit grants, configuration revalidation, undeclared arguments, pagination, missing/duplicate tools and unsupported schemas tested |
| Lifecycle and results | Same tests | Startup timeout reaps the child; cancellation and oversized/malformed results break the session; caller exceptions remain intact |
| Credential isolation | Same tests | Named environment value reached the child; unnamed secret did not; inherited HOME was blanked |
| Wire diagnostics | Same tests | SDK parser logged rejected wire values during fault injection; adapter filters now redact the message and exception before handlers receive it |
| Compatibility gate | `make check` | Full suite: 595 tests passed, 2 optional external-source skips; 87% branch-inclusive coverage; lint, strict typing, runtime export and wheel/sdist build passed |
| Final focused checks | `tests/test_mcp.py` | 16 tests passed after adding diagnostic redaction and four additional lifecycle/configuration cases; final lint/type checks passed |
| Dependencies | `uv audit --locked --no-dev` | No known vulnerabilities or adverse statuses in 40 packages |

The package smoke initially encountered sandbox-blocked dependency metadata
downloads; its rerun with network access passed in a disposable environment. No live
provider requests, production database changes or HDD data reads were performed.

The initial full suite contained 12 MCP tests; four further regressions brought
current discovery to 599 tests. The two external-source tests were also executed
separately against the real data-mcp installation and disposable PostgreSQL.
They remain opt-in in normal CI. Self-review and fixture evidence are not an
independent security review or a production deployment approval.

## Remaining limits

Application byte limits apply after SDK decoding. Supporting hostile executables
requires process isolation and wire-frame limits. Default server results exceed
the canonical agent's small output reserve; aggregate/narrow queries or explicitly
aligned budgets are required. New sessions cannot deduplicate previously submitted
writes. Cloud grants, certificates and actual HDD paths still require deployment
validation. Paid analytical conversations require their own transfer, spend,
retention and whole-run budget integration; existing paid commands remain tool-free.
