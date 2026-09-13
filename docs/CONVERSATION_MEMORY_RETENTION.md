# Review project-memory backup retention

`memory-project-retention` inventories resolution backups and proposes a bounded
prune using both a newest-count rule and an explicit file-time cutoff. It runs only
when invoked by the user. Preview is read-only; apply requires its exact hash.

```sh
mos memory-project-retention --workspace-identity /projects/api \
  --keep-newest 5 --before-ns 1788739200000000000 --json
# Inspect the inventory, protected reasons and selected names, then repeat with:
# --apply --expected-sha256 HASH_FROM_PREVIEW
```

The example cutoff is an absolute Unix timestamp in nanoseconds. Choose the cutoff
you intend; the command never substitutes the current time. Use the same
`--memory-storage PATH` for preview and apply when overriding
`~/.mos-eisley-memory`. Existing private storage and its memory lock are required;
preview never creates them. The exact canonical `--workspace-identity` can name a
vanished project. Aliases and relative paths are rejected. Saved session mappings
and the persistent mapping registry do not choose this identity.

## Selection and protections

For the selected project, the command:

1. Protects the newest `--keep-newest` backups, from 0 to 128. It ranks file
   modification times descending and breaks ties by filename ascending.
2. Protects every backup with `mtime_ns >= --before-ns`. File time is an observed
   retention input; it does not prove when the document was authored or copied.
   Document revisions and `updated_at` timestamps do not determine this order.
3. Protects every backup matching the current project snapshot hash. If current
   memory is absent, it protects all backups. Unreadable current memory blocks the
   inventory rather than treating it as absent.
4. Proposes at most 32 remaining backups for deletion, oldest file time first,
   with filename ascending as the tie-breaker. `remaining_eligible` names any excess
   that requires another fresh review after this batch.

These protections combine; the final number retained can exceed `keep-newest`.
The current-memory backup counts toward the newest set when its file time places
it there, and receives its independent protection otherwise. With no eligible
records, preview selects nothing and reviewed apply completes without deletion.
No documents are copied, restored or merged. User/project memory, saved sessions,
registry files, staging files and other projects' backups are left in place.

## Complete bounded inventory

The command enumerates at most 1,024 direct directory entries, including unrelated
files, and validates at most 128 `resolution-backup-64_HEX_DIGITS.json` records
across the entire storage directory. It reads at most 256 KiB per backup and 8 MiB
in aggregate. Exceeding a limit rejects the whole inventory; there is no partial
listing that could weaken newest-count protection.

Every backup must be a private, current-user, single-link regular file with a
canonical project snapshot and a filename matching the digest of that complete
snapshot. Symlinks, FIFOs, directories, foreign ownership, public permissions,
multiple links, invalid data and noncanonical encodings block inventory. An
unrecognized name beginning `resolution-backup-` also blocks it. Unrelated names
are counted but their contents are not read. The command never traverses child
directories.

Backups for other projects must validate too, because invalid records cannot be
safely attributed or silently omitted from a complete inventory. The receipt
includes their project identity, hashes and file metadata, but omits their memory
text. It includes complete snapshots for the selected project, current memory,
all relevant file identities, the storage/lock and workspace identity, limits,
ordering rules, protected reasons and selected names.

An incomplete inventory must be addressed through explicit inspection and the
existing named cleanup/recovery workflows. For example, repair a verified backup's
extra staging link with [staging cleanup](CONVERSATION_MEMORY_CLEANUP.md) before
retention. [Named batch pruning](CONVERSATION_MEMORY_CLEANUP.md#batch-cleanup-and-retained-backup-pruning)
remains available without scanning; its receipt makes no newest-count guarantee.
[Unsupported backup disposal](CONVERSATION_MEMORY_BACKUP_DISCARD.md) now reviews
one exact invalid backup or a verified noncanonical/misnamed project backup,
with explicit limits through 4 MiB. The project path protects missing or matching
current memory. Review retention again after resolving each unsupported file.
[Exact-byte staging review](CONVERSATION_MEMORY_STAGING_REVIEW.md) covers staging
files only and cannot prune a retained backup. No force option skips
unreadable records or limits.

## Apply, concurrency and recovery

The preview hash binds the full inventory, policy and selection. Changes to a
retained or other-project backup, current memory, workspace, storage or lock
invalidate the old review. A changed count of unrelated directory entries also
requires a new preview. Enumeration order does not affect the receipt.

Apply holds the existing exclusive nonblocking memory lock. It revalidates the
inventory before every deletion, comparing it with the reviewed inventory minus
only its own completed deletions. It does not fill vacated selection slots from
`remaining_eligible`. Inventory reads also recheck file identities and directory
change times to detect changes during a scan. These checks coordinate cooperating
local writers; they do not isolate against arbitrary code running as the same OS
user.

Each successful unlink is followed by a storage-directory flush. The receipt's
`removed` list records names whose unlink returned; `synced` records names whose
following directory flush returned. An in-process failure returns `status:
incomplete`, these progress lists, and exit code 2. Failure before progress leaves
both lists empty. No rollback is attempted. A successful batch returns `completed`;
its inventory describes the reviewed state before deletion, not a new final scan.

Process death may leave a deleted prefix with no receipt, and death before a flush
leaves durability uncertain. Inspect storage and request a fresh inventory before
continuing. Old hashes cannot authorize replacement files or a smaller remaining
selection. Preserve preview output if you need its full historical content.
There is no automatic retry, background retention, startup cleanup or recovery
journal.
