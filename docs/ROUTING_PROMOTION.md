# Independently authenticated routing promotion

Routing promotion has two separate inputs that must exist before authorization:

1. a `RoutingPromotionPolicy` whose thresholds are pinned into the holdout-use
   claim and holdout report before scoring; and
2. an independently distributed `RoutingPromotionAuthorityPolicy` containing the
   Ed25519 public keys allowed to authorize the derived result.

The promotion policy binds the frozen candidate policy and sealed study. It fixes
minimum calibrated-policy coverage, selected-route adequacy and regret-observation
rates, plus maximum under-routing, fail-closed, missed-alternative, mean cost-regret,
and mean latency-regret thresholds. Changing any value changes its digest and no
longer matches the holdout report.

```json
{
  "schema_version": 1,
  "mode": "pre_holdout_routing_promotion_policy",
  "policy_id": "critic-routing-promotion-v1",
  "activation_authorized": false,
  "population_unit": "sealed_profiles_equal_weight",
  "candidate_policy_sha256": "<64 lowercase hex characters>",
  "sealed_study_sha256": "<64 lowercase hex characters>",
  "min_calibrated_policy_coverage": 0.95,
  "min_selected_adequacy_rate": 0.95,
  "max_under_routing_rate": 0.01,
  "max_fail_closed_rate": 0.01,
  "max_missed_adequate_alternative_rate": 0.01,
  "min_regret_observation_rate": 0.95,
  "max_mean_cost_regret_microusd": 5000,
  "max_mean_latency_regret_ms": 250
}
```

These numbers are illustrative, not recommended defaults. Power, product risk, and
the intended traffic distribution must determine the reviewed values.

All policy-level rates give each sealed profile equal weight. They are not estimates
of production traffic frequency. A traffic-weighted claim requires a separately
pre-registered, representative traffic distribution; this milestone does not infer
one from the evaluation dataset.

The holdout command now requires the pre-registered input:

```console
mos eval-evaluate-routing-holdout \
  --promotion-policy trusted/routing-promotion-policy.json \
  ...
```

After holdout, derive the only valid threshold result:

```console
mos eval-derive-routing-promotion \
  --promotion-policy trusted/routing-promotion-policy.json \
  --holdout-report private/routing-holdout-report.json \
  --output private/routing-promotion-decision.json
```

This deterministic artifact records eight observed/threshold comparisons and
`criteria_satisfied`; it deliberately has no `promotion_ready` field. A release
authority signs the exact canonical decision outside Mos Eisley's CLI using the
domain `mos-eisley/routing-promotion/v1\0`. The library helper
`sign_routing_promotion_decision` exists for external integrations and tests, but no
CLI command accepts private key material.

`eval-authenticate-routing-promotion` takes that signed decision, the independently
supplied authority policy, the use claim, holdout report, and the complete calibration
and holdout source chains. It:

- recomputes the frozen policy and holdout report from every source;
- derives the threshold decision again;
- requires the signing identity and key to be absent from all grader and resolver
  trust policies; and
- verifies the exact Ed25519 signature against the authority trust root.

Only the resulting `AuthenticatedRoutingPromotion` may have
`promotion_ready: true`. A signed threshold failure produces a valid receipt with
`promotion_ready: false`. Both outcomes retain literal
`activation_authorized: false`.

## Deliberate limits

The content chain proves which thresholds were used, not when the promotion policy
was authored. The local holdout claim prevents a second CLI attempt in one directory,
but external pre-registration and holdout custody remain necessary. An attacker who
can replace the authority policy can trust their own key, so its distribution is a
root of trust rather than a self-authenticating artifact.

This milestone uses one release-authority signature. It does not implement quorum,
runtime policy installation, rollback, or traffic routing. Promotion readiness is
an evidence decision, not activation authority. The next non-executing boundary is
the separately documented [routing activation eligibility](ROUTING_ACTIVATION_ELIGIBILITY.md)
gate; its operational values are signed attestations, not provider queries.
