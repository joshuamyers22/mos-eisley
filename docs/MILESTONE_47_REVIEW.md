# Milestone 47 adversarial review: provider failure classification

## Disposition

Accepted as privacy-preserving operator diagnostics. Rejected as proof of provider
receipt, exact remote cause, invoice state, or authorization to retry.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Every SDK failure becomes `provider_error` | Map typed SDK exceptions to a fixed category vocabulary | Provider SDK types can still combine several underlying causes |
| A token-count failure is confused with generation failure | Bind `token_count`, `response`, or coarse `exchange` stage into schema-4 audit evidence | Stage records local execution position, not remote receipt |
| Raw exception text leaks prompts, keys, account data, or upstream bodies | Persist only allowlisted enum values; discard messages and bodies at the broker boundary | Trusted process memory still briefly contains SDK exceptions |
| A transport rejection is mislabeled as definite network failure | Use `transport_error` for both connectivity and local bounded-transport rejection | Further distinction would require another carefully bounded signal |
| A 429 is always called ordinary throttling | Map only the exact SDK code `insufficient_quota` to `quota_error`; otherwise retain `rate_limit_error` | Provider code changes fall back conservatively and cannot be inferred from prose |
| New diagnostics retroactively embellish old evidence | Keep schema-1 through schema-3 audits readable without inventing a failure stage | Old generic failures remain generic permanently |
| Better diagnostics invite automatic retry | Recovery and failure artifacts retain literal `retry_permitted=false` | A replacement attempt still requires a new policy, authorization, audit, and consent |

## Verification status

Typed synthetic SDK failures cover authentication, permission, quota, rate limit,
not found, invalid request, transport, timeout, and generic fallbacks. Broker tests
verify safe stage/category propagation and prove raw upstream details do not enter
the audit. Automated tests make no provider requests.
