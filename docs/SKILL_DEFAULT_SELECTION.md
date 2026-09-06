# Atomic skill default selection

Mos Eisley can independently authorize and atomically select one exact installed
persona package as its inert default. The selection changes only a private control-plane
pointer. No shipped runtime reads that pointer, no prompt is changed, and no activation
or model request occurs.

## Authority and state binding

`SkillDefaultAuthorityPolicy` enrolls separate Ed25519 public keys and pins the exact:

- installed-store and historical installation-authority policies;
- latest skill-release control anchor policy;
- private default-store identity and decision lifetime;
- narrow authority to mutate only the default pointer.

Default signers must be disjoint by identity and key from evaluators, resolvers,
promoters, release controllers, and installers. A signable decision binds the installed
manifest and historical installation authorization, current release-control entry,
candidate or rollback action, archive and persona identity, next sequence, exact prior
pointer digest, store identity, and bounded UTC window. Any intervening pointer change
or release-control advance makes it stale.

## Commands

Create the private atomic pointer store:

```sh
mos skill-default-store-create private/skill-default.sqlite \
  --store-policy trusted/default-store-policy.json \
  --default-authority-policy trusted/default-authorities.json \
  --installed-store private/installed-skills
```

Derive an exact decision for external signing, authenticate the returned signed
decision, and apply it:

```sh
mos eval-derive-skill-default \
  --action rollback \
  --installed-store private/installed-skills \
  --installation-authority-policy trusted/installation-authorities.json \
  --default-store private/skill-default.sqlite \
  --default-authority-policy trusted/default-authorities.json \
  --issued-at 2026-09-06T17:00:00+00:00 \
  --valid-until 2026-09-06T17:05:00+00:00 \
  --output private/default-decision.json \
  ...the complete release-control and evaluation lineage...

mos eval-authenticate-skill-default \
  --signed-default private/signed-default.json \
  --output private/default-authorization.json \
  ...the same bound inputs...

mos eval-select-skill-default \
  --authenticated-default private/default-authorization.json \
  --output private/default-result.json \
  ...the same bound inputs...
```

## Atomicity and recovery

The default store uses an owner-private SQLite database with rollback journaling and
`synchronous=EXTRA`. One `BEGIN IMMEDIATE` transaction verifies the complete immutable
revision chain, expected previous pointer, exact installed package, state-bound signed
decision, signed count/aggregate-byte capacity limits, and one-use decision digest. It
inserts the immutable selection record and changes the singleton current pointer in the
same commit.

A failure before commit leaves neither consumption nor a pointer mutation, so the exact
authorization may be retried while it remains current. A commit whose result is
ambiguous is resolved by read-only status inspection; a committed decision cannot be
replayed. Inspect and fully reverify the chain with:

```sh
mos skill-default-store-status \
  --store private/skill-default.sqlite \
  --default-authority-policy trusted/default-authorities.json \
  --installed-store private/installed-skills \
  --installation-authority-policy trusted/installation-authorities.json
```

## Remaining boundary

The pointer is durable configuration evidence, not runtime activation. All contracts
and events deny other configuration changes, runtime lookup, and activation. There is
no runtime reader, automatic uninstallation, post-selection health check, drift monitor,
or external monotonic witness. The owning OS user can still roll back or clone the local
database and control stores; stronger isolation or external witness state is required
for that threat model.
