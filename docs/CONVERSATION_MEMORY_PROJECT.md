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

The hash identifies what was inspected; it is not authorization for an apply
operation. Automated copy/merge and collision resolution remain planned. A future
apply operation must recheck documents, directory identities and the preview under
an exclusive lock before publication.

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
