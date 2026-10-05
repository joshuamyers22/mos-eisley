# Git review scope prerequisites

Mos can acquire a bounded, revision-bound Git brief and connect it to the existing
recorded `/review` workflow. This initial implementation supports an explicitly
selected POSIX repository root with its own `.git` directory. Linux and actual
Windows-hosted WSL2 qualification remain pending.

```sh
mos review-scope --workspace /path/to/repository --uncommitted
mos review-scope --workspace /path/to/repository --base main
mos review-scope --workspace /path/to/repository --commit COMMIT_ID
mos review-scope --workspace /path/to/repository --file src/example.py
mos review-scope --workspace /path/to/repository --uncommitted --range src/example.py:10-20
```

Uncommitted review includes staged changes, unstaged changes and untracked files
reported by Git, with staged and unstaged patches retained separately. Branch
review compares HEAD against its unique merge base with the selected reference;
dirty checkout contents do not enter that brief. Commit review compares the exact
commit with its parent, or an empty tree for a root commit. Merge commits require
`--parent N`. References must be plain names or object IDs; revision expressions
such as `HEAD~1` are unsupported. `--criteria "..."` supplies review criteria.

The command prints JSON containing the frozen scope, preview and brief. Optional
`--output /new/path/scope.json` writes only the scope to a new private file. Preview
includes exact revisions, file hashes, staged/unstaged/untracked flags, omissions,
scope digest and explicit absence of live review, pricing and posting authority.
A successful preview exit does not establish code acceptance. An empty scope has
no brief. Incomplete scopes disclose omissions and cannot dispatch a review.

## Connect to `/review`

Start a conversation with its explicit chat cassette and optional
`--review-packet`, using `--workspace /path/to/repository`. Type one of:

```text
/review --uncommitted
/review --base main
/review --commit COMMIT_ID --parent 1
/review --file src/example.py --file tests/test_example.py
/review --uncommitted --range src/example.py:10-20 --criteria "Check error handling."
```

Each command acquires and displays the scope. Without a packet, this is a preview
only. Dispatch requires a complete scope and a recorded packet whose brief and
request hashes already match that exact frozen brief. The demo recording is bound
to its synthetic change and cannot review arbitrary repository changes. No
recording is generated or rebound automatically. Bare `/review` retains its
existing explicit-packet behavior. Pasted command text remains literal input.

Scope-bound packets use schema 3, or schema 4 with project guidance. They retain
their scope in the existing private session snapshot. Source, index, revisions,
configuration and repository identity are checked before dispatch and again
before publishing a result. Queued reviews retain their original scope on resume;
stale inputs require a fresh selection. Critics receive only the frozen brief and
their persona; chat history and peer findings remain outside critic requests.

## Acquisition boundary

The reader uses fixed Git arguments, a system-path executable and a clean
environment. It disables hooks, fsmonitor, external diff/textconv, automatic
maintenance, lazy fetching and optional index writes. Repository configuration
includes, worktree configuration, escaped config syntax, external object alternates,
promisor stores and
metadata links are rejected. Metadata must be caller-owned and not writable by
other users. No repository-supplied command, credential helper or provider is invoked.

Working files are opened relative to the pinned repository descriptor, without
following links in any path component. Hardlinks and special files are rejected;
tracked symlinks and submodules are omitted. Uncommitted scopes conservatively
omit every indexed submodule without inspecting its checkout or configuration.
Binary, oversized and protected
`.git`, `.agents`, `.codex`, `.mos-eisley`, `.mos-eisley-sessions`,
`.mos-eisley-memory` and `.mos-eisley-guidance` paths are
disclosed without including their contents. Untracked files ignored by Git are
outside this preset. Diffs use raw blobs and bounded UTF-8 files, without filters.

## Explicit files and line ranges

Repeat `--file PATH` for whole files or `--range PATH:START-END` for disjoint
intervals. Paths are literal and relative to the workspace root. Quote spaces;
globs and Git pathspecs are never expanded. The range parser splits at the last
colon; `--file` selects names literally even when they end in a range-like suffix.

Without a comparison preset, selectors review a working-tree source snapshot with
**no comparison diff**, including unchanged or explicitly selected ignored files.
With `--uncommitted`, `--base` or `--commit`, they restrict that comparison before
any file/blob content is opened. Missing files, directories, traversal paths,
duplicate files, overlapping intervals and mixing whole-file and interval
selection for the same path are rejected.

Coordinates are one-based, inclusive LF records, preserving CRLF and Unicode text.
A range must exist completely in the target source: the working file for
source-only/uncommitted review, the target commit for base/commit review, or the
before version for a deleted file. Comparison ranges slice the **same numeric
coordinates independently in each version**; they do not follow moved lines.
Shorter comparison versions are explicitly labeled as clipped; absent versions
use an empty side. These are excerpt comparisons, not complete-file diffs. Staged
and unstaged excerpt differences remain separate, and diff headers retain original
line numbers. If no selected difference exists, the selected source is shown with
a no-diff label.

Only selected excerpts enter the brief; other lines and files are excluded.
Acceptance is limited to the selection. The reader still bounds and hashes the
entire selected file/blob, so edits outside a selected interval invalidate its
scope. Unselected working-file edits do not invalidate a file-only scope; pinned
HEAD, configuration and identity changes still do. A short interval in an oversized
file does not bypass the per-file limit or protected paths. Targets persist in the
existing scope/packet contracts; old packets without targets retain their canonical
bytes. Plain, JSON and TUI paths share acquisition and dispatch, and pasted
selectors remain literal conversation input.

Limits are 64 changed files, 16 KB per file/blob, 64 KB for the serialized scope,
512 KB for each Git command's combined output, five seconds per command and
twenty seconds per acquisition. Acquisition must agree across two capture passes;
changes fail closed rather than yielding a partial successful review.

This is a local prerequisite, not kernel containment or full managed-worktree
qualification. Git metadata is trusted to remain under the owner's control during
acquisition; this does not defend against malicious concurrent rewrites by the
same owner. Linked worktrees, repository discovery from subdirectories, paid live
dispatch and external posting remain future work.

Tests use synthetic repositories and recordings to cover scope semantics,
helper suppression, unsafe reads, stale inputs, isolated dispatch and persistence.
They also run against the installed wheel through the package smoke check.
