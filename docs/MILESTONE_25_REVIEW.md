# Milestone 25 adversarial review: retained skill archives

## Disposition implemented

Retain one exact immutable prompt-skill snapshot in a deterministic contract and
semantically verify it without extraction. Keep package storage entirely separated
from installation, configuration, activation, and signed promotion readiness.

## Adversarial findings addressed

- Reopening a package during archival creates a validation-to-use race, so retention
  serializes only the loader's immutable byte snapshot.
- A package hash alone cannot recover evidence, so the archive includes every exact
  validated file byte and path.
- Per-file hashes alone permit omission or reordering ambiguity, so the existing
  domain-separated digest commits to sorted, length-prefixed paths and contents.
- An outer checksum can be recomputed over forged metadata, so verification reparses
  retained control files and rebuilds the complete descriptor and instruction digest.
- An archive could smuggle a future executable surface, so paths remain bounded and
  traversal, collisions, and `scripts/` are rejected; no extraction API exists.
- Project content must not gain trust through retention, so a `project:` reference
  still needs explicit invocation-local approval.
- Evidence retention can be mistaken for deployment approval, so three literal-false
  fields deny installation, activation, and configuration mutation in every archive.
- Timestamps make identical evidence nondeterministic and imply chronology without a
  trusted clock, so the archive has no timestamp and makes no existence-time claim.

## Remaining limits

The archive proves internal content identity, not authorship, provenance, prompt
safety, or quality. A malicious owner can replace both the archive and any locally
stored expected digest. File modes are not retained because no materialization path
exists; the source loader rejects executable bits before snapshotting.

Most importantly, archives are not yet bound to still-valid signed promotion
receipts. There is no revocation anchor, rollback selection, atomic installer,
default-persona transaction, or post-install drift monitor. Runtime and configuration
authority therefore remain unavailable.
