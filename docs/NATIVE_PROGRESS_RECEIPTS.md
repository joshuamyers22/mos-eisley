# Native failure progress receipts

Claude native-process failures can include an additive version-1 `progress`
object in the existing private `failure.json`. It helps diagnose RC12-SUB-01's
ambiguous native timeout without retaining client text. Older receipts and
failures before process creation may omit it. Existing failure reason, admitted
deadline and overall elapsed fields keep their meanings.

| Field | Observation |
|---|---|
| `schema_version` | Fixed integer 1 |
| `phase` | `input`, `output` or `exit`: the last exchange stage entered |
| `elapsed_ms` | Monotonic time since process creation completed, sampled before cleanup |
| `stdin_drained` | The local writer's drain returned; no claim that the provider consumed the input |
| `stdout` / `stderr` | Separate `bytes_observed`, `first_read_ms`, `last_read_ms` and `eof` |
| `leader_exited_before_cleanup` | The subprocess return code was available before the stop routine |
| `cleanup_completed` | The existing owned-group stop routine returned without an error |

Every byte count and millisecond value saturates at 1,000,000. First/last read
times are null until a nonempty chunk is observed. EOF requires observing an
empty read. These are host read observations, not exact native emission times.
The strict, immutable, extra-forbidden schema has fixed fields and constant-size
state; serialized progress stays under the tested 768-byte ceiling. Native
failure receipts with this object stay under the tested 1,024-byte ceiling.

A live leader with no observed output differs from a leader that emitted bytes
but remained alive. An exited leader with open streams points to inherited
pipes or another EOF delay. Two observed EOFs with a live leader identify an
exit wait. Input-phase failure identifies a local write/drain wait. These
observations narrow the failure location; they do not establish provider-side
generation, quota, retries, service health or billing.

The output readers are cancelled and their observations frozen before cleanup.
Signals and pipe closures during cleanup cannot manufacture a prior EOF or exit
observation. Cleanup failure retains its existing overriding `cleanup` reason
and sets completion false; the original stop/signalling behavior is unchanged.
Completion is not an independent attestation that every descendant is absent.
Cancellation still propagates normally and retains the existing uncertain-usage
semantics; it does not acquire a completed provider result.

No prompt, output, stderr excerpt, native event value, path, PID, argument,
environment, credential or arbitrary exception text enters the progress object.
No native-event parser, log discovery, telemetry sink or new transport is added.
The shared runner observes both clients, but this batch persists the new object
only through Claude's existing native-process failure receipt.

Timeouts, stream/output ceilings, private no-overwrite receipt writes, process
ownership and replay refusal remain authoritative. A progress receipt does not
authorize retry, scope renewal, deadline widening or a fresh provider call. The
published rc.12 artifacts and prior campaign records remain immutable. A new
installed artifact and separately bounded diagnostic call require their own
delivery and qualification evidence. See the [work note](NATIVE_PROGRESS_WORK_NOTE.md).
