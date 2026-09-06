# One-use skill installation authorization

Mos Eisley can authenticate an independent, expiring Ed25519 decision authorizing one
exact quarantined persona package for one inert installation target. This grants a
narrow installation permission, but it does not install files, change a default, add a
runtime search path, or activate prompt content.

## Bound authority

The reviewed authority policy pins:

- the exact quarantine-store and release-control-anchor policies;
- one private claim-store identity and one installation-target identity;
- a bounded policy window and maximum decision lifetime; and
- sorted unique installation signers.

Every installation signer identity and public key must differ from all release-control
and promotion authorities, graders, and resolvers in both evidence splits. As with the
other signed gates, independently distribute and review the public-key policy; the CLI
never accepts private signing material.

Derive canonical bytes for external signing:

```sh
mos eval-derive-skill-installation \
  --action rollback \
  --authenticated-control private/authenticated-release-control.json \
  --control-anchor private/release-control.sqlite \
  --staging-store private/skill-staging \
  --installation-authority-policy trusted/installation-authorities.json \
  --issued-at 2026-09-06T16:00:00Z \
  --valid-until 2026-09-06T16:05:00Z \
  --output private/installation-decision.json \
  ...the complete release-evidence and calibration/holdout inputs...
```

The decision binds the full upstream lineage plus the exact staging manifest, archive,
source-qualified skill identity, candidate/rollback action, signed release control,
latest anchor entry, claim-store identity, target identity, and time window.

After an external authority signs those canonical bytes, authenticate them using the
host clock:

```sh
mos eval-authenticate-skill-installation \
  --signed-installation trusted/signed-installation.json \
  --action rollback \
  --authenticated-control private/authenticated-release-control.json \
  --control-anchor private/release-control.sqlite \
  --staging-store private/skill-staging \
  --installation-authority-policy trusted/installation-authorities.json \
  --output private/installation-authorization.json \
  ...the complete release-evidence and calibration/holdout inputs...
```

Authentication reconstructs the signable decision, rechecks every staged byte, and
requires the same control entry still to be latest. The resulting receipt has
`installation_authorized: true`, `one_use_required: true`, and
`installation_performed: false`; activation and configuration mutation remain false.

## At-most-once claim store

Create and inspect the private ledger from exact reviewed policies:

```sh
mos skill-installation-claim-store-create private/install-claims.sqlite \
  --store-policy trusted/install-claim-store-policy.json \
  --installation-authority-policy trusted/installation-authorities.json

mos skill-installation-claim-store-status \
  --store private/install-claims.sqlite \
  --installation-authority-policy trusted/installation-authorities.json
```

The standalone authority layer still exposes no unguarded consume command. The
[atomic inert installer](SKILL_ATOMIC_INSTALLATION.md) calls the guarded library
primitive immediately around its commit. That primitive reverifies all
sources, holds a latest-control SQLite read transaction, and durably consumes the
signed decision digest while retaining the exact authenticated receipt before yielding.
Re-authenticating the same signature therefore cannot create another use. A concurrent
revocation cannot commit during the
installer's critical section, and an exception never refunds ambiguous authority.

## Remaining boundary

The installation target now has a private content-addressed inert package layout and
completion manifest, but still has no atomic default pointer, uninstaller, automatic
recovery, runtime consumer, or drift monitor. Owner-driven deletion, rollback, or
cloning of the claim store or control anchor can defeat local at-most-once and freshness
guarantees; an external monotonic witness remains necessary for that threat model.
