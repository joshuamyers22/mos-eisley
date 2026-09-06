# Milestone 26 adversarial review: skill-release evidence

## Disposition implemented

Bind retained package bytes to current authenticated promotion evidence only after
recomputing both source lineages. Preserve the boundary as verification-only: no
extraction, installation, configuration mutation, or activation.

## Adversarial findings addressed

- A valid receipt can be placed beside different bytes, so the binder requires exact
  equality of the archive and promoted `SkillIdentity`.
- An internally consistent forged archive can lie about parsed instructions, so the
  archive is semantically reverified before binding.
- A copied receipt can lie about upstream success, so both complete dual-grade
  lineages and the signed decision are recomputed from independently supplied sources.
- A historically valid receipt can be stale now, so the CLI reads the host UTC clock
  and rejects the expiration boundary.
- Hash-only joins can leave the actual evidence unavailable, so the artifact embeds
  both the exact archive and authenticated receipt as well as their canonical hashes.
- Evidence readiness can be mistaken for deployment authority, so the schema can
  represent only literal-false installation, activation, and configuration fields.
- Artifact fields can be edited after creation, so verification deterministically
  rebuilds the complete binding and rejects any difference.

## Remaining limits

Host time has no external witness, and historical signature validity is not current
revocation status. Authority-policy distribution, package authorship, and local
artifact custody remain operator trust boundaries.

Milestone 27 adds authenticated release revocation, exact retained rollback
nomination, and a local monotonic anchor as a separate non-deploying gate. There is
still no external anti-rollback witness, transactional extraction/installation,
default-persona update, or post-install drift monitor. This artifact remains
disconnected from runtime until those controls are separately designed and tested.
