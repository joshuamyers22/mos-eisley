# Atomic inert skill installation

Mos Eisley can consume one authenticated installation decision and atomically copy the
exact authorized quarantine archive into a private content-addressed installed store.
Installed means the bytes and complete provenance were durably materialized; it does
not mean selected as a default, visible to runtime lookup, or active in a model request.

## Commands

Create a store from the exact reviewed policies and quarantine store:

```sh
mos skill-installed-store-create private/installed-skills \
  --store-policy trusted/installed-store-policy.json \
  --installation-authority-policy trusted/installation-authorities.json \
  --staging-store private/skill-staging \
  --claim-store-policy trusted/install-claim-store-policy.json
```

Install the exact candidate or rollback authorized by the signed decision:

```sh
mos eval-install-skill-release \
  --action rollback \
  --authenticated-installation private/installation-authorization.json \
  --authenticated-control private/authenticated-release-control.json \
  --control-anchor private/release-control.sqlite \
  --staging-store private/skill-staging \
  --claim-store private/install-claims.sqlite \
  --installed-store private/installed-skills \
  --installation-authority-policy trusted/installation-authorities.json \
  --output private/install-result.json \
  ...the complete release-evidence and calibration/holdout inputs...
```

The command uses the host UTC clock. It rejects an already installed digest and visible
capacity failure before consuming permission. It then reverifies the full lineage,
exact staged bytes, signed installation decision, and latest control state. The claim
is durably consumed before package writes and is never refunded after an ambiguous
failure.

## Store transaction

```text
installed-skills/
├── policy.json
├── install.lock
├── packages/
│   └── <archive-sha256>/
│       ├── intent.json
│       ├── authorization.json
│       ├── claim.json
│       ├── staging-manifest.json
│       ├── manifest.json
│       └── payload/...
└── transactions/
    └── <transaction-id>/...
```

The private lock serializes inventory checks and commits across processes. A transaction
writes and fsyncs intent and provenance, writes each exact payload byte privately,
reconstructs the complete semantic archive, writes the completion manifest last,
reverifies exact inventory, fsyncs every directory, and atomically renames the directory
to its archive digest. Existing destinations are never overwritten or repaired.

Inspect all packages and partial transaction markers with:

```sh
mos skill-installed-store-status \
  --store private/installed-skills \
  --installation-authority-policy trusted/installation-authorities.json
```

## Read-only recovery

```sh
mos skill-install-recovery-status \
  --installed-store private/installed-skills \
  --claim-store private/install-claims.sqlite \
  --installation-authority-policy trusted/installation-authorities.json
```

Recovery correlates each durable signed-decision claim as `completed`, `incomplete`, or
`claim_only`; transaction directories lacking an intent appear separately as
`unbound_transactions`. It verifies completed bytes and partial canonical provenance.
It never resumes, retries, finalizes, deletes, refunds, or otherwise mutates state.

## Remaining boundary

No default-persona pointer or runtime code reads the installed store. All contracts and
events fix default changes, configuration mutation, activation, and runtime lookup to
false. Owner-driven state rollback/cloning, same-UID ancestor replacement, external
revocation delivery, automatic recovery, uninstallation, post-install health, and drift
monitoring remain outside this local milestone. A separate signed authority and atomic
pointer store can now select an inert default, but runtime consumption and drift gates
remain separate.
