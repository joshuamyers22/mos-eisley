# Prompt-only skills

Mos Eisley's first skills milestone turns personas and procedures into portable,
content-addressed prompt assets. It deliberately does not add executable extensions,
tools, credentials, network access, or filesystem authority.

## Package format

A package is a directory whose name matches the required `name` in `SKILL.md`.
`SKILL.md` uses the [Agent Skills specification](https://agentskills.io/specification)
YAML frontmatter followed by Markdown instructions:

```markdown
---
name: critic-correctness
description: Hunt logic defects and incorrect error handling. Use for code review.
metadata:
  mos.version: "1"
  mos.kind: persona
---
Check correctness and cite every claim from the supplied brief.
```

The optional `mos.yaml` sidecar has only two fields in this milestone:

```yaml
version: 1
kind: persona # persona | procedure
```

If the sidecar and `metadata.mos.version` or `metadata.mos.kind` both specify a
value, they must agree. A portable `SKILL.md` with only the standard required fields
loads as an unversioned `procedure`. The standard's experimental `allowed-tools`
field is rejected because this loader has no tool-granting surface.

## Discovery and activation

Discovery reads only roots explicitly named on the command line. It never searches
the current repository, home directory, `AGENTS.md`, or configuration files. Use:

```sh
mos skills list --user-root /path/to/user/skills --json
mos skills validate --project-root /path/to/repo/.mos/skills
```

`list` exposes frontmatter and sizes, not instruction bodies. `validate` reports
structural validity only; its output includes `authority_granted: false`.

Activation requires the exact reference printed by `list`:

```text
user:critic-correctness@sha256:<64 lowercase hex characters>
```

Name-only and version-only lookup do not exist. User and project packages with the
same name are both retained and reported as shadowed; neither wins. Activating a
`project:` reference additionally requires `--allow-project`. That flag approves the
specific digest named for that invocation—it is not persistent trust and grants no
capability.

```sh
mos skills show \
  'user:critic-correctness@sha256:<digest>' \
  --user-root /path/to/user/skills
```

## Snapshot and digest rules

Discovery takes one bounded in-memory byte snapshot of the complete package.
Activation and resource reads use that snapshot, not the live filesystem. A second
inventory check rejects ordinary mutations during discovery.

The package SHA-256 is domain-separated and covers every file in sorted POSIX-path
order using length-prefixed path and content bytes. It therefore changes when the
body, sidecar, or a lazily requested reference/asset changes. It does not normalize
newlines or Markdown. Schema-2 skill identity also records the digest of the exact
activated body so a prompt asset cannot claim the package identity with different
instructions.

Limits are fail-closed: 64 root entries/skills, 128 entries and 64 files per package,
16 KB frontmatter, 32 KB body, 1 MB per resource, 4 MB per package, 16 MB per
catalog, four path levels, 1,024 YAML tokens, and 16 YAML collection levels. YAML
aliases, anchors, explicit tags, duplicate keys, symlinks, hard links, special files,
executable bits, `scripts/`, and `toolbundle` are rejected. Resource requests reject
absolute paths and traversal.

The controller and ancestors of explicitly supplied roots remain trusted, matching
the current local-file boundary. Another process with the same OS identity can race
or replace those ancestors and can rewrite a completed run manifest; this mechanism
is not a host sandbox or signature system.

## Retained package archives

One exact catalog snapshot can be serialized as a deterministic, private JSON
archive without reopening the package:

```sh
mos skills archive \
  'user:critic-correctness@sha256:<digest>' \
  --user-root /path/to/user/skills \
  --output private/critic-correctness.skill.json

mos skills verify-archive private/critic-correctness.skill.json
```

The archive retains every validated path and byte, including `SKILL.md`, `mos.yaml`,
and progressive resources. Each file has canonical base64, a byte count, and a
SHA-256 digest. The outer descriptor commits to the same domain-separated
whole-package digest used during discovery. There is no timestamp, so retaining the
same immutable snapshot produces the same canonical bytes and archive digest.

Verification never extracts files. It rechecks path, count, size, canonical order,
collision, file digest, and package digest constraints; reparses the retained
frontmatter and sidecar; and rebuilds the complete descriptor and instruction-body
digest from bytes. A project-source archive requires the same invocation-local
`--allow-project` approval as activation.

An archive is neither a package signature nor an approval. Its schema fixes
`activation_authorized`, `installation_authorized`, and
`configuration_mutation_authorized` to `false`. It proves only that these bytes
match this content identity. No extraction, materialization, install, configuration,
or activation command exists.

## Recorded review binding

The existing `review` command accepts an optional schema-1 JSON skill roster:

```json
{
  "schema_version": 1,
  "assignments": [
    {
      "critic_id": "critic-1",
      "skill": "user:critic-correctness@sha256:<digest>"
    }
  ]
}
```

The roster must cover every cassette critic exactly. Each package must be a
`persona`, and its activated instructions (the Markdown body with outer whitespace
removed) must equal the already request-bound cassette persona byte for byte. This
makes the initial integration observational: it cannot silently modify a recorded
request.

```sh
mos review --brief brief.json --cassette cassette.json \
  --skill-roster roster.json --user-skill-root /path/to/user/skills
```

Such a run uses manifest schema 2 and adds `skills.json`. Every binding records the
critic ID, source, name, version, kind, whole-package digest, instruction digest,
and instruction byte count. `events.jsonl` also contains bounded `skill.loaded`
events. Replay verifies the artifact hash and rechecks the instruction digest against
the cassette persona.

## Deliberately deferred

- automatic home/project discovery and persistent trust decisions;
- executable scripts, tool bundles, custom doctor checks, and capability requests;
- remote registries, downloads, package-author signatures, and archive stores;
- SecretRef providers and `doctor --fix`;
- replacing inline personas in live review;
- automatic promotion of persona revisions. Exact prompt-only revisions can now use
  the non-promoting [paired evaluation protocol](SKILL_EVALUATION.md), but no pass
  grants configuration or activation authority.
- transactional installation/default changes and post-install drift monitoring.
  Retained-byte binding plus independent signed revocation and rollback nomination
  are implemented as non-deploying evidence gates.

These are separate authority or evidence problems. A `SKILL.md` makes prompt assets
portable, inspectable, versionable, and measurable; it does not make their
instructions trustworthy or effective.
