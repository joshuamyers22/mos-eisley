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
hash and the default snapshot backend. The bounded batch command below handles
multiple explicit sessions. The transfer command below copies one session across
storage roots. Single-session and bounded batch reverse exports are described
below; automatic source removal remains planned.

## Copy a JSON session to another storage directory

Create a private destination directory, preview one selected JSON session, and
apply using the returned `transfer_sha256`:

```sh
mkdir -m 700 /path/to/destination
mos session-transfer SESSION_ID --storage /path/to/source --destination-storage /path/to/destination -C /path/to/project --json
mos session-transfer SESSION_ID --storage /path/to/source --destination-storage /path/to/destination -C /path/to/project --apply --expected-sha256 TRANSFER_HASH --json
mos resume SESSION_ID --storage /path/to/destination --storage-backend sqlite -C /path/to/project
```

Both storage roots must already exist, be private and belong to the current user.
Preview creates no directories, locks or database files. The version-1 transfer
plan binds both absolute paths and device/inode identities, owner, workspace,
session ID, canonical state hash, revision, message count and source/logical bytes.
The receipt exposes metadata, without copied conversation or evidence text. Apply
requires that exact plan hash before opening the writable destination. Changing a
selected source, serialization size, workspace or directory requires a fresh
preview. Destination status and source timestamps do not affect the hash.

Transfer preserves the complete state, admission records, memory, retained evidence,
consumed attempts and original workspace identity. It copies the source timestamp
to the destination index without changing source bytes or modification time. Running
and queued messages remain as saved until an explicit resume. This command changes
session storage, not project identity or the location of user/project memory files.

The source lock is held throughout selection and transfer; destination access uses
its own session lock. Apply checks both directory identities before creating
destination metadata and rechecks identities and source selection inside the atomic
import transaction. An identical existing destination returns `already_present`;
an advanced or different destination is never overwritten. A retry after a lost
commit acknowledgment verifies the committed copy with the same transfer hash.
Other destination sessions are retained. These checks assume trusted parent
directories and do not isolate storage from another process with the same user ID.

Read-only preview refuses hot rollback journals without recovering them. Explicit
apply with a previously reviewed transfer hash permits SQLite recovery. A failed
first import can leave an empty database or lock files; incomplete initial schemas
are rejected and are not automatically repaired. Both copies can later diverge:
there is no synchronization, source deletion or implicit backend switch. Individual
32 MB snapshot, saved logical and physical SQLite limits still apply; selection and
verification decode bounded complete sessions. Cross-root batches are described
below. Retention and the long-session capacity gate remain open.

## Import a selected batch of JSON sessions

Preview the explicit session IDs, then apply using the returned `batch_sha256`:

```sh
mos session-migrate-batch SESSION_A SESSION_B --json
mos session-migrate-batch SESSION_A SESSION_B --apply --expected-sha256 BATCH_HASH --json
```

Pass the same `--storage PATH` and `-C WORKSPACE` when using non-default locations.
A batch accepts 1–32 distinct session IDs, sorted into a stable order. It does not
scan for other sessions. All selected sources must belong to the current user and
the selected workspace. The command copies them into SQLite in the same storage
root and retains every JSON source. It preserves the same state, ownership,
attempt, admission-record and evidence guarantees as single-session migration.

The version-1 plan contains the selected IDs and canonical state hashes, revisions,
message counts, source/logical byte counts, owner, workspace and storage directory
path/device/inode. Selected JSON source bytes total at most 64,000,000; each read
also respects the individual 32 MB ceiling and saved session limit. Source
preflight reads one bounded snapshot at a time and retains only metadata between
sessions. This byte admission does not reserve database space or bound total Python
memory; verification rereads sources and the existing importer decodes one complete
destination for comparison. Physical SQLite and artifact limits remain independent.

Both modes validate every selected source before touching destination data. Preview
then checks each destination through the existing read-only importer. Apply requires
the exact batch hash before opening a writable destination. The hash binds the
complete source selection, including source byte sizes and directory identity,
and excludes destination status and source timestamps. Reordering IDs has no effect.
Changed source content, serialization size, selected IDs, root or workspace require
a new preview. Each source is checked again against its selected hash and sizes
under its session lock, including a final check inside an import transaction.

