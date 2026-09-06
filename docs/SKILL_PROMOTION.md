# Independently authenticated persona-skill promotion

A passing paired comparison is evidence, not authorization. Mos Eisley now supports
one additional verification-only boundary: an independently enrolled release
authority can sign an exact, short-lived decision derived from both calibration and
holdout reports. The resulting receipt may say `promotion_ready: true`, but it still
has literal `activation_authorized: false` and
`configuration_mutation_authorized: false`.

## Authority policy

The trust root is an operator-distributed `SkillPromotionAuthorityPolicy`:

```json
{
  "schema_version": 1,
  "mode": "skill_promotion_authority_policy",
  "policy_id": "persona-release-authorities-v1",
  "activation_authorized": false,
  "valid_from": "2026-09-06T00:00:00Z",
  "valid_until": "2026-09-13T00:00:00Z",
  "max_decision_lifetime_seconds": 86400,
  "authorities": [
    {
      "authority_id": "persona-release-manager",
      "algorithm": "ed25519",
      "public_key_base64": "<canonical 32-byte Ed25519 public key>"
    }
  ]
}
```

Authorities must have sorted, unique IDs and unique keys. The policy is not
self-authenticating: its controlled distribution is a root of trust. Its validity
window bounds every decision, and an individual decision cannot exceed the policy's
maximum lifetime.

## Derive, sign, authenticate

The deterministic derive command takes the dataset and plan because it reverifies
the sealed comparison before producing signable bytes. It requires one calibration
report and one holdout report for the same seal, exact candidate IDs and prompt
digests, and the same registered gate. Both split gates must pass for
`criteria_satisfied` to be true.

```sh
mos eval-derive-skill-promotion \
  --dataset eval/dataset.json \
  --plan private/plan.json \
  --sealed-comparison private/sealed-skill-comparison.json \
  --calibration-report private/calibration-skill-report.json \
  --holdout-report private/holdout-skill-report.json \
  --authority-policy trusted/skill-promotion-authorities.json \
  --issued-at 2026-09-06T12:00:00Z \
  --valid-until 2026-09-06T18:00:00Z \
  --output private/skill-promotion-decision.json
```

The unsigned decision deliberately has no `promotion_ready` field. It binds the
authority-policy digest, seal, both report hashes, baseline and candidate prompt
hashes, exact `SkillIdentity`, split results, and UTC validity window.

A release authority signs the canonical decision outside the CLI using Ed25519 and
the domain `mos-eisley/skill-promotion/v1\0`. The library helper
`sign_skill_promotion_decision` exists for integrations and tests; no CLI accepts a
private key.

Authentication takes both complete evaluation lineages, the holdout-use claim, both
reports, the signed decision, and an independently supplied authority policy. The
CLI reads the host UTC clock; it does not accept a caller-selected verification time:

```sh
mos eval-authenticate-skill-promotion \
  --dataset eval/dataset.json --plan private/plan.json \
  --sealed-comparison private/sealed-skill-comparison.json \
  --holdout-use-claim private/claims/skill-<seal-digest>.json \
  --calibration-report private/calibration-skill-report.json \
  --holdout-report private/holdout-skill-report.json \
  --signed-promotion trusted/signed-skill-promotion.json \
  --authority-policy trusted/skill-promotion-authorities.json \
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
  --output private/authenticated-skill-promotion.json
```

The authenticator recomputes both paired reports from every execution, blinding,
grading, resolution, and observation source. It requires the release authority's ID
and key to be absent from both splits' grader and resolver policies, checks the
policy and decision windows, derives the decision again, and verifies the exact
signature. A correctly signed failed experiment produces a valid receipt with
`promotion_ready: false`.

## Deliberate limits

Promotion readiness means an independent authority accepted this exact evidence
within this time window. It cannot install the prompt, edit configuration, dispatch
a model, or activate a skill. Live CLI authentication uses the host clock.
Historical receipt verification uses the recorded authentication time to reproduce
the original decision.

The authority policy can be replaced by anyone who controls its distribution. One
signature is required; quorum is not implemented. Historical verification uses the
receipt's recorded authentication time and therefore does not assert that the
decision is still current.

Deterministic [package retention](SKILL_ARCHIVES.md) and a separate
[current release-evidence binding](SKILL_RELEASE_EVIDENCE.md) now exist. The latter
recomputes both lineages and requires the archive identity to equal this receipt's
exact candidate identity before expiry. Package signature/authorship, rollback,
revocation, default-persona installation, and post-promotion drift checks remain
unimplemented. Those gates must exist before promotion readiness can become
configuration or runtime authority.
