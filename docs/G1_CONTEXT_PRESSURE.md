# G1 advisory context-pressure indicators

Status: implemented on 2026-09-21. This is the advisory pressure slice of plan
§6.7.3. It does not enable automatic compaction, delegation, stopping, approval,
or additional tool authority.

## Measurement contract

Every new author request records a schema-5 admission, or schema 6 when it also
contains work-unit-owned profile acquisition, with a versioned
`context-pressure-v1` snapshot. The denominator is the complete canonical request's
usable input-byte budget. Exact request bytes are partitioned into base system,
conversation, reusable memory, task profile, checkpoint, compaction, selected tool
schemas, and the remaining request envelope; the categories must sum to the admitted
request size.

Bytes and tokens are never conflated. The snapshot reports exact byte capacity and
overage. It labels `ceil(canonical request UTF-8 bytes / 4)` as a local estimate,
reports the current provider token count as unavailable, and separately totals only
historical usage whose provider unit is explicitly `tokens`. Byte-denominated
provider usage is counted as unavailable, not converted into confirmed tokens.

Executed tool results of at least 4,096 UTF-8 bytes are substantial under the
default policy. Repeated reads are duplicate canonical `(allowlisted tool ID, args)`
operations after the first since the active boundary. Tool call IDs do not defeat
duplicate detection. Status-bar and `/status` polling only reads saved state and is
never activity.

## Boundaries and events

Session start, checkpoint closure, fresh continuation, and author compaction are
explicit pressure boundaries. Snapshots report request growth, executed/substantial
tool counts, repeated reads, and compactions since that boundary. The default trial
threshold is 35% of usable request input and 25 substantial results; every
denominator, threshold, read allowlist, and counting rule is frozen in the saved
policy.

Threshold crossings and material changes produce one content-addressed, bounded
advisory event. The event contains reasons and a recommendation, but its contract
sets automatic stop, compaction, delegation, approval, and authority to false.
Hard context/request limits remain authoritative and unchanged.

`/context` preview schema 4 shows the exact prospective snapshot and advisory
without dispatch. `/status` reports the last admitted snapshot plus current
post-request activity. The TUI status bar shows the latest percentage, substantial
result count, and repeated-read count. None of these inspection paths mutates the
session or consumes an attempt.

## Persistence and compatibility

The selected policy, latest boundary, schema-5/6 admission, and per-entry activity
survive strict JSON and SQLite replay. Older admission schemas remain readable and
are never backfilled. SQLite hot/cold entry reconstruction preserves the same
activity contract, and author-compaction source bindings include that activity so a
changed retained record cannot silently alter pressure history.

## Acceptance coverage

Deterministic tests cover exact category totals and capacity, the labeled local
estimate and unavailable provider counts, threshold dispatch without blocking,
substantial results, duplicate reads with distinct call IDs, material growth,
read-only polling, strict request-admission binding, persistence, and installed-wheel
execution. Existing hard-limit tests continue to prove that an advisory cannot
enlarge a budget or bypass admission.
