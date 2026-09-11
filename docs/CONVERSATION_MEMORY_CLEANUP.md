# Review memory staging cleanup

`memory-project-cleanup` reviews one explicitly named staging file. It can discard
a complete single-link staging record or remove the extra staging link left by an
interrupted resolution-backup publication. It never scans storage or runs at startup.

| Action | Required record | Effect after explicit apply |
| --- | --- | --- |
| `discard-staging` | One private, canonical project snapshot in an exact `.memory-migration-32_HEX_DIGITS.tmp` or `.memory-resolution-32_HEX_DIGITS.tmp` file, with one link | Removes that staging name and its contents |
| `recover-backup-link` | One private canonical project snapshot with exactly two links: an exact migration staging name and its matching `resolution-backup-64_HEX_DIGITS.json` | Removes only the staging alias; the backup remains as a normal one-link file |

Both actions require `--workspace-identity` to be the exact canonical project path
in the record's `document.workspace`. That directory may no longer exist. Relative
paths, aliases and normalization are rejected as in
[memory relocation](CONVERSATION_MEMORY_PROJECT.md#copy-memory-after-a-project-moves).
The nearest existing ancestor and the path's presence/absence are bound to review.

## Discard a reviewed staging record

Inspect the exact file and retain any content you still need. Provide its validated
snapshot `sha256` as `--record-sha256`, then review the full cleanup receipt:

```sh
mos memory-project-cleanup --workspace-identity /projects/api \
  --action discard-staging \
  --temporary-name .memory-resolution-EXACT_32_HEX_DIGITS.tmp \
  --record-sha256 REVIEWED_SNAPSHOT_SHA256 --json
# Repeat the exact selection with:
# --apply --expected-sha256 HASH_FROM_CLEANUP_PREVIEW
```

The receipt includes the full candidate snapshot and current project snapshot,
or `current_project: null` when no live document exists. Discard permanently removes
the selected staging copy even in that case. Keep the file if you need its content;
cleanup does not publish it, restore it or create a missing project document.
A single-link staging name does not prove that its contents were never published
elsewhere in the past; review the actual record and current memory before discarding.

Incomplete, oversized, noncanonical or invalid snapshots cannot be discarded by this
command. Neither can symlinks, directories, foreign-owner files, files with group/other
permissions or multiply linked records. Retain unsupported artifacts for investigation;
there is no force or wildcard option. Ordinary user-memory staging files are outside
this project's cleanup scope.

For one bounded empty, truncated or integrity-invalid staging file, use the separate
[raw staging discard](CONVERSATION_MEMORY_STAGING.md) workflow. That review is
storage-wide and explicitly leaves project attribution unverified; it is not a
project cleanup action or an option in the batch manifest.

## Repair an interrupted backup publication

A resolution can crash after linking a durable backup but before removing its
`.memory-migration-*.tmp` alias. Ordinary resolution rejects the two-link backup.
Select both exact names to restore its ordinary single-link form:

```sh
mos memory-project-cleanup --workspace-identity /projects/api \
  --action recover-backup-link \
  --temporary-name .memory-migration-EXACT_32_HEX_DIGITS.tmp \
  --backup-name resolution-backup-EXACT_64_HEX_DIGITS.json \
  --record-sha256 REVIEWED_PRIOR_TARGET_SNAPSHOT_SHA256 --json
# Repeat the exact selection with:
# --apply --expected-sha256 HASH_FROM_CLEANUP_PREVIEW
```

The record hash is the prior target's snapshot `sha256`, available as `target.sha256`
in the original resolution preview. It is different from the outer review hash and
the backup filename's digest of the complete canonical snapshot. The command verifies
all three bindings rather than inferring a backup from its filename alone. The two
names must refer to the same inode with exactly two links, correct owner and project
scope, and exact canonical bytes. The backup bytes remain unchanged after repair.

Current project memory may have changed since that backup was written; cleanup shows
and binds its current state but preserves it. If you still want to complete the
resolution, obtain a fresh resolution preview after repair. This command never
deletes a retained backup or restores its text into live memory. To restore text,
use a separately reviewed resolution with `--strategy use-text`.

A staging alias linked to a **published project document** uses the existing
[copy-recovery workflow](CONVERSATION_MEMORY_PROJECT.md#interrupted-copy-publication-and-recovery),
including relocation recovery for vanished source directories. Backup-link repair
requires a backup filename and cannot substitute for published-project recovery.

## Review, locking and failures

Use the same `--memory-storage` override for preview and apply when configured.
Preview is read-only and creates no storage, lock or project directory. Apply
requires `--apply` and the exact preview hash together. The operation hash binds the
action, full candidate and current snapshots, record identities/change times, exact
names, workspace presence/ancestor, private storage and lock identities. All inputs
are rechecked under an exclusive existing memory lock immediately before unlink.
The one-record selection is bounded by the existing 256 KiB record limit.

Changing the candidate, current project record, names, workspace or lock invalidates
the approval. Unreadable current project memory stops cleanup; repair any interrupted
published-project link first. No automatic retry is performed.
Other staging files, live source/project/user documents and saved sessions are
untouched. After backup repair, the retained backup is checked with the normal
single-link validation. These checks coordinate cooperating local writers; they do
not isolate files from a hostile process running as the same OS user.

An error before unlink leaves the selection in place. A process death or directory-flush
failure after unlink can mean cleanup already happened despite the missing success
receipt. Inspect the exact names and retained records before further action; an old
preview cannot delete a replacement file or repeat cleanup against a missing name.
Re-preview any changed selection. There is no attempt to roll back a completed unlink.

## Batch cleanup and retained-backup pruning

`memory-project-cleanup-batch` accepts a JSON selection of 1–32 explicitly named
records for one exact workspace identity. It supports the two staging actions above
and `prune-backup` for retained resolution backups. No directory inventory, wildcard
selection or automatic age-based deletion occurs. Unselected backups remain retained.

Create a selection file, replacing the example names and hashes with the exact
records you intend to review:

```json
{
  "schema_version": 1,
  "records": [
    {
      "action": "discard-staging",
      "temporary_name": ".memory-resolution-EXACT_32_HEX_DIGITS.tmp",
      "record_sha256": "REVIEWED_STAGING_SNAPSHOT_SHA256"
    },
    {
      "action": "prune-backup",
      "backup_name": "resolution-backup-EXACT_64_HEX_DIGITS.json",
      "record_sha256": "REVIEWED_BACKUP_SNAPSHOT_SHA256"
    }
  ]
}
```

`recover-backup-link` entries require both `temporary_name` and `backup_name`, as
in the single-file command. No filename may appear in more than one entry, including
retained repair destinations. Repairing and pruning the same backup require separate
reviews. Unknown fields, duplicate JSON keys, invalid names/hashes and duplicate or
empty selections are rejected. The manifest must be a regular file of at most 64 KiB;
its final path cannot be a symlink. Each selected record has the existing 256 KiB read
bound. The command never reads a directory listing.

```sh
mos memory-project-cleanup-batch --workspace-identity /projects/api \
  --selection cleanup.json --before-ns REVIEWED_CUTOFF_UNIX_NS --json
# Repeat the same selection and cutoff with:
# --apply --expected-sha256 HASH_FROM_BATCH_PREVIEW
```

The positive integer `--before-ns` is required exactly when the selection contains
`prune-backup`. A backup is eligible only when its observed filesystem modification
time is **strictly less** than that cutoff. This is an explicit file-age policy;
mtime is not an authenticated creation or publication time and can change during
copying/restoration. Review the full record and its `record_identity.mtime_ns`, not
age alone. Changing the cutoff or timestamp invalidates the preview. There is no
implicit "keep newest N" or minimum backup-count policy: you select the records to
retain by leaving them out of the manifest.

Pruning also requires a private, canonical, single-link backup with the matching
content-addressed filename, record hash, owner and workspace. A readable current
project document must exist, and its snapshot hash must differ from the selected
backup's hash. A backup matching current memory, or any backup when current memory
is absent, is protected. The project directory itself may have vanished. Pruning
permanently removes the selected historical backup; preserve any content you may
need first. It neither restores text nor edits live memory or saved sessions.

The preview includes every full selected snapshot and current memory observation.
Records are sorted by the filename being removed, so reordering the same manifest
does not change the review hash. Apply validates the entire selection again under
one exclusive existing memory lock before any unlink, then rechecks each record
immediately before deleting it. Storage, lock, workspace and current memory remain
bound throughout. Existing single-file cleanup approvals cannot authorize a batch.

### Partial batch progress

Filesystem batch cleanup is sequential, not transactional. A failure can leave a
completed prefix. Each successful unlink is followed by a directory flush. Receipts
use `status: planned`, `completed` or `incomplete`, with `removed` listing names whose
unlink returned successfully and `synced` listing those followed by a successful
directory flush. An in-process apply failure returns an incomplete JSON receipt and
exit status 2; initial validation failures remove nothing. A name in `removed` but
absent from `synced` has uncertain durability after a system crash. A completed flush
does not imply a later backup verification succeeded; inspect incomplete receipts.

A process death may return no receipt at all. Inspect the exact selected names and
retained backups, omit already completed work, and preview the remaining selection
again. Repaired backups now have one link and cannot reuse a repair approval. Old
hashes cannot be reused for a smaller selection or a replacement file. There is no
rollback, journal, automatic retry or automatic continuation. The same-user process
boundary described above also applies to batches.

Bounded invalid-record disposal uses the separate raw staging workflow above.
Oversized/valid-noncanonical disposal, automatic retention policies and
inventory-based backup count protection remain planned. Retained backups are never
deleted automatically.
