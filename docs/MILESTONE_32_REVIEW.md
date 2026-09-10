# Milestone 32 adversarial review: post-selection skill health evidence

## Disposition

Accepted as a non-executing evidence gate. Runtime consumption remains prohibited.

## Adversarial findings and controls

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A valid observation is replayed for another default | Policy and observation bind the exact pointer, installed manifest, archive, persona identity, and default-store policy | Whole-store rollback/cloning needs an external witness |
| Evidence predates selection or is gathered after issuance | The verifier enforces `selected_at <= observed_from <= observed_through <= now` | Host-clock integrity is external |
| An operator signs lenient thresholds after seeing results | Threshold policy and observation require distinct keys; both are independent of all upstream authorities | Organizational independence and policy timing are external |
| A signer asserts `healthy: true` despite bad measurements | No signed pass boolean is accepted; Mos Eisley recomputes absolute and reference-drift gates from integer metrics | The referenced raw evidence is not fetched or recomputed |
| Tiny or partial samples masquerade as health | All three quality metrics meet the larger historical/new group floor; configured cost requires full coverage | Independence remains an observer assertion |
| Revoked candidate bytes retain old health status | Issuance and verification require the latest anchored control and the currently permitted candidate or nominated rollback archive | External monotonic delivery is still absent |
| A health receipt silently activates the prompt | Every artifact denies dispatch, activation, configuration mutation, and automatic rollback; no runtime imports it | One-use dispatch preflight is future work |

## Changes made during review

- Replaced categorical health/drift statuses with direction-aware integer metrics and
  deterministic threshold recomputation.
- Bound the policy to the authenticated promotion holdout report so drift has an exact
  historical reference rather than an operator-selected label.
- Required evidence to be strictly post-selection and bounded by both freshness and
  expiry.
- Required policy and observation signers to be distinct and disjoint from every
  upstream evaluator and control authority.
- Kept rollback automatic action out of scope: failed evidence yields no eligibility
  and performs no mutation.

## Follow-on requirement

Before runtime use, add a one-use brokered preflight that atomically binds a fresh
request, exact current pointer, current control/health evidence, selected model route,
spending reservation, and prompt bytes. It must fail closed on any state advance and
must not turn health failure into automatic rollback without a separate authority and
transaction design.
