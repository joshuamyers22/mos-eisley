# Prune an explicit batch of SQLite sessions

`mos session-prune-batch` previews and atomically deletes 1–32 explicit session IDs
from one workspace and storage directory. Every selected session must qualify
under the [retention policy](CONVERSATION_RETENTION.md) and pass full-state
verification. Preview first, then apply the returned `batch_prune_sha256`:

```sh
mos session-prune-batch SESSION_A SESSION_B --storage /path/to/sessions -C /path/to/project --before 2026-08-01T00:00:00Z --keep-newest 20 --json
mos session-prune-batch SESSION_A SESSION_B --storage /path/to/sessions -C /path/to/project --before 2026-08-01T00:00:00Z --keep-newest 20 --apply --expected-sha256 BATCH_PRUNE_HASH --json
```

The cutoff is an explicit whole-second UTC timestamp. `--keep-newest` defaults to
20 and accepts 0–1,000. Selected sessions must be older than the cutoff, outside
the newest protected positions, inactive, and contain only completed messages or
no messages. Completed work can still be valuable; the explicit IDs and apply hash
select what the operator chooses to discard. There is no automatic selection or
scheduled deletion.

## Selection and bounds

IDs must be unique. The command sorts them before acquiring existing exclusive
session locks, so argument order does not change the preview hash. A missing or
busy selected lock fails the operation and releases every earlier acquired lock.
It creates no storage directories, databases or lock files. Cooperating JSON and
SQLite writers for every selected ID remain excluded throughout both modes.

One read-only transaction reads at most 1,000 workspace indexes. Only locks held
by this operation are excluded from activity probes. All selected IDs must appear
as candidates, and their total indexed logical snapshot size must be at most
64 MB, before any selected body is loaded. The command then fully verifies each
selected session's header, messages, retained inputs, artifacts, state digest and
checkpoint using the existing SQLite verifier. Full states are released between
selections; the result retains metadata only. Each snapshot still has its saved
budget and the existing 32 MB maximum, and all record/artifact/message limits
remain in force. A valid index cannot substitute for full verification.

The 64 MB bound covers logical snapshots, not total Python memory, physical file
size or reclaimed space. The operation holds up to 32 storage handles, uses one
transaction for verification, and reads the workspace policy once per phase.
Unselected bodies are not loaded. Batches above either limit must be split into
separate operations, each with a fresh preview after the preceding commit.

The version-1 plan declares `operation: "delete_sqlite_sessions"` and
`verification: "selected_full_states"`. It contains one complete workspace
retention observation, the database identity, and sorted selected IDs with state
digests, lock identities and artifact counts/bytes. The nested policy plan binds
root identity, owner, canonical workspace, store ID/generation, policy and ordered
index observations. Preview returns `status: "planned"` and zero removal counts.
Single-session prune hashes, retention report hashes and snapshot hashes cannot
authorize a batch, even if it contains only one ID.

## Apply and failure recovery

Apply acquires all selected locks and repeats the read-only full-state preflight.
It compares the batch hash before reopening the first storage handle for writing.
Inside `BEGIN IMMEDIATE`, it reads the policy again, verifies all selected states
again, and compares the complete batch plan. Only after every verification passes
does it delete the selected sessions and their cascading message/artifact rows.
The database generation advances **once for the whole batch**. Root, database and
all selected lock identities are rechecked through verification and before commit.

An observed change to the policy, activity, generation, selected state or file
identities requires a fresh preview. Even a commit in another workspace advances
the shared generation. The write transaction excludes competing SQLite commits
during final verification and deletion; activity probes on unselected sessions
remain momentary observations.

A successful full synchronous commit produces one `conversation.batch_prune`
receipt with `status: "deleted"` and exact total removed session, message,
artifact, artifact-byte and logical-snapshot-byte counts. There are no partial
success receipts: a statement or validation failure before commit rolls back the
whole batch, including cascades and generation. A crash after the first deletion
also requires recovery of the entire uncommitted transaction.

Both modes refuse a hot journal encountered by initial read-only preflight without
changing it. Recover through an explicit writable storage operation, then preview
again. A transaction that crashes after preflight may undergo SQLite's normal
rollback recovery during the authorized writable reopen; final policy and state
must still match before deletion.

Commit I/O errors, process exit and lost acknowledgment can make commit status
uncertain. Inspect storage and obtain a fresh preview before further action.
Missing selected IDs do not prove an earlier batch succeeded and never produce an
`already_deleted` receipt. A changed batch cannot reuse the old hash.

Published JSON copies, JSON temporary files, backups, other sessions, the database
file and all lock files remain in place. No backup is required or verified.
Restoring deleted content requires a separately retained valid copy. Logical
deletion does not promise disk-space reclamation or secure erasure. The existing
cooperative owner-local trust model applies; identity checks do not isolate SQLite
from hostile processes running as the same OS user.

Automatic expiry, backup/journal retention, physical quotas, vacuum/compaction and
the separate 1,000-message capacity gate remain open in the
[storage plan](CONVERSATION_STORAGE.md#planned-incremental-storage).
