# Signed OpenAI evaluation conformance authorization

Mos Eisley requires a short-lived independent Ed25519 authorization before the
paid-capable `openai-conformance` command may read `OPENAI_API_KEY`. This signature
supplements, rather than replaces, the explicit `--allow-data-transfer` confirmation.

## Trust policy and signable authorization

An operator supplies a strict `EvaluationConformanceAuthorityPolicy` containing a
UTC validity window, maximum authorization lifetime of at most one hour, and sorted
unique authority identities and public keys. Every authority identity and key must
be distinct from every post-run observer in the exact conformance policy.

Derive an unsigned authorization from the already prepared conformance policy and
its exact spend policy:

```console
mos eval-derive-brokered-conformance-authorization \
  --conformance-policy trusted/conformance-policy.json \
  --spend-policy trusted/spend-policy.json \
  --authority-policy trusted/conformance-authority-policy.json \
  --issued-at 2026-09-06T12:00:00+00:00 \
  --valid-until 2026-09-06T12:10:00+00:00 \
  --output private/conformance-authorization.json
```

The derivation command reads no credential or private key, reserves no money, creates
no audit, and sends nothing. It emits canonical authorization bytes for signing out
of process with the domain `mos-eisley/evaluation-conformance-authorization/v1`.
Mos Eisley's command-line paths never accept an authority private key.

The signature binds the authority-policy and conformance-policy hashes, exact plan,
batch, sample, candidate, evaluation and provider requests, spend policy, ledger,
ledger entry, maximum micro-USD exposure, issue time, and expiry. It explicitly
authorizes one exact blinded transfer, credential access, and bounded spend while
denying unblinded transfer, retry, automatic budget release, conversion, grading,
scoring, promotion, and routing activation.

## Paid-capable boundary

The live command now requires both trust artifacts:

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
  --authorization-output trusted/assignment-authorization.json \
  --artifact-output private/conformance.json \
  --allow-data-transfer
```

Before credential access, Mos Eisley reparses every strict contract, verifies signer
enrollment and the domain-separated signature, reconstructs the complete expected
authorization, enforces authority/observer separation and all nested validity windows,
and requires the signed window to cover the configured request timeout. The existing
ceremony preflight independently reconstructs the assignment authorization and checks
SDK, audit, and ledger freshness.

## Limits

The authority policy and signed file are locally supplied trust anchors; their
distribution, signer judgment, organizational independence, key custody, and clock
correctness remain external. A signature proves control of an enrolled key, not human
identity or informed consent. Same-UID state replacement, path races, and rollback or
cloning need stronger host or external monotonic controls. The fresh audit and output
boundaries prevent ordinary repeat dispatch, but this is not an external one-use
receipt. No provider request or spend occurs until the separately invoked live
command. A successful attempt still needs post-run observer authentication and remains
non-scoreable.
