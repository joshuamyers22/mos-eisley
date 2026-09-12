# Reviewed mapping-history retention

Review old saved-mapping backups as one bounded batch, then apply that exact plan:

```sh
mos memory-project-mapping retain --keep-newest 10 --before-ns CUTOFF_NS --json
# Inspect the complete inventory, protected reasons, selected names and policy.
mos memory-project-mapping retain --keep-newest 10 --before-ns CUTOFF_NS \
  --apply --expected-sha256 PREVIEW_HASH --json
```

Replace `CUTOFF_NS` with your chosen positive Unix timestamp in nanoseconds, below
`2**63`, and `PREVIEW_HASH` with the preview's hash. Use the same `--memory-storage
PATH` throughout when overriding `~/.mos-eisley-memory`. Both policy options are
required; `--keep-newest` accepts 0–128. There is no scheduled, startup or background
retention, and preview creates no storage. Existing private storage and its lock
are required.

## Selection and protection

The command inventories the `mapping-backup-` namespace. Each backup must be a
private, current-user, single-link regular file containing a canonical same-owner
mapping registry, with a filename matching its exact content hash. Every backup is
validated, including backups the policy would protect.

Protection rules combine:

- Preserve the newest `--keep-newest` backups, ranked by filesystem modification
  time descending and filename ascending for ties.
- Preserve backups whose modification time is at or after `--before-ns`.
- Preserve backups exactly matching the current registry bytes, including revision.
- If the current registry is missing, preserve every backup.

A present corrupt, foreign-owner or unsafe current registry blocks retention.
Recover it through [reviewed restore](CONVERSATION_MEMORY_MAPPING_RECOVERY.md) first.
A valid current registry is never deleted or rewritten. Historical directory paths
need not exist; retention validates saved records without rebinding or accessing
those directories.

Eligible backups are sorted oldest first, then filename ascending. The plan selects
at most **32 deletions**. Additional eligible names appear in `remaining_eligible`
and need a fresh preview after this batch. Apply does not recalculate which files
to delete halfway through a batch.

Filesystem modification time is an explicit local policy input, not proof of a
successful transaction, last use, or chronological lineage. A retained backup can
have been written before an update that never committed. Records with identical
mappings but different revisions are distinct history; only exact current bytes
receive the matching-current protection.

## Complete inventory and bounds

A review admits at most **128 backups**, **8 MiB of aggregate backup bytes**, and
**1,024 storage directory entries**. Each backup and the current registry are
bounded to **1 MiB**. Exceeding a limit fails the whole review. It does not select
from a truncated or paginated inventory.

Malformed `mapping-backup-` names, partial/invalid bytes, duplicate JSON keys,
noncanonical encodings, foreign owners, unsupported schemas, mismatched content
hashes and unsafe files all block retention, even if a newest-count or age rule
would have protected them. Use [exact-file history review and discard](CONVERSATION_MEMORY_MAPPING_RECOVERY.md)
for supported files that require individual review. Unsupported names and files
above the existing review size limit remain outside these commands.

Mapping staging files, project-memory backups, memory documents and other entries
are excluded from deletion. They count toward the directory-entry limit; their
contents are not inspected by this policy. A change in their count invalidates the
inventory. Changing unrelated file contents has no retention meaning.

The receipt shows every decoded backup, its content hash and file identity, the
current registry and its identity, storage/lock identities, policy, protection
reasons, selected names, and remaining eligible names. A shared nonblocking lock
coordinates preview; apply takes the existing exclusive lock. The operation binds
retained files as well as selected ones to the review hash.

## Interrupted or stale apply

Apply rechecks the complete inventory and current registry before every unlink,
allowing only its own prior deletions. A changed retained backup, new/missing backup,
changed file identity, replaced storage/lock, changed current registry or changed
policy invalidates the review and stops remaining deletions. Every successful
unlink is followed by a directory flush.

Receipts contain separate `removed` and `synced` name lists. A caught mutation
failure emits `status: incomplete` and exits 2. Names in `removed` had their unlink
return successfully; names in `synced` also had their directory flush return.
Preflight errors may have no receipt. Failure does not promise rollback, and
process death cannot return a final receipt. Inspect current history and obtain a
new preview for the remaining files; an old preview cannot be replayed after a
partial deletion.

Retention affects only selected mapping-backup files. It does not modify the
current mapping registry, working directories, tool authority, user/project memory
or saved sessions. Snapshot and SQLite resumes keep their original identities.
These are local integrity checks under the shared storage lock, not authentication
against software already running as the same user or a guarantee that arbitrary
storage honors filesystem durability semantics.
