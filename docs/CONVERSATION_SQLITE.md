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
JSON. Selecting SQLite neither imports nor rewrites existing snapshots. Use the
explicit migration command below to copy a selected JSON session.

`--session-max-bytes` works on launch/resume for either backend. In SQLite it limits
the canonical **logical snapshot**, including all retained evidence and historical
memory, with the existing 2 MB default and 32 MB ceiling. The listing fields
`snapshot_bytes` and `snapshot_max_bytes` report that logical size and budget;
they do not report physical database file size. Memory refresh/off and combined
memory/budget changes retain the same controller behavior.

SQLite requires version 3.37 or newer for its
[STRICT tables](https://www.sqlite.org/stricttables.html). It uses Python's bundled
`sqlite3` module; no new package dependency or database service is required.

## Import an existing JSON session

Preview one session, then apply using the returned `snapshot_sha256`:

```sh
mos session-migrate SESSION_ID --json
mos session-migrate SESSION_ID --apply --expected-sha256 HASH --json
mos resume SESSION_ID --storage-backend sqlite
```

Pass the same `--storage PATH` and `-C WORKSPACE` to all three commands when using
non-default locations. Migration copies `<SESSION_ID>.json` into `sessions.sqlite3`
within that storage root. It preserves the session ID, owner, workspace, revision,
canonical state hash, consumed attempts, historical memory and retained review/
recording evidence. The source file's saved timestamp becomes the imported index
timestamp. Running and queued entries remain unchanged during import; only an
explicit resume performs interrupted-state recovery, without replaying attempts.

The default command is a read-only preview and never creates storage or locks.
Its receipt reports status (`planned` or `already_present`), paths, source bytes,
canonical logical bytes, revision, message count and hash; it prints no transcript
or memory content. Sizes do not predict database allocation or reserve free space.
`--apply` requires an exact source hash and retains the original JSON file. A shared
session lock excludes cooperating JSON and SQLite writers throughout selection and
import. Ownership, file privacy, source integrity and destination schema are checked.
The importer reconstructs and compares the complete destination state and rechecks
the source hash before committing the transaction. The receipt reports `imported`
only after commit. An identical existing state returns `already_present` without
rewriting it; a different or subsequently advanced destination is rejected.

After an interrupted import, retry the apply command with the same source hash.
SQLite rolls back unfinished transactions; if the commit already completed, retry
verifies the existing copy. A read-only preview cannot recover a hot rollback journal
and returns an error without modifying it; the explicit apply path permits recovery.
An incomplete initial database schema is still rejected and has no automatic repair.
The JSON source remains available after failure. Migration can copy a session whose
workspace was removed, but resume still requires that workspace to exist.

The two copies can diverge after migration. Continue using `--storage-backend sqlite`
to use the imported session. There is no automatic synchronization or source removal.
Deleting the JSON copy is a separate `session-delete` operation using its current
hash and the default snapshot backend. Bulk imports, cross-root moves and reverse
migration remain planned; this command copies one local session in place.

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

## Transcript pages

Read SQLite conversation text without opening the interactive session:

```sh
mos session-transcript SESSION_ID --limit 4 --json
mos session-transcript SESSION_ID --limit 4 --cursor TOKEN --json
```

This command selects SQLite explicitly; use the same `--storage PATH` and
`-C WORKSPACE` as the saved session. Pages run in read-only transactions and can
inspect committed content while the session is open. They create no files, do not
recover running entries, and do not dispatch work. Missing storage or a hot rollback
journal produces an error rather than an implicit initialization or recovery.

Each page returns positions, text, status, answers, usage and steering links, plus
artifact field names, hashes and byte sizes. Memory, review packets/results and the
retained recording are not loaded. Reference availability and size are checked only
for returned entries; artifact content integrity is still verified on full resume.
Explicit artifact expansion and terminal scroll integration remain planned. This
reader is a user-invoked CLI/library operation, not an ambient-history tool for
models or independent critics.

`--limit` accepts 1–16 messages, defaulting to four. Pages also admit at most 512,000
stored message-record bytes, checking lengths before fetching payloads. They may
return fewer messages than requested with a continuation cursor. Record bounds,
contiguous positions and saved per-entry hashes are checked before returning any
page. Reads touch one bounded session index, at most the requested number of row
lengths, admitted message payloads and selected reference lengths. They never load
the session header, other message payloads or artifact values. The byte count covers
stored records, not escaped JSON output or physical disk reads/cache allocation.

Cursors bind the owner, database, workspace, session, snapshot hash, catalog
generation and next position. Any committed save, deletion or index preparation
invalidates outstanding cursors, including changes in other sessions. Restart from
the first page after a stale-cursor error. Pages use chronological message positions;
cursor tokens are continuation data, not credentials. Corrupt unread pages can
remain undiscovered until selected; page verification does not replace a full-state
integrity check.

New saves and imports include per-entry digests in the derived session index.
Older SQLite sessions remain resumable, but page reads require explicit preparation:

```sh
mos sessions --storage-backend sqlite --json
mos session-transcript SESSION_ID --prepare --expected-sha256 HASH --json
```

Preparation locks the session, verifies the complete bounded state, checks the
selected hash and transactionally adds the derived digests. It preserves the
session hash, revision, saved timestamp, message/artifact records and consumed
attempts. Repeating preparation verifies the state without rewriting the index.
It cannot be combined with page options and never runs automatically during reads.
A normal session save also writes the new index. Use this version of Mos Eisley
for prepared/new indexes; older builds may reject the added index field. The digest
list is bounded by the current 16-message schema; lifting that cap also requires an
index layout that stays bounded as history grows. Preparation still uses a full-state
read, and neither paginated interactive resume nor the
long-session capacity gate is implemented by this milestone.

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
release has no automatic initializer repair.

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
shrinking. Backup expiry, vacuum/compaction, bulk retention and bulk migration remain
explicit future work.

The database has an initial 256 MB physical file ceiling, enforced on open and via
SQLite's page-count limit on writable connections. Each existing sidecar is also
bounded. This is separate from the per-session logical budget, is not a disk-space
reservation, and is not yet configurable. The 16-message/attempt preview cap,
recorded responses, context budgets and 32 KiB memory limit remain unchanged.

The next stages are bounded interactive resume, transcript scrolling and selected
artifact loading, context compaction,
configurable physical retention, bulk migration and the 1,000-message
capacity/recovery gate in [plan §17.5](mos-eisley-plan.md#175-long-session-storage-and-independent-budgets).
Passing metadata pagination for 260 sessions does not satisfy that long-session gate.
