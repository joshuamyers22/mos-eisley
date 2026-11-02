# Bounded Claude event-state diagnostics

Claude's private native attempt now includes a separate strict schema-1
`event-progress.json`, alongside the unchanged generic failure progress. It is
written after the native exchange on success, controlled failure or cancellation.
It never admits an early completion or supplies retry/usage authority.

Fixed milestone groups `init`, `thinking`, `assistant` and `result` contain a
count and nullable first/last observed milliseconds. Other fixed fields count
rate-limit events, unknown events, records after a result marker, malformed and
oversized lines. No event-provided string, text, identifier, path, argument,
environment or credential enters this receipt. Counts/times saturate at
1,000,000 and the tested serialized receipt is smaller than 2,048 bytes.

`result_validation` is `not_seen`, `valid`, `invalid` or `unavailable`. At most
the first result prefix is checked with the existing strict Claude parser,
including exact model/session/tool restrictions, matching answer and usage/output
bounds. This is an observation of that prefix. The unchanged final parser still
requires complete streams and a successful native exit, and rejects trailing
records or other invalid data. A valid native result does not establish a valid
coding `ModelReview`, approval, integration or billing result.

Inspection uses at most 128,000 line bytes, 1,000,000 prefix bytes and 4,096
classified records. Transient native bytes remain in bounded memory only and
are discarded before writing the receipt. These buffers contain no persistent
payload store. `inspection_limited`, `oversized_lines`, `malformed_lines` and
`pending_line_bytes` expose incomplete observation. In particular, a partial
unframed last line cannot establish the absence of a terminal result.

`stdout_eof` and `stdout_eof_ms` require an actual empty stdout read. Event
milestones share the generic runner's post-process-creation monotonic clock.
`adapter_elapsed_ms` spans the invocation including startup and cleanup; native
authentication preflight is outside it. Read timestamps are host observations,
not exact provider emission times. Neither reader cancellation nor cleanup
manufactures a prior EOF or result marker.

Offline fixtures exercise unfinished output, a validated terminal result with
open pipes, closed streams awaiting leader exit, an exited leader with inherited
pipes, ordinary completion, fragmented UTF-8, unterminated final lines at EOF,
invalid/trailing records and inspection/output ceilings. Signature, authorization,
one-use uncertain ledgers and process-group cleanup remain authoritative.

## Fresh one-call result, 2026-11-02 UTC

One newly authorized source-orchestrated probe used the exact retained synthetic
failed rc.13 implementation-critic packet under a new grant/workspace/usage root.
The unreleased source and probe harness were frozen by hashes. Claude Code
2.1.283 / Sonnet 5/high received a 120-second native ceiling, with unchanged
128,000 input bytes, 16,000 text output bytes and 8,192 reported output tokens;
the outer wall/monotonic ceiling was 180 seconds. Actual HOME/context stayed
fixed; API keys were absent. No signing/publication or full campaign was run.

| Native observation | Time / count |
|---|---|
| Init | 294 ms |
| Thinking metadata | 38 records, 2,494–48,213 ms |
| Assistant records | 2 records, 49,137–49,478 ms |
| Validated terminal result | 49,492 ms |
| Stdout EOF | 49,671 ms |
| Terminal-to-EOF interval | 179 ms |
| Adapter exchange including cleanup | 49,679 ms |
| Entire authorized call | 50.205 s |

The probe reserved/dispatched/completed exactly once. It returned a
protocol-valid native result, 4,797 reported output tokens, no trailing records,
no observation limitations and a clean exit. No final-result/exit stall was
reproduced: the long observed interval preceded the terminal result, with thinking
metadata continuing near the assistant response. This does not reconstruct
RC13-SUB-01's discarded event contents or prove the cause of either historical
60-second timeout.

The returned text did not validate as the coding `ModelReview` contract. The
probe retained that safe Boolean and a response hash, not the response body or
arbitrary validation messages. Its exact schema defect therefore remains
unclassified; there was no repair or second call. Native completion must not be
reported as successful coding review or full workflow acceptance.

Private proof is retained under this source worktree's `.work/one-event-probe/`.
The canonical request SHA256 is
`121a207e96b424f848d55c01d2f1e09821fee206fed8665e80564635b70ea2f6`;
the frozen 864-input manifest SHA256 is
`6261d4bbd826b6648962237f4c08279f680c77b1ad320f7842ffc71898884cda`.
All source/harness hashes and all seven historical campaign fingerprints remain
unchanged. Every historical uncertain call remains closed. No prospective
sampling registry, custodian mapping, label store or outcome store was read;
these are ordinary engineering receipts, not evaluation eligibility evidence.

The decision is to retain strict completion handling and use the explicit
[revised qualification latency profile](CLAUDE_NATIVE_LATENCY_PROFILE.md).
Its full workflow qualification and the `ModelReview` artifact issue remain
open. The one-probe authorization is exhausted.
