# Review project overrides and effective guidance

`mos guidance-overrides` stores a reviewed advisory override profile independently
for each project's [private bindings](PROJECT_GUIDANCE_BINDING.md). Overrides can
replace or omit existing advisory rules, with an explicit reason. Shared source
templates and other projects remain unchanged.

## Profile and review

Start with [the editable example](../templates/PROJECT_GUIDANCE_OVERRIDES_EXAMPLE.json)
after attaching its matching `engineering-example` template. A profile uses this
shape:

```json
{
  "schema_version": 1,
  "kind": "advisory_project_overrides",
  "overrides": [
    {
      "template_id": "engineering-example",
      "rule_id": "ENG-001",
      "action": "omit",
      "reason": "An accepted project design documents this advisory departure.",
      "replacement": null
    }
  ]
}
```

`replace` requires a complete advisory `replacement` rule with the same ID, text,
applicability, rationale and checks as defined by the
[descriptor contract](PROJECT_GUIDANCE_INSPECTION.md). Replacement text need not
appear in the original Markdown: it is the explicitly reviewed project adjustment.
`omit` accepts no replacement and records why that advisory rule is excluded.
The reason is explanatory text; it cannot itself accept requirements or authenticate
an ADR. Every qualified `(template_id, rule_id)` must refer to an attached rule.
Duplicate or unknown rule selections reject the entire profile.

```sh
mos guidance-overrides set -C /path/to/project \
  --input templates/PROJECT_GUIDANCE_OVERRIDES_EXAMPLE.json --json
```

`set` replaces the entire project's override profile. It does not merge entries.
The preview includes complete before/after records, a unified diff, previous and
proposed effective rules, and `preview_sha256`. Repeat the command with
`--apply --expected-sha256 REVIEW_HASH` to adopt that exact review. This explicit
apply command needs no additional confirmation. A stale hash rejects.

Profiles permit 1–64 overrides, at most 64 KiB for both raw UTF-8 input and the
canonical profile. Individual replacement fields inherit the inspector's rule
bounds. Reasons are nonblank strings of at most 1,000 characters. Duplicate JSON
keys, unknown/authority-bearing fields, malformed content and unsafe source files
reject. Only the explicitly selected profile file is read; links and prose do not
choose additional inputs.

## Effective rules and changed bindings

```sh
mos guidance-overrides show -C /path/to/project
mos guidance-overrides effective -C /path/to/project --json
mos guidance-overrides clear -C /path/to/project --json
```

`show` reports the saved profile, its pinned digest, binding basis and stale status.
It does not reopen the profile source file. `effective` shows each rule's base and
effective content, whether it was omitted, and its template/override digests. Approved
project adjustments take precedence over advisory template defaults. Unmodified
rules remain visible as defaults. IDs are qualified by template, and iteration
order does not settle contradictions between different rules. Effective inspection
now includes [explicit conflict assessments](PROJECT_GUIDANCE_CONFLICTS.md), their
current/stale/unassessed status and reviewed rule exclusions.

The profile is pinned to the complete binding revision. Any attach, update or
detach makes a nonempty profile stale. `effective` then rejects instead of silently
using old adjustments or dropping them. Repeating `set` with the reviewed profile
shows the old pinned rule text and current proposed rules for explicit reapproval.
If a selected rule has disappeared, edit the profile first. Detach and reattach of
the same template cannot reactivate the old profile. A cleared profile does not
block later inspection of new template defaults.

`clear` also previews before application with its review hash. It removes all current
overrides without changing template bindings. To remove some overrides, set an
edited complete profile; to remove all, use clear. Current user direction, accepted
brief/ADR requirements and mandatory policy remain separate higher-authority layers.
This view resolves the two advisory layers and explicit reviewed conflict choices.
Automatic semantic conflict detection, conversation controls
and role-context loading are subsequent work.

## Private versions and recovery

Storage defaults to `~/.mos-eisley-guidance`, shared with the owner's private binding
store; `--guidance-storage DIRECTORY` explicitly selects another private location.
The same ownership, permissions, exact directory identity, lock and bounded-file
checks apply. Neither nested projects nor other users inherit a profile.

Every applied version has an immutable snapshot containing its exact source JSON,
parsed profile and pinned binding basis. Current records keep a revision counter
through clear/reapply. Inspect a known historical override digest with
`show --snapshot-sha256 SNAPSHOT_HASH`. Historical inspection does not restore it.
Original template versions remain available through `mos guidance show` by digest.

Publication rechecks current bindings, referenced snapshots, the old profile,
storage/project identity and exact input bytes under the write lock. The immutable
override snapshot is synced before the current profile is replaced atomically.
A failure before replacement preserves the prior profile; a later error can leave
the new version saved, so inspect `show` before retrying. Retained history and
unreferenced snapshots can accumulate; automatic retention and cleanup are future
work. Each stored file remains limited to 512 KiB. Existing trusted ancestor and
same-user filesystem assumptions still apply.

Output is escaped JSON (`guidance.overrides`), indented by default or one event with
`--json`. These commands do not execute text, grant tools or permissions, load
history, start sessions, invoke providers or materialize model context. Semantic
classification of disguised history and frozen role provenance remain required
before automatic context inclusion under [plan §16.6](mos-eisley-plan.md#166-project-specific-points-of-view-and-best-practice-templates).

[Requirement acceptance](PROJECT_REQUIREMENTS.md) and
[combined precedence review](PROJECT_GUIDANCE_PRECEDENCE.md) are separate commands.
The advisory effective view retains its original scope.
