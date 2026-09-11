# Preview workspace retention

`mos session-retention` evaluates an explicit retention policy against the SQLite
sessions indexed for one workspace:

```sh
mos session-retention --storage /path/to/sessions -C /path/to/project --before 2026-08-01T00:00:00Z --json
mos session-retention --storage /path/to/sessions -C /path/to/project --before 2026-08-01T00:00:00Z --keep-newest 5 --json
```

This command is **read-only**. It has no `--apply` or `--expected-sha256` option and
does not schedule cleanup. The report fixes `mode: "preview"`,
`verification: "index_metadata"` and `deletion_authorized: false`. Its hash identifies
an observation, not permission to remove a session. A separate
[single-session pruning command](CONVERSATION_PRUNE.md) now verifies the full
selected state and requires its own preview hash before deletion. Bulk and
automatic policy apply remain planned.

## Policy and retained work

`--before` is required and accepts an exact UTC timestamp at whole-second precision,
such as `2026-08-01T00:00:00Z`. There is no implicit current-time cutoff or local
timezone conversion. The accepted range begins at the Unix epoch and fits SQLite's
signed 64-bit nanosecond timestamp range.

The report orders all selected workspace sessions by saved modification timestamp,
newest first, breaking ties by descending session ID. `--keep-newest` defaults to
20 and accepts 0–1,000. Those positions are protected across the **whole workspace**,
including sessions that would already be retained for another reason.

Every entry has a summary, `candidate` or `retain`, and all applicable reasons in
this order:

| Reason | Meaning |
| --- | --- |
| `keep_newest` | Falls within the newest N workspace sessions. |
| `not_before_cutoff` | Saved at or after the cutoff; equality is retained. |
| `active` | The per-session lock was busy when probed. |
| `noncompleted_messages` | The index does not report every message as completed. This protects queued, running, failed, interrupted and cancelled work. |

A session is a candidate only when no retention reason applies. An old empty
session can qualify. A completed session is not automatically disposable: the
command reports policy candidates for review, and leaves every session in place.
Saved modification time is not a creation time or last-read time; imports and
exports can preserve an older source timestamp.

## Verification, scope and bounds

The default storage root is `~/.mos-eisley-sessions`; the default workspace is the
current directory, with `-C` selecting another. Workspace paths use the existing
canonical resolution rules. Only that workspace's SQLite index records are read.
A removed or empty workspace can produce an empty report; no workspace directory
is created. JSON snapshots and temporary files are outside this report.

The database is opened read-only and all index reads use one SQLite read
transaction. Each index is checked against its saved digest, row identity, owner,
workspace and timestamp. The report binds the storage directory's path/device/inode,
owner, canonical workspace, database store ID and generation, policy, and ordered
results. `plan_sha256` hashes that canonical version-1 plan. Counts and indexed
logical snapshot-byte totals are reported separately for candidates and retained
sessions. These are **indexed logical sizes, not reclaimable disk-space estimates**.

The pass admits at most 1,000 workspace sessions. An initial query fetches at most
1,001 IDs, bounds catalog ID/checksum fields, and rejects an oversized or malformed
catalog before reading any indexes. There is
no silent truncation or partial-policy result. Each index is capped at 32,000 bytes,
read and validated one at a time; only summaries remain in the result. Transcript
headers, messages, recordings and artifact bodies are not loaded or verified.
Consequently, even a readable index can refer to damaged retained content. A
candidate is not evidence of full-state integrity or a verified backup.

The shared session lock is probed nonblockingly and released immediately for each
entry. Activity is a momentary observation, not a reservation: a writer can start
after its probe or finish before the report is returned. The database read
transaction provides a consistent metadata snapshot; it may briefly delay commits
from other writers. The plan hash can change when activity changes, or when any
workspace advances the database generation, even if selected session summaries do
not change. Re-run the preview when reviewing a changed situation.

Private owner-local storage, regular-file and lock checks remain mandatory.
Missing, unsafe or corrupt selected indexes/locks abort the entire report without
printing a partial selection or private record contents. A hot rollback journal
is refused unchanged; preview performs no recovery. As with the other storage
commands, the local integrity model assumes cooperative writers and trusted
owner-local parent directories, not isolation from hostile processes with the same
OS user ID.

## Remaining retention work

Explicit [temporary-file cleanup](CONVERSATION_CLEANUP.md) and
[single-session deletion](CONVERSATION_SQLITE.md#privacy-retention-and-bounds) remain
separate commands. [Single-session pruning](CONVERSATION_PRUNE.md) now adds explicit
policy apply with full selected-state verification and atomic deletion. Bulk policy
apply, backup/journal expiry, broader unreferenced-object
retention, configurable physical quotas and SQLite vacuum/compaction are still
planned. Logical deletion does not promise secure erasure from backups, snapshots
or hardware. This 1,000-session **metadata** bound does not satisfy the separate
[1,000-message long-session capacity gate](CONVERSATION_STORAGE.md#planned-incremental-storage).
