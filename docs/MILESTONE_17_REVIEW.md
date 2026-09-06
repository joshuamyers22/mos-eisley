# Candidate routing policy freeze review

Scope: deterministic derivation of a non-activating candidate policy from reverified
calibration evidence. No holdout outcomes, provider calls, runtime routing,
configuration mutation, promotion, activation, or publishing is included.

| Attack or failure | Implemented control | Residual boundary |
|---|---|---|
| Edited calibration score steers selection | Recompute the complete sealed profile report from all execution and authenticated grading sources before freezing | Source retention and independent distribution remain operator duties |
| Cheap route below the role minimum wins | Intersect quality-eligible routes with the sealed role allowlist and explicitly record excluded plan candidates | Humans still define whether the floor and fallback are prudent |
| Missing prices make a measured route look cheapest | Separate quality/latency from cost eligibility and require full cost coverage for every quality-eligible permitted route; any gap makes the entire profile uncalibrated | Reviewed prices and metering correctness still need live operational validation |
| Tie behavior changes between runs | Pin cost → p95 latency → candidate digest ordering in the protocol and implement it deterministically | Cost and latency are observed summaries without population confidence bounds |
| Fallback is relabeled as empirically selected | Give calibrated, no-quality, and incomplete-cost bases distinct schema values; fallback decisions omit selected metrics and carry the sealed fallback ID | Users must preserve that distinction in later interfaces |
| Holdout data tunes the policy | Accept only a strict calibration report and fully reverify its hard-coded split; record holdout as not evaluated | Local code cannot attest that analysts avoided separate holdout access |
| Candidate artifact is used as production configuration | Literal promotion and activation denial; no router or config writer accepts the schema | Holdout governance, drift checks, signed promotion, and runtime availability handling remain future work |

The next gate is a one-time holdout evaluator that takes this frozen candidate policy
as an immutable input, measures routing quality and fallback coverage, and still
cannot promote or activate it. That boundary is now implemented; see
[frozen-policy holdout evaluation](ROUTING_HOLDOUT.md).
