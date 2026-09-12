# Choose a project-memory root

Use an explicit ancestor directory when several working directories should load
the same project memory:

```sh
mos memory-project-preview -C /repo/packages/api --memory-project-root /repo
mos chat -C /repo/packages/api --memory-project-root /repo --name "API cleanup"
mos chat -C /repo/packages/web --memory-project-root /repo
```

The preview is read-only. A new chat loads the selected root's existing project
document plus enabled user memory. Without an explicit root or mapping option, the
canonical working directory remains the project-memory identity.

The root must be an existing directory containing the workspace, or the workspace
itself. Paths and aliases resolve canonically; relative flags use the launching
shell's directory and `~` expands to home. Selection is explicit and does not
require a Git marker. Git discovery, remote URLs and worktree metadata never select
or merge memory automatically. Use the separate mapping option below for unrelated
directories.

`--choose-directory` previews the effective memory root and rejects workspaces
outside it. The selected directories are rechecked before startup. The root is
saved even with `--no-memory`, so a later explicit memory refresh uses the same
identity. The synthetic `conversation-demo` and `conversation-review-demo` commands
also accept `--memory-project-root`; repeat the same memory options when generating
and using custom recordings.

## Share memory across worktrees

Map a new session explicitly to another existing directory's project memory:

```sh
mos memory show --scope project -C /projects/main
mos chat -C /worktrees/feature-a --memory-project-map /projects/main
mos chat -C /worktrees/feature-b --memory-project-map /projects/main
```

The worktrees can live outside the selected directory. Both sessions load the same
owner-scoped project document, plus user memory. Use the same `--memory-storage`
override for inspection, editing and sessions when configured. Edit shared project
memory with the existing memory commands using `-C /projects/main`; changes affect
all sessions selecting that identity and use the normal explicit refresh guard.

`--memory-project-map` and `--memory-project-root` are mutually exclusive. The root
option still requires an ancestor. These explicit launch flags override
[saved workspace mappings](CONVERSATION_MEMORY_MAPPINGS.md). The selected mapping
is saved with the session; Git never selects one.
The selected directory must exist, paths resolve canonically, and aliases are
pinned before startup. Bare `mos --memory-project-map PATH` and the two recording
generators accept the option. Repeat it when creating and using custom recordings.

`--choose-directory` previews the mapped identity while allowing an unrelated
workspace. Source and selected memory directories are rechecked before startup.
`--no-memory` retains the selected identity without loading or creating memory
storage; a later explicit refresh uses it. It bypasses automatic registry selection
too, preserving only an explicit root/map flag’s identity. Resume retains the saved mapping and
accepts neither root nor mapping overrides. A saved target path retargeted through
a symlink is rejected. `/directory` and startup JSON show the effective memory
workspace and expose `memory_project_mapping` for mapped sessions.

Mapping changes memory selection only. It preserves the session's working
directory, lookup and filesystem/tool authority. It does not copy or merge the
workspace's existing memory, edit documents, rewrite old sessions or share memory
between OS users. Directory switching clears explicit root/map flags and selects
the new workspace’s saved mapping, unless `--memory-project-local` is active.
The existing copy/resolution commands retain their ancestor-only scope.

Use the relocation command below to copy documents or explicitly resolve collisions
across identities, including from vanished directories. Use
`mos memory-project-mapping set` to review and persist a workspace mapping. Keep
the selected directory accessible for mapped sessions; mapping and document relocation do not relocate saved sessions.

## Copy memory after a project moves

Use the exact former canonical identity from a saved session's `memory_workspace`
display (its mapping, root or workspace), or the memory record's `document.workspace`.
The old directory may be absent. The destination must be an existing directory,
and can be unrelated to the source:

```sh
mos memory-project-relocate --from-workspace /old/projects/api \
  --to-workspace /projects/api --json
mos memory-project-relocate --from-workspace /old/projects/api \
  --to-workspace /projects/api --apply --expected-sha256 HASH_FROM_PREVIEW --json
mos chat -C /projects/api
```

Repeat any `--memory-storage` override in preview, apply and subsequent sessions.
Review and retain the complete preview, including both identities, full documents,
proposed content and hash. Although the command is named relocate, it retains the
source document. It copies only when a source exists and the destination document
is absent. Empty and disabled documents count as existing; copy mode shows
collisions and never overwrites them. Use a separate strategy-bound resolution
review below when both identities already have documents.

