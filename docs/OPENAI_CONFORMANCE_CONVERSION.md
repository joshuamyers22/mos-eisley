# Offline OpenAI conformance conversion

`eval-convert-openai-conformance` projects only the 18 qualifying records from the
reviewed OpenAI live-conformance gate into a private partial calibration seed. It is
an offline lineage conversion, not a provider command, a complete evaluation run, or
a quality decision.

The committed
[`openai-conformance-conversion-v1.json`](../policies/openai-conformance-conversion-v1.json)
policy pins the exact aggregate-report, plan, batch, six profile, and 18 position
commitments. The command requires that exact gate report, the frozen 360-assignment
batch, and exactly 18 authenticated conformance receipts plus their 18 matching
brokered artifacts. Input order is irrelevant; sample identity restores frozen batch
order.

The converter verifies the aggregate's pass state, all 23 execution positions, five
failure boundaries, 20 reauthenticated successes, two explicit historical
exclusions, all six three-success profile streaks, and every downstream denial. It
then matches each qualifying gate entry to the canonical receipt, artifact,
assignment, route, request, response, authorization, outcome, ledger entry, latency,
cost, usage, and critique. The aggregate report's exact committed digest is the trust
anchor for its earlier full source reauthentication; the converter does not replace
that ceremony or independently reopen its audits and ledgers.

The command refuses to run while `OPENAI_API_KEY` or `MOS_OPENAI_KEY` is present and
requires explicit `--allow-offline-conversion`. It imports no provider client and
has no transport or spending path.

```console
mos eval-convert-openai-conformance \
  --batch .mos-eisley/eval/calibration-batch.json \
  --gate-report private/openai-live-conformance-gate-v1/report.json \
  --conversion-policy policies/openai-conformance-conversion-v1.json \
  --authenticated-conformance private/receipt-01.json \
  --artifact private/artifact-01.json \
  ...repeat the two source options for all 18 qualifying samples... \
  --output private/openai-live-conformance-gate-v1/calibration-seed.json \
  --allow-offline-conversion
```

The output is `openai_conformance_partial_calibration_seed`, not `RawResultSet`.
It records 18 converted assignments against the 360-assignment batch and fixes
complete-batch coverage, raw-result issuance, provider authorship, billing,
quality, grading, scoring, promotion, routing activation, and another provider
request to false. The seed includes route identity and must never be supplied to a
grader. A later reviewed boundary must obtain and validate complete calibration
coverage before creating route-blind grading material.
