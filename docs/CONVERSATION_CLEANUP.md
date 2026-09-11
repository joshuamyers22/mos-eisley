# Clean up interrupted JSON writes

`mos session-cleanup` previews unpublished JSON temporary files for one explicit
session ID. Apply removes those files without deleting the published session:

```sh
mos session-cleanup SESSION_ID --storage /path/to/sessions --json
mos session-cleanup SESSION_ID --storage /path/to/sessions --apply --expected-sha256 CLEANUP_HASH --json
```

The ID is the first 32-character lowercase hexadecimal component in filenames of
the form `.SESSION_ID.RANDOM_HEX.tmp`. Only that exact naming pattern is eligible.
This covers interrupted saves and SQLite-to-JSON exports, including a first write
that never published a JSON snapshot. Empty and truncated files are eligible;
cleanup does not attempt to interpret their contents or recover unfinished work.
A temporary file can hold the only surviving bytes of an uncommitted write.
Applying its preview explicitly discards those bytes.

This is **storage-owner maintenance**. Incomplete bytes cannot reliably identify a
project, so the command has no workspace filter or `-C` option. The receipt declares
`scope: "storage_owner"`, the selected storage directory, owner UID and session ID.
Selecting a directory and ID is explicit; cleanup does not run during listing,
startup, resume, migration or export retry. The default directory is
`~/.mos-eisley-sessions`.

## Selection and bounds

Preview reads existing storage and takes the existing per-session exclusive lock.
It creates no directory, lock, snapshot or database, changes no saved timestamps,
and performs no directory sync. Normal filesystem access-time behavior may still
apply to reads. A busy or missing session lock prevents both preview and apply.
Orphans whose lock file is also missing require separate manual investigation;
cleanup never creates a replacement lock to bypass an existing writer.

The version-1 plan binds the directory path/device/inode, owner, session ID and
lock device/inode. Its sorted file selections include each filename, device/inode,
logical byte size, modification/change timestamps and SHA-256 of the actual bytes.
`cleanup_sha256` hashes the canonical plan. Preview and apply admit at most 256
selected files, 32 MB per file and 64 MB total, scanning at most 4,096 directory
entries. These use decimal bytes. Reads stream in chunks of at most 65,536 bytes;
only selection metadata is retained between files. A one-byte read beyond the
selected length detects growth and aborts the pass. Exceeding any bound fails
before removal; this command does not silently choose a smaller subset.

Byte counts describe logical file lengths, **not guaranteed reclaimed disk space**.
An empty selection is valid and has its own hash. Receipts expose file metadata
and digests, never the temporary content or conversation bodies.

## Apply, failures and recovery

Apply requires the exact hash from a fresh preview. It holds the same session lock
while re-reading and validating the entire selection before the first unlink.
New, missing, changed or replaced selected files invalidate the old plan. All
targets must be private regular files owned by the current user, with one hard
link; symlinks, directories, special files and permissive modes fail closed. Root
and lock identity are rechecked before each removal, along with the next file's
identity, size and timestamps.

Removals are sequential, followed by a directory sync. A successful JSON receipt
has `type: "conversation.cleanup"`, `mode: "apply"`, `status: "completed"`, the
plan/hash, `removed` filenames, `removed_bytes` and `directory_synced: true`.
Preview uses `mode: "preview"`, `status: "planned"` and an empty removed list.

A late failure exits with status 2 and a `stopped` receipt showing the acknowledged
removed prefix. Failure categories are `selection_changed`, `storage_unavailable`
and `durability_unconfirmed`. The latter means the directory sync failed; removed
names are not a durability guarantee. Earlier successful unlinks are not rolled
back. If a process exits after unlink but before reporting it, a receipt can be
absent or undercount the removals.

**Run a new preview after partial cleanup, a crash or a lost acknowledgment**, then
apply its new hash. The original hash cannot authorize a changed remainder. If no
files remain, applying that empty preview still syncs the directory, allowing
recovery after a previous directory-sync failure. A successful cleanup's hash is
therefore generally not reusable.

## Retained data and trust boundary

Published JSON, SQLite databases, SQLite journals/sidecars, backup files, other
sessions' temporary files and empty lock inodes remain in place. The command
neither opens SQLite nor performs journal recovery. It can clean an export's JSON
staging files while leaving a hot SQLite journal untouched. Normal session
[deletion](CONVERSATION_SQLITE.md#privacy-retention-and-bounds) remains separate.

As with snapshot save/delete, this relies on cooperative writers and trusted
owner-local parent directories. It does not isolate files from hostile processes
running as the same OS user. Holding the shared session lock excludes normal JSON
and SQLite writers throughout selection and removal.

Unlinking is logical deletion, not secure erasure from filesystem snapshots,
backups, storage hardware or already-open file descriptors. Backup/journal expiry,
automatic age-based deletion, broader unreferenced-object retention, configurable physical
quotas and SQLite vacuum/compaction remain planned. This step does not satisfy the
[long-session capacity and recovery gate](CONVERSATION_STORAGE.md#planned-incremental-storage).

A separate [workspace retention preview](CONVERSATION_RETENTION.md) now evaluates
a saved-time cutoff and keep-newest policy against SQLite index metadata. It
reports candidates and retention reasons; policy apply remains planned.
