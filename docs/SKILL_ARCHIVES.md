# Deterministic retained skill-package archives

Mos Eisley can retain every byte of one validated, digest-pinned skill snapshot in
a canonical JSON contract. This closes an evidence-retention gap: a later verifier
does not need the mutable source directory to recover the exact package that was
evaluated. It does not create an installation mechanism.

## Retain an immutable snapshot

First discover the exact reference, then archive it from the same catalog snapshot:

```sh
mos skills list --user-root /path/to/skills
mos skills archive \
  'user:critic-correctness@sha256:<package-digest>' \
  --user-root /path/to/skills \
  --output private/critic-correctness.skill.json
```

The command writes a private file with mode `0600`. A `project:` reference requires
`--allow-project`; that approval applies only to this invocation and exact digest.
The package is not reopened after discovery. Each archive contains:

- the complete `SkillDescriptor` and `SkillIdentity`;
- every validated file in canonical sorted POSIX-path order;
- canonical base64 plus byte count and SHA-256 for each file;
- the same domain-separated whole-package digest used by discovery; and
- literal false values for installation, activation, and configuration mutation.

The contract has no creation timestamp, random identifier, or host path. Archiving
the same snapshot therefore yields the same canonical bytes and `archive_sha256`.

## Verify without extraction

```sh
mos skills verify-archive private/critic-correctness.skill.json
```

This command needs no discovery roots and never writes package contents. Contract
validation rejects oversized or noncanonical base64, unsafe paths, the reserved
`scripts/` subtree, traversal, path collisions, duplicate or unsorted paths, missing `SKILL.md`,
incorrect sizes, and changed file or package digests. The verifier then parses
`SKILL.md` and `mos.yaml` with the same bounded strict-YAML rules as discovery and
rebuilds the exact name, version, kind, description, license, compatibility, byte
counts, package digest, and normalized instruction-body digest. Any difference from
the archived descriptor fails closed.

The existing package limits remain in force: 64 files, 1 MB per resource, 4 MB total,
64 KB for `SKILL.md`, 16 KB for `mos.yaml`, four path levels, 16 KB frontmatter,
32 KB body, and bounded YAML structure.

## Security boundary

An archive authenticates internal consistency only: these retained bytes produce
this content identity. It does not authenticate an author, prove prompt safety or
quality, establish when the package existed, or show that a promotion receipt is
current. Anyone who can replace both an archive and the expected digest can replace
the evidence.

There is intentionally no extraction, materialization, installation, configuration,
or activation command. Archives are not yet linked to signed promotion receipts,
revocation state, rollback targets, or drift monitors. Those must be implemented as
separate gates before a promoted persona can change a default or reach runtime.
