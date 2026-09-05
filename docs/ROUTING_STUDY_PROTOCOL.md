# Pre-registered routing study protocol

Mos Eisley can now seal the design inputs for an empirical prompt-difficulty routing
study before calibration outcomes are inspected. This is a study-design artifact,
not a routing policy, recommendation, or activation grant.

The protocol fixes:

- a complete dataset and sweep-plan digest;
- a label-free feature manifest tied to each case's exact brief;
- numeric feature bucket boundaries and exact categorical partition fields;
- each role's reviewed candidate allowlist and conservative fallback;
- the cost-first selection objective and missing-cost behavior;
- simultaneous comparison across all profiles, routes, metrics, and both splits;
- fallback versus fail-closed behavior; and
- a freeze-before-single-holdout rule.

Numeric bins are part of the protocol so an analyst cannot redraw “easy” and “hard”
regions after seeing route performance. Role, output contract, tool requirements,
and risk tags remain exact. Tool and tag tuples, role constraints, candidate IDs,
and case assignments must use canonical ordering. Numeric upper bounds are inclusive;
values above the last bound enter a deterministic overflow bucket.

The feature manifest carries no expected findings or outcomes. `input_bytes` is
recomputed from canonical `Brief` bytes, the brief digest is checked, and risk tags
must equal the dataset's deterministic tags. Changed files, changed lines, language
count, role, output contract, and tool requirements remain operator-supplied
pre-dispatch assertions. Each resulting profile must contain clean and defective
cases in both calibration and holdout; sparse profiles fail sealing instead of being
silently pooled after results are known.

```console
mos eval-seal-routing-study \
  --dataset private/dataset.json \
  --plan private/sweep-plan.json \
  --feature-manifest private/prompt-features.json \
  --protocol reviewed/routing-study-v1.json \
  --output private/sealed-routing-study.json
```

The output is created mode 0600 without overwrite and includes the canonical
protocol plus every source digest and derived profile ID. Downstream code must call
`verify_sealed_routing_study` with independently supplied dataset, plan, and feature
manifest rather than trusting the receipt by itself.

## Deliberate limits

`activation_authorized` is literal `false`. The command accepts no observations,
scores, provider credentials, runtime configuration, or policy destination. It does
not fit a route, inspect calibration results, access holdout results, or modify model
selection.

Content addressing proves what was sealed, not when it was authored. A meaningful
study must publish or authenticate the sealed digest in an external, append-only
record before evaluation outcomes are available. Mos Eisley does not yet provide
that time-attestation service. Human review is also still responsible for feature
correctness, candidate floors, dataset representativeness, and independence groups.

Next, a calibration-only scorer must use the sealed partition and widen its
simultaneous confidence family across every profile. A separate policy freezer must
consume that report without holdout access. Only then may a one-time holdout command
measure under-routing, regret, and coverage; activation remains a later, separately
authorized boundary.
