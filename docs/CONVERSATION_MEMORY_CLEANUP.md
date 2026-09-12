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

Backup retention/pruning, bulk cleanup and incomplete-record disposal remain planned.
Retained resolution backups are never deleted automatically.
