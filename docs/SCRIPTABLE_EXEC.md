# Scriptable execution

`mos exec` runs one literal input or one explicitly selected frozen review through
the same conversation startup, private stores, controller, policy checks and
spending admission as chat. It never starts a terminal input loop or interprets
slash commands in input. The default is recorded execution; live chat requires
the same explicit transfer consent, policy, ledger and artifact options as chat.
An exact live-review selection retains all existing launch and one-use checks.
No execution mode grants publication authority.

```sh
mos exec --json --no-memory "Remember that the fixture boundary is ten."
printf %s "Remember that the fixture boundary is ten." | mos exec --json --stdin --no-memory
mos exec --json --stdin < prompt.txt
mos exec --json --review --review-packet frozen-review.json
```

Input is strict UTF-8, at most 8,000 bytes and 256 lines, with nonblank text.
Bytes and newlines are preserved; an added newline changes a recording's exact
request identity. Stdin is selected by `--stdin`, positional `-`, or omission of
positional input when stdin is redirected. Positional input and nonempty piped
input are ambiguous and rejected. Empty redirected stdin is allowed alongside
a positional prompt. `--stdin` cannot accompany a positional prompt. Review
requires `--review` and exactly one of `--review-packet` or
`--live-review-selection`; review rejects prompt/piped text because its input is
already frozen. Input validation precedes session creation and provider use.
The result records input source, byte count and SHA-256, without copying input text.
Byte admission does not impose a pipe-completion deadline; Ctrl-C interrupts a
producer that never closes its pipe.

With `--json`, stdout contains one JSON object per line. Every event carries
`schema_version: 1` and a contiguous invocation-local `sequence`. Events include
`exec.input_requested`, shared startup events and `exec.started`. The final line
is exactly one `exec.result`, including on argument rejection and cancellation.
Diagnostics and live-review child output go to stderr. `--help` is a documentation
request and prints help rather than an execution result. A killed process or
closed stdout cannot deliver a terminal record; neither condition permits replay.

The result identifies task `status`, `exit_code`, `session_id`, `mode`, optional
`review_mode`, session-local `artifact_ids`, `answer`, `usage`, `usage_status`,
`omissions` and `omissions_status`. Review additionally reports `review_status`,
`review_verdict` and the retained result's SHA-256 when available. Artifact IDs
identify entries in the saved session; use existing session inspection commands
with the same workspace/storage/backend. `persistence_status: uncertain` discloses
failed persistence and suppresses claims about result bytes. Unknown usage or
omissions are null/unavailable, never fabricated zeroes. Recorded usage uses byte
units; observed provider usage is not a claim of reconciled billing. Review usage
is unavailable through this projection; its existing private receipts remain the
authority. No selected input is silently truncated.

| Exit | Status | Meaning |
|---:|---|---|
| 0 | `completed` | The operation completed; inspect `review_verdict` separately |
| 1 | `failed` | Provider, execution, storage or output failure |
| 2 | `invalid_input` | Invalid arguments, encoding, size, ambiguity or input schema |
| 3 | `policy_denied` | Startup/admission refused by existing policy or required authority |
| 4 | `budget_exhausted` | Context, pending-input, request or aggregate spending admission failed |
| 5 | `review_incomplete` | A started review lacks a complete valid verdict/quorum |
| 130 | `cancelled` | Interrupted input or cancelled controller work |

`review_status` is `not_requested`, `completed` or `incomplete`.
`review_verdict` is null, `accept`, `revise`, `reject` or `infrastructure_error`.
Both `revise` and `reject` are complete review outcomes and return zero. A CI
acceptance gate must require `status == "completed"`, `review_status == "completed"`
and `review_verdict == "accept"`; exit zero alone is insufficient.

SIGINT/SIGTERM during controller execution cancels the owned work and awaits its
existing cleanup. Repeated signals during cleanup do not create retries or reset
exposure. Retained cancelled/failed attempts stay consumed. Resume through existing
session controls; exec does not automatically resume or retry unfinished work.
Interactive-only directory selection, TUI and implementation workflow options are
rejected. Literal input is not permission to inspect a repository, run tools or
implement changes.

`tests/test_exec.py` runs CLI subprocess journeys plus controller cancellation and
ledger checks. `tools/smoke_package.py` repeats the same tests from an installed
wheel outside the checkout. These tests use synthetic recordings and no paid calls.