**Transactions are per session.** A later conflict, lock, storage failure or source
change can stop a batch after earlier imports committed. No completed import is
rolled back to compensate. Retrying with the same source selection and batch hash
verifies those existing copies as `already_present` and imports the remainder.
An advanced or different destination is never overwritten. A process can exit after
commit but before returning a result; retry verification resolves that uncertainty.
A read-only preview refuses a hot rollback journal without recovering it. An apply
with the previously verified batch hash permits the existing SQLite recovery path.
An incomplete schema still requires separate investigation; it is not repaired.

The `conversation.migration_batch` JSON result contains `schema_version: 1`, `mode`,
`status` (`planned`, `completed` or `stopped`), `batch_sha256`, `plan`, ordered
per-session `receipts`, and `imported`/`already_present` counts. A stopped result
also identifies `failed_session_id` and a bounded `failure` category. Its receipts
cover the successfully verified prefix; the failing session may have committed
before a result was lost. The command exits 2 on failure. Invalid selection or
source preflight errors exit before a batch result is available and print a safe
notice. No source text, memory or review evidence is included in these reports.

Bulk retention and the long-session capacity gate
remain separate work.

## Copy a selected batch to another storage directory

`session-transfer-batch` combines the bounded source selection of same-root batches
with cross-root transfer. Both directories must already exist and be private and
owned by the current user. Preview one to 32 explicit JSON session IDs, then apply
using the returned `batch_sha256`:

```sh
mos session-transfer-batch SESSION_A SESSION_B --storage /path/to/source --destination-storage /path/to/destination -C /path/to/project --json
mos session-transfer-batch SESSION_A SESSION_B --storage /path/to/source --destination-storage /path/to/destination -C /path/to/project --apply --expected-sha256 BATCH_TRANSFER_HASH --json
```

The version-1 plan nests source selection metadata under `sources` and the other
directory's path/device/inode under `destination`. Source metadata binds sorted,
distinct IDs, owner, workspace, source directory identity, state hashes, revisions,
message counts and source/logical byte totals. At most 64 MB of source JSON is
selected; per-session reads also respect the 32 MB ceiling and saved session limit.
Every source is preflighted before destination inspection, retaining only metadata
between sessions. Reverification limits each source read to its selected byte count.
This bounds admitted source bytes, not total Python memory or reserved disk space.

Apply requires the complete batch transfer hash before opening a writable
destination. It reuses the single-session transfer checks, including both root
identities and a source selection recheck inside each import transaction. The hash
excludes destination status and source timestamps, so an unchanged selection can
retry after earlier commits or single-session imports. An advanced destination is
never overwritten. Preview creates no files and never repairs a hot journal;
explicit apply permits SQLite recovery after validating the batch selection.

**Each session commits independently.** Sources are locked one at a time, rather
than frozen as one batch. A late lock, source change, directory replacement or
destination conflict can stop after earlier copies committed. The
`conversation.transfer_batch` result reports `mode`, `status`, `batch_sha256`, the
plan, ordered single-transfer `receipts`, and `imported`/`already_present` counts.
A stopped result also identifies `failed_session_id` and a bounded `failure`
category; CLI exit status is 2. The reported prefix includes only returned,
verified results. The failing session may have committed before its acknowledgment
was lost; retry verifies that copy. Invalid selection and source-preflight failures
occur before a batch result exists and produce a safe notice without source text.

The source files, workspace identity, memory, review/recording evidence, admission
records, timestamps and consumed attempts retain the single-transfer guarantees.
Transfer does not resume queued/running work, synchronize copies or remove sources.
Use `mos resume SESSION_ID --storage /path/to/destination --storage-backend sqlite
-C /path/to/project` to resume an imported session explicitly. Physical
retention and the long-session capacity gate remain separate work.

## Export a SQLite session to JSON

`session-export` copies one selected SQLite session into the JSON snapshot backend.
The destination defaults to the source storage directory:

```sh
mos session-export SESSION_ID --storage /path/to/sessions -C /path/to/project --json
mos session-export SESSION_ID --storage /path/to/sessions -C /path/to/project --apply --expected-sha256 EXPORT_HASH --json
mos resume SESSION_ID --storage /path/to/sessions --storage-backend snapshot -C /path/to/project
```

