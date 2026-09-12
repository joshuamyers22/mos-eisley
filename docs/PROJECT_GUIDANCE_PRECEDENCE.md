# Combined requirement and advisory review

`mos guidance-assess set|clear|show|effective` reviews the combined inventory of
[accepted requirements](PROJECT_REQUIREMENTS.md), approved advisory overrides and
attached advisory defaults. Each assessment pins the exact requirement, binding and
override revisions. This is explicit conflict review; it does not automatically
detect semantic contradictions or evaluate trusted policy.

## Inspect and review

```sh
mos guidance-assess effective -C /path/to/project --json
mos guidance-assess set -C /path/to/project --input /path/to/assessment.json --json
```

Effective inspection lists qualified references, source/snapshot provenance, original
and selected text, omissions and conflict exclusions. Requirement provenance includes
the accepted snapshot hash, brief/ADR hash, selected path and exact character span;
the complete source text remains in the pinned requirement record. Nothing is loaded
into a model or role context by inspection.

Start with the [assessment example](../templates/PROJECT_GUIDANCE_ASSESSMENT_EXAMPLE.json).
Edit its review rationale and conflicts for the current inventory. A conflict uses
2–8 distinct references. Requirement references have `kind: "requirement"`, a
`rule_id`, and no template ID. Advisory references have `kind: "advisory"`, a
`rule_id` and `template_id`. For example, an entry could contain:

```json
{
  "id": "EXECUTION",
  "rules": [
    {"kind": "requirement", "rule_id": "REQ1"},
    {"kind": "advisory", "template_id": "engineering", "rule_id": "ENG1"}
  ],
  "explanation": "The accepted batch requirement conflicts with this service preference.",
  "preferred_rule": {"kind": "requirement", "rule_id": "REQ1"},
  "resolution_rationale": "The accepted project requirement takes precedence."
}
```

The example references must exist in the selected project's inventory. Omit both
preference and resolution rationale to record an unresolved conflict. After reviewing
the complete previous/proposed records, diff and reports, repeat `set` with
`--apply --expected-sha256 REVIEW_HASH`. `set` replaces the entire assessment.
Unknown/omitted participants and inconsistent overlapping winners reject.

## Precedence and incomplete review

Accepted project requirements rank above approved project overrides, which rank
above advisory defaults. A preferred participant cannot have lower priority than
another participant. Two contradictory accepted requirements cannot be resolved by
silently excluding one in this command: they remain unresolved until the user
revises the accepted requirement set and reviews conflicts again. This operation
does not change the requirement acceptance record.

Unassessed or stale output has `project_resolution_complete: false`. Explicitly
unresolved entries also keep completion false. A reviewed empty conflict list says
only that the reviewer reported no conflicts. Completion is scoped to the explicit
assessment of requirements and advisory guidance; it is not a proof of semantic
consistency, permission to execute, or trusted-policy compliance.

Changes to requirements, bindings or overrides invalidate the combined assessment,
including clear/reaccept of identical text. Stale choices stop excluding rules;
prior conflicts remain visible as stale IDs. Stale overrides block effective
inspection and fresh assessment until the override profile is reviewed or cleared.

[Advisory-only assessments](PROJECT_GUIDANCE_CONFLICTS.md) remain available through
their existing commands, with their original scope. Their choices are not silently
imported into combined review, and they cannot establish combined completion. Include
all relevant advisory-only conflicts and choices in the new assessment explicitly.
Changing an advisory-only assessment does not change this independent combined
assessment; binding and override changes still invalidate both.

## History, storage and recovery

`show --snapshot-sha256 HASH` exposes the retained basis and its `pinned_report`.
Historical output always has `assessment_status: "historical"`, no current rules
and false current completion. An archived candidate can exist even when publishing
it as current failed. `clear` requires the same reviewed apply flow, leaves a revision
tombstone and returns the project to unassessed status. It preserves requirements,
guidance, project files and historical records.

Combined records use their own `assessment-` filenames in the private guidance root
(`~/.mos-eisley-guidance`, or `--guidance-storage`). Existing binding, override and
advisory-assessment schemas remain compatible. Reads and publication share the
owner-held lock; apply rechecks all three inputs and their private files under that
lock. Exact project identity, bounded private regular files, canonical records,
immutable snapshots and guarded atomic replacement follow the existing guidance
storage contract. Previews do not create storage.

Assessments allow 64 conflicts, 64 KiB raw/canonical JSON and 512 KiB canonical saved
records including the basis. A large requirement/override basis can reach the saved
record limit before the input limit. Interrupted writes may leave unreferenced
snapshots; failure after replacement can leave the new version saved, so inspect
before retrying. Clear is not erasure. Retention and relocation recovery remain
subsequent work; trusted ancestors and the same OS user remain the filesystem boundary.

[Owner policy checks](PROJECT_GUIDANCE_POLICY.md) now evaluate explicitly selected
private prohibitions against this combined view. Broader runtime/user/admin policy
integration remain subsequent work. [Frozen role packets](PROJECT_GUIDANCE_ROLE_CONTEXT.md)
now materialize explicitly relevant rules with retained provenance; runtime loading remains later work.
No assessment can grant tools, select secrets, relax containment, execute source prose
or retrieve conversation history.
