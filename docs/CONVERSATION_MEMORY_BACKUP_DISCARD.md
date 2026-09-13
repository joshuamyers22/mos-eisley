# Review unsupported memory backups

An invalid or noncanonical backup can block a complete retention inventory. Review
one exact file with these commands before running retention again:

| Command | Accepted contents | Protection |
| --- | --- | --- |
| `memory-backup-discard` | Bytes that fail the current `MemorySnapshot` validator | Project attribution and current-memory protection remain unverified. Every valid snapshot is refused, including foreign-owner or noncanonical snapshots. |
| `memory-project-backup-discard` | A valid current-user project snapshot with a noncanonical encoding, mismatched content-addressed filename, or encoding over the retention record limit | Exact historical project identity is verified. Current project memory must be readable, present, and have a different document hash. Duplicate JSON keys are refused. |

Both commands accept only an exact `resolution-backup-64_LOWERCASE_HEX_DIGITS.json`
basename in the selected private memory storage. They require an existing lock and
an owner-private regular file with a single link. They do not scan the directory.
Live documents, staging names, mappings, symlinks, hardlinks, directories, malformed
backup names and wildcards are rejected.

## Preview and apply

Calculate SHA-256 over the file's exact bytes, including whitespace. This is not the
document hash stored in the snapshot or necessarily the filename's embedded hash.
For example, inspect an invalid backup with:

```sh
shasum -a 256 /private/memory/resolution-backup-64_HEX_DIGITS.json
mos memory-backup-discard --memory-storage /private/memory \
  --backup-name resolution-backup-64_HEX_DIGITS.json \
  --raw-sha256 RAW_FILE_SHA256 --json
```

For a valid snapshot with unsupported encoding or filename, specify its exact
canonical historical project path:

```sh
mos memory-project-backup-discard --memory-storage /private/memory \
  --workspace-identity /projects/api \
  --backup-name resolution-backup-64_HEX_DIGITS.json \
  --raw-sha256 RAW_FILE_SHA256 --json
```

The project directory may have vanished; it is not recreated. A symlink alias or
relative identity is not accepted. The receipt contains complete raw bytes as
base64, the raw hash, file metadata, storage and lock identities, and review limit.
The project receipt additionally contains the validated snapshot, current memory,
workspace anchor, expected canonical backup name, and `unsupported_reasons`.
`filename-mismatch` reports the difference explicitly and does not rename the file.

Review and preserve any content you still need. Repeat the same command with
`--apply --expected-sha256 PREVIEW_SHA256` to remove that exact file. Both flags are
required together. Raw invalid-file review cannot establish whether the bytes are
the last recoverable copy or whether they contain current project memory; the
receipt reports `current_memory_protection: unverified-invalid-record`. Project
review refuses absent, unreadable, or matching current memory.

The default raw review limit is 262,144 bytes (256 KiB). Use
`--review-max-bytes N` to explicitly select 1 through 4,194,304 bytes (4 MiB).
The entire file must fit; no truncated preview can authorize deletion. Use the
same limit during apply because the preview hash binds it. This does not change
memory document, session, context or inventory limits.

## Retention and interruption

Supported canonical, correctly named backups within 256 KiB still require
[retention](CONVERSATION_MEMORY_RETENTION.md) or explicit
[batch pruning](CONVERSATION_MEMORY_CLEANUP.md#batch-cleanup-and-retained-backup-pruning).
This unsupported-file workflow provides no newest-count or age guarantee. It does
not run at startup, prune other records, normalize snapshots or publish a repair.
Obtain a fresh retention inventory after addressing each blocking file.

Apply holds the existing exclusive memory lock and repeats the complete inspection
before unlink. Changes to bytes, metadata, review policy, storage, lock, or the
project's current memory and workspace anchor invalidate review. Staging commands
cannot apply backup receipts, and the raw path cannot apply project receipts.

Success reports `status: completed`, `removed: true`, and `synced: true`. An
in-process unlink or directory-flush error returns an incomplete receipt and CLI
exit code 2. `removed` and `synced` report only completed calls: deletion may have
happened even if durability is uncertain. Process death may return no receipt.
Inspect the exact filename and obtain a fresh review before further action; a
replacement file cannot reuse an old preview. There is no rollback or automatic
retry. The lock coordinates cooperating writers; it does not isolate arbitrary
code running as the same OS user.

Files above 4 MiB, valid snapshots with duplicate keys, foreign project/owner or
user snapshots, unsupported filename syntax, and unsafe filesystem objects remain
outside this disposal workflow. Extra staging links use the existing link-recovery
commands. Memory mappings and their temporary files have separate planned recovery
work.
