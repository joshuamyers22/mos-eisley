# Reviewed bulk mapping import

Import several workspace-to-project-memory mappings together using a private JSON
manifest. The preview resolves directory identities, compares every incoming entry
with saved mappings, and shows the complete before/after registry. Apply requires
that preview's hash, saves the previous registry first, and publishes one complete
new revision.

Create a manifest such as this, replacing `501` with your numeric user ID (`id -u`)
and using your own existing absolute directory paths:

```json
{
  "schema_version": 1,
  "owner_uid": 501,
  "mappings": [
    {"workspace": "/worktrees/feature-a", "target": "/projects/main"},
    {"workspace": "/worktrees/feature-b", "target": "/projects/main"}
  ]
}
```

```sh
chmod 600 mappings.json
mos memory-project-mapping import --input mappings.json --json
# Inspect input bytes, resolved directories, changes and the full resulting registry.
mos memory-project-mapping import --input mappings.json \
  --apply --expected-sha256 PREVIEW_HASH --json
```

Use the same `--memory-storage PATH` on preview and apply when overriding the default
`~/.mos-eisley-memory`. Preview does not create missing memory storage. A valid
first apply can create its private storage and lock. The input is retained unchanged.

## Merge and replacement policies

| Options | Result |
| --- | --- |
| Default: `--mode merge --on-conflict error` | Keep unmentioned mappings; add new ones. Conflicts produce a review with `status: conflicts`, `can_apply: false`, and no resulting registry. Apply is blocked. |
| `--mode merge --on-conflict keep` | Keep existing conflicting entries and add nonconflicting incoming ones. The review identifies skipped conflicts. |
| `--mode merge --on-conflict replace` | Replace conflicting entries with the reviewed incoming directory identities; keep unmentioned mappings. |
| `--mode replace` | Make the registry exactly match the manifest. The preview identifies every removed or replaced entry. An empty manifest explicitly clears all mappings while retaining a versioned registry. |

A conflict means that an incoming workspace has a different saved target **or any
different directory pin**, including a replaced directory at the same path.
Unchanged entries are identified separately. Merge with `keep` can retain an old
mapping whose directory pin is stale; it does not silently repair that mapping.
Default conflict previews are inspection-only: there is no partial import of the
nonconflicting entries. Choose a policy and obtain a fresh preview before applying.
`--on-conflict` policy overrides apply only to merge mode; replacement mode rejects
`keep`/`replace` conflict overrides because it already specifies the full result.

Policies are included in the preview hash. For example, after inspecting conflicts:

```sh
mos memory-project-mapping import --input mappings.json --on-conflict replace --json
mos memory-project-mapping import --input mappings.json --on-conflict replace \
  --apply --expected-sha256 NEW_PREVIEW_HASH --json
```

Every successful apply publishes revision `current + 1`, including an import whose
mappings are all unchanged. There is no version/revision value to copy from the
manifest. See [history and restore](CONVERSATION_MEMORY_MAPPING_RECOVERY.md) to
recover an existing saved registry while preserving its original directory pins.

## Input and identity checks

The manifest is bounded to **1 MiB** and **128 mappings**; the resulting registry
must also satisfy its existing 128-mapping/1-MiB limits. Whitespace and JSON key
ordering are accepted, but exact source bytes are bound to review. Duplicate keys
at any depth, unknown fields, unsupported versions, invalid types, deeply nested
JSON, and foreign-owner manifests are rejected.

The input must be a private current-user single-link regular file. Final symlinks,
hardlinks, public files, FIFOs and directories are refused. The explicit input
parent is pinned and rechecked, including parent aliases. The command accepts a
relative `--input` path; paths *inside* the manifest must be absolute, printable
and at most 4,096 UTF-8 bytes. They do not expand `~` or use the manifest's directory
as a base. Directory aliases resolve to canonical paths and device/inode identities
shown in the preview. Duplicate workspaces after resolution are rejected, even if
their target paths agree.

Every incoming workspace and target must exist and remain at its reviewed identity,
including incoming entries that a keep policy skips. Unmentioned mappings retained
by merge keep their saved identities; their historical directories need not exist.
A moved or replaced directory requires a new preview and an explicit conflict
policy when it differs from a saved mapping.

The receipt includes complete input and current bytes in base64, raw hashes,
file/parent identities, resolved mappings, policies and the full registry change.
Existing registry storage and lock identities are bound to review. Bootstrap binds
the logical destination configuration because no storage inode exists yet. Apply
checks the source, directories and current registry again under the exclusive
nonblocking memory lock and before publication. Old hashes become invalid after
input changes (even whitespace), file/parent replacement, directory replacement,
policy changes or unrelated registry edits.

## Persistence and scope

Import preserves and flushes exact previous registry bytes before atomic
replacement. A corrupt or unsafe destination is rejected; use
[reviewed recovery](CONVERSATION_MEMORY_MAPPING_RECOVERY.md) when recovering a
corrupt registry is intended. Existing incomplete backups block publication until
reviewed cleanup resolves them.

Receipts distinguish `backup_synced`, `published` and `synced`. A caught mutation
failure emits `status: incomplete` and exits 2; preflight errors may have no receipt.
A failure does not promise rollback. Bootstrap failure can leave a private empty
storage/lock. Process death may leave a backup, a staging file, or a complete old or
new registry, and cannot return a final receipt. Inspect current mappings and
history, then obtain a fresh preview before retrying.

Imported mappings affect new launches. Import does not change working directories,
tool/filesystem authority, memory documents, or existing saved-session identities.
Snapshot and SQLite sessions resume with their original mapping. There is no
startup import, directory scan, cross-user sharing or automatic history retrieval.
See [saved mappings](CONVERSATION_MEMORY_MAPPINGS.md) for startup and override rules.
