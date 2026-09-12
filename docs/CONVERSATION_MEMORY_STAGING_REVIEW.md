# Review noncanonical and oversized staging files

Two explicit disposal paths share the same bounded raw-file reader and deletion
receipts. Choose the path that matches the record:

| Command | Accepted content | Project attribution |
| --- | --- | --- |
| `memory-staging-discard` | Bytes that fail the current snapshot validator | Unverified; no workspace is accepted or inferred |
| `memory-project-staging-discard` | A valid current-user project snapshot, with an exact workspace match and no duplicate JSON keys | Verified from the snapshot and explicit historical identity |

Both accept only an exact `.memory-migration-32_HEX_DIGITS.tmp` or
`.memory-resolution-32_HEX_DIGITS.tmp` name. They require existing private memory
storage and its lock, current-user filesystem ownership, a regular file and exactly
one link. They never scan, select backups, follow final symlinks or run at startup.
Names alone do not establish that content was never published or retained elsewhere.

## Review a valid project staging snapshot

Use this path for pretty-printed JSON, extra whitespace, alternate field ordering
or other noncanonical serialization that still passes the current snapshot contract.
Canonical snapshots are also supported. The command verifies the snapshot digest,
owner, scope and exact `document.workspace`, and rejects duplicate JSON keys rather
than choosing one interpretation of an ambiguous document.

```sh
mos memory-project-staging-discard --memory-storage /private/memory \
  --workspace-identity /projects/api \
  --temporary-name .memory-resolution-EXACT_32_HEX_DIGITS.tmp \
  --raw-sha256 RAW_FILE_SHA256 --json
# Inspect the complete record and bytes, then repeat with:
# --apply --expected-sha256 HASH_FROM_PREVIEW
```

`--raw-sha256` is the SHA-256 of the exact file, including formatting; for example,
calculate it with `shasum -a 256 FILE`. It differs from the snapshot's internal
`sha256` and the preview receipt hash. Changing whitespace invalidates the raw
binding even if the logical snapshot is unchanged. Recalculating only the raw hash
cannot reuse an old preview.

The receipt contains complete base64 bytes, the validated snapshot, `serialization:
canonical` or `noncanonical`, the explicit project identity and its presence/anchor,
current project memory (or null), file metadata, and private storage/lock identities.
The canonical project directory may be gone. Aliases and relative identities are
refused; no project directory or missing memory is recreated. Saved mapping
configuration does not select this command's identity.

This explicit staging discard can remove the last staged copy when current memory
is absent. Preserve any content you still need before applying. Unreadable current
project memory blocks project-aware review. Current project changes invalidate the
preview; unrelated user-memory changes do not. No content is normalized, copied,
restored or merged into live memory.

## Expand the raw review limit explicitly

The default remains 262,144 bytes (256 KiB). Both commands accept
`--review-max-bytes N`, from 1 through 4,194,304 bytes (4 MiB). For example:

```sh
mos memory-staging-discard --memory-storage /private/memory \
  --temporary-name .memory-migration-EXACT_32_HEX_DIGITS.tmp \
  --raw-sha256 RAW_FILE_SHA256 --review-max-bytes 1048576 --json
```

An oversized *valid* project snapshot, such as JSON padded with whitespace, uses
`memory-project-staging-discard` with the same explicit limit. The raw invalid path
still refuses every valid snapshot, including foreign-owner, user-scope,
noncanonical and duplicate-key inputs accepted by the underlying validator.
The project path rejects invalid, foreign-owner, user-scope, wrong-project and
ambiguous duplicate-key records. There is no force option between these boundaries.

The limit applies only to the selected staging file. Snapshot text/schema limits,
live-memory read limits, session budgets and active context limits remain unchanged.
The receipt binds `review_max_bytes`; changing it requires a fresh preview. Existing
receipts from versions without that field must also be refreshed. Every byte up to
the selected limit is included in `raw_bytes_base64`; exceeding the limit rejects
the operation, with no truncated review. Base64 and JSON output are larger than the
raw file and can contain sensitive historical content.

## Deletion and recovery

Preview creates nothing. Apply requires the exact preview hash and holds the
existing exclusive nonblocking memory lock. It re-reads and revalidates the complete
selection before unlink, including raw bytes, file identity/metadata, review limit,
storage/lock and, for project review, the project/current-memory observations.

Both paths use `planned`, `completed` and `incomplete` receipts. `removed` means
unlink returned successfully; `synced` means the following directory flush returned.
An in-process unlink/flush failure returns an incomplete receipt and exit code 2.
Initial validation failure removes nothing. Process death may leave no receipt,
including after deletion, and missing flush confirmation leaves durability uncertain.
Inspect the file and preserve needed evidence before a fresh review; an old approval
cannot remove a replacement file. There is no rollback or automatic retry.

Live memory, user preferences, registry files, other staging files, retained backups
and saved sessions are preserved. Multiply linked publication/backup records require
the existing [link-recovery workflows](CONVERSATION_MEMORY_CLEANUP.md). These staging
operations are separate from backup retention and project cleanup batches.

Files over 4 MiB, unsupported backup encodings and ambiguous duplicate-key snapshots
remain outside these disposal workflows. Such artifacts require separate inspection;
this feature does not add a backup-policy bypass. The checks coordinate cooperating
local writers and do not isolate against arbitrary code running as the same OS user.
