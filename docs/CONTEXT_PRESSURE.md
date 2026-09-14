# G1 context-pressure indicators

The recorded author conversation exposes advisory-only context pressure through
`/status` and `/context`. The implementation measures metadata already selected by
the request and task-state boundaries; it does not read extra project content,
hydrate historical artifacts, run a provider/tool, automatically compact context,
or grant authority. Explicit validated compactions contribute to the count.

## Measurement contract

The version-1 pressure report contains:

- the upcoming request's exact canonical byte total split without double-counting
  into system instructions, selected tool schemas, project guidance, selected
  memory, checkpoint/task state, conversation blocks, retained reasoning, tool
  output and remaining request-envelope bytes;
- independent saved-context and usable-model-input capacities, available bytes and
  overflow bytes;
- a clearly labeled local `ceil(UTF-8 bytes / 4)` token estimate, kept separate from
  provider-reported input/output/cached tokens and explicit unavailable-request
  counts;
- admitted serialized-input growth since the selected checkpoint or session start,
  plus projected growth if the queued request were dispatched; and
- cumulative substantial completed non-inspection tool calls, repeated still-valid
  reads and compactions from the immutable checkpoint baseline plus the recorded
  session where those observations exist.

The checkpoint baseline remains visible as its original cumulative metrics. Session
growth is separate, so a status read cannot rewrite, reset or masquerade as the
task-wide ledger. Reviews have no chat admission and do not receive author checkpoint
context. Provider byte usage is never relabeled as provider tokens.

## Policy and advisories

Policy version 1 uses `usable_model_input_bytes_v1` as the utilization denominator,
`completed_noninspection_tool_calls_v1` as the substantial-call rule and
`ceil_utf8_bytes_div_4_v1` for the local estimate. Defaults are 35% request usage and
25 calls. Trusted `chat`/`resume` launch configuration may select 30–40% with
`--context-pressure-percent` and 20–30 calls with
`--substantial-tool-call-threshold`.

A threshold crossing requests assessment. For an ongoing author objective it may
name validated author compaction as an option; after a terminal milestone it may
name checkpoint-based fresh continuation. It never performs either. Exceeding a hard
context/request byte limit is reported separately and the existing admission limit
remains authoritative.

The terminal may emit a `conversation.context_pressure` metadata event when pressure
crosses, clears, or a pressured request materially changes. The ephemeral monitor
suppresses repeats and caps events at 16 per terminal run. Events contain no prompt,
message, memory, checkpoint or evidence text and are never stored as conversation
entries. Repeated pressure cannot approve work, delegate, enable a tool, grant
credentials/spend/execution, or change critic/judge isolation.

## Acceptance boundary

Focused fixtures reproduce category totals, distinguish bytes/local estimates from
provider tokens, preserve unavailable counts and checkpoint counters, reject policy
values outside the adopted evaluation ranges, distinguish advisory pressure from
hard overflow, suppress repeated events, and verify read-only line/TUI inspection.
These fixtures establish instrumentation behavior only. The separate validated
author-compaction gate establishes reconstruction, authority, freshness and overflow
safety, but neither mechanism establishes improved live task quality. That claim
remains behind the G3 evaluation gate.
