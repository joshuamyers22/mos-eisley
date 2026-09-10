# Skill runtime aggregate billing evidence

Mos Eisley can authenticate a billing auditor's narrow claim that complete OpenAI
organization usage and cost exports for an exclusive one-request scope match one
content-verified runtime publication. This is evidence reconciliation, not a provider
receipt, invoice-finality proof, refund instruction, or permission to send again.

## Why the claim is aggregate

OpenAI's organization [completion usage API](https://developers.openai.com/api/reference/python/resources/admin/subresources/organization/subresources/usage/methods/completions)
supports one-minute buckets and grouping by project, API key, model, and service tier.
Its [costs API](https://developers.openai.com/api/reference/python/resources/admin/subresources/organization/subresources/usage/methods/costs)
uses one-day buckets and can group by project, API key, and line item. Neither documented
schema exposes a Responses API response ID. Mos Eisley therefore requires an auditor to
attest that the complete grouped scope contains exactly one model request, while every
artifact explicitly records that exact request-cost attribution is not proven.

The signable observation binds:

- the fully reauthenticated conformance receipt and exact response-store publication;
- transaction, outcome, spend-ledger entry, model, effort, token counts, and local cost;
- exact matching externally observed token counts and aggregate cost;
- fixed one-minute usage and one-day cost windows containing the publication;
- hashes of project and API-key identifiers rather than their raw values;
- digests of separately retained complete usage and cost evidence; and
- an evidence retrieval time after both reporting buckets closed.

The policy pins both upstream policies, validity and freshness bounds, the documented
OpenAI endpoints and grouping dimensions, and trusted Ed25519 billing auditors. The
authenticator rejects an auditor identity or key enrolled as a conformance observer.

## Verification-only CLI

Derivation requires explicit acknowledgement that the operator has complete official
Admin API evidence and isolated the grouped scope to the one request. It never accepts
an OpenAI credential or signing private key:

```console
mos eval-derive-skill-runtime-billing-evidence \
  --authenticated-conformance private/authenticated-conformance.json \
  --conformance-policy trusted/conformance-policy.json \
  --response-store private/runtime-responses.sqlite \
  --billing-policy trusted/billing-policy.json \
  --external-input-tokens 12 --external-output-tokens 7 \
  --external-cost-microusd 42 \
  --usage-bucket-start 2026-09-06T22:29:00+00:00 \
  --usage-bucket-end 2026-09-06T22:30:00+00:00 \
  --costs-bucket-start 2026-09-06T00:00:00+00:00 \
  --costs-bucket-end 2026-09-07T00:00:00+00:00 \
  --project-id-sha256 PROJECT_ID_SHA256 \
  --api-key-id-sha256 API_KEY_ID_SHA256 \
  --usage-evidence-sha256 COMPLETE_USAGE_EXPORT_SHA256 \
  --costs-evidence-sha256 COMPLETE_COST_EXPORT_SHA256 \
  --evidence-retrieved-at 2026-09-07T00:01:00+00:00 \
  --attest-complete-exclusive-billing-evidence \
  --output private/billing-observation.json

mos eval-authenticate-skill-runtime-billing-evidence \
  --signed-observation trusted/signed-billing-observation.json \
  --billing-policy trusted/billing-policy.json \
  --authenticated-conformance private/authenticated-conformance.json \
  --conformance-policy trusted/conformance-policy.json \
  --response-store private/runtime-responses.sqlite \
  --at 2026-09-07T00:01:30+00:00 \
  --output private/authenticated-billing.json
```

The manual fields can instead be replaced by `--collected-evidence` pointing to the
strict private bundle produced by
[`openai-billing-collect`](SKILL_RUNTIME_BILLING_COLLECTION.md). The completeness and
exclusivity acknowledgement remains mandatory because the documented aggregates cannot
prove all-day API-key exclusivity. Private-key custody remains outside both commands.
Derivation and authentication console output is hash-only and does not include prompts,
responses, raw billing pages, raw project/API-key identifiers, provider credentials, or
signing keys.

## Deliberate limits

The original manual path does not fetch or parse the evidence named by its digests. The
separate collector now fetches and strictly parses retained pages, but still cannot
prove daily exclusivity or response-level attribution. A trusted auditor or operator
can lie about scope isolation. OpenAI does not sign these artifacts through this
workflow. Cost exports may later receive adjustments, credits, taxes, or invoice-level
treatment, so matching a closed daily aggregate is not invoice finality. The
authenticated result cannot mutate the ledger, release reserved exposure, retry a
request, establish provider authorship, claim quality, promote a skill, or activate
routing.

A separately authorized credentialed conformance run is still required. Future work
must preserve the aggregate attribution limit unless OpenAI exposes a documented
request-bound billing receipt.
