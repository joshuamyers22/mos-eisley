# ADR 0004: Empirical prompt-difficulty routing

Date: 2026-09-05. Status: proposed; blocked on evaluation data.

Implementation note: the offline routing-study protocol, feature-partition sealing,
profile-aware calibration scorer, deterministic candidate-policy freezer, one-attempt
holdout evaluator, and independently authenticated promotion gate are implemented.
Runtime routing and activation remain disabled.

## Decision

Mos Eisley will select model and reasoning effort per task using a versioned policy
learned from blinded evaluations, not a permanent role mapping or an intuitive
difficulty score. A role defines a hard minimum and a conservative fallback. The
router may choose a route cheaper than that fallback only when held-out evidence
shows that it satisfies pre-registered quality constraints for prompts with a
comparable observable profile; it may never route below the minimum.

The initial feature set is deterministic and available before provider dispatch:
role, input size, changed files and lines, language count, requested output contract,
tool requirements and risk tags derived without a model. Prompt length alone is not
a difficulty label. A model-based preflight classifier may be evaluated later, but
is excluded from the initial policy because it adds cost, latency and another source
of error.

`mos eval --sweep` will evaluate the joint backend × model × effort grid with repeated
runs on blinded clean changes, filtered mutations, historical defects and
human-adjudicated examples. API and subscription-backed executions are distinct cells
even when they name the same model because their client harness and entitlement
behavior can differ. The primary constraints are a lower confidence bound on defect
detection and an upper confidence bound on false positives. Cost and latency are
optimized only among routes that pass those constraints. Routing regret,
under-routing and out-of-distribution coverage are reported separately.

Every promoted policy is a content-addressed artifact that pins its feature schema,
dataset digest, provider/backend/model registry snapshot, client versions, candidate
cells, metrics, confidence method and thresholds. A run records the policy digest,
extracted features, requested route, resolved route, substitutions and decision
reason. For subscription-backed execution, the candidate set is intersected with
the official client's current model catalog. An unavailable calibrated cell is
ineligible; it is not replaced with a nearby model or effort. Uncalibrated, stale or
out-of-distribution inputs use the role fallback or fail closed. They never silently
receive a weaker model or effort level.

Format repair and capability escalation are separate. Invalid structured output can
receive one bounded repair at the same route. A harder retry requires a role-specific,
externally observable signal whose payoff has itself passed evaluation. Model
self-confidence is not sufficient evidence.

This follows current provider guidance that reasoning effort should increase only
when evaluations demonstrate a measurable gain: the
[OpenAI model guide](https://developers.openai.com/api/docs/guides/latest-model) and
[Anthropic cost/intelligence guide](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence).

## Consequences

Automatic routing cannot ship with the first provider adapter because no qualifying
Mos Eisley dataset exists yet. Manual selection remains available for experiments,
and fixed role routes remain the production baseline until the evaluation gate
passes. This delays apparent intelligence but prevents an unvalidated heuristic from
quietly sending difficult reviews to an inadequate model.

Provider effort labels remain incomparable. The policy treats each concrete backend
× model × effort tuple as its own candidate and records the resolved provider
setting. A new model, client version, material provider drift or feature-schema
change invalidates the applicable calibration and requires re-evaluation before it
can receive traffic.
