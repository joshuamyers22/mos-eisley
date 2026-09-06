# Monotonic routing-control anchor and runtime preflight

Mos Eisley maintains a private append-only SQLite anchor for signed routing-control
states and can perform a short-lived, read-only preflight against its latest entry.
Neither operation routes traffic, installs configuration, opens provider connections,
or grants dispatch authority.

The pre-registered `RoutingControlAnchorPolicy` fixes:

- an operator-generated unique anchor identity;
- the exact activation-authority-policy digest; and
- the enrolled identities allowed to sign control state, rather than allowing every
  activation authority to perform that role.

Its digest is pinned into the separately signed activation policy and copied into the
activation-eligibility receipt. Create the private database from that exact policy:

```console
mos routing-control-anchor-create private/control.sqlite \
  --anchor-policy trusted/control-anchor-policy.json \
  --activation-authority-policy trusted/activation-authorities.json
```

After a control authority signs a current state outside the CLI, advance the anchor:

```console
mos routing-control-anchor-advance \
  --anchor private/control.sqlite \
  --activation-authority-policy trusted/activation-authorities.json \
  --signed-control-state trusted/signed-control-state.json
```

Every update must have a strictly greater sequence and issuance time. It is
hash-linked to the prior entry, and candidate-policy and promotion-receipt revocation
sets may only grow. The anchor accepts an emergency stop and permits a later enrolled
control signer to clear it; consumers still reject a currently stopped state. Status
inspection reverifies the complete chain and every signature:

```console
mos routing-control-anchor-status \
  --anchor private/control.sqlite \
  --activation-authority-policy trusted/activation-authorities.json
```

The runtime preflight reverifies the entire calibration, holdout, promotion, and
activation-eligibility chain. It then requires the supplied signed control state to
equal the latest anchored entry and requires the anchor policy to equal the policy
pinned by the activation signer. The result expires at the earliest existing deadline
or the activation policy's signed `max_runtime_preflight_age_seconds` limit, which is
at most 300 seconds.

```console
mos eval-routing-runtime-preflight \
  --activation-eligibility private/routing-activation-eligibility.json \
  --control-anchor private/control.sqlite \
  --signed-control-state trusted/signed-control-state.json \
  --output private/routing-runtime-preflight.json \
  ...complete calibration, holdout, promotion, and activation inputs...
```

The output has `preflight_passed: true` but fixes `dispatch_authorized`,
`runtime_activation_authorized`, and `configuration_mutation_authorized` to false.
It is evidence for a future trusted transaction, not permission to execute one.

## Deliberate limits

The anchor prevents replay of an older message relative to the state in one intact,
trusted database. It cannot prove that its first entry was globally latest. A process
with the same operating-system identity can clone or roll back the entire database to
an internally valid earlier copy carrying the same pinned policy. Detecting that
requires an external monotonic service, transparency log, trusted counter, or
independently retained latest-entry digest.

The database is private, owner-checked, non-resettable through this API, and uses
rollback journaling with synchronous commits. Its parent directory, SQLite library,
filesystem durability, system clock, and same-UID processes remain trusted. The
hash chain detects inconsistent edits; it is not a signature or tamper-proof storage.
The anchor pins one authority policy; controlled key rotation requires a new anchor
policy and newly signed activation chain rather than silently replacing keys in place.

A control update can arrive immediately after preflight, and a preflight artifact can
be replayed during its short validity window. A future dispatcher must atomically
couple its own one-use authorization to a fresh anchor read or recheck immediately
before dispatch. That time-of-check/time-of-use boundary is why this milestone
deliberately grants no dispatch authority.
