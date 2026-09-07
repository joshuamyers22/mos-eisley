# Independently authorized OpenAI Responses canary

`openai-responses-canary` tests the narrow boundary that model metadata cannot:
whether one fixed `gpt-5.6-luna` text generation can complete through the Responses
API. It is not a user-prompt command, evaluation run, model-quality test, or routing
activation mechanism.

OpenAI's [Responses create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
defines `max_output_tokens` as covering visible and reasoning tokens and documents
that `store` defaults to true when omitted. The canary therefore fixes the request to
reasoning effort `none`, a 32-token output ceiling, `store=false`, disabled
truncation, standard service tier, foreground non-streaming operation, and no tools.
The [model catalog](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
documents Responses support and the selected reasoning level. OpenAI's
[data-control guide](https://developers.openai.com/api/docs/guides/your-data)
describes retention boundaries that `store=false` does not eliminate.

## Exact request and authorization

The request contains only fixed repository-owned synthetic text:

```text
Instructions: This is a synthetic API connectivity canary. Do not call tools.
              Return one short, non-empty acknowledgement.
Input:        Synthetic canary. Reply with OK.
```

Before credential access, an enrolled Ed25519 authority must sign a short-lived
authorization binding:

- the exact token-count and generation request hashes;
- fixed provider, model, reasoning level, service tier, output cap, and no-tool shape;
- authority policy, spend policy, ledger, fresh run-directory identity, and maximum
  micro-USD exposure;
- an exact timeout and validity window that covers it;
- two provider requests at most: one input-token count and one generation.

The authorization explicitly denies user-data transfer, retry, automatic budget
release, grading, scoring, promotion, and routing activation. The CLI never accepts
an authority private key. Signature creation is deliberately out of process using
`sign_openai_responses_canary_authorization` and the domain
`mos-eisley/openai-responses-canary-authorization/v1`.
The signable authorization includes the synthetic instructions and input in clear
text as well as their exact provider-request hashes, so the signer need not approve
an opaque prompt digest.

Create an authority policy containing a current UTC window, a maximum authorization
lifetime no greater than 3600 seconds, a request timeout no greater than 30 seconds,
and one or more sorted unique authority IDs and public keys. Then derive canonical
unsigned bytes without credential access, reservation, or network activity:

```console
mos openai-derive-responses-canary-authorization \
  --spend-policy trusted/spend-policy.json \
  --spend-ledger private/spending.sqlite \
  --authority-policy trusted/canary-authority-policy.json \
  --run-dir private/canary-001 \
  --timeout 10 \
  --issued-at 2026-09-07T19:00:00+00:00 \
  --valid-until 2026-09-07T19:10:00+00:00 \
  --output private/canary-authorization.json
```

An external signer must review those exact canonical bytes and return a
`SignedOpenAIResponsesCanaryAuthorization`. The live command then requires the
same immutable inputs and a separate local transfer acknowledgement:

```console
OPENAI_API_KEY="$MOS_OPENAI_KEY" mos openai-responses-canary \
  --spend-policy trusted/spend-policy.json \
  --spend-ledger private/spending.sqlite \
  --authority-policy trusted/canary-authority-policy.json \
  --signed-authorization trusted/signed-canary-authorization.json \
  --run-dir private/canary-001 \
  --timeout 10 \
  --allow-data-transfer
```

The command verifies the signature, reconstructs the authorization, checks all
windows, confirms the ledger is unblocked, can cover the maximum authorized exposure,
and has no path-derived entry, then preserves the exact trusted inputs before
dispatch. It repeats those checks at the dispatch boundary. Only then does it read
`OPENAI_API_KEY` and make the two
zero-retry official-SDK requests through the bounded identity-encoded HTTP client.

## Evidence and replay

A successful run privately stores the authority policy, signed authorization, spend
policy, exact request, spend reservation, settled receipt, canonical response, and a
manifest written last. The result records `responses_access_verified=true` only for
a completed, non-empty, tool-free text response whose model, service tier, usage,
request, authorization, and ledger entry all match. Reverify it without network or
credential access:

```console
mos openai-verify-responses-canary \
  --run-dir private/canary-001 \
  --spend-ledger private/spending.sqlite
```

If counting, generation, parsing, settlement, or final verification fails, no
completion manifest is written. Once a reservation exists, failure retains the full
uncertain exposure and cannot retry under the same directory/ledger identity.

## Limits

Canary success proves only that this credential completed the exact synthetic
Responses request at that time. It does not prove invoice attribution, billing
correctness, future availability, user-prompt safety, critic/judge conformance,
quality, grading eligibility, scoring, promotion, or routing activation. The
authority policy and signature are local trust inputs; signer identity, informed
judgment, organizational independence, key custody, clock correctness, filesystem
rollback, and same-UID interference remain external boundaries.