To select another existing private destination directory:

```sh
mos session-export SESSION_ID --storage /path/to/sqlite-source --destination-storage /path/to/json-destination -C /path/to/project --json
mos session-export SESSION_ID --storage /path/to/sqlite-source --destination-storage /path/to/json-destination -C /path/to/project --apply --expected-sha256 EXPORT_HASH --json
mos resume SESSION_ID --storage /path/to/json-destination --storage-backend snapshot -C /path/to/project
```

Preview reads and verifies the complete bounded SQLite state and creates no files.
Its plan binds both directory paths/device/inodes, backend direction,
owner, workspace, session ID, state hash, revision, message count and exact canonical
JSON snapshot bytes. The `conversation.export` receipt reports `planned`, `exported`
or `already_present`, plus `export_sha256`, the plan and source retention. Apply
requires this export hash before creating destination metadata. Source changes,
directory replacement or a different workspace require a new preview. Destination
status and source timestamps are excluded from the hash, allowing verified retries.
Cross-directory plans retain version 1 and their existing hash format. Plans for
the same physical directory use version 2; a version/layout mismatch is rejected.
The outer receipt remains version 1. A plan cannot authorize the other layout.

Within one directory, SQLite and JSON share the same session lock. Export reuses
that held lock and directory handle instead of attempting a second acquisition.
Different paths naming the same physical directory use this same behavior, while
the plan still binds both supplied paths. Preview does not create a JSON file;
apply adds only the selected snapshot and retains the SQLite database, indexes,
timestamps and lock files. An old JSON source retained by forward migration is
verified if identical and rejected if different. Export does not synchronize it
with an advanced SQLite session. Resume must explicitly select the desired backend.

Export preserves the original revision, consumed attempts, admission records,
historical memory, review/recording evidence and workspace identity. It copies the
SQLite index timestamp to the JSON file without modifying SQLite. Running and queued
entries remain as saved; only explicit resume changes their execution state. A
verified JSON copy can be imported into SQLite again with `session-transfer`.
The output must fit the saved logical budget and 32 MB snapshot ceiling. This
operation decodes complete state; it does not provide streaming unbounded export.

The source SQLite handle is read-only in **both preview and apply**. A hot source
journal therefore blocks export without recovery or destination writes. Recover
the source separately, then preview again. Export does not repair a damaged schema.

Apply holds the shared session lock, or both locks for different directories,
writes and syncs a private temporary JSON file,
then rechecks both directory identities, the source state and destination absence
before atomically publishing. An identical destination is verified; a different,
advanced or invalid snapshot is rejected. Existing-copy apply also syncs the
directory, allowing retry after a publication acknowledgment or directory-sync
failure. These checks assume cooperative writers and trusted owner-local parent
directories; they do not isolate files from hostile processes with the same user ID.

A process exit before publication can leave a private temporary file and the empty
session lock. Retry ignores that temporary and publishes a complete snapshot.
An exit after publication is resolved by verifying the existing copy. Temporary
files are not removed by preview or retry; the existing explicit snapshot
`session-delete` cleanup handles this session's temporary files when deleting its
published copy. `session-cleanup` now provides separate
[previewed temporary-file cleanup](CONVERSATION_CLEANUP.md), including orphaned
first writes without a published JSON copy. There is no source deletion,
synchronization or automatic backend switch. Broader retention and the long-session
capacity gate remain separate work.

## Export a selected batch of SQLite sessions

`session-export-batch` previews one to 32 explicit session IDs and at most
64,000,000 bytes of canonical JSON snapshots. The destination defaults to the
source directory; pass `--destination-storage PATH` for another existing private
directory. Apply requires the returned `batch_sha256`:

```sh
mos session-export-batch SESSION_A SESSION_B --storage /path/to/sessions -C /path/to/project --json
mos session-export-batch SESSION_A SESSION_B --storage /path/to/sessions -C /path/to/project --apply --expected-sha256 BATCH_EXPORT_HASH --json
```

