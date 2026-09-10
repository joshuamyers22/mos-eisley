# Current skill-release evidence

A retained archive and a signed promotion receipt solve different problems. The
archive preserves exact package bytes; the receipt authenticates an independent,
expiring decision over paired evaluation evidence. Mos Eisley now binds the two in a
single non-installing `SkillReleaseEvidence` artifact.

## Binding command

```sh
mos eval-bind-skill-release-evidence \
  --dataset eval/dataset.json --plan private/plan.json \
  --sealed-comparison private/sealed-skill-comparison.json \
  --holdout-use-claim private/claims/skill-<seal-digest>.json \
  --calibration-report private/calibration-skill-report.json \
  --holdout-report private/holdout-skill-report.json \
  --promotion-receipt private/authenticated-skill-promotion.json \
  --authority-policy trusted/skill-promotion-authorities.json \
  --archive private/candidate.skill.json \
  --calibration-batch private/calibration-batch.json \
  --calibration-mapping private/calibration-map.json \
  --calibration-raw-results private/calibration-raw.json \
  --calibration-grading-batch private/calibration-grading.json \
  --calibration-dual-grading-resolution private/calibration-dual.json \
  --calibration-dual-graded-observations private/calibration-observations.json \
  --calibration-grading-trust-policy trusted/calibration-graders.json \
  --calibration-resolution-trust-policy trusted/calibration-resolvers.json \
  --holdout-batch private/holdout-batch.json \
  --holdout-mapping private/holdout-map.json \
  --holdout-raw-results private/holdout-raw.json \
  --holdout-grading-batch private/holdout-grading.json \
  --holdout-dual-grading-resolution private/holdout-dual.json \
  --holdout-dual-graded-observations private/holdout-observations.json \
  --holdout-grading-trust-policy trusted/holdout-graders.json \
  --holdout-resolution-trust-policy trusted/holdout-resolvers.json \
  --output private/skill-release-evidence.json
```

The CLI uses the host UTC clock and writes the artifact privately with mode `0600`.
It does not accept a caller-selected verification time.

## What is reverified

The binder does not trust booleans or hashes copied from its inputs. It:

- semantically reparses every retained archive control byte and rebuilds the complete
  package descriptor and instruction digest;
- recomputes both paired skill-comparison reports from execution, blinding, dual
  grading, resolution, trust policies, and observation artifacts;
- re-derives and verifies the independently signed promotion decision;
- requires the authenticated receipt to be passing and current at the host time; and
- requires byte-for-byte `SkillIdentity` equality between archive and receipt.

The output embeds the archive and promotion receipt and commits their canonical
digests, exact identity, check time, and receipt expiration. Library reverification
rebuilds the artifact from every source and can also enforce current validity.

## Security boundary

Positive `package_retained` and `promotion_ready` fields describe evidence only.
`installation_authorized`, `activation_authorized`, and
`configuration_mutation_authorized` are literal `false` values. There is no extraction,
materialization, default-persona mutation, or runtime consumer.

The host clock is not externally trusted. The artifact does not prove package
authorship or safety and cannot detect a later revocation by itself. The follow-on
[authenticated release-control gate](SKILL_RELEASE_CONTROL.md) adds independent
allow/revoke evidence, exact rollback nomination, and a local monotonic anchor, but
still grants no deployment authority. Transactional installation, atomic default
changes, an external anti-rollback witness, and post-install drift monitoring remain
required before deployment can exist.