The source argument is literal: relative paths, `~`, trailing slashes, dot segments,
duplicate separators, symlink aliases and non-directory paths are rejected. Do not
substitute a new path for the historical identity. Destination aliases resolve
canonically and the selected directory is bound to the preview. Preview creates no
storage, lock or missing project directories. Apply requires the fresh hash and an
exclusive existing storage lock. Both snapshots, source record device/inode/change
time, destination directory, storage and lock identities are rechecked immediately
before atomic no-overwrite publication. The source's presence or absence and its
nearest existing ancestor identity are also bound; recreating a vanished directory
or missing ancestor invalidates the review. An existing source is supported for
explicit copies between worktrees. Ordinary ancestor-copy previews now also bind
the source record identity, so obtain a fresh preview after upgrading.

The new record preserves source text, enabled state and update time, sets the new
canonical workspace, and starts revision 1 with a new document hash. User memory and
old project records are untouched. Saved sessions retain their identities and
history, and ordinary startup/resume still requires the saved directories to exist.
Launch a new session at the destination, or map a new session to it explicitly;
this command does not make a session from a vanished directory resumable. Existing
sessions using the destination follow the normal changed-memory guard. Existing
individual and combined memory byte limits still apply.

The same publication failure rules below apply. A flush error may leave a published
copy; inspect before retrying. For a process killed after publication but before
staging-alias removal, use the same command with an exact alias and the approved
`proposed.sha256`:

```sh
mos memory-project-relocate --from-workspace /old/projects/api \
  --to-workspace /projects/api \
  --temporary-name .memory-migration-EXACT_32_HEX_DIGITS.tmp \
  --target-sha256 APPROVED_PROPOSED_DOCUMENT_SHA256 --json
# Review the recovery receipt, then repeat with:
# --apply --expected-sha256 HASH_FROM_RECOVERY_PREVIEW
```

Recovery uses a distinct operation hash and the same private ownership, scope,
canonical content, exact two-link inode and exclusive-lock checks as ancestor-copy
recovery. It removes only the verified staging alias, preserves target bytes and
works while the old directory is absent. Changed source-path presence or anchor
requires another review. Source document edits do not block recovery. No source is
deleted, copy/recovery mode never overwrites an existing target, and no automatic
orphan cleanup runs.
Use [memory staging cleanup](CONVERSATION_MEMORY_CLEANUP.md) for an explicitly
reviewed complete staging discard or interrupted backup-link repair.

## Resolve collisions across worktrees or after a move

When both identities already contain project memory, select a resolution strategy
explicitly with the same exact source identity and existing destination:

```sh
mos memory-project-relocate --from-workspace /old/projects/api \
  --to-workspace /worktrees/api --strategy append-source --json
mos memory-project-relocate --from-workspace /old/projects/api \
  --to-workspace /worktrees/api --strategy append-source \
  --apply --expected-sha256 HASH_FROM_RESOLUTION_PREVIEW --json
```

`keep-target` keeps the destination unchanged, `use-source` replaces its text,
`append-source` joins destination and source text literally, and `use-text` uses
the supplied `--text "Reviewed content"` (including an explicit empty string).
The destination's enabled state is preserved in every case. Both documents must
exist, even for keep-target or use-text; this mode never implicitly creates a missing
document. Omit the strategy to use the separate absent-target copy workflow.
Repeat the same strategy, text and storage override when applying the preview.

The receipt's operation is `resolve-relocated-project-memory`. Copy, ancestor
resolution, mapped resolution and recovery hashes are not interchangeable. Strategy,
text, both complete snapshots and record identities, destination directory and
source presence/nearest existing ancestor are bound alongside storage and lock
identities. Source reappearance or any reviewed input change requires a fresh
preview. `--temporary-name`/`--target-sha256` recovery flags cannot be mixed with a
strategy, and `--text` is accepted only with `use-text`.