The version-1 batch plan contains sorted, distinct single-session export plans,
the output byte limit, total `output_bytes` and message count. Every entry binds
the same source/destination paths and identities, owner and workspace, together
with its session ID, state hash, revision and exact snapshot bytes. Entry plans
use version 2 within one physical directory and version 1 across directories.
Destination status and source timestamps remain outside the hash, so retries and
intervening identical single-session exports retain the same batch selection.

Every source is fully verified before destination JSON inspection or publication.
Preflight retains metadata between sessions, not decoded histories. Each read
checks the indexed snapshot size against the remaining output budget before
decoding full state; full verification checks that the index matches the snapshot.
Per-session reads also respect the 32 MB ceiling and saved logical limit. The
execution pass and final source recheck cap reads at the selected snapshot size,
so growth requires a new preview. This is a verified output-size admission, not a
bound on SQLite's physical bytes read, Python memory overhead or reserved disk
space. Corrupt index claims still encounter the existing bounded full verifier.

**Publication is per session.** Sources are locked individually, not frozen as one
batch. A late conflict, lock, changed source or directory replacement can stop
after earlier JSON files were published. The `conversation.export_batch` result
reports `mode`, `status` (`planned`, `completed` or `stopped`), `batch_sha256`, the
plan, ordered per-session `receipts`, and `exported`/`already_present` counts. A
stopped result identifies `failed_session_id` and a bounded `failure` category;
CLI exit status is 2. Receipts cover the verified prefix, while the failing session
may have published before its acknowledgment was lost. Retry verifies identical
copies and exports the rest; a different or invalid JSON destination is rejected.
Invalid selection and source-preflight errors produce a safe notice before a
batch receipt is available. Receipts contain metadata, without source text.

