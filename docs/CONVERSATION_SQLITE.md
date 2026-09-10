# Incremental SQLite conversation storage

SQLite is now an explicit local storage option for the recorded conversation
preview. New sessions use incremental message records and session-scoped artifact
references. Metadata listing is paginated and does not load transcripts, recordings
or reviews. Existing JSON sessions continue to use the default snapshot backend.

## Start, resume and list

```sh
mos --storage-backend sqlite
mos resume --last --storage-backend sqlite
mos sessions --storage-backend sqlite --limit 20 --json
```

Use the same `--storage PATH`, `-C PATH` and `--storage-backend sqlite` selection on
subsequent commands. The default root is `~/.mos-eisley-sessions`. SQLite and JSON
sessions may coexist in that root, but listing and latest-session selection use
only the explicitly selected backend. A missing SQLite session never falls back to
JSON. Selecting SQLite neither imports nor rewrites existing snapshots; migration
remains planned.

`--session-max-bytes` works on launch/resume for either backend. In SQLite it limits
the canonical **logical snapshot**, including all retained evidence and historical
memory, with the existing 2 MB default and 32 MB ceiling. The listing fields
`snapshot_bytes` and `snapshot_max_bytes` report that logical size and budget;
they do not report physical database file size. Memory refresh/off and combined
memory/budget changes retain the same controller behavior.

SQLite requires version 3.37 or newer for its
[STRICT tables](https://www.sqlite.org/stricttables.html). It uses Python's bundled
`sqlite3` module; no new package dependency or database service is required.

## Metadata pages

`--limit` accepts 1–100 rows, defaulting to 50. JSON listing returns `sessions` and
`next_cursor`; a null cursor means the final page. Pass a returned cursor unchanged:

```sh
mos sessions --storage-backend sqlite --limit 20 --cursor TOKEN --json
```

Human output also prints the next cursor. Keep the same storage root and workspace.
A cursor binds the database identity, OS owner, workspace, database generation and
last sort position. Any committed session save or deletion invalidates outstanding
cursors, including changes in another workspace. Restart listing when a cursor is
stale; the command returns no partial page on an error. Cursors are continuation
positions, not credentials or authorization.

Pages order by saved timestamp and session ID, newest first, and read at most one
extra index record to determine whether another page exists. Records and cursor
inputs have byte bounds. The SQLite index avoids the snapshot backend's 256-session
scan cap. `--catalog-max-bytes` applies only to JSON snapshots and is rejected with
SQLite. `resume --last` selects one metadata row, acquires that session's lock, then
revalidates the complete saved state and its selected hash.

Metadata pages verify their index records and ownership, not every referenced
artifact. Corruption in an artifact can therefore leave its metadata visible while
resume rejects it. Full load/save/delete validates the retained state. Listing
uses a read-only connection; it does not repair, migrate or initialize storage.

## Incremental writes and recovery

The private `sessions.sqlite3` file contains versioned owner/database metadata,
session heads, message records and immutable artifact values keyed by session and
content digest. Memories, review packets/results and retained recordings are
referenced from records. Equal artifacts are reused within a session; the backend
does not share artifacts between sessions or owners.

A save validates the current state and revision, then commits the updated head,
changed message rows, new artifact references and catalog generation in one
transaction. Unchanged message rows/artifacts are not rewritten. Objects no longer
referenced by the saved state are removed in that same transaction. Earlier memory
remains retained while historical entries reference it. The current implementation
still reconstructs and validates the complete bounded logical state on load and
save; this is incremental disk persistence, not yet bounded transcript loading.
Repeated artifact references count toward an expanded byte bound before their
values are decoded, so corrupt references cannot bypass the input limits.

The adapter uses rollback journaling and full synchronization under SQLite's
[atomic-commit mechanism](https://www.sqlite.org/atomiccommit.html). A per-session
file lock prevents cooperating writers from opening the same session concurrently;
SQLite also serializes database writes across sessions. Busy/open/transaction
failures are reported without automatically repeating a request. On an uncertain
commit, reopen to inspect the durable state. Saved running entries become
interrupted, queued messages stay paused, and consumed attempts are not replayed.
An interrupted initial database setup that lacks a valid schema is rejected; this
release has no automatic initializer repair or migration command.

## Privacy, retention and bounds

The root, database, journal and lock files must be private and owned by the current
OS user. Checks reject symlinks, hardlinks, special files, foreign owners, unexpected
schema and unsupported journal modes before normal use. SQLite owns its own file
descriptors: the root and its parent paths must remain trusted. Hostile same-user
path replacement, deliberate valid database rewrites and rollback of backups are
outside this local integrity model. The database is not encrypted by this adapter;
use an appropriately protected local volume for retained content.

Exact-state deletion uses the same command and hash from listing:

```sh
mos session-delete SESSION_ID --expected-sha256 HASH --storage-backend sqlite
```

Deletion atomically removes the session, its messages and its artifacts. It keeps
the shared database and empty session lock. The backend enables SQLite's
[`secure_delete`](https://www.sqlite.org/pragma.html#pragma_secure_delete), but
logical deletion is not a promise of erasure from filesystem snapshots, storage
hardware, journals or backups. Database space can be reused without the file
shrinking. Backup expiry, vacuum/compaction, bulk retention and migration remain
explicit future work.

The database has an initial 256 MB physical file ceiling, enforced on open and via
SQLite's page-count limit on writable connections. Each existing sidecar is also
bounded. This is separate from the per-session logical budget, is not a disk-space
reservation, and is not yet configurable. The 16-message/attempt preview cap,
recorded responses, context budgets and 32 KiB memory limit remain unchanged.

The next stages are paginated transcript/artifact loading, context compaction,
configurable physical retention, explicit legacy migration and the 1,000-message
capacity/recovery gate in [plan §17.5](mos-eisley-plan.md#175-long-session-storage-and-independent-budgets).
Passing metadata pagination for 260 sessions does not satisfy that long-session gate.
