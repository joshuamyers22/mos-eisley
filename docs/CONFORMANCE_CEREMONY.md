# OpenAI conformance ceremony preflight

Mos Eisley prepares one exact conformance policy without reading an OpenAI
credential, creating the broker audit, reserving money, starting Docker, or sending a
provider request. The resulting policy is required by the paid-capable
`openai-conformance` command, along with a separate
[signed execution authorization](EVALUATION_CONFORMANCE_AUTHORIZATION.md).

## Prepare the policy

An operator first supplies the blinded batch, reviewed spend policy, existing shared
ledger, planned fresh audit path, validity window, trusted observer records, and
allowed installed OpenAI SDK versions:

```console
mos eval-prepare-brokered-conformance-policy \
  --batch trusted/blinded-batch.json \
  --sample-id <sha256> \
  --spend-policy trusted/spend-policy.json \
  --spend-ledger private/spending.sqlite \
  --audit-dir private/audit-RUN \
  --policy-id openai-probe-1 \
  --valid-from 2026-09-06T12:00:00+00:00 \
  --valid-until 2026-09-06T12:30:00+00:00 \
  --max-observation-age-seconds 120 \
  --observer trusted/observer-a.json \
  --sdk-version 2.54.0 \
  --output trusted/conformance-policy.json
```

Observer records are strict `TrustedEvaluationConformanceObserver` JSON documents.
Repeated observers must be sorted by unique observer ID and use unique Ed25519 keys;
repeated SDK versions must be sorted and unique. Both lists are capped at 20. The
ceremony window must fit wholly inside the spend-policy window. The audit path must
not exist, its trusted parent must exist, and its deterministic ledger-entry identity
must be unused. Inputs, output, and planned audit may not overlap.

The prepared policy fixes the exact plan, batch, sample, candidate, evaluation
request, serialized OpenAI request, spend policy, shared ledger, ledger entry, audit
path indirectly through that entry, observer set, SDK allowlist, and time limits.
Console output explicitly records that credential access, provider send, and spend
reservation did not occur.

## Credentialed boundary

The later command must receive the same policy:

```console
mos openai-conformance \
  --batch trusted/blinded-batch.json --sample-id <sha256> \
  --spend-policy trusted/spend-policy.json \
  --spend-ledger private/spending.sqlite \
  --conformance-policy trusted/conformance-policy.json \
  --conformance-authority-policy trusted/conformance-authority-policy.json \
  --signed-conformance-authorization trusted/signed-authorization.json \
  --docker /usr/local/bin/docker --image sha256:<64-hex-image-id> \
  --audit-dir private/audit-RUN \
  --authorization-output trusted/authorization.json \
  --artifact-output private/conformance.json \
  --allow-data-transfer
```

Before reading `OPENAI_API_KEY`, Mos Eisley verifies the independent short-lived
transfer/spend signature, then reconstructs the request and assignment authorization,
checks every policy identity, verifies the installed `openai` package version, requires
both time windows to be current, ensures the policy covers the full request timeout,
rechecks the unblocked ledger and unused entry, and rechecks the fresh audit/output
layout. The spending controller still performs its atomic reservation after token
counting; this preflight does not reserve capacity and cannot eliminate concurrent
ledger changes.

The request contract keeps `store=false`, `truncation=disabled`, an explicit output
token ceiling, and zero automatic retries. OpenAI's
[Responses create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
documents storage control, disabled-truncation failure behavior, the combined visible
and reasoning output-token limit, response IDs, and usage fields.

## Limits

The policy is an operator-controlled local authorization input, not consent by OpenAI
or proof that an observer is independent. Local files, clocks, SDK installation, and
policy custody remain trusted. A same-UID attacker can replace local state or race
paths, and ledger rollback or cloning needs an external witness. Preparation neither
authorizes data transfer nor makes a paid request. One later successful probe remains
non-scoreable and does not prove provider authorship, exact billing, batch conformance,
quality, promotion, or routing activation.
