# Credential-isolated OpenAI billing collection

Mos Eisley can collect the private OpenAI Admin API pages used by the aggregate
billing-evidence layer. Collection is a real account read, but it does not call a model
endpoint, send prompt data, sign evidence, or alter spending state.

The collector uses the official OpenAI SDK and the documented organization
[completion usage API](https://developers.openai.com/api/reference/python/resources/admin/subresources/organization/subresources/usage/methods/completions)
and [costs API](https://developers.openai.com/api/reference/python/resources/admin/subresources/organization/subresources/usage/methods/costs).
It disables automatic retries, inherited proxy settings, redirects, and streaming;
bounds every decoded response; follows every cursor to a coherent terminal page; and
caps page, bucket, result, identifier, and output sizes.

## Collection

Use a dedicated OpenAI Admin API key in the environment of a short-lived collector
process. The output path must be new and its parent must already exist.

```console
OPENAI_ADMIN_KEY=... mos openai-billing-collect \
  --authenticated-conformance private/authenticated-conformance.json \
  --conformance-policy trusted/conformance-policy.json \
  --response-store private/runtime-responses.sqlite \
  --billing-policy trusted/billing-policy.json \
  --project-id proj_example \
  --api-key-id key_example \
  --output private/collected-billing.json \
  --allow-account-billing-read
```

All policy, publication, time-window, identifier, and output preflight checks occur
before the credential is read. After access, the collector requires:

- one completed, UTC-aligned one-minute usage bucket containing one completion request;
- exact project, API-key, model, and default-service-tier grouping;
- one completed, UTC-aligned daily cost bucket with exact project/API-key groups;
- a complete non-repeating pagination chain and no duplicate cost line-item groups; and
- nonnegative totals representable as exact integer microusd.

The mode-0600 output retains the raw parsed pages because they are the evidence. It can
contain project and API-key identifiers and billing line items, so it is not a portable
or public artifact. Console output contains only paths, digests, match booleans, and
explicit authority denials. The Admin credential is never serialized.

## Derivation and signing boundary

The private bundle can replace the manually entered counts, windows, and page digests:

```console
mos eval-derive-skill-runtime-billing-evidence \
  --authenticated-conformance private/authenticated-conformance.json \
  --conformance-policy trusted/conformance-policy.json \
  --response-store private/runtime-responses.sqlite \
  --billing-policy trusted/billing-policy.json \
  --collected-evidence private/collected-billing.json \
  --attest-complete-exclusive-billing-evidence \
  --output private/billing-observation.json
```

Derivation revalidates the entire collection and requires exact token and cost equality
with the locally settled publication. It still requires the operator's separate
complete/exclusive-scope attestation. Collection does not possess an auditor signing
key; signing remains external and authentication remains a separate command.

## Deliberate limits

One completion request in one minute does not prove that the API key had no other
activity during the daily cost bucket. Other endpoint families, zero-cost activity,
credits, and later adjustments may not be visible as an additional completion request.
The documented cost rows contain no Responses API response ID. The collection contract
therefore records daily API-key exclusivity and exact request-cost attribution as false.

Admin reads reach OpenAI and require organization-level authorization even though no
model inference is requested. The host OS, process environment, SDK, TLS, provider
service, credential scope, and private-file custody remain trusted. No collected or
authenticated artifact authorizes ledger mutation, budget release, retry, invoice
finality, quality claims, promotion, or routing activation.
