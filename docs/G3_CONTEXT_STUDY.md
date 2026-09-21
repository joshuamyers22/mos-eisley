# G3 baseline/ablation policy and label eligibility

Status: offline sealing and metadata-only inventory boundary implemented. No real
study label catalog has been supplied, and no study execution is authorized.

## Frozen comparison design

`BaselineAblationPolicy` pre-registers one available baseline that preserves the
existing selection policy, one available full candidate containing bounded work
units, explicit checkpoints, narrow tool views and task profiles, and exactly one
leave-one-component-out ablation for each candidate component. An ablation that is
not yet executable remains in the family as `unavailable` with a reason; it cannot
silently disappear after results are known.

Every policy binds exact model-route, rubric, quality-gate, resource-plan,
implementation and label-inventory digests, plus the assignment seed and escaped-
defect follow-up window. It fixes these rules before held-out evaluation:

- matched cases with balanced arm order;
- completion, missed evidence, stale-state error, verifier disagreement, harmful
  action, cumulative input, latency and whole-task cost as one complete outcome family;
- exclusion and reporting, never imputation, for missing labels;
- one held-out evaluation after sealing;
- every stage, child, retry, repair and abandoned task in total cost; and
- retention of the baseline when the result is inconclusive.

Its seal is content addressed and explicitly denies study execution, promotion and
activation authority.

## Independently graded label inventory

The inventory command accepts only an `IndependentLabelCatalog` and a separately
supplied `GradingTrustPolicy`. Each opaque case digest needs two Ed25519-signed claims from
distinct enrolled identities and keys. A claim contains case and independence-group
identities, split, clean/defective class, finding count, source/sampling frame,
reviewed sampling-manifest digest, selection probability, label-observation probability
and rubric identity. It cannot
contain a brief, expected-finding text, transcript, model response or session outcome.

Case and independence-group references are SHA-256 digests, not session names; joining
them to private cases requires a separately controlled mapping. Both graders must agree
on all decision metadata. A disagreement remains visible but ineligible. Unknown
selection or label-observation probability is also ineligible;
the inventory does not impute either value. Eligible independence groups may not
cross calibration and holdout. The seal additionally requires clean and defective
labels plus a random ordinary-task audit in both splits.

Distinct valid keys authenticate exact claims; they do not prove physical grader
independence or representative sampling. Those remain accountable study-owner and
independent-review responsibilities.

```sh
uv run --frozen mos eval-inventory-labels \
  --catalog private/label-catalog.json \
  --grading-trust-policy private/label-trust-policy.json \
  --output private/eligible-label-inventory.json

uv run --frozen mos eval-seal-context-policy \
  --policy private/context-policy.json \
  --catalog private/label-catalog.json \
  --grading-trust-policy private/label-trust-policy.json \
  --label-inventory private/eligible-label-inventory.json \
  --output private/sealed-context-policy.json
```

Both outputs are written privately. Neither command reads an evaluation dataset or
session store, and neither accepts a holdout-session path.

## Current production inventory

Repository and tracked-artifact inspection on 2026-09-21 found no production
`IndependentLabelCatalog`, no enrolled G3 label-grading trust policy and no sealed
G3 context-study policy. Therefore the truthful current production inventory is zero
verified eligible labels and zero sealed executable arms. Synthetic unit-test claims
exercise the contracts only; they are not empirical evidence. Supplying real private
signed claims and reviewed arm/resource digests is the next external input.
