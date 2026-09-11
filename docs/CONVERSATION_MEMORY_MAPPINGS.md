# Saved project-memory mappings

Save an exact workspace-to-memory-directory mapping once, then start new sessions
there without repeating `--memory-project-map`:

```sh
mos memory-project-mapping set -C /worktrees/feature-a --target /projects/main --json
# Inspect the full before/after registry, paths and directory identities.
mos memory-project-mapping set -C /worktrees/feature-a --target /projects/main \
  --apply --expected-sha256 PREVIEW_HASH --json
mos -C /worktrees/feature-a
mos memory-project-mapping show --json
```

Use the same `--memory-storage PATH` on all commands when overriding the default
`~/.mos-eisley-memory`. The private, current-user registry is
`project-mappings.json` inside that storage. A missing registry means no mappings;
read-only inspection and startup never create it. The first reviewed update creates
private storage and its shared memory lock if needed.

Only an exact canonical workspace matches. Child directories, Git markers, remote
URLs and common Git metadata do not select a mapping. Saving resolves aliases and
records canonical paths plus device/inode identities for both directories. Moving,
replacing or retargeting a saved canonical directory requires a fresh reviewed
mapping. Changing the original alias used to save a mapping does not retarget it.
A mapped target may be unrelated to the workspace or equal to it.

New `mos`, `mos chat`, `conversation-demo` and `conversation-review-demo` launches
use saved mappings by default. Explicit `--memory-project-map PATH` or
`--memory-project-root PATH` overrides the registry. Use `--memory-project-local`
to select the workspace's own memory. These three flags are mutually exclusive.
`--no-memory` bypasses both memory documents and automatic registry lookup,
including unsafe storage. An explicit root/map flag still records its identity
for a later refresh; otherwise that disabled session retains its workspace identity.

The directory picker shows the mapped identity before selection. One bounded
registry snapshot is captured at the first preview or startup lookup and retained
through startup, so concurrent edits do not silently change what was displayed.
Directories are rechecked before saving the session. Directory switching clears
an explicit root/map override and captures a new registry snapshot for the
handoff; `--memory-project-local` remains in effect for the invocation. Each
switch uses the same snapshot for its picker and fresh session. A failed or
cancelled switch leaves the original session saved.

Saved sessions retain their existing `memory_project_mapping` identity. Resume
and memory refresh use that identity independently of later registry edits,
removal or corruption. Resume does not accept mapping overrides. Registry inode
pins protect new-session selection; they do not add new inode checks to legacy
saved-session formats. Existing resume checks still reject a canonical saved
memory path that now resolves elsewhere.

Mappings select context, not filesystem or tool permissions. They do not copy or
merge documents, rewrite saved sessions or change working directories. Edit the
shared document explicitly with `mos memory ... -C /projects/main`; memory editing
and migration commands do not consult the registry. Existing sessions require the
normal explicit memory refresh after document edits.

## Update and remove

Repeat `set` to review a changed target or rebind a replaced directory. Every set
or removal requires the fresh preview hash, including when the logical target is
unchanged. The receipt covers the complete before/after registry, owner, revision,
logical storage location and selected directory identities. An unrelated mapping
edit invalidates old receipts. Bootstrap binds logical configuration, rather than
a storage inode that did not exist during preview.

Remove using the exact saved canonical workspace path shown by `show`; removal
works even when the workspace or target no longer exists:

```sh
mos memory-project-mapping remove -C /worktrees/feature-a --json
mos memory-project-mapping remove -C /worktrees/feature-a \
  --apply --expected-sha256 PREVIEW_HASH --json
```

Removal keeps a versioned empty registry when the last entry is removed. It never
deletes memory documents. There is no automatic pruning or prefix matching.

## Storage and recovery limits

The registry accepts at most 128 sorted, unique mappings and 1 MiB of canonical
JSON. Unknown fields, duplicate keys, noncanonical encodings, foreign owners,
public files, symlinks, multiple hardlinks and nonregular files are rejected.
Shared nonblocking memory-storage locks coordinate inspection and atomic updates.
Updates write a private temporary file, flush it, verify the reviewed state and
directory identities again, replace the registry, then flush the storage directory.
A stale hash is rejected before creating absent storage and checked again under
the write lock. These are local same-user integrity checks, not cryptographic
protection against software already running as the owner.

A failure after replacement can leave the new registry visible without confirmed
durability; an error never promises rollback. Inspect `show` and obtain a fresh
preview before retrying. Process death before replacement can leave a private
`.memory-mappings-*.tmp` file, which startup ignores. Automatic staging recovery,
registry history/backups, bulk import and cleanup of these registry temporary files
are not implemented. Preserve the preview output when recovery evidence matters.
A corrupt registry blocks automatic mapping selection; an explicit map/root or
`--memory-project-local` lets a new launch proceed without consulting it. Reviewed
updates reject corruption rather than overwriting data they cannot inspect.
