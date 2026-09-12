# Inspect a local advisory guidance template

`guidance-inspect` validates and displays an explicitly selected descriptor and
Markdown file for a workspace. This is the first project-guidance slice: inspection
does not attach guidance, accept requirements, change policy or load it into a
conversation. Trusted binding, overrides and frozen role context are subsequent work.

From a repository checkout, inspect the included example:

```sh
mos guidance-inspect \
  --descriptor templates/PROJECT_GUIDANCE_EXAMPLE.json \
  --markdown templates/PROJECT_GUIDANCE_EXAMPLE.md \
  -C . --json
```

Omit `--json` for a readable report with metadata, each rule and the complete Markdown.
Terminal control characters are escaped. The command reads only the two explicit
files and checks that the target directory exists. It creates no binding, session,
memory store or evidence file. Redirecting its output is a separate user action.

The [example descriptor](../templates/PROJECT_GUIDANCE_EXAMPLE.json) and
[Markdown](../templates/PROJECT_GUIDANCE_EXAMPLE.md) are editable project choices.
The broader [project point-of-view starter](../templates/PROJECT_POINT_OF_VIEW.md)
remains a manual document; not every section of that starter is an inspector rule.

## Descriptor contract

A descriptor contains:

| Field | Meaning |
|---|---|
| `schema_version` | `1` |
| `kind` | `advisory_project_guidance` |
| `template_id` | Stable bounded identifier |
| `version` | Explicit numeric `major.minor.patch` label; no `latest` tracking |
| `source_revision` | Declared bounded source label, such as a revision or local version |
| `content_sha256` | SHA-256 of the exact UTF-8 Markdown bytes |
| `rules` | One to 64 advisory rule records |

Each rule supplies a unique case-sensitive `id`, `kind: "advisory"`, `text`,
`applies_when`, `rationale`, and one to eight `checks`. Each exact rule text must occur
once in the Markdown, including overlapping occurrences. Missing or repeated spans
reject. Matching does not parse Markdown or normalize Unicode, case or whitespace.
The report includes the exact character offsets for every rule.

Unknown fields and duplicate JSON keys reject at every nesting level. A template
cannot declare accepted requirements, tools, storage paths, history inputs or user
identity through this schema. Advisory text can describe a command or link, but
inspection does not execute it or follow references. The source revision is a
declaration; this command does not fetch Git or authenticate an upstream origin.

Both the raw and canonical descriptor must fit 32 KiB. Markdown must fit 64 KiB of
UTF-8. Rule text is limited to 4,000 characters; applicability, rationale and each
check to 1,000. Text fields must be nonempty. Identifiers use the existing bounded
alphanumeric/dot/underscore/hyphen form, up to 80 characters. Numeric version labels
are limited to 40 characters. Read limits apply before parsing, and deeply nested
or invalid UTF-8 JSON is rejected.

## Snapshot and integrity

JSON reports `guidance.inspected`, a `snapshot_sha256`, and the complete snapshot:
owner UID derived by the inspector, canonical target workspace, explicit input
paths, exact descriptor text and digest, parsed descriptor, complete Markdown and
rule locations. Snapshot validation rechecks the raw descriptor hash, its parsed
equivalence, the Markdown hash and every location. Even descriptor-only whitespace
changes affect snapshot identity. Different owners or workspace targets produce
different identities without changing shared source files.

The snapshot is explicitly `unbound`; accepted-requirement, execution and history
loading flags are fixed false. Its digest identifies inspected bytes and metadata,
not approval to attach, execute or retrieve history. The snapshot can be revalidated
without reading its original files, which supplies a foundation for later replay.

Source files must be readable regular files. Final-component symlinks, directories,
FIFOs and oversized files reject; reads do not wait on a FIFO. Sources may be public
shared templates. These checks do not establish private binding storage or native
Windows filesystem support. Ancestor directories and the same user retain the
existing local trust boundary. The snapshot records the bytes inspected, not a
promise that files remain unchanged afterward; adoption must revalidate its inputs.

## Remaining adoption work

Trusted per-owner/project attach, show, update and detach; concrete update diffs;
independent overrides; conflict handling; accepted brief/ADR requirements; and
role-scoped materialization remain planned under [plan §16.6](mos-eisley-plan.md#166-project-specific-points-of-view-and-best-practice-templates).
Inspection does not classify arbitrary prose as safe guidance or authenticate its
claims. History disguised as Markdown cannot reach a fresh session through this
command because it has no activation or context-loading path. Later binding must
enforce the full guidance/history separation contract.
