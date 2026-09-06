# Skill runtime publication witness

Mos Eisley can now derive, independently sign, and verify a portable hash-only
checkpoint of the ordered skill-runtime response-publication history. If the signed
checkpoint is retained outside the response store, a later verifier can detect a
deleted, reordered, or divergent prefix without reading or exporting provider
responses or published assistant text.

## Rolling history commitment

The private response store first performs its existing full validation of every raw
response, published result, manifest, transaction, and ledger relationship. It then
computes a domain-separated rolling digest over publication-manifest digests in their
explicit immutable sequence. Response-store policy schema version 2 adds and validates
that sequence instead of relying on SQLite's mutable implicit `rowid`. The history
artifact contains only:

- the response-store policy digest;
- publication count and rolling history digest; and
- latest publication ID and manifest digest.

The raw responses and published results are explicitly absent. A checkpoint for the
first N publications remains verifiable after legitimate publications N+1 onward. A
missing, reordered, or changed record at or before N changes the prefix digest and
fails verification.

## Witness policy and signature

The witness policy pins the response store, validity window, maximum checkpoint age,
minimum publication count, and canonical trusted Ed25519 witness identities and keys.
A signable checkpoint binds that policy, the exact history commitment, and an explicit
UTC witness time. The CLI never accepts a signing private key.

Verification authenticates the domain-separated Ed25519 signature, policy and
checkpoint freshness, and exact history prefix against the current private response
store. The resulting artifact fixes retry, budget release, content export, external
retention proof, and proof that this is the latest external checkpoint to false.

```console
mos eval-derive-skill-runtime-publication-checkpoint \
  --response-store private/runtime-responses.sqlite \
  --witness-policy trusted/publication-witness-policy.json \
  --witnessed-at 2026-09-06T22:00:00+00:00 \
  --output private/publication-checkpoint.json

mos eval-verify-skill-runtime-publication-checkpoint \
  --signed-checkpoint trusted/signed-publication-checkpoint.json \
  --witness-policy trusted/publication-witness-policy.json \
  --response-store private/runtime-responses.sqlite \
  --at 2026-09-06T22:01:00+00:00 \
  --output private/verified-publication-checkpoint.json
```

The unsigned checkpoint must be signed outside this CLI and the signed copy must be
retained in a genuinely separate trust or storage domain for rollback detection to
survive replacement of the local store.

## Deliberate limits

A locally created or locally retained checkpoint is not an external witness. A valid
old checkpoint cannot prove that it is the newest checkpoint another system has seen;
an attacker who can replace the store and suppress a newer checkpoint can present a
matching older pair. The witness may lie, lose its key, or collude. Host clocks, key
custody, external delivery, retention, availability, and hardware durability remain
operator responsibilities. The checkpoint says nothing about provider authorship,
billing, model quality, or whether a live request should be retried.
