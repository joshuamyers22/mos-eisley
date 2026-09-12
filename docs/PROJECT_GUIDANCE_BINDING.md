# Bind reviewed guidance to a project

`mos guidance` stores explicitly reviewed advisory templates in private owner
configuration. Each binding belongs to one canonical workspace and its directory
device/inode identity. Opening a repository or nested directory does not attach
guidance. [Independent overrides and effective advisory inspection](PROJECT_GUIDANCE_OVERRIDES.md)
are available separately. Conversation controls, conflict handling and role-context
materialization remain subsequent work.

## Review and apply

Inspect a source using [guidance-inspect](PROJECT_GUIDANCE_INSPECTION.md), then
preview its attachment:

```sh
mos guidance attach -C /path/to/project \
  --template-id engineering-example \
  --descriptor templates/PROJECT_GUIDANCE_EXAMPLE.json \
  --markdown templates/PROJECT_GUIDANCE_EXAMPLE.md --json
```

Use the actual descriptor's `template_id`; the selected ID must match exactly.
The result includes complete before/after bindings, the previous and proposed
snapshots, a unified diff, and `preview_sha256`. Inspection and preview do not create
storage. To adopt that exact review, repeat the command with
`--apply --expected-sha256 REVIEW_HASH`. The apply command is explicit authorization;
there is no additional interactive confirmation. Changed inputs or bindings require
a new review.

`update` uses the same inputs for an already attached template ID. It never tracks
the source's latest version automatically. `attach` rejects an existing ID;
`update` rejects an absent ID or unchanged snapshot. Source revision/version labels
remain declared metadata, not authenticated origin or an ordering guarantee.

```sh
mos guidance show -C /path/to/project
mos guidance detach -C /path/to/project --template-id engineering-example
```

Detach also previews first; repeat with its review hash to apply. It accepts no
source files. `show` displays the complete stored snapshots without reopening the
original files. `--json` emits one `guidance.binding` event; default output is
indented JSON. Both escape control characters in source text and paths.

## Pinned versions and isolation

By default, storage is `~/.mos-eisley-guidance`; `--guidance-storage DIRECTORY`
explicitly selects another private location. The root and files must be owner-held
with no group/other permissions; they are created with modes 0700 and 0600.
Unsafe ownership, permissive permissions, final symlinks,
hard-linked files, FIFOs, corrupt records and oversized files reject. Shared source
templates remain permitted under the inspector's existing explicit-input boundary.

Each project can bind up to eight distinct template IDs. A binding references an
immutable, content-addressed snapshot containing the full validated inspection and
directory identity. Each persisted file is bounded to 512 KiB. Rule and source
limits from the inspector still apply. Binding order is deterministic by ID and
does not imply conflict precedence.

Two projects using the same source receive independent records. A nested directory
does not inherit its parent's binding. Symlink aliases selected explicitly resolve
to the same canonical project; replacing a directory at that path fails identity
validation. Another user cannot read private bindings. Renamed/deleted project
recovery and automatic cleanup are not implemented in this slice.

Updates and detach retain older snapshots. Given a previously recorded snapshot
digest, inspect it explicitly with:

```sh
mos guidance show -C /path/to/project --snapshot-sha256 SNAPSHOT_HASH
```

Historical inspection checks the same owner and project identity. A snapshot digest
is distinct from an operation's review hash and the inner inspector snapshot hash.
The retained inspection remains marked `unbound` because it records the original
inspection; the current project record establishes attachment. Detached projects
retain an empty record with an incremented revision, preventing old review reuse.
Snapshot storage can grow with updates; retention/export/recovery controls are
future work. These files are private configuration, not published repository files.

## Publication and authority

Apply uses the existing private-storage lock, rechecks the full current record,
directory identity, immutable snapshots and source files, and atomically publishes
the updated project record after syncing the new snapshot. Concurrent changes,
changed storage identity and stale hashes reject. It validates the final revision
again inside the write lock, including an initially absent record.

A failure before project-record replacement preserves the old binding. An error
after replacement may leave the new binding saved; inspect `show` before retrying.
An interrupted operation may leave an unreferenced private snapshot or temporary
file. These are never discovered or activated automatically. Existing trusted
ancestor-directory and same-user filesystem assumptions continue to apply.

Binding grants no execution, tools, secrets, storage-selection authority, accepted
requirements or history retrieval. It does not parse links or scan the project,
load sessions, call providers, or insert guidance into conversation contexts.
Current and historical sessions remain unchanged (`context_materialized: false`).
Reviewed overrides and advisory precedence are available through
`guidance-overrides`. Semantic classification of disguised history, broader conflict
handling and frozen role provenance remain required before automatic
context materialization under [plan §16.6](mos-eisley-plan.md#166-project-specific-points-of-view-and-best-practice-templates).
