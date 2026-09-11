# Prune one verified SQLite session

`mos session-prune` applies a retention policy to **one explicit session ID**. Start
with its full-state preview, then use that preview's `prune_sha256` to apply:

```sh
mos session-prune SESSION_ID --storage /path/to/sessions -C /path/to/project --before 2026-08-01T00:00:00Z --keep-newest 20 --json
mos session-prune SESSION_ID --storage /path/to/sessions -C /path/to/project --before 2026-08-01T00:00:00Z --keep-newest 20 --apply --expected-sha256 PRUNE_HASH --json
```

The separate [workspace retention report](CONVERSATION_RETENTION.md) remains
read-only. Its metadata hash, a snapshot hash, and a different session's prune hash
cannot authorize this operation. For an explicit batch, use the separate
[batch pruning command](CONVERSATION_BATCH_PRUNE.md) and its batch hash. Neither
command performs automatic deletion.

## Policy and verification

The cutoff and keep-newest rules are the same as the retention report:
`--before` is an explicit whole-second UTC timestamp, and `--keep-newest` defaults
to 20, with a range of 0–1,000. The selected session must be older than the cutoff,
outside the newest protected positions, and contain only completed messages or no
messages. Queued, running, failed, interrupted and cancelled work is protected.
Completed work is not necessarily disposable; the explicit ID, policy and apply
hash select what the operator chooses to discard.

Preview opens existing private storage read-only, holds the selected session's
existing exclusive lock, and evaluates at most 1,000 workspace indexes in one
read transaction. A busy selected session fails rather than being selected. Only
the lock held by this operation is excluded from activity probes; other session
locks are observed normally. Missing directories, databases or locks are not
created. Storage must remain private, owned by this OS user, and free of unsafe
symlink, hardlink or special-file substitutions.

After checking eligibility, preview verifies the selected session's full header,
messages, retained inputs, artifacts, state digest and saved checkpoint. A readable
index alone is insufficient. The selected logical snapshot must fit its saved
budget and the existing 32 MB maximum. Existing record, artifact and message bounds
also apply. Verification materializes the selected state, so that logical limit is
not a bound on total Python memory. Other sessions' bodies are not hydrated.

The version-1 prune plan declares `verification: "selected_full_state"` and binds
the complete retention metadata plan, selected ID/state digest, database and lock
device/inode identities, and verified artifact counts/bytes. The nested retention
plan binds root identity, owner, canonical workspace, store ID/generation, policy
and ordered index observations. Preview reports `status: "planned"`, the plan and
its `prune_sha256`, with zero removal counts. Receipts contain metadata, not retained
conversation content.

## Apply and concurrency

Apply repeats the read-only full-state preflight and compares the exact prune hash
**before opening a writable database connection**. It keeps the selected session
lock while reopening the same existing database for writing. Inside
`BEGIN IMMEDIATE`, it re-evaluates the policy and full selected state and compares
the entire plan again. It then deletes the session and its cascading message and
artifact rows, and advances the database generation once in the same transaction.
Root, database and session-lock identities are checked through this operation and
again before commit.

The held session lock excludes cooperating JSON and SQLite writers for that ID;
the write transaction excludes other SQLite commits during final validation and
deletion. Any observed policy, activity, index, state or generation change rejects
the selection. Even a commit in another workspace advances the shared generation
and requires a fresh preview. Replacing a database or lock with an identical copy
also invalidates the hash. Activity probes for other sessions remain momentary;
they do not reserve those sessions or authorize their deletion.

The SQLite backend uses its existing full synchronous commit behavior. A
`conversation.prune` receipt with `status: "deleted"` is returned only after a
successful commit. It reports one removed session and exact selected message,
artifact, artifact-byte and logical-snapshot-byte counts. These byte counts are
not guarantees of physical disk-space reclamation.

## Failure and recovery

A validation or statement failure before commit rolls back the transaction; there
is no partially deleted session/child-record result. A commit I/O error, process
exit or lost acknowledgment may leave the caller unsure whether the commit
completed. No success receipt is issued for an exception. Inspect storage again
and obtain a fresh preview before any further action. A missing ID is not reported
as proof that an earlier prune succeeded, and an old prune hash is not a retry
authorization for a changed selection.

A hot rollback journal encountered by the initial read-only preflight is refused
unchanged in both modes. Recover through an explicit writable storage operation,
then preview again. If another transaction crashes after preflight but before the
authorized writable reopen, SQLite may perform its normal rollback recovery;
the recovered policy and state must still match the selected plan before pruning.
Preview never performs that recovery.

The database file, empty session lock, published JSON copies, JSON temporary files,
other sessions and backup files remain in place. No JSON copy or backup is required
or verified by pruning. Deleted SQLite content cannot be restored by this command;
recovery of deleted content depends on a separately retained valid copy. Database
pages may be reused without shrinking the file. Logical deletion is not secure
erasure from journals, backups, filesystem snapshots or storage hardware.

As with the other SQLite operations, this relies on cooperative writers and
trusted owner-local parent paths. SQLite owns its descriptors; identity checks do
not provide isolation from hostile processes running as the same OS user.

Explicit [batch policy apply](CONVERSATION_BATCH_PRUNE.md) is available for 1–32
sessions in one transaction. Automatic expiry, backup/journal retention policies, configurable
physical quotas and vacuum/compaction remain open in the
[storage plan](CONVERSATION_STORAGE.md#planned-incremental-storage). The separate
1,000-message capacity and recovery gate remains unchanged.
