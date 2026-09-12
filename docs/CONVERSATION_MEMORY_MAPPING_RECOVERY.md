# Mapping history and recovery

Saved mappings choose which project memory a new session loads. A reviewed mapping
set/remove now saves the previous `project-mappings.json` before replacing it.
Use the same `--memory-storage PATH` throughout if overriding the default
`~/.mos-eisley-memory`.

```sh
mos memory-project-mapping history --json
mos memory-project-mapping restore --file-name mapping-backup-SHA256.json --json
# Inspect selected/current bytes, every mapping and directory identity, and after.
mos memory-project-mapping restore --file-name mapping-backup-SHA256.json \
  --apply --expected-sha256 PREVIEW_HASH --json
```

Substitute an exact filename reported by history and the preview's SHA-256. History
includes complete decoded canonical owner registries, file identities, byte hashes,
and whether backup content matches its filename. Invalid/incomplete files are shown
without claiming valid mapping data. History is sorted by filename, not by an
asserted transaction time or chronological lineage. Backups do not prove that a
later update committed; a crash can happen after backup creation but before publish.
Missing storage is reported without creating anything.

Each file is bounded to **1 MiB**, including temporary files and corrupt bytes.
History admits at most **128 files**, **8 MiB** of total artifact bytes and **1,024
storage entries**. Exceeding a bound fails the whole listing instead of silently
showing a partial history. Exact-name restore/discard does not scan inventory, so
known files can still be inspected when the listing exceeds its limit. No automatic
retention policy deletes old backups. Unsupported filenames are outside the listing
and maintenance commands; there is no completeness claim about arbitrary filenames.

## Restore a backup or interrupted write

Restore accepts either `mapping-backup-64lowercasehex.json` or
`.memory-mappings-32lowercasehex.tmp`, as an exact basename inside private memory
storage. Files must be current-user, private, single-link regular files, valid
canonical registry JSON with the current owner, and within existing mapping-count
limits. Backup filenames must match the exact contents. Duplicate keys,
noncanonical encodings, unknown schemas, foreign owners, symlinks, hardlinks, and
nonregular or public files cannot be restored. Temporary files are not presumed to
be completed or approved updates simply because they have a recognized name.

The preview shows the complete selected source and current bytes in base64, their
hashes and file identities, storage and lock identities, before/after mappings,
and the backup name for current bytes. Apply requires the matching fresh preview
hash and an exclusive existing storage lock. Both selected and current files are
rechecked, and every selected workspace/target must still have its saved canonical
path and device/inode. Restore refuses moved, missing or replaced directories;
it never silently rebinds a historical path. Use ordinary reviewed mapping updates
when rebinding an existing valid registry is intended.

Restore publishes the selected mappings with revision `max(current, source) + 1`.
If current data is absent or invalid, only the selected source revision is usable;
this does not promise a monotonic lineage through unknown corrupt revisions.
The selected backup or staging file remains available. Existing current bytes,
including bounded private corruption, are retained and flushed before replacement.
An unsafe current file or recognized foreign-owner registry blocks replacement.
A missing current registry can be recovered without inventing a previous backup.
Storage and its existing private lock are required; restore never bootstraps them.

The restored registry affects new launches. It does not edit memory documents,
rewrite saved sessions or alter existing resume identities on either snapshot or
SQLite storage. Startup does not consult backup/staging files, fetch history into
chat context or recover anything automatically.

## Explicit cleanup

```sh
mos memory-project-mapping discard --file-name .memory-mappings-UUID.tmp --json
# Inspect the exact raw bytes and current registry before approving deletion.
mos memory-project-mapping discard --file-name .memory-mappings-UUID.tmp \
  --apply --expected-sha256 PREVIEW_HASH --json
```

Use an actual 32-character lowercase hexadecimal UUID in place of `UUID`.
Discard also accepts exact backup basenames. It can remove invalid or partially
written files, and valid historical files when a valid current registry exists.
Valid owner-scoped recovery files are protected while current data is absent or
invalid. Discarding a valid historical file with a valid current registry can still
lose older or unpublished mappings; the preview shows the whole selected record.
Invalid bytes carry no verified mapping attribution or last-copy guarantee.
There is no automatic deletion, age/count policy, session cleanup or recursive scan.

An interrupted backup write can leave incomplete bytes under its content-addressed
name. An update needing that backup fails until the file is reviewed and discarded;
then a fresh reviewed update creates the full backup. Existing valid backups are
verified and flushed again before reuse. No existing artifact is silently overwritten.

## Interrupted operations

Successful maintenance receipts report `status: completed`. Failure receipts can
report `status: incomplete`, with independent `backup_synced`, `published`,
`removed` and `synced` fields. The CLI emits the receipt and exits 2 on a caught
mutation failure. `published` or `removed` means that syscall returned; `synced`
means the final directory flush returned. A preflight rejection may have no receipt.
A failure never promises rollback. Process death cannot return a final receipt.
Inspect history/current data and obtain a fresh preview before retrying.

A crash while writing a backup may leave only partial bytes; a crash while writing
or publishing a registry can leave the old complete registry, the new complete
registry, or a staged file. Source and current backups allow explicit investigation.
The implementation uses the shared nonblocking memory lock and local filesystem
flushes. These are integrity checks for one user's storage, not authentication
against other software already running as that user or a claim about storage that
does not honor the filesystem's durability contract.

[Reviewed bulk import](CONVERSATION_MEMORY_MAPPING_IMPORT.md) now accepts a private
path manifest with fresh directory selection and explicit conflict policies.
Explicit history retention remains planned. See
[saved mapping selection](CONVERSATION_MEMORY_MAPPINGS.md) for startup, override and
resume behavior.
