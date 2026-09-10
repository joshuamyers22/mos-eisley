# Milestone 88 adversarial review: cache-write spending

## Disposition

Accept as a fixture-validated spending prerequisite only. This milestone does not
authorize a credential, transfer, reservation, provider request, campaign run,
retry, grading, scoring, promotion, or routing activation.

## Findings and controls

- **A schema-1 policy could understate cache-write exposure.** Schema 2 requires an
  explicit cache-write rate at least as high as the ordinary input rate. The future
  campaign executor must reject schema 1.
- **Actual cache-write usage is unknown before sending.** Admission reserves every
  input token at the cache-write rate. Settlement charges ordinary input plus only
  the reported cache-write-rate delta.
- **Provider usage can be missing or incoherent.** Missing, negative, or non-integer
  schema-2 cache-write usage retains the full reservation as `uncertain`. A count
  above total input is a `violation` and blocks the shared ledger.
- **Cache reads could tempt an unsafe discount.** Neither reservation nor settlement
  applies a cache-read discount. This overstates rather than understates exposure.
- **A provider report arrives after financial exposure.** Post-response validation
  cannot undo a charge. Full-reservation retention makes that uncertainty visible;
  it is not a refund or invoice reconciliation.
- **Adding a field could invalidate existing signed artifacts.** Schema-1 policies
  and receipts omit the new optional field from canonical bytes. Regression tests
  preserve that representation while schema 2 opts into the new contract.
- **Prices and cache semantics can change.** Rates remain short-lived operator
  assertions sourced from current official model pages. There is no trusted live
  price feed, so every paid campaign decision must recheck policy freshness.
- **A unit-only change could miss composed paths.** Tests cover the shared transport
  failure modes, a signed Responses canary from authorization ceiling through
  ledger settlement and offline replay verification, and exact schema-2 settlement
  at the separate skill-runtime transaction boundary. Existing suites also protect
  schema-1 compatibility.

## Residual risks

The local ledger is not an account-wide billing cap, provider usage is not an
invoice, and a process or power failure may leave exposure unresolved. These limits
remain fail-closed and do not justify automatic retry or budget release.
