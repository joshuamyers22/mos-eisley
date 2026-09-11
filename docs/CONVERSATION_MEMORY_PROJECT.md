# Choose a project-memory root

Use an explicit ancestor directory when several working directories should load
the same project memory:

```sh
mos memory-project-preview -C /repo/packages/api --memory-project-root /repo
mos chat -C /repo/packages/api --memory-project-root /repo --name "API cleanup"
mos chat -C /repo/packages/web --memory-project-root /repo
```

The preview is read-only. A new chat loads the selected root's existing project
document plus enabled user memory. Without `--memory-project-root`, the canonical
working directory remains the project-memory identity.

The root must be an existing directory containing the workspace, or the workspace
itself. Paths and aliases resolve canonically; relative flags use the launching
shell's directory and `~` expands to home. Selection is explicit and does not
require a Git marker. Git discovery, remote URLs and worktree metadata never select
or merge memory automatically. Unrelated directories require future explicit mapping.

`--choose-directory` previews the effective memory root and rejects workspaces
outside it. The selected directories are rechecked before startup. The root is
saved even with `--no-memory`, so a later explicit memory refresh uses the same
identity. The synthetic `conversation-demo` and `conversation-review-demo` commands
also accept `--memory-project-root`; repeat the same memory options when generating
and using custom recordings.

## Inspect before adopting

Add `--json` to `memory-project-preview` for a structured receipt. Use the same
`--memory-storage` override as your sessions, if configured. The preview contains
both project document paths, complete versioned snapshots, enabled states and a
deterministic `preview_sha256`. It reads both documents under one shared storage
lock; missing storage stays absent. User memory is outside this project comparison.

| Status | Meaning |
| --- | --- |
| `same-identity` | Source and selected root identify the same document. |
| `empty` | Neither project document exists. |
| `source-only` | Only the workspace document exists. |
| `target-only` | Only the root document exists. |
| `collision` | Both documents exist, including empty or disabled documents. |

No files are copied, merged, cleared or enabled by preview or by starting a chat.
If only the source document exists, selecting the root starts without its project
text; the source document remains saved. If both exist, the new chat uses the root
document and leaves the workspace document intact. Inspect and reconcile content
explicitly with the existing memory commands before adopting when needed:

```sh
mos memory show --scope project -C /repo
mos memory show --scope project -C /repo/packages/api
```

The hash from `memory-project-preview` identifies what was inspected; it is not
accepted by the migration command below. Collision resolution and merging remain
planned.

## Copy workspace memory to an empty root

Use the separate migration preview to inspect the complete proposed document:

```sh
mos memory-project-migrate -C /repo/packages/api --memory-project-root /repo --json
mos memory-project-migrate -C /repo/packages/api --memory-project-root /repo \
  --apply --expected-sha256 HASH_FROM_MIGRATION_PREVIEW --json
```

Use the same `--memory-storage` on both commands when overriding the default.
Preview creates no storage or lock files. Only `source-only` is eligible: an empty
or disabled target still counts as an existing document and blocks copying.
Inspect the paths, source and `proposed` snapshot before supplying its hash.
The proposal copies text, enabled state, owner, source and original update time,
sets the selected root as its workspace, and starts the new document at revision 1.
Keeping the source timestamp makes the exact proposed bytes stable and reviewable.

Apply requires both flags. It binds the operation, source/target snapshots, proposed
bytes, canonical directories and their device/inode identities, storage directory
and lock identity. It recomputes the preview under an exclusive nonblocking lock,
then checks the directories, storage, lock and documents again after staging the
file and immediately before publication. Changed content or identities requires a
new preview. Publication is atomic and cannot overwrite a concurrently created
target. Other memory writers using the same storage lock cannot interleave.

The source and user documents remain byte-for-byte intact. Copying does not change
saved session identities, historical memory or request hashes. New root-selected
chats load the copied document; existing sessions use their existing memory checks
and require an explicit refresh if their root document has changed.

### Interrupted publication and recovery

The private staging file is flushed before an atomic hard-link publication; its
temporary name is then removed and the storage directory flushed. Ordinary failures
clean up the temporary name. A failure after publication can leave a complete
target even when the command reports failure. Inspect both documents before doing
anything further: the old preview cannot overwrite or retry an existing target.

A process killed between linking and removing the temporary name can leave the
target and one `.memory-migration-*.tmp` name linked to the same inode. Readers
deliberately reject that record under the existing single-link rule. Use the
explicit recovery command to inspect and remove only its verified temporary alias:

```sh
mos memory-project-recover -C /repo/packages/api --memory-project-root /repo \
  --temporary-name .memory-migration-EXACT_32_HEX_DIGITS.tmp \
  --target-sha256 APPROVED_PROPOSED_DOCUMENT_SHA256 --json
mos memory-project-recover -C /repo/packages/api --memory-project-root /repo \
  --temporary-name .memory-migration-EXACT_32_HEX_DIGITS.tmp \
  --target-sha256 APPROVED_PROPOSED_DOCUMENT_SHA256 \
  --apply --expected-sha256 HASH_FROM_RECOVERY_PREVIEW --json
```

Inspect the configured memory storage directory for the exact staging filename;
wildcards and paths are rejected. `--target-sha256` is `proposed.sha256` from the
approved migration preview, not its outer `preview_sha256`. The second command
requires the new recovery preview's hash. Use the same `--memory-storage` override
on both commands when configured. Preserve the migration preview for this purpose.

Recovery checks private ownership, exactly two links, matching device/inode for
the target and alias, canonical snapshot bytes, document owner and project scope,
and the approved document hash. Its receipt binds the full target, source/root
directory identities, storage and lock identities, exact alias name and target
inode/change time. Preview is read-only; apply rechecks under an exclusive lock,
removes only that alias, flushes the directory and validates the target with the
ordinary single-link reader. Missing storage remains absent. Changed or invalid
inputs stop recovery before cleanup. The source may have been edited since the
copy; recovery preserves its current contents and never rewrites the copied target.

Recovery runs only when explicitly invoked. It does not scan or clean unrelated
temporary files, finish an unpublished copy, merge collisions, or retarget saved
sessions. If the original approved hash is unavailable or validation fails, retain
the files for investigation; the source remains available. A directory-flush error
after unlink can mean cleanup already succeeded. Inspect the target with the normal
memory command before retrying; a one-link target is already recovered and is
ineligible for alias cleanup. These filesystem checks coordinate local writers;
they do not isolate memory from a hostile process running as the same user.

To stop using the copied memory, launch without the explicit root or use the
existing memory disable command at that root after inspection. Disabling affects
other sessions sharing the root and does not undo the copy or delete its source.

## Resume and compatibility

Resume with the original working directory and storage/backend. The saved memory
identity is reused; `resume` does not accept a root override. Changed Git markers
cannot retarget memory. `/memory refresh`, `/memory off`, and resume refresh preserve
the identity, historical memory and consumed recording exchanges. `/directory` and
startup JSON report the effective `memory_workspace` separately from the discovered
`project_root`.

Directory switching starts a fresh session with workspace-scoped memory and clears
the old explicit root option. Use a separate new launch to select another memory
root. Session lookup, names, tool authority and filesystem access stay scoped to
their existing contracts.

Legacy sessions retain their workspace binding and canonical bytes. Root-selected
sessions carry an optional `memory_project_root` field in saved state and SQLite
indexes. Current JSON/SQLite transfers and historical artifact readers preserve
and validate it. Older binaries may reject these sessions; retain an updated CLI
to resume them. Removing the field is not a supported downgrade or migration.
