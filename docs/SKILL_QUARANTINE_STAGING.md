# Transactional skill quarantine staging

Mos Eisley can materialize one exact, fully controlled skill archive into a private,
content-addressed quarantine store. Staging is deliberately not installation: no
runtime or configuration code reads this store, and every policy, intent, manifest,
result, and CLI event fixes installation, activation, and configuration mutation to
`false`.

## Commands

Create a store from a reviewed policy and the exact release-control anchor policy:

```sh
mos skill-staging-store-create private/skill-staging \
  --store-policy trusted/skill-staging-policy.json \
  --anchor-policy trusted/skill-release-anchor-policy.json
```

Stage an exact candidate or nominated rollback package:

```sh
mos eval-stage-skill-release \
  --action rollback \
  --authenticated-control private/authenticated-release-control.json \
  --control-anchor private/release-control.sqlite \
  --staging-store private/skill-staging \
  --output private/staging-result.json \
  ...the complete release-evidence and calibration/holdout source arguments...
```

The command uses host UTC time. `candidate` requires the exact current archive and an
allowed latest control. `rollback` requires a revoked latest control and its exact
embedded rollback archive. The full release, promotion, comparison, and dual-grade
lineages are reauthenticated before either path can write.

Inspect every completed package and conservative crash inventory with:

```sh
mos skill-staging-store-status --store private/skill-staging
```

## Store and transaction layout

```text
skill-staging/
├── policy.json
├── packages/
│   └── <archive-sha256>/
│       ├── intent.json
│       ├── manifest.json
│       └── payload/...
└── transactions/
    └── <transaction-id>/...
```

The root must be exclusively created and owner-private. Its immutable policy pins the
exact release-control anchor policy plus package and incomplete-transaction limits.
Unexpected root entries, invalid content-addressed names, symlinks, special files,
hard-linked files, non-private files, and noncanonical manifests fail closed.

For a new package the controller:

1. creates an unpredictable exclusive private transaction directory;
2. writes and fsyncs an intent binding the current control receipt and anchor entry;
3. writes every archive byte with exclusive mode `0600` under private directories;
4. rebuilds the complete archive and semantic skill descriptor from staged bytes;
5. writes the completion manifest last and fsyncs every nested directory; and
6. atomically renames the verified directory to its archive-digest package path,
   then fsyncs both sides of the rename.

An already-present exact package is verified before idempotent reuse. A conflicting,
partial, or modified package is never repaired in place.

## Revocation race guard

Latest-state verification and filesystem commit are one local critical section. The
anchor holds a SQLite read transaction from its complete chain check until staging's
atomic rename and fsync finish. A concurrent anchor advance may begin but cannot
commit a newer revocation during that interval.

This guarantee does not survive an owner replacing the entire anchor database path,
store, policies, or process. Those remain same-UID and external-witness trust
boundaries.

## Crash behavior and remaining boundary

A failure before atomic rename leaves a bounded directory under `transactions/`.
Status reports whether its intent and completion marker exist, but never resumes,
deletes, or finalizes it automatically. A completed package appears only at a
content-addressed `packages/` path and is fully reverified on every inventory/load.

The store is quarantine evidence, not a trusted runtime search path. There is no
signed installation authority, default-persona pointer, overwrite operation,
uninstaller, automatic crash recovery, external anti-rollback witness, post-stage
health check, or drift monitor. A later installer must consume an exact verified
staging manifest in a separate one-use transaction and preserve the latest-control
guard through its configuration commit.
