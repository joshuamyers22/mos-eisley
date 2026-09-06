# Milestone 30 adversarial review: atomic inert skill installation

## Disposition implemented

Consume one exact signed decision and durably materialize its verified quarantine bytes
under both a latest-release-control guard and a private installed-store lock. Record
enough canonical evidence to distinguish crash states, but perform no automatic recovery,
default mutation, runtime lookup, or activation.

## Adversarial findings addressed

| Attack or ambiguity | Disposition | Remaining limit |
|---|---|---|
| Installed bytes differ from the authorized quarantine package | Preserve authorization, claim, staging manifest, and intent; reconstruct every payload byte and semantic descriptor before commit | Upstream public-key policy distribution and package authorship remain trusted externally |
| A revocation commits between claim and installation | Hold the release-control read transaction from final reverification through the installed-store atomic rename and fsync | Whole-anchor replacement/rollback and external delivery remain outside the local lock |
| Concurrent installers overwrite content or exceed limits | Owner-private file lock serializes the second inventory check, bounded transaction creation, and no-overwrite content-addressed commit | Same-UID lock/path replacement can cause denial or bypass without stronger OS isolation |
| A crash exposes partial content as installed | Completion manifest is written last; full verification and fsync precede atomic rename from a separate transaction directory | Filesystem/hardware durability semantics remain trusted |
| A failed attempt silently reuses permission | Signed decision is consumed before writes and never refunded; the installer rejects an existing digest before claim when visible | Races and failures after consumption require a newly signed decision |
| Recovery guesses or mutates ambiguous state | Read-only correlation reports completed, incomplete, claim-only, and unbound transactions from exact claims/manifests | Operators must investigate; no retry, cleanup, finalization, or liveness proof exists |
| Installed is confused with active | Manifests/results distinguish `installation_performed: true` from literal false default, configuration, runtime, and activation fields; no runtime reader exists | A later default-selection layer must keep this separation explicit |

## Stop condition

This milestone stops at inert installed bytes and read-only recovery evidence. It does
not select a default persona, expose installed bytes to a model request, automatically
change configuration, recover or clean up, uninstall packages, or monitor drift.
