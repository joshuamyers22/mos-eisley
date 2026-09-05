# OpenAI preview spending control

`openai-run` requires `--spend-policy PATH` and an existing `--spend-ledger PATH`
([shared spending](SHARED_SPENDING.md)) in addition to an API key and explicit
data-transfer consent. This is a one-response generation-token cost admission
control, not an account-wide or invoice spending cap. No live evaluation sweep is
enabled by this change. Tests use synthetic rates and fake transports, not credits.

## Reviewed policy

Create a JSON policy using this template. Replace every angle-bracket placeholder;
the two rate placeholders must become JSON integers, not strings. The template
intentionally fails validation until reviewed. Check the exact model's current
[official pricing](https://developers.openai.com/api/docs/pricing) and account
terms; rates must conservatively cover the entire permitted input range and any
applicable pricing thresholds. There is no automatically trusted price feed.

```json
{
  "schema_version": 1,
  "model": "gpt-6-astra",
  "currency": "USD",
  "service_tier": "default",
  "pricing_source": "<reviewed official pricing URL and rate assumptions>",
  "valid_from": "<UTC ISO-8601 timestamp with timezone>",
  "valid_until": "<short-lived UTC ISO-8601 expiry with timezone>",
  "input_microusd_per_million": "<reviewed integer rate>",
  "output_microusd_per_million": "<reviewed integer rate>",
  "max_cost_microusd": 1000000,
  "max_input_tokens": 64000,
  "max_output_tokens": 4096
}
```

One USD is 1,000,000 micro-USD. For unit conversion only, a hypothetical $2 per
million tokens becomes `2000000`; that is not a quoted model price. The example
ceiling is $1 **per invocation**, not per day or project. Input is additionally
bounded by the existing prompt/instructions byte limits; the policy allows at
most 200,000 input tokens and 4,096 output tokens. Output includes reasoning.

```sh
uv run --frozen mos openai-run --prompt prompt.txt \
  --spend-policy spend-policy.json --spend-ledger spending.sqlite \
  --allow-data-transfer --json
```

The API key still comes only from `OPENAI_API_KEY`. Subscription-backed providers
are not implemented. The SDK endpoint is fixed to `https://api.openai.com/v1`;
environment proxy routing and HTTP redirects are disabled. Custom gateways are
not supported by this preview.

## Admission and reconciliation

1. Validate current policy, exact model, explicit text-only input and output cap.
   Reject tools, remote references and unsupported request parameters.
2. Send matching input/instructions/reasoning to the official token-count endpoint.
   **This already transfers prompt data**, even if generation is subsequently
   denied. Consent covers both calls. Counting is not an offline preflight, and
   this control does not establish or reserve any token-count endpoint charges.
3. Recheck expiry and input limit. Compute the ceiling, rounding up to micro-USD:
   `ceil((counted_input * input_rate + output_cap * output_rate) / 1000000)`.
   If it exceeds the policy ceiling, do not request generation.
4. Exclusively create and file-fsync `spend-reservation.json` before generation.
   Request standard service tier, `store=false`, disabled truncation and the
   reserved output cap. SDK retries are disabled; the controller is single-use.
5. Require nonnegative integer usage within the reservation and exact returned
   model/service tier. Persist a settled receipt using actual tokens at policy
   rates. Do not assume cache discounts or add reasoning a second time.

This follows OpenAI's [token counting guide](https://developers.openai.com/api/docs/guides/token-counting)
and the installed SDK's input-token count contract. The documented
[output cap](https://developers.openai.com/api/reference/cli/resources/responses/methods/create#responses-create-max-output-tokens)
covers visible and reasoning tokens. It is not a byte limit, so the application
also bounds decoded HTTP bodies before SDK JSON construction. The guard relies on the provider honoring
those contracts; a returned violation is detected after generation and cannot
undo charges. An alias resolving to a different returned model name fails closed
until credentialed conformance establishes an explicitly supported contract.

## Artifacts and limits

Successful runs include policy, reservation and receipt in the content-verified
manifest, with semantic checks against the result's usage. JSON completion output
includes `cost_upper_bound_microusd` and the policy hash. Legacy manifests remain
readable, but must not be interpreted as spending-controlled runs.

Timeouts, cancellation, missing/invalid usage and provider errors retain the full
reservation as `uncertain`; model/tier/count violations retain it as `violation`.
These are exposure records, not refunds or proof of the actual bill. A reservation
without a receipt must also be treated as uncertain. Failed runs have no completion
manifest and are not resumable. Even a settled receipt does not mean the agent
result parsed successfully; only the manifest marks complete output.

Policy provenance and rates are operator assertions, not authenticated pricing.
Checksums are integrity checks, not signatures against someone who can rewrite all
artifacts. The local directory and its ancestors must be trusted. File fsync does
not provide a transactional ledger across arbitrary filesystem/power failures.
The CLI additionally uses a transactional cross-process ledger for participating
local runs. It is not shared-account enforcement; there is no automatic retry,
resume, budget top-up, tax/fee accounting or total-invoice guarantee. Each new CLI
invocation requests new admission against that ledger. Provider errors are intentionally
generic; inspect private artifacts for completion state without disclosing secrets.

`BoundedOpenAIHttpClient` is the only HTTP client constructed by `openai-run`.
It forces non-streaming responses through a 1,000,000-byte decoded-body ceiling,
counts chunks incrementally, closes rejected bodies, and rejects a declared encoded
`Content-Length` above the ceiling early. Counting decoded chunks also rejects a
compressed body that expands beyond the limit. The same bound covers token-count
and error responses. Streaming SDK operations are disabled on this client; adding
streaming later requires a separate bounded event protocol and cancellation design.
The cap does not limit response headers, provider-side work, or charges already
incurred, and an accepted body still occupies up to the configured limit in memory.

The host-built [conformance request](OPENAI_CONFORMANCE.md) may add a strict
`text.format` JSON Schema. This output constraint is included in input-token counting
and in the exact request snapshot; it does not let the isolated worker alter the
schema or bypass output-token and cost ceilings.

Before live empirical sweeps: connect validated broker responses to live evaluation
provenance and complete explicitly authorized credentialed conformance. The bounded
HTTP client is synthetic-tested, not proof of provider behavior or invoice limits.
