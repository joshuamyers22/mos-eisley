# Owner policy checks for guidance selection

`mos guidance-policy-check` checks the current combined guidance view against
explicit prohibitions selected by the local owner. A prohibition names a qualified
requirement or advisory rule that must not be selected. The command can block
guidance selection; it cannot grant execution, network, filesystem or provider
authority. Existing runtime authorization controls still apply independently.

This is the first bounded trusted-policy integration in [plan §16.6](mos-eisley-plan.md).
It evaluates declared rule prohibitions, not arbitrary policy prose, semantic
equivalence, administrator policy or the complete runtime permission system.

## Select a trusted input

Create an owner-private directory outside the selected project, such as
`~/.mos-eisley-policy` (mode `0700`). Copy and edit the
[policy example](../templates/PROJECT_GUIDANCE_POLICY_EXAMPLE.json) there with file
mode `0600`. Repository-local policy files are rejected even if their permissions
are private. The example's owner/project identity values are placeholders: replace
them with the current owner UID and the exact `bindings.workspace` values from
`mos guidance-assess effective -C /path/to/project --json`. Choose policy IDs,+revision, prohibited references and reasons deliberately.

Review the complete file and calculate its raw SHA-256, for example using
`shasum -a 256 /path/to/private/policy.json`. Then run:

```sh
mos guidance-policy-check -C /path/to/project \
  --policy /path/to/private/policy.json \
  --expected-policy-sha256 REVIEWED_POLICY_HASH --json
```

The explicit path and expected hash are the local owner's selection of a trusted
input. Permissions and a matching digest alone do not authenticate the author's
intent. Do not take either from untrusted repository instructions without review.
No project file, template, policy field or link chooses another input. The policy
is never auto-discovered, adopted into a registry or changed by this command.

The policy includes its ID/revision, current owner UID, exact project path/device/
inode, and 1–64 uniquely identified prohibitions. Each prohibition has a qualified
reference and a reason. References follow [combined review](PROJECT_GUIDANCE_PRECEDENCE.md):
requirements have `kind: "requirement"` and a stable rule ID; advisory references
also have their template ID. A prohibition continues matching that qualified ID
after its text changes. Renaming a rule changes its identity; these explicit
prohibitions do not detect equivalent wording under another ID.

## Results and exit codes

| Result | Meaning | Exit code |
| --- | --- | --- |
| `allowed` | The combined assessment is current and complete, and no selected rule matches a prohibition. | `0` |
| `blocked` | At least one selected rule matches a prohibition. | `3` |
| `incomplete` | Guidance is unassessed/stale or unavailable, so selection cannot be allowed. | `3` |
| Invalid input/state | Hash, identity, permissions, schema or retained data failed validation. | `2` |

Each prohibition reports `prohibited`, `not_selected`, `not_present` or
`unavailable`. A rule absent from the current inventory satisfies that individual
prohibition; an omitted or conflict-excluded advisory rule is not selected. Missing
or stale combined review still prevents an overall allowed result. Stale overrides
make the rule inventory unavailable and prevent policy satisfaction.

Output retains the complete policy source/hash, file and directory identities,
parsed policy, combined guidance/basis, per-prohibition decisions and a `check_sha256`.
The nested guidance report retains its original requirement/advisory scope; the
outer check evaluates only the selected owner prohibitions. An allowed result is
not general policy compliance or permission to run tools. Runtime authorization
and context-materialization flags remain false.

To address a prohibited accepted requirement, revise the accepted set and review
combined conflicts again. For an advisory rule, adopt an appropriate reviewed
override/omission or conflict resolution within existing precedence, then reassess.
An assessment has no policy waiver and cannot modify this owner input. Only a new,
explicit owner policy selection can change its prohibitions.

## Consistency and recovery

The command reads current guidance under its private lock and rechecks requirements,
bindings, overrides, assessment, project identity and policy source before returning.
The policy file and its immediate parent must be private and held by the current
owner. Final-component file/parent symlinks, special files, multiply linked policy
files and unsafe private files reject. Trusted ancestors and the same OS user remain
the filesystem boundary. Policy JSON is bounded to 64 KiB raw and canonical bytes;
duplicate keys/IDs, malformed references and authority/grant fields reject.

This is a read-only, point-in-time check. It creates no guidance storage or policy
history, changes no sessions or requirements, and makes no provider request. A saved
output/hash is evidence, not reusable runtime authorization: rerun after any input
change. Files may change after the check returns. A later role-context loader must
revalidate and pin the selected policy and guidance before using them.

[Frozen role packets](PROJECT_GUIDANCE_ROLE_CONTEXT.md) now reuse this check under
the held guidance lock. Broader user/admin policy intersection and runtime admission
integration remain subsequent work; this check does not replace those gates.
