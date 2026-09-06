# Evaluation foundation adversarial review

Date: 2026-09-05. Scope: evaluation dataset, candidate, plan, observation and report
contracts; deterministic matrix planning; offline split scoring; CLI artifact
writes. Reviewer: implementing assistant self-review; no provider sweep or
independent statistical review was performed.

Disposition: suitable for building and testing datasets. It is not sufficient to
promote or execute an automatic routing policy.

## Findings and corrections

| Impact | Finding | Correction / evidence |
|---|---|---|
| High | Missing or failed trials could be dropped and make a route look stronger | Require exact assignment coverage; record errors and count them against detection and completion |
| High | Thresholds chosen after results would invalidate a claimed gate | Require a gate input before plan generation and include it in the plan digest; external timestamping remains future work |
| High | A nominal model name does not identify a comparable execution path | Candidate identity includes backend, provider, model, effort, client version and registry digest |
| High | Calibration and holdout observations could be mixed | Score exactly one declared split and reject any missing or cross-split assignment |
| Medium | Repeated sweeps in fixed order could confound model quality with provider drift | Deterministically randomize the complete matrix from a recorded seed |
| Medium | Point estimates encourage promotion on small samples | Gate detection, clean false positives and completion on fixed 95% Wilson bounds |
| Medium | Missing cost data could accidentally pass a cost cap | A configured cost gate requires 100% cost coverage |
| Medium | Malicious sizes could exhaust memory before schema validation | Bound input files, cases, candidates, repetitions and total assignments before expansion |
| Low | Output overwrite could erase the evidence used for a decision | Create private output files exclusively and fail if the target exists |

## Remaining work and violations of the full plan

- There is no blinded executor, live backend sweep or human-adjudication workflow.
  The dataset contains labels, so label isolation is currently an operator duty.
- Holdout secrecy and one-time use are not enforceable by local JSON artifacts.
  Plan creation embeds thresholds but cannot prove they were pre-registered before
  an analyst inspected results.
- Wilson intervals treat trials as independent. Repeated outputs for the same case
  and related mutations are clustered; production analysis needs cluster-aware
  uncertainty and a pre-specified multiple-comparison procedure.
- False-positive gating is the fraction of clean runs with at least one false
  finding. Counts remain recorded, but severity-weighted harm needs a separate,
  pre-registered measure.
- Dollar cost is meaningful for API observations. Subscription quota consumption
  has no validated conversion to micro-US dollars, so cross-billing-mode cost
  optimization remains blocked.
- No prompt-profile features, out-of-distribution detector, policy learner,
  policy-signing/promotion process, drift monitor or routing runtime exists.

Next review trigger: a label-isolating recorded executor and an adjudication
artifact with reviewer provenance, followed by a statistical design review before
any paid sweep.