Changed text follows the [same durable backup protocol](#resolve-existing-workspace-and-root-documents)
as ancestor resolution: a verified private canonical prior-target backup is flushed
before atomic replacement, the target revision increases by one, and its UTC update
time is assigned at apply. All inputs are rechecked under an exclusive lock just
before publication. No-ops preserve bytes, metadata and revision and create no
backup. Source/user documents and saved session identities/history are preserved;
existing destination sessions retain the explicit changed-memory refresh guard.
Literal append does not deduplicate. Existing memory byte limits still apply.

Keep the backup for review or a later explicit use-text restoration. A crash before
replacement leaves the old destination and its backup; a crash after replacement
can leave the new destination even without a success receipt. Inspect before retrying.
An interrupted backup or unpublished resolution staging file is retained for
investigation. Copy-recovery mode does not clean these files or restore a resolution
backup. The separate [memory cleanup command](CONVERSATION_MEMORY_CLEANUP.md)
now supports complete staging disposal and backup-link repair. Retained-backup
pruning remains planned; nothing is deleted automatically.

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
accepted by the migration or resolution commands below.

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

## Resolve existing workspace and root documents

When both documents exist, choose a strategy and inspect a resolution preview:

```sh
mos memory-project-resolve -C /repo/packages/api --memory-project-root /repo \
  --strategy append-source --json
mos memory-project-resolve -C /repo/packages/api --memory-project-root /repo \
  --strategy append-source --apply --expected-sha256 HASH_FROM_RESOLUTION_PREVIEW --json
```

Use the same `--memory-storage` override and strategy on preview and apply.

| Strategy | Proposed root text |
| --- | --- |
| `keep-target` | Keep the existing root text unchanged. |
| `use-source` | Use the workspace text in place of the root text. |
| `append-source` | Append workspace text after root text, with two newlines when both are nonempty. |
| `use-text --text "Reviewed text"` | Use explicitly reconciled text; `--text ""` explicitly clears it. |

These are literal operations. Appending does not deduplicate repeated decisions or
resolve contradictions; use reviewed text for that. The root's enabled state is
preserved, including disabled roots. A disabled source's text can be selected
explicitly into an enabled root, so review both snapshots and the proposed state.
The 32 KiB document limit applies to the complete result, including UTF-8 bytes.
Existing combined user/project load limits still apply; a document-sized result
may need shortening before a session can load both active documents.
Missing documents and identical source/root identities are ineligible; use the copy
command when the root document is absent.

The preview binds both documents, strategy, proposed content and revision, record
identities/change times, source/root directories, storage/lock identity, and backup
path/existence. Apply requires both flags and rechecks under an exclusive lock
immediately before publication. Source and user files stay byte-for-byte intact.
Changed text increments the root revision once; its update time is assigned in UTC
at apply, as declared by `updated_at_policy`. The returned `result` contains the
final snapshot and hash. The reviewed content, enabled state and revision are fixed
by the preview. `keep-target` or an identical replacement reports `will_write:false`,
creates no backup, and preserves the existing revision, timestamp and bytes.

Before replacing a changed root document, apply saves and flushes a private,
content-addressed `resolution-backup-*.json` containing its complete canonical prior
snapshot. It verifies and flushes an existing matching backup before reuse; unsafe,
changed or multiply linked backups block replacement. The new target is staged,
flushed and atomically replaced only after a final input/backup check, then the
storage directory is flushed. Writers using the same memory lock cannot interleave.
The backup remains available for inspection; it is not loaded as active memory.

### Resolution failures and recovery

A failure before replacement leaves the target intact; a complete backup may remain.
Obtain a fresh preview because backup existence is included in the hash. A failure
after replacement may leave the new target and old backup even if the command
reports an error. Inspect both; the old receipt cannot repeat an append against a
changed target. Existing root-bound sessions retain their saved history and use the
normal changed-memory guard; explicitly refresh or disable their memory to continue.

A process killed while publishing the backup may leave its staging alias linked to
the backup. The old target remains readable, and resolution rejects the multiply
linked backup. A process killed before replacement can also leave an unpublished
`.memory-resolution-*.tmp` file. Retain these for investigation; the copy-recovery
command does not clean resolution backups or unpublished files. Use the separate
[memory cleanup workflow](CONVERSATION_MEMORY_CLEANUP.md) to review one complete
staging discard or verified backup-link repair. The same guide covers explicit
1–32-record batch cleanup and retained-backup pruning under a reviewed age cutoff.
Bounded invalid records use the separate
[raw staging review](CONVERSATION_MEMORY_STAGING.md), without claiming a verified
project identity. No cleanup scans or runs at startup.

To restore prior content, inspect the backup's `document.text`, use it with a fresh
`use-text` resolution preview, and review/apply that proposal. This creates a new
revision and backs up the current root; it does not rewind session history. Enabled
state remains a separate explicit memory edit. Keep backups until their retention
is explicitly managed; this command does not prune them.

## Interrupted copy publication and recovery

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
identity is reused; `resume` does not accept root or mapping overrides. Changed Git markers
cannot retarget memory. `/memory refresh`, `/memory off`, and resume refresh preserve
the identity, historical memory and consumed recording exchanges. `/directory` and
startup JSON report the effective `memory_workspace` separately from the discovered
`project_root`.

Directory switching starts a fresh session with workspace-scoped memory and clears
the old explicit root or mapping option. Use a separate new launch to select another memory
root. Session lookup, names, tool authority and filesystem access stay scoped to
their existing contracts.

Legacy and ancestor-root sessions retain their existing canonical bytes. Mapped
sessions add the optional `memory_project_mapping` field to saved state and SQLite
indexes, mutually exclusive with `memory_project_root`. Current JSON/SQLite
transfers, cold resume and historical artifact readers preserve and validate the
selected identity. Older binaries may reject mapped sessions; retain an updated
CLI to resume them. Removing either identity field is not a supported downgrade
or migration.
