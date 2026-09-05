# Statistical design for offline route comparisons

Status: implemented for offline reports. Automatic routing remains disabled.
This design is an implementing-assistant proposal and has not received an
independent statistical review or validation on live provider data.

## Independent units and the quantity being estimated

Each dataset case may declare an `independence_group`. Assign related mutations,
revisions of the same underlying change, and other dependent examples to the same
group. Select the grouping scale before execution: use repository-level groups
when dependence between changes in a repository matters. A group may occur in
only one split. Exact duplicate briefs are rejected; use repetitions for repeated
execution of the same input.

Missing group declarations leave per-run diagnostics available but make a route
ineligible. Group metadata stays in the labeled dataset and does not enter the
execution batch or grading packet.

The gating estimand is an **equal-weight mean over independent groups**:

1. Average repetitions within each case. Detection is the fraction of expected
   findings detected, completion is the fraction of completed executions, and the
   clean-review risk measure is the fraction with any false finding or execution
   failure.
2. Average case rates within each group. Detection uses defective cases only;
   clean-review risk uses clean cases only; completion uses all cases.
3. Average the resulting group rates with equal weight.

Every group contributes one bounded value to each applicable metric. Extra runs
and related cases can change that value, but cannot increase the independent group
count. Weighting is deliberately different from the original pooled per-finding
and per-run metrics; those remain in reports as Wilson diagnostics and do not
control eligibility.

An unsuccessful execution contributes zero detection and completion. For clean
cases it contributes worst-case risk of one, because absence of an output cannot
establish absence of false positives. The pooled diagnostic still reports observed
false positives separately.

## Confidence bounds and the comparison family

For independent group values in [0, 1], the two-sided Hoeffding bound gives radius
`sqrt(log(2 / alpha_interval) / (2 * group_count))` around their mean, clipped to
[0, 1]. Unlike a percentile bootstrap on all-identical outcomes, this radius does
not collapse to zero. The independence assumption is essential.
[Hoeffding, 1963, original paper](https://www.cs.rpi.edu/academics/courses/spring06/random/hoefding.pdf).

Allocate total error probability 0.05 across a fixed family of
`route_count * 3 metrics * 2 splits` intervals. Each interval receives
`alpha_interval = 0.05 / family_size`. Bonferroni controls simultaneous coverage
without requiring independence between the comparisons.
[NIST, Bonferroni's method](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm).

Applying these results to the group aggregation above is Mos Eisley's design
choice. Coverage describes means over the declared independent group population,
conditional on correct labels, representative sampling and an unchanged design.
It does not prove generalization to a new repository domain.

The gate stores the method, estimand, family scope, fixed-matrix stopping rule and
minimum groups per metric in its content-addressed plan. Default minimum: 30 groups
for each metric; this is an operational floor, not a power calculation or a guarantee
that the thresholds can pass. A test fixture may explicitly lower it to two.

For one route and 100 groups per metric, the radius is approximately 0.16554.
Flawless results therefore give detection lower bound 0.83446 and clean-risk upper
bound 0.16554. One group repeated 100 times still has a [0, 1] interval. Adding
candidate routes increases the family size and widens the interval.

## Decisions and remaining limits

`eligible` means group coverage, the three group confidence gates, and the
configured observed cost/latency checks passed for this report. It is not a routing
promotion. All reports and CLI summaries explicitly return `promotion_ready: false`.
Cost and latency checks are descriptive constraints without population confidence
bounds. They are outside the six-per-route statistical confidence family.

The design is conservative and can require many groups for strict false-positive
targets. Plan sample size from the formula and the chosen thresholds before buying
a sweep; a minimum count alone is insufficient. Statistical power analysis and
less conservative methods require a separately reviewed protocol.

Only one fixed matrix is covered. Repeated inspection of unchanged data does not
add evidence; adding cases, changing thresholds, trying new candidate grids or
stopping as soon as a gate passes invalidates the original guarantee. Sequential
stopping, adaptive candidate selection and family-wide tracking across multiple
plans are not implemented. Freeze selection on calibration, then test once on
holdout under a pre-registered protocol before promotion.

Group independence, physical adjudicator identity and labels are operator claims.
Exact duplicates and split conflicts are detectable; hidden common ancestry and
semantic duplicates are not. Ed25519 receipts authenticate exact human grading to
enrolled keys, but downstream comparison and compilation do not yet require them.
External protocol attestation, holdout access control, authenticated resolution,
isolated live execution and representative empirical data remain prerequisites for
routing promotion.

Per-finding grading and descriptive two-grader agreement are now implemented.
Separate authentication receipts prove key possession, but neither those receipts
nor agreement establish independence or an inferential reliability guarantee.

## Artifact compatibility

Dataset, gate, sweep-plan and report schemas are version 2. Older version-1 inputs
are rejected. Recreate datasets with reviewed grouping, create a new gate/plan, and
regenerate the batch, cassette bindings, grading and observations. Changing only a
schema number or copying old hashes does not preserve the chain or statistical
meaning.
