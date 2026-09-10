# Milestone 29 adversarial review: skill installation authorization

## Disposition implemented

Authorize only one exact, latest-controlled quarantined package for one pinned inert
target using an evaluation-independent Ed25519 signer. Require durable at-most-once
claiming under a release-control guard, but stop before installation, default changes,
runtime activation, or automatic recovery.

## Adversarial findings addressed

| Attack or ambiguity | Disposition | Remaining limit |
|---|---|---|
| A valid signature authorizes a nearby package or arbitrary destination | Decision binds the exact staging manifest, archive, source-qualified persona, action, store policy, and installation-target identity | The target is an opaque policy identity until the installer/store schema lands |
| An evaluator or release controller approves its own install | Installer authority IDs and keys must be disjoint from both split graders/resolvers, promotion authorities, and release controllers | Declarations cannot prove organizational independence or prevent collusion |
| Authorization outlives promotion or release control | Decision lifetime is capped by installation policy, release evidence, and current control; authentication uses the host clock | No trusted external clock exists |
| An older allowed state is used after revocation | Derivation and authentication require the exact latest anchored entry; guarded consumption holds that anchor read transaction through future caller commit | Whole-database replacement or rollback remains owner-controlled |
| One signed decision is reauthenticated or replayed | It binds one claim-store identity; guarded consumption keys uniqueness on the signed decision digest and retains the exact authenticated receipt before side effects | Store deletion, rollback, and cloning need an external monotonic witness |
| A crash is treated as safe to retry | The claim is durably burned before yielding and is never refunded on caller failure | Recovery requires a new authorization; no completed-install receipt exists yet |
| “Authorized” is reported as “installed” or “active” | Receipt and claim record `installation_performed: false`; activation/configuration remain literal false; no consume CLI or runtime reader exists | The next installer must preserve these distinctions in its transaction states |

## Stop condition

This milestone stops at signed permission plus a guarded at-most-once substrate. It
does not materialize an installed store, mutate a default-persona pointer, recover an
interrupted installation, expose a runtime lookup, or monitor post-install drift.
