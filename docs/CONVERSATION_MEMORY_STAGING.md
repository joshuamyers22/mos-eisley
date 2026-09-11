# Discard one invalid staging file

An interrupted memory publication may leave an empty or partially written staging
file. Its bytes cannot establish a valid memory snapshot or reliably identify a
project. `memory-staging-discard` therefore reviews one exact file in private memory
storage, with **unverified project attribution**. It accepts no workspace argument
and never guesses a project from a partial JSON header or the launch directory.

Inspect and preserve any bytes you still need. The file may be the only recoverable
copy of some content. Calculate the SHA-256 of its exact raw bytes, for example with
`shasum -a 256 FILE`, then request a read-only preview:

```sh
mos memory-staging-discard --memory-storage /private/memory \
  --temporary-name .memory-migration-EXACT_32_HEX_DIGITS.tmp \
  --raw-sha256 REVIEWED_RAW_FILE_SHA256 --json
# Repeat the exact selection with:
# --apply --expected-sha256 HASH_FROM_DISCARD_PREVIEW
```

Supported names are exactly `.memory-migration-32_HEX_DIGITS.tmp` and
`.memory-resolution-32_HEX_DIGITS.tmp`, using lowercase hexadecimal digits. The
command requires an existing private memory directory and its existing lock. It
does not create either, list the directory, select by age, or follow a final
symlink. It accepts one regular file owned by the current OS user, with no
group/other permissions and exactly one link. The default review limit is 256 KiB;
`--review-max-bytes` explicitly changes it up to 4 MiB. The limit is bound to review. Ordinary
user-memory staging names, live project/user document names, backup names,
wildcards, symlinks, directories, pipes and multiply linked files are refused.

The receipt explicitly reports `scope: storage`, `project_identity: null` and
`project_identity_verified: false`. Filesystem ownership is checked; ownership or
scope claims inside an invalid document are not trusted. `raw_bytes_base64` carries
the complete bounded file, including non-UTF-8 bytes, without printing terminal
control sequences. Decode it into a private file for inspection when needed. The
preview can contain sensitive memory fragments and should be handled accordingly.

`raw_sha256` hashes the file bytes, not a snapshot's internal `sha256` field. The
separate `preview_sha256` binds those bytes, the exact name/path, file owner,
device/inode/change time/modification time/size, and the private storage and lock
identities. Altering the bytes, replacing the file, changing metadata or replacing
storage/lock invalidates the old review. Apply rechecks under one exclusive existing
memory lock before unlink and directory flush. Cooperating writers use that same
lock, so a writer still publishing a record blocks preview or apply.

This command accepts only bytes that fail the current `MemorySnapshot` validation,
including empty, truncated, non-JSON and integrity-invalid records. Any valid
snapshot is refused—even a noncanonical serialization, a user-scope snapshot or a
snapshot claiming a different owner/project. Use the separately reviewed
[project-aware cleanup](CONVERSATION_MEMORY_CLEANUP.md) where supported. Raw discard
cannot bypass those commands for a valid snapshot, repair hardlinks, prune backups
or publish a missing project document. The separate
[project staging review](CONVERSATION_MEMORY_STAGING_REVIEW.md) supports valid
canonical/noncanonical project snapshots and the same explicit review limit.
Raw discard still refuses valid snapshots at every limit. Files above 4 MiB and
ambiguous duplicate-key snapshots remain outside these disposal workflows.

Failure of this version's validator does not prove the bytes are unusable;
unrecognized formats can also fail validation. Preserve any needed data before
applying the raw-byte review.

Current memory documents are not read or bound to this review. Changes to unrelated
memory do not invalidate a selected raw-file approval. No project directory needs
to exist. Only the selected staging name is removed; live documents, retained
backups, other staging files, session history and memory mappings are preserved.
The command is deliberately separate from project-scoped batch cleanup because its
project identity is unverified.

## Interruption and recovery

Deletion is permanent. Receipts use `status: planned`, `completed` or `incomplete`.
`removed: true` means unlink returned successfully; `synced: true` means the
subsequent directory flush succeeded. An in-process unlink or flush failure returns
an incomplete JSON receipt with exit status 2. Initial validation failures remove
nothing. A removed file without a successful flush has uncertain durability after a
system crash.

A process death may leave no receipt, including after unlink. Inspect the exact
filename and preserved data before further action. A missing file is not recreated,
and an old approval cannot authorize a replacement. If the file remains, obtain a
fresh preview before retrying. There is no rollback, journal, automatic scan,
automatic retry or startup cleanup. These checks coordinate cooperating writers;
they do not isolate files from a hostile process running as the same OS user.
