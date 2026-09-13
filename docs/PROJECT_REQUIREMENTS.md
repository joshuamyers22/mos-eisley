# Reviewed project requirements

`mos requirements set|show|clear` accepts an explicitly reviewed set of requirements
from local project briefs or ADRs. A preview shows the complete previous/proposed
record and diff, including the source files, selected passages, applicability,
rationale and checks. Acceptance is private to the current OS user and exact project
directory identity. Opening a repository or attaching advisory guidance does not
accept its requirements.

## Review and accept

Start with the [selection example](../templates/PROJECT_REQUIREMENTS_EXAMPLE.json)
and its [brief](../templates/PROJECT_REQUIREMENTS_BRIEF.md). Edit both for the project
and update the source's SHA-256 after any byte change. Pass one explicit `--source`
path for each declared source, in the same order:

```sh
mos requirements set -C /path/to/project \
  --input /path/to/selection.json --source /path/to/brief.md --json
```

Review the complete output. Repeat the same command with
`--apply --expected-sha256 REVIEW_HASH`, using its `preview_sha256`. Only successful
apply makes the proposed set current. `set` replaces the **entire** accepted set;
include every requirement and source that should remain accepted. Stable IDs identify
requirements within a project; source hashes and the record revision identify the
accepted version. Each text must match one unique exact passage in its declared
source. The full source is retained, so that passage and its context remain reviewable.

The source `kind` (`brief` or `adr`) is a user-declared provenance label, not an
authentication claim. Requirement selections cannot declare themselves mandatory or
grant authority. Source paths come only from explicit CLI arguments; JSON and source
links are never followed to read more files. Relative paths use the process working
directory; `-C` selects the project receiving the acceptance. Selected inputs may
live outside that directory. They are not discovered recursively or fetched remotely.

## Inspect, replace and clear

```sh
mos requirements show -C /path/to/project --json
mos requirements show -C /path/to/project --snapshot-sha256 SNAPSHOT_HASH --json
mos requirements clear -C /path/to/project --json
```

Clear is also a preview; apply it with its reviewed hash. It preserves a revision
tombstone and immutable history, preventing old reviews from being replayed after
clear/reaccept. Historical output always sets `accepted_current` to false, including
an archived proposal whose current-record publication failed. History is evidence of
retained content, not proof that a candidate became current. Source edits or deletion
after acceptance do not change the pinned requirements; replace the set to accept
new content. Historical inspection requires no access to the original source files.

## Storage and limits

The default is `~/.mos-eisley-guidance`; use `--guidance-storage` to select another
private owner-held root. Requirement records have their own filenames and use the
existing guidance lock and guarded file publication. Previews do not create storage.
Apply rejects changed inputs, prior records or storage/project identity. Current
records must match their immutable snapshots. Final-component symlinks, special
files, unsafe private-file permissions and cross-owner/project snapshots reject.
Input ancestors and the same OS user remain part of the trusted filesystem boundary.

Selections allow 1–64 requirements, 1–8 explicitly selected sources, 64 KiB raw and
canonical selection JSON, 64 KiB per UTF-8 source, 128 KiB combined source bytes,
and 512 KiB canonical saved records. Limits are byte-based as well as field-bounded.
Malformed JSON, duplicate keys/IDs, ambiguous passages and mismatched hashes reject.
All retained source text is private local data; avoid including unrelated secrets.

Publication archives and syncs the candidate before replacing the current record.
A failure after replacement can leave the new version saved: inspect before retrying.
Interrupted writes may leave unreferenced private snapshots. Clear is not secure
erasure; history retention and relocation/recovery are subsequent work. Reverting
this additive feature leaves guidance, memory and session records intact.

## Integration boundary

This implements acceptance and provenance in [plan §16.6](mos-eisley-plan.md).
Accepted requirements are separate from [advisory overrides](PROJECT_GUIDANCE_OVERRIDES.md)
and [advisory conflict assessments](PROJECT_GUIDANCE_CONFLICTS.md). Their existing
effective views assess advisory rules only; they do not claim to reconcile accepted
requirements or trusted policy. This command does not load model/role contexts,
change permissions, execute source prose or retrieve conversation history.

[Combined precedence and conflict review](PROJECT_GUIDANCE_PRECEDENCE.md) now pins
these accepted revisions, exposes unresolved requirement contradictions and invalidates
combined assessments after requirements change. Existing advisory assessments cannot
establish completion for the expanded scope. [Owner policy checks](PROJECT_GUIDANCE_POLICY.md)
now evaluate explicit private selection prohibitions. Broader runtime/user/admin policy
integration and role context materialization remain subsequent work.
