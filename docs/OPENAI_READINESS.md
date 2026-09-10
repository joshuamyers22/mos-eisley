# OpenAI model-readiness check

`mos openai-readiness` performs one narrow credentialed metadata request for one
explicit model in Mos Eisley's reviewed OpenAI registry. The default remains
`gpt-5.6-luna`; `--model` accepts only `gpt-5.6-luna`, `gpt-5.6-terra`,
`gpt-5.6-sol`, or `gpt-6-astra` in this release. It calls OpenAI's documented
[`GET /models/{model}`](https://developers.openai.com/api/reference/cli/resources/models/methods/retrieve)
endpoint through the official SDK. It sends the API key and model identifier, but
no prompt, instructions, evaluation sample, tool definition, or generation request.
The returned object must be `model` and its identifier must exactly equal the
selected registry entry.

This is a live provider request. The command therefore requires explicit
`--allow-provider-access`, reads the credential only from `OPENAI_API_KEY`, disables
SDK retries, environment proxies, redirects, and streaming, applies a maximum
30-second timeout, forces identity response encoding, retains a bounded decoded
response body if that preference is ignored, and closes the SDK client after the
single attempt. It never reads the conformance batch or spending ledger.

The output parent must already exist and the receipt path must be fresh. The file is
created privately and exclusively:

```console
mkdir -p private/readiness
OPENAI_API_KEY="$MOS_OPENAI_KEY" uv run --frozen mos openai-readiness \
  --model gpt-5.6-terra \
  --output private/readiness/gpt-5.6-terra.json \
  --timeout 10 --allow-provider-access
```

A successful receipt means only that the supplied API credential could retrieve
metadata whose object type and exact identifier matched the selected model. The
current [model catalog](https://developers.openai.com/api/docs/models) lists these
models as supporting the Responses endpoint, but the metadata check does not exercise
that endpoint. Therefore success does not prove:

- Responses API permission or a successful generation;
- usable billing, quota, rate limits, credits, or final invoice treatment;
- conformance with Mos Eisley's request/response boundary;
- quality, grading eligibility, scoring eligibility, promotion, or routing safety.

Those denials are literal fields in the receipt. The receipt cannot be passed to any
grading, scoring, conformance-authentication, or routing-activation command.

New receipts use schema 2. On a provider failure the same fresh receipt records only
one allowlisted category:
authentication, permission, quota, rate limit, not found, invalid request, transport,
timeout, or generic provider error. Transport failures add only one local allowlisted
detail: connection, protocol, response decode, response limit, or unknown transport.
SDK messages, response bodies, headers, account details, and credentials are
discarded. A failed attempt returns exit status 2 and is never retried automatically.
Prior schema-1 receipts are not modified or promoted. Because the Models API
documentation does not make a billing guarantee for this lookup, Mos Eisley does not
describe the request as free; it records only that no model-generation spend was
authorized.

Each command selects exactly one model and makes one request. There is no implicit
loop or campaign authorization; checking all campaign models requires separate
operator-acknowledged invocations and fresh outputs.

Automated tests use synthetic HTTP transports and make no live provider request.
