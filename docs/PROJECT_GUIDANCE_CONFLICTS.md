# Review explicit advisory conflicts

`mos guidance-conflicts` records a project-specific assessment of explicitly
identified conflicts among attached advisory rules. Each reviewed resolution names
a preferred rule and explains the choice. The assessment is pinned to the exact
binding and override revisions. This slice records human-supplied assessments;
automatic semantic conflict detection remains future work.

## Assess and review

Start with [the editable no-known-conflicts example](../templates/PROJECT_GUIDANCE_CONFLICTS_EXAMPLE.json)
and review it against your project's actual [bindings](PROJECT_GUIDANCE_BINDING.md)
and [overrides](PROJECT_GUIDANCE_OVERRIDES.md). For a template containing `BATCH`
and `SERVICE` rules, an unresolved entry would look like:

```json
{
  "schema_version": 1,
  "kind": "advisory_conflict_assessment",
  "review_rationale": "Reviewed execution-model guidance for this project's workload.",
  "conflicts": [
    {
      "id": "ARCH-001",
      "rules": [
        {"template_id": "architecture", "rule_id": "BATCH"},
        {"template_id": "architecture", "rule_id": "SERVICE"}
      ],
      "explanation": "The two rules recommend incompatible execution models here.",
      "preferred_rule": null,
      "resolution_rationale": null
    }
  ]
}
```

The example IDs must be replaced with actual attached, non-omitted rule IDs.
To resolve an entry, set `preferred_rule` to one of its participants and provide a
nonblank `resolution_rationale`. A preferred rule cannot have lower advisory
precedence than another participant: approved project overrides rank above template
defaults. Equal-priority choices require an explicit reviewed preference. Mutually
inconsistent overlapping resolutions reject; one resolution cannot exclude another
resolution's preferred rule. Unresolved entries remain visible until explicitly
reassessed.

```sh
mos guidance-conflicts set -C /path/to/project --input assessment.json --json
```

`set` replaces the complete assessment. The read-only preview includes the full
previous and proposed records, a unified diff, and previous/proposed rule reports.
Repeat with `--apply --expected-sha256 REVIEW_HASH` to adopt the exact review.
The apply command is explicit authorization and adds no further confirmation.
Sources, current guidance, old assessment and storage/project identity are rechecked
under the private lock before atomic publication.

An assessment requires an explicit review rationale, even when `conflicts` is empty.
An empty list means the reviewer reported no known conflicts; it is not proof that
the prose is consistent. No existing assessment, or a cleared one, means unassessed.

## Inspect the result

```sh
mos guidance-conflicts show -C /path/to/project
mos guidance-conflicts effective -C /path/to/project --json
mos guidance-overrides effective -C /path/to/project --json
```

Both effective views include conflict status. `assessment_status` is `unassessed`,
`current`, or `stale`; current assessments can still contain unresolved entries.
`unresolved_conflict_ids` lists unresolved entries in the current assessment.
`stale_conflict_ids` lists entries requiring a new review after guidance changed.
`advisory_resolution_complete` is true only for a current assessment whose reported
conflicts are resolved. It makes no claim about undiscovered contradictions, policy
compliance or execution authorization.

Each rule retains `pre_conflict_rule` and `excluded_by_conflicts` provenance. A losing
rule has `effective_rule: null` and `selected: false`; the preferred rule remains
selected. Unresolved or unassessed status never becomes implicit approval. These
commands still only inspect advisory guidance; no consumer materializes model
context in this slice.

Any binding or override revision change makes a saved assessment stale, including
clear/reapply and detach/reattach. Stale choices are not applied to current rules.
Review and set a new assessment against the current basis. If the override profile
itself is stale, effective inspection rejects until the profile is reviewed or
cleared; `show` remains available with `guidance_stale: true` and no effective rules.

`clear` previews removal of the assessment and uses the same apply/hash flow. It
leaves the project unassessed, preserves bindings and overrides, and retains a
revision counter. Clear remains available when guidance has become stale.

## Private history, limits and authority

Storage uses the same private owner directory as bindings and overrides, normally
`~/.mos-eisley-guidance`; `--guidance-storage DIRECTORY` explicitly selects another
private location. Exact workspace/device/inode identity, private permissions,
non-symlink single-link regular files and bounded reads are required. Two projects,
nested directories and different users do not share assessments automatically.

The raw UTF-8 input and canonical assessment are each limited to 64 KiB. An assessment
has at most 64 conflicts, each with 2–8 distinct qualified rules; explanations,
rationales and the overall review rationale are nonblank and at most 1,000 characters.
Duplicate conflict IDs or participant groups, unknown/omitted rules, inconsistent
choices, duplicate JSON keys and authority-bearing fields reject. Persisted records
are bounded to 512 KiB. Only the selected input and referenced private snapshots are
read; assessment prose cannot choose paths, execute text or recursively load links.

Every applied version retains its exact source, parsed assessment, binding/override
basis and content-addressed snapshot. Inspect a known historical digest with
`show --snapshot-sha256 SNAPSHOT_HASH`. It is labeled `historical`, reports no current
resolution completion, and exposes its original result separately in `pinned_report`.
Historical inspection never restores a choice. Input source files are not reopened
for ordinary show/effective/history inspection.

Output is escaped JSON (`guidance.conflicts`), indented by default or one event with
`--json`; the existing override command retains its `guidance.overrides` event type.

Publication syncs the immutable snapshot before replacing the current record.
Pre-publication failure preserves the prior record; a later error may leave the new
version saved, so inspect before retrying. Interrupted writes can leave private
unreferenced snapshots or temporary files. Retention, cleanup and relocated-project
recovery remain future work; existing trusted-ancestor/same-user filesystem
assumptions continue to apply.

Conflict entries address advisory rules only. They cannot identify a template label
as mandatory policy, accept brief/ADR requirements, grant tools or permissions, load
history, start sessions, call providers or modify existing runs. Accepted-requirement
and trusted-policy integration, automatic semantic analysis and frozen role context
remain subsequent work under [plan §16.6](mos-eisley-plan.md#166-project-specific-points-of-view-and-best-practice-templates).

For accepted requirements together with advisory guidance, use
[combined review](PROJECT_GUIDANCE_PRECEDENCE.md). This advisory-only assessment
cannot establish completion for that expanded scope.