The single-export guarantees apply to each member: SQLite stays read-only even
on apply, hot source journals block export without recovery, complete state and
evidence are retained, and queued/running messages are not resumed. Publication
uses a synced temporary file and atomic replacement under the session lock;
crash leftovers follow the documented single-export cleanup behavior. The command
does not synchronize copies, delete sources or change backend selection. Retention
and the long-session capacity gate remain separate work.

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
resume rejects it. Full load/delete validate retained state; saves reuse a verified
checkpoint or fully revalidate after external commits as described below. Listing
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
artifact field names, hashes, byte sizes and opaque selection tokens. Memory, review packets/results and the
retained recording are not loaded. Reference availability and size are checked only
for returned entries; artifact content integrity is verified on explicit expansion
or full resume.
The [terminal's F5 browser](CONVERSATION_TUI.md#saved-sqlite-history) now uses this
reader with one-page retention and background reads. F7/F8 select and expand one
artifact as described below. This reader is a user-invoked CLI/terminal/library operation, not an ambient-history tool for
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
selected hash and transactionally adds the derived digests and resume checkpoint.
It preserves the
session hash, revision, saved timestamp, message/artifact records and consumed
attempts. Repeating preparation verifies the state without rewriting the index.
It cannot be combined with page options and never runs automatically during reads.
A normal session save also writes the new index. Use this version of Mos Eisley
for prepared/new indexes; older builds may reject the added index fields. The digest
list is bounded by the current 16-message schema; lifting that cap also requires an
index layout that stays bounded as history grows. Preparation still uses a full-state
read, and neither paginated interactive resume nor the
long-session capacity gate is implemented by this milestone.

## Selected artifacts

Copy an artifact's `selection` from `session-transcript --json`, then open it:

```sh
mos session-artifact SELECTION --storage PATH -C WORKSPACE --json
mos session-artifact SELECTION --storage PATH -C WORKSPACE --max-bytes 2000000 --json
```

This explicitly reads one memory context, review packet or review result. The
default limit is 512,000 stored artifact bytes; `--max-bytes` accepts 1–32,000,000.
The reader checks the size before fetching the payload, rejects an over-budget
selection without truncation, verifies its SHA-256 hash and validates its typed
schema. Historical memory also must match the owning user and workspace. Output
contains normalized typed JSON and selection metadata, with terminal controls
escaped. The budget covers stored payload bytes, not escaped output size, physical
disk reads or peak RAM. It is independent of session storage and model context.

Selections bind the owner, store, workspace, session, snapshot, catalog generation,
message position, field, digest and size. They are selection data, not credentials;
the private storage and ownership checks still apply. Any committed catalog change
invalidates them, including another session's save. Reload the transcript to select
again. No index preparation or storage mutation happens during expansion.

Each read checks one bounded session index and the selected message's stored hash
and reference, then loads only the selected artifact. It does not load the header,
other message payloads or other artifacts, and does not check cross-artifact state
relationships. Full resume still performs complete state validation. Unselected
corruption may remain undiscovered. The terminal keeps one expanded artifact at a
time; expansion never dispatches work or makes history available to models/critics.

## Resume inspection

Inspect a saved session before opening the controller:

```sh
mos resume SESSION_ID --storage-backend sqlite --inspect --json
mos resume --last --storage-backend sqlite --inspect --storage PATH -C WORKSPACE
```

The command reads a derived resume checkpoint, verifies the stored header and
selects the latest four messages, all queued/running work and their complete steering
ancestry. It reports selected positions, omitted-message count, consumed recording
attempts, pending positions and which running position normal resume would mark
interrupted. Inspection itself does not recover work, construct a controller, read
current memory files, consume an attempt or save anything. It also works while the
session is open. It cannot be combined with memory/recording changes, storage-budget
changes or terminal display flags. `--last` selects from the bounded SQLite catalog
and rechecks the selected snapshot hash before reading its header.

The byte budget is independent of session retention: at most 512,000 stored header
and selected-message bytes, plus one separately bounded 32,000-byte session index.
All selected record sizes are admitted before fetching any message payload. An
over-budget working set produces an error; use transcript pages to inspect smaller
sections. Returned message records use the same hash verification and artifact
selection tokens as transcript pages. Memory, retained recordings, review packets
and review results remain references. Header references report their digest and
size; their content is not fetched. Output escapes terminal control characters.
These are stored-payload limits, not physical disk/cache, output-size or RAM limits.

New saves/imports write the checkpoint atomically with the session. It records the
exact header hash/size and per-message status, review kind, steering target and raw
record size. Full loads verify the checkpoint against the reconstructed state.
Older sessions remain fully resumable, but inspection requires explicit preparation
with `session-transcript SESSION_ID --prepare --expected-sha256 HASH` using the same
storage/workspace. Preparation preserves raw header/message bytes, session hash,
revision, timestamp and consumed attempts; it never runs implicitly during reads.

Inspection verifies selected records and reference availability. Corrupt omitted
records or artifact contents can remain undiscovered until selected or fully loaded.
The owner-local index provides snapshot binding, not protection against deliberate
same-user rewrites. This is a candidate working-set reader; **normal resume verifies
every entry and artifact**, using incremental hydration for current records as
described below. Its selection does not change model context or authorize omitting
earlier instructions. Active-input limits apply to normal resume as described below;
inspection rejects these unused options. A scalable replacement for the 16-entry
checkpoint remains open.

## Controller working state

Normal SQLite chat/resume verifies historical memory and review artifacts one entry
at a time and releases their decoded values before validating the next entry.
The controller retains message text,
status, usage and steering links for the current 16-message preview, plus verified
artifact references. Active memory and the selected recording remain decoded within
[per-launch input limits](CONVERSATION_STORAGE.md#active-memory-and-recording-input-limits).
At most the latest review result stays decoded for the live F3 renderer; queued
review packets remain references until explicit continuation starts their work.

Before dispatching an archived review, the store verifies its source record and
references against the current checkpoint. It admits the record plus unique
artifact payload sizes against a separate 512,000-byte input limit before reading
those payloads, then checks hashes and typed entry validation. The existing packet
and result bounds still apply. Reading a packet does not consume an attempt.

Working-state saves validate current inputs and verify that each archived entry
belongs to the expected record hash and position. Archived content cannot be edited
through a reference; only queued cancellation and running-to-interrupted recovery
may change its status. Newly executed work supplies a fully validated entry.
The writer streams retained artifact bytes in 32 KiB chunks and checks their hashes,
preserving the exact canonical snapshot hash and logical byte count without
reconstructing historical artifact objects or a complete proposed snapshot.
It still hashes all logical history bytes; this is not constant-time persistence.

Working saves first measure the exact logical snapshot from canonical record
structure, new artifact sizes and stored artifact lengths. Repeated references
count once per occurrence in the logical snapshot, even when storage deduplicates
their bytes. This admission happens inside the write transaction after checkpoint
and archive validation. With a current verified checkpoint, an oversized save reads
no artifact payloads and performs no session writes; the storage error includes
required and allowed bytes. External commits or a missing checkpoint still require prior cold verification,
which can read artifacts. Admitted saves retain complete streamed hash verification
and must match the preflight size before publication. The metadata pass still walks
all packed records and adds work to successful saves; it does not lift any limit.

During an admitted working save, repeated archived artifacts may share a cache of
at most 64 KiB of encoded payload. The first eligible values that fit are retained
as immutable chunks only after the source finishes and exact size/SHA-256 checks
pass. A partial read or late verification failure cannot populate the cache.
Single-use, oversized and non-fitting values stream normally; new inputs already
encoded by the save are not copied into this cache. Cached chunks still contribute
to the complete snapshot hash and size on every reference. The cache is cleared
when that streaming pass exits, including failures, and is never reused by another
save, cold verification or resume. This reduces repeated disk reads, with a bounded
payload-memory tradeoff; the 64 KiB limit excludes Python object overhead and is
not a total process RAM limit. It does not remove full-history hashing.

Each packed header/message record is encoded once during working-save preparation.
Its admitted bytes and message digest are reused for archive checks, checkpoint
metadata and writes, avoiding repeated encoding and a packed-record JSON round trip.
Selected-entry hydration also shares one encoding between source verification and
byte admission. These prepared values live only within the operation; subsequent
saves revalidate inputs and prepare fresh records, including nested reference
changes. Cold resume skips a second preparation pass over already verified entries
when normalizing its header. All text records still participate in each save, and
working-state validation still rebuilds the complete runtime data tree.

Runtime revalidation now passes that fresh Python tree through the strict schema,
avoiding a complete state JSON encode/decode buffer. Nested models and mutable
containers are checked anew; native tuples and timestamps are preserved. The
excluded latest-review cache receives full nested schema validation before its
hash/summary checks. Persisted JSON still uses the existing compatibility decoder.
This preserves canonical bytes for valid states, while malformed runtime values
must satisfy their native types instead of relying on JSON conversion. Active
integrity checks still serialize selected inputs; validation remains proportional
to the complete working state.

The latest completed review event still carries its full result. On resume, older
review events retain their brief ID and text summary; use F5/F7/F8 or the transcript
and artifact CLI to expand older evidence explicitly. The saved evidence is intact.
Working-state references are internal and are not accepted as JSON snapshots.

Older indexes without preparation metadata, and admitted artifacts stored in
valid noncanonical JSON, use the compatible full-state controller. An ordinary save
prepares canonical records; reopening then enables the working-state path.
Opening a session does not silently rewrite those records. Current prepared records
with legacy whitespace or omitted defaults retain their semantics when saved.

### Incremental cold verification

Current prepared sessions no longer reconstruct one complete decoded snapshot on
open or after external commits. Inside one read transaction, the loader verifies
the index, stored header digest/size, contiguous entry records and their saved
digests/sizes, and the complete artifact inventory. Each historical entry admits
its packed record plus referenced artifact bytes against a 512,000-byte limit
before fetching those artifacts. Repeated field references count separately.
Artifacts are read through 32 KiB blob chunks, checked against their hashes, and
validated with the complete entry schema, including review evidence/summary matching
and historical memory ownership. Only verified references and text survive each
entry's validation; at most the latest review result remains decoded.

The assembled working state still validates cross-entry progress, steering, active
memory identity and retained-recording consistency. The loader then streams the
canonical logical snapshot to verify its exact hash, byte count, saved limit and
summary. Header/entry defaults and legacy record whitespace retain their original
meaning. The verified state, revision and checkpoint become usable only after the
read transaction succeeds. Interrupted streams close their blob handles, and a
failed reload discards the previous checkpoint before a later transition.

This bounds historical hydration to one admitted entry, not total process RAM or
cold-read work. It still reads all history and retains all 16 bounded text records.
Before hydrating active header values, the CLI now checks memory and recording
sizes independently (131,072 and 2,000,000 bytes by default). Both sizes must pass
before either payload is fetched; the check also precedes the legacy full reader.
The existing aggregate 32 MB artifact ceiling still applies. Canonical input sizes
are checked after validation, and configured saves check selected inputs before
writing. Size and retained-recording digest checks now stream canonical encoder
segments, avoiding complete encoded byte buffers for those checks. Active values
remain decoded; reducing remaining state/persistence serialization remains
open. Noncanonical artifacts that fit the cold entry bound
and unprepared indexes use the full-state compatibility reader; opening does not
rewrite them. A prepared entry exceeding the cold-input bound is rejected without
a save or dispatch, including oversized legacy encodings.
Larger histories and smaller text/record transition inputs also remain open before
the long-session gate can pass.

## Incremental writes and recovery

Routine saves now reuse a verified checkpoint held by the same database connection.
A successful full or incremental verification, or committed save, establishes it.
Before reusing it, the
write transaction checks the database identity, connection change indicators,
stored index and expected snapshot hash/revision. Unchanged messages do not reach
an upsert; unchanged artifacts are not reinserted. The working-state path streams
archived bytes as described above. The compatible full-state save API instead
serializes its supplied values without rereading old payloads. New artifacts are
inserted, and only no-longer-referenced artifacts are deleted. The existing
read/save guard and transaction-before-dispatch rule apply.

This relies on [SQLite's connection-local data version](https://www.sqlite.org/pragma.html#pragma_data_version),
which changes after commits from another connection. Any such commit, including
another session's save, forces complete validation of this session before another
save. The working-state controller uses incremental cold verification; the
full-state compatibility API retains its original full reader.
The connection's total-change counter also detects direct writes on the same
connection. Versions are captured inside the transaction, and the replacement
checkpoint is published only after commit succeeds. Failed saves, index preparation,
deletion and connection reopen discard it. A failed or uncertain controller save
still stops that controller and requires reopening; the checkpoint cannot authorize
retrying consumed work or overwriting a changed revision.

The checkpoint retains the bounded session index, at most 50 artifact digests,
canonical-artifact verification status and bounded review brief IDs. It has no
decoded artifact or payload cache. It uses the existing owner-local
storage trust boundary. Explicit load, deletion and migration still verify full
state. Successful working saves publish the new reference-based state and checkpoint
only after commit. Failed streams close their blob handles before rollback. The
16-message limit remains unchanged.

The private `sessions.sqlite3` file contains versioned owner/database metadata,
session heads, message records and immutable artifact values keyed by session and
content digest. Memories, review packets/results and retained recordings are
referenced from records. Equal artifacts are reused within a session; the backend
does not share artifacts between sessions or owners.

A save validates the current state and revision, then commits the updated head,
changed message rows, new artifact references and catalog generation in one
transaction. Unchanged message rows/artifacts are not rewritten. Objects no longer
referenced by the saved state are removed in that same transaction. Earlier memory
remains retained while historical entries reference it. Explicit full loads and
compatible full-state saves still reconstruct or serialize complete logical state.
The working-state path verifies historical entries incrementally on cold load and
external-commit revalidation. Active-input limits are per-launch settings; reducing
repeated serialization remains planned.
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
shrinking. Backup expiry, vacuum/compaction and bulk retention remain
explicit future work.

Interrupted JSON saves and exports now have separate, explicit
[temporary-file cleanup](CONVERSATION_CLEANUP.md). Its storage-owner selection hash
and shared session lock authorize removal of unpublished JSON staging files only;
SQLite journals, databases and published sessions are retained.

The database has an initial 256 MB physical file ceiling, enforced on open and via
SQLite's page-count limit on writable connections. Each existing sidecar is also
bounded. This is separate from the per-session logical budget, is not a disk-space
reservation, and is not yet configurable. The 16-message/attempt preview cap,
recorded responses, context budgets and 32 KiB memory limit remain unchanged.

The next stages are bounded controller resume, context compaction,
configurable physical retention and the 1,000-message
capacity/recovery gate in [plan §17.5](mos-eisley-plan.md#175-long-session-storage-and-independent-budgets).
Passing metadata pagination for 260 sessions does not satisfy that long-session gate.
