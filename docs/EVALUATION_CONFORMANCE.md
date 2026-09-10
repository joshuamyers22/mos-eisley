# Authenticated brokered evaluation conformance

Mos Eisley can authenticate one trusted observer's claim that a successful
`openai-conformance` artifact came from a credentialed OpenAI Responses exchange.
This is a one-assignment conformance receipt, not a batch result, provider receipt,
billing reconciliation, or quality signal.

## Pre-registered policy

`EvaluationConformancePolicy` fixes the exact plan, blinded batch, sample, candidate,
evaluation request, serialized provider request, spend policy, ledger, and ledger
entry before the observation is accepted. It also pins a UTC validity window,
maximum observation age, sorted SDK allowlist, and sorted unique Ed25519 observer
identities and keys. The provider, endpoint origin, API family, credential mode,
command, SDK, bounded-client, isolated-broker, zero-retry, no-storage, and
no-truncation requirements are literals rather than caller-selected strings.

The policy is supplied as data; Mos Eisley does not create or distribute observer
keys. Policy custody, creation time, clock correctness, and organizational
independence remain operator responsibilities.

Use the no-send [conformance ceremony preflight](CONFORMANCE_CEREMONY.md) to derive
this policy from the exact assignment, spend scope, ledger, planned fresh audit,
observer roster, and SDK allowlist before any credential access. The paid-capable
command now requires that prepared policy and revalidates it before reading
`OPENAI_API_KEY`. It also requires an independent
[signed transfer and spend authorization](EVALUATION_CONFORMANCE_AUTHORIZATION.md)
whose authority is disjoint from every post-run observer.

## Derive, sign, and authenticate

After a separately authorized successful `openai-conformance` run, derive canonical
metadata with an explicit attestation:

```console
mos eval-derive-brokered-conformance \
  --batch trusted/blinded-batch.json \
  --artifact private/conformance-artifact.json \
  --expected-authorization trusted/authorization.json \
  --audit-dir private/audit-RUN \
  --spend-ledger private/spend.sqlite \
  --conformance-policy trusted/conformance-policy.json \
  --observed-at 2026-09-06T12:00:00+00:00 \
  --sdk-version 2.54.0 \
  --transport-evidence-sha256 <sha256> \
  --attest-credentialed-exchange \
  --output private/conformance-observation.json
```

The derivation command accepts no signing key. An enrolled observer signs the
canonical observation out of process with the domain-separated Ed25519 signing
contract. Authentication then consumes that signed file:

```console
mos eval-authenticate-brokered-conformance \
  --signed-observation trusted/signed-observation.json \
  --conformance-policy trusted/conformance-policy.json \
  --batch trusted/blinded-batch.json \
  --artifact private/conformance-artifact.json \
  --expected-authorization trusted/authorization.json \
  --audit-dir private/audit-RUN \
  --spend-ledger private/spend.sqlite \
  --at 2026-09-06T12:00:30+00:00 \
  --output private/authenticated-conformance.json
```

Both commands require the expected authorization outside the audit tree and reject
the audit's own file, symlink aliases, and hard links. All other input and output
artifacts must also remain outside the authoritative audit directory. Authentication
reparses every strict contract, verifies the observer key and signature, enforces
policy and observation freshness, and reopens the audit and ledger. The terminal
response hash, outcome hash, measured latency, settled entry, and charged micro-USD
amount must still match the exact broker artifact.

Console events expose hashes and status booleans, not prompts, critiques, usage,
provider request IDs, raw responses, credentials, or private keys.

## Deliberate limits

The receipt authenticates an enrolled observer's statement. It does not prove that
the observer is honest, that the opaque transport-evidence digest was independently
retained, or that OpenAI authored the response. The local audit has no terminal UTC
timestamp, so the observer supplies the observation time and the host clock remains
trusted. Aggregate billing, invoice finality, exact provider-side request cost, TLS
peer identity, and model quality remain unproven.

Only successful, settled, token-usage artifacts qualify. A failed broker outcome
cannot establish whether a provider send occurred, so failure conformance remains
closed rather than guessed. One authenticated probe does not prove complete batch
conformance and cannot convert `BrokeredEvaluationResultSet` into `RawResultSet`.
Policy, observation, authenticated receipt, and CLI output all fix batch conversion,
grading, scoring, quality, promotion, and routing activation to false.

Tests use locally generated keys and synthetic transport artifacts. No provider or
paid request is made by this milestone.
