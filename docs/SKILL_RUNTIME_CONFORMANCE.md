# Skill runtime OpenAI conformance attestation

Mos Eisley can now record and authenticate a trusted observer's narrow claim that one
content-verified skill-runtime publication came from an observed credentialed OpenAI
production exchange. This is a verification-only evidence layer. It neither sends a
request nor accepts a provider credential or signing private key.

## Pinned observation

The conformance policy pins the exact response-store policy, validity window, maximum
observation age, trusted Ed25519 observer identities and keys, and an allowlist of
reviewed OpenAI SDK versions. It also fixes the OpenAI production origin, Responses
API family, API-key credential mode, official SDK requirement, zero automatic retries,
`store=false`, and disabled truncation.

The signable observation binds:

- the exact publication, result, transaction, response-store policy, model, effort,
  and provider request ID;
- the observed SDK version and a digest of separately retained redacted transport
  evidence; and
- explicit claims that the bounded HTTP client and credentialed exchange were
  observed.

It also fixes provider authorship proof, billing reconciliation, quality, promotion,
and routing activation to false. A signature authenticates the enrolled observer's
statement; it does not independently establish that the statement is true.

Authentication verifies the Ed25519 signature and trust policy, observation and
policy freshness, allowlisted SDK version, and the exact publication loaded from the
private response store. That store revalidates the canonical retained response and
its settled transaction lineage. The authenticated artifact contains hashes and
metadata only, not the prompt, assistant text, private reasoning, raw response, API
credential, or signing key.

## Verification-only CLI

Derivation requires explicit acknowledgement that the operator actually observed a
credentialed exchange. It produces unsigned metadata for out-of-process signing:

```console
mos eval-derive-skill-runtime-conformance \
  --response-store private/runtime-responses.sqlite \
  --publication-id PUBLICATION_SHA256 \
  --conformance-policy trusted/runtime-conformance-policy.json \
  --observed-at 2026-09-06T21:00:00+00:00 \
  --sdk-version 2.54.0 \
  --transport-evidence-sha256 EVIDENCE_SHA256 \
  --attest-credentialed-exchange \
  --output private/conformance-observation.json

mos eval-authenticate-skill-runtime-conformance \
  --signed-observation trusted/signed-conformance-observation.json \
  --conformance-policy trusted/runtime-conformance-policy.json \
  --response-store private/runtime-responses.sqlite \
  --at 2026-09-06T21:01:00+00:00 \
  --output private/authenticated-conformance.json
```

The CLI has no signing operation and does not inspect the evidence named by its
digest. Creating a truthful signed observation and retaining trustworthy redacted
transport evidence remain operator responsibilities.

## Deliberate limits

The attestation does not prove TLS peer identity, provider authorship, credential use,
account ownership, request receipt, invoice correctness, absence of upstream retries,
or model quality. The trusted observer and policy enrollment can lie or collude. Local
database rollback and evidence replacement still need an external monotonic witness.
One separately authorized paid run is conformance evidence only and must never enter
empirical model-routing promotion as a quality sample.
