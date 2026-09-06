# Authenticated skill-release control

Mos Eisley can now authenticate an independent, expiring decision that either allows
or revokes one exact `SkillReleaseEvidence` artifact. A revoked decision may nominate
one exact retained archive for rollback. This is release-control evidence only: it
cannot extract, install, activate, or change configuration.

## Control flow

1. `eval-derive-skill-release-control` reverifies the release artifact, retained
   archive, signed promotion, and both complete evaluation lineages. It emits the
   only signable decision for the selected sequence, disposition, UTC window, and
   optional rollback archive.
2. An external authority signs that canonical decision with
   `sign_skill_release_control`. No CLI command accepts a private key.
3. `eval-authenticate-skill-release-control` uses the host UTC clock, repeats the
   complete recomputation, verifies authority independence and the domain-separated
   Ed25519 signature, and writes a private authenticated receipt.
4. The three `skill-release-control-anchor-*` commands create, advance, and inspect
   a private append-only SQLite anchor scoped to the exact release-evidence digest.

The derive and authenticate commands take the same dataset, plan, calibration and
holdout lineages, comparison artifacts, promotion receipt/policy, retained archive,
release evidence, and control-authority policy used by the preceding gates.
`--rollback-archive` is optional for a revoked decision and forbidden for an allowed
decision. Derivation additionally requires `--sequence`, `--disposition`,
`--issued-at`, and `--valid-until`; authentication instead requires
`--signed-control` and uses the host clock.

## Exact rollback nomination

A rollback target is embedded in the authenticated receipt as complete retained
bytes and signed by its canonical archive digest and `SkillIdentity`. It must be a
different package for the same source-qualified persona-skill name. The verifier
reparses its exact bytes and rebuilds semantic metadata. A nearby version label,
same-name package, or substituted archive is rejected.

Nomination is not execution. The archive continues to carry literal-false
installation, activation, and configuration-mutation fields. There is no extraction
path or default-persona update in this milestone.

## Independent authority and freshness

Every authority ID and public key in the release-control policy must be disjoint from
the promotion authorities and all calibration/holdout graders and resolvers. The
decision binds the exact trust-policy digest, release-evidence digest, current archive
digest, candidate identity, sequence, disposition, optional rollback target, and
bounded UTC window. Authentication rejects the expiration boundary.

## Monotonic local anchor

An anchor policy pins:

- one anchor identity and exact release-evidence digest;
- the exact control-authority policy digest and allowed signer IDs; and
- a minimum bootstrap sequence.

Each entry is canonical, hash-linked to its predecessor, and fully signature-checked
when the chain is read. Sequence and issue time must increase. Once an entry revokes
the scoped release, no later entry may return it to `allowed`. Consumers must require
the exact latest anchored signed state; a sequence field without this state is not
anti-replay protection.

## Remaining boundary

The local anchor is private and fsynced, but an owner who can replace or restore the
whole database and its expected policy can clone or roll it back. Bootstrap and the
host clock have no external witness. Authority enrollment, key custody, organizational
independence, package authorship, and the judgment that selected rollback bytes are
safe remain external responsibilities.

The follow-on [quarantine-staging gate](SKILL_QUARANTINE_STAGING.md) can now
transactionally materialize exact latest-controlled bytes without installing them.
There is still no signed installation authority, atomic default change, automatic
recovery, post-install validation, or drift-triggered rollback. Any future installer
must consume the verified staging manifest and preserve exact latest-anchor equality
inside its own one-use configuration transaction.
