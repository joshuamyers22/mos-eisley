# Dual-lineage observation compilation

Mos Eisley can join a verified `DualGradingResolution` back to the private
evaluation mapping without collapsing its provenance into a single-grader
artifact. The resulting `DualGradedObservationSet` binds the dataset, sweep plan,
execution batch, private mapping, raw results, grading batch, both trust policies
and the complete dual-grade artifact digest.

This compiler is offline and makes no provider calls. It first reconstructs the
route-blind grading batch from the dataset → plan → execution batch/map → raw
result chain and requires exact equality with the supplied packet. It then
reverifies both grader signatures, the independently signed conflict resolution,
and the derived final judgments before joining sample IDs to private case and route
identities. Stored derived judgments and observations are recomputed, not trusted.

```console
mos eval-compile-dual \
  --dataset eval/dataset.json \
  --plan private/holdout-plan.json \
  --batch private/holdout-batch.json \
  --mapping private/holdout-map.json \
  --raw-results private/holdout-raw.json \
  --grading-batch private/holdout-grading.json \
  --dual-grading-resolution private/holdout-dual-resolution.json \
  --grading-trust-policy trusted/human-graders.json \
  --resolution-trust-policy trusted/conflict-resolvers.json \
  --output private/holdout-dual-observations.json
```

The output is exclusively created with mode 0600 and reports literal
`promotion_eligible: false`. It deliberately uses a different schema from the
legacy `ObservationSet`; `eval-score` rejects it. Use
`verify_dual_graded_observations` with every independently supplied source artifact
to rederive and compare a stored result.

The observation artifact stores a digest link rather than embedding the already
large `DualGradingResolution`. Retain both files together. Deleting the source
artifact does not change the hash, but makes independent revalidation impossible.

## Remaining boundary

This step establishes authenticated grading lineage through observation
compilation. It does not establish that the human labels are correct, that graders
were independent, or that the evaluation sample is representative. It also does
not authorize scoring or routing changes. A later scorer must accept this distinct
contract explicitly, retain its lineage digests in the report, and remain
non-promotable until the empirical and operational release gates are satisfied.
