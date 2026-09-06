# Routing promotion authentication review

Scope: pre-register policy-level holdout thresholds and authenticate the resulting
promotion decision. No provider call, runtime installation, activation, traffic,
configuration mutation, or publishing is included.

| Attack or failure | Implemented control | Residual boundary |
|---|---|---|
| Thresholds are selected after viewing holdout | Pin the complete promotion-policy digest into the exclusive use claim and holdout report before scoring | A local digest cannot prove wall-clock ordering; independent pre-registration and custody remain required |
| Missing cost data silently passes regret limits | Pre-register minimum regret-observation coverage; absent means fail both regret comparisons | Meter correctness and population uncertainty remain external |
| An unsigned passing report is treated as promoted | Derived decisions expose only `criteria_satisfied`; `promotion_ready` exists only on authenticated receipts | Downstream consumers must accept only the verified receipt schema |
| A grader approves their own experiment | Reject authority identities or public keys appearing in either calibration or holdout grader/resolver policy | Organizational independence beyond keys and claimed identities is not proven |
| Signature is replayed onto altered thresholds or results | Domain-separated Ed25519 signature binds the exact content-addressed decision, report and promotion policy | Authority-key custody, revocation and compromise response are not implemented |
| An attacker supplies a trust policy containing their own key | Require an independently supplied authority policy and pin its digest into the receipt | Distribution of that policy is an external root of trust |
| Failed criteria are hidden | Recompute all eight checks and authenticate denials as `promotion_ready: false` | Product owners still choose the pre-registered thresholds |
| Equal-profile rates are mistaken for production frequency | Pin `population_unit: sealed_profiles_equal_weight` in the threshold policy | Representative traffic weights and domain prevalence are not established by this study |
| Promotion is confused with deployment | Every decision and receipt has literal activation denial; no runtime accepts or installs it | Drift, expiry, availability, rollback and activation authorization remain future gates |

The next boundary is a time-bounded activation policy that consumes only an
authenticated promotion receipt after fresh provider/catalog, price, conformance,
and drift checks. It must preserve conservative fallback behavior and support
revocation without giving the model configuration authority.
