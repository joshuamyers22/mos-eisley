# Adaptive reasoning routing — revised Mos Eisley design

Reviewed 2026-09-08. Status: planned extension, no runtime activation.
This is the revised, repository-owned version of
`/Users/josh/Downloads/adaptive-reasoning-routing.md`. The original remains an input
reference. Integration authority is [plan §26](mos-eisley-plan.md#26-integrated-project-review-and-delivery-contract).
Findings and source provenance are in [the project review](PROJECT_REVIEW_2026-09-08.md).

## Objective and boundaries

Reduce whole-task cost while preserving independently measured correctness,
completion, and latency requirements. Treat the claimed learnability of hidden
difficulty, cross-family transfer, and the value of historical lookups as hypotheses.
None has been established by Mos Eisley's recorded fixtures.

Reuse the existing sealed study, calibration, freeze, holdout, promotion,
activation-eligibility, and preflight chain. Do not build a second policy authority.
Start with fixed eligible role routes and the existing deterministic-feature study.
Compare historical lookup and bounded cascade candidates offline before enabling
either. A lookup table is an automatic selector and needs the same quality gates.

Eligible future stages are creator implementation, independent plan reading,
reviewer derivation, and reviewer binding. General tool subtasks need separate
role-specific outcomes and evaluation before inclusion. Freeze the judge and human
grading/resolution path within each experiment and initial production cohort.
Calibration executes the registered candidate matrix; it does not adaptively choose
cells. A tested route may vary in an evaluation, while the evaluator stays fixed.
Pin prompt/skill, model/backend/client, effort, budget, toolset, and rubric as well
as role; changing any measurement component starts a new measurement version.

## Decision and observation contracts

The trusted controller creates a bounded, versioned `RouteDecision` before dispatch.
Names below are proposed schema fields, not implemented contracts.

| Record | Required contents |
|---|---|
| Identity | Owner, task, stage, attempt and parent-attempt IDs; plan, artifact, feature-schema and policy digests |
| Eligibility | Exact candidate IDs and exclusions; registry, capability, conformance, price and authority versions |
| Action | Provider/backend/model/client, prompt/skill digest, requested and resolved effort, output ceiling and context reserve |
| Selection | Strategy/version, decision-time features, complete probability distribution over the eligible actions, selected-action probability, experiment/cohort and randomization reference |
| Dispatch | Actual action, admission result, reservation ID, one-use request identity and control sequence |
| Outcome | Execution status, verification status/provenance, terminal task status, follow-up window, usage, elapsed time, settled or uncertain cost, trigger and escalation chain |

Require finite nonnegative probabilities summing to one and a positive selected
probability. For deterministic selection record probability one for the selected
eligible action and zero elsewhere. An admission failure is not a completed action.
If eligibility changes before send, record no-dispatch and reselect with a new
decision/distribution; never assign the old propensity to a fallback. Historical
records missing these fields stay descriptive, with unknown values explicitly
marked. Do not fabricate propensities or backfill observed cost as a reservation.

Add these records through §17.5's bounded Mos telemetry mapping. Decision and
before-send evidence required for an experiment must be durable before dispatch;
missing records make that episode unusable for inference. Optional diagnostics
retain their counted-loss behavior. Logging consumes disk, engineering work and
possibly tokens: measure its overhead rather than calling it free.

Keep retained content and the selection store separate. Automatic cross-session
selection uses only that owner's minimal aggregates allowed by §17.3: no raw
conversations, code, embeddings, exact paths, case fingerprints, or retrieval of
nearest historical trajectories. Explicit same-owner inspection does not grant a
standing retrieval permission. An offline study can explicitly select same-owner
evidence; its resulting selection artifact must still satisfy §17.3. No pooling
across users. Deletion/reset invalidates dependent aggregates and policies whose
required evidence is no longer available.

## Features, actions, and outcomes

Features must exist before the particular decision. Stage-0 divergence is available
for a later implementation decision, never for the reading call that generated it.
Historical aggregates use only episodes resolved before the cutoff; exclude the
current task, related revisions and held-out groups. Validate feature extraction
from frozen inputs and record provenance; operator-entered risk tags are assertions,
not proof that a risk was detected. Missing, sparse, stale and OOD profiles fall back
to a currently eligible conservative route or stop.

Keep effort and output length as distinct requested controls, but respect actual
provider coupling, context capacity and total reasoning/output billing. Initially
hold output ceilings fixed by route. Adding budget choices requires versioning
`RouteCandidate`, grid/request identity, reports and replay bindings; today's
candidate schema does not make output budget an independent action dimension.
Do not change a budget underneath existing quality evidence. No global assumption
that a nominally higher effort is better, or that effort names order model families.

Test pass/fail, author rejection, cycle count and judge verdict are proxy outcomes.
They are not correctness labels. Preserve at least:

- execution: completed, invalid output, truncation, test failure, provider/tool
  failure, cancellation, timeout, or admission denial;
- verification: independently supported success/defect, disputed, or unknown;
- task follow-up: completed, unresolved, abandoned, or still awaiting a defined
  escaped-defect observation window.

Distinguish missing/delayed outcomes from action-dependent selection bias. Include
failed and abandoned episodes in whole-task denominators and cost; never compute
savings only among successful cheap calls. Budget exhaustion and truncation are
failures, not evidence that a smaller answer was adequate. Carry uncertain spend
conservatively under the existing ledger contract.

## Cascade and counterfactual evidence

A proposed cascade has one evaluated capability escalation after an observable,
role-specific failure. Format repair is a distinct bounded attempt at the same
route. All calls, children, repairs and escalation share one task cost/deadline
budget. Provider uncertainty does not authorize retry of a possibly sent request.
Recheck data permissions, floors, conformance and current spending at each dispatch.
No downgrade after budget pressure; stop if an eligible fallback cannot fit.

A cheap failure followed by expensive success is an observed recovery sequence,
not a causal difficulty bracket: the second attempt may see feedback, changed code,
different tests, more context, or provider randomness. Evaluate the entire cascade
as a policy. To estimate effort effects, execute paired independent attempts from
the same frozen starting state, randomize order, record state and feedback access,
and replicate within independent task/repository groups. Never let one arm mutate
the other's checkout or caches. Study shared-difficulty versus route-specific
predictors by held-out family/version ablation; a model release invalidates affected
evidence until transfer is demonstrated, even if the corpus is retained.

Exploration is off by default. First use isolated, non-authorizing offline/shadow
trials with a separate bounded study allocation. Shadow calls still need inference
data permission and spend admission. Any later online randomization may choose
only already qualified routes above the hard role floor under an explicitly
registered cohort and stop policy. Never send unqualified weaker routes into live
coding merely to gather labels. Offline/shadow exploration outputs cannot write,
publish, update gold labels, or change the active policy. A later qualified online
cohort retains the normal controller's approval and machine-capability boundaries.

## Evaluation and promotion

Use the fixed role fallback as the first baseline; then compare lookup, cascade,
the existing interpretable selector, and only subsequently a learned two-part or
bandit selector. Seal the candidate family, independent groups, split/cutoff,
minimum effect, quality limits, sample-size feasibility, and stopping rule before
outcomes. Keep all revisions/retries of a task within one split. Include a later
time window and OOD tasks; bootstrap repeated calls as independent samples is
prohibited. The implemented fixed-matrix group bounds remain the default gate.
Adaptive logging needs a separately reviewed estimator; do not feed selected
trajectories into the existing exact-coverage matrix scorer.

Propensities alone do not identify unobserved alternatives. Off-policy reports must
name the target policy/population, verify positive logging support for its actions,
report weight extremes/effective sample size, and state any clipping and sensitivity
analysis. Unsupported or low-information comparisons are inconclusive. Proposed
IPS/doubly robust estimates require separate validation; stage-level propensities
do not by themselves identify the value of a sequential multi-step coding policy.
Prefer randomized whole-task policy comparisons for the initial cost claim. The
motivation for separating reward models from logging-policy models follows
[Dudík, Langford and Li](https://arxiv.org/abs/1103.4601); these Mos release rules are
design choices, not claims that an estimator is already implemented.

Optimize cost only after passing absolute quality limits and registered
non-inferiority margins for detection, completion, escaped defects and correct-work
damage. A scalar `success - lambda * cost` cannot trade away these constraints.
Report total cost per independently verified successful task with failed-task cost
in the numerator, completion rate, paired whole-task cost difference, p95 latency,
truncation, fallback/OOD coverage and escalation payoff. Zero verified successes
makes cost-per-success undefined and the policy ineligible. No fixed number of
cases proves rare damage is below its ceiling; plan attainable confidence first.

Freeze the candidate on calibration and consume the independently held holdout
once. Monitoring may quarantine/stop a policy; it cannot refit and reactivate it.
Model/client/prompt/tool/template drift, insufficient recent evidence, or a passed
freshness deadline triggers conservative fallback or stop and a new study. Keep
calendar freshness limits as well as recent-window comparisons; quiet traffic is
not evidence of continued quality. Reuse the existing promotion/control chain;
resolve external monotonic witness, authority custody and atomic one-use broker
dispatch before runtime traffic.

## Delivery gates

1. **R0 — instrument fixed routes:** record decisions/outcomes and reject malformed
   distributions, post-decision features, missing evidence and cross-owner access.
2. **R1 — offline baselines:** compare fixed, lookup and cascade on a preregistered
   complete matrix; include artifact isolation, failed episodes and all costs.
3. **R2 — candidate evaluation:** shadow a frozen selector and meet the registered
   quality and useful-savings margins on held-out independent groups. No qualifying
   evidence means retain fixed routes; stopping at R0/R1 is a valid outcome.
4. **R3 — operational activation:** current conformance, ownership enforcement,
   signer/witness operations, race-tested dispatch, spend, cancellation and rollback
   gates pass. Start a bounded cohort with fixed measurement components.
5. **R4 — advanced experiments:** transfer, output-budget routing, supported
   off-policy estimation and bandits each need their own R1–R3 evidence. Online
   learning is not implied by installing a frozen policy.
