# Adjudication authentication

Mos Eisley can authenticate one route-blind human adjudication before it enters the
dual-grade disagreement-resolution workflow. This replaces a self-asserted grader ID
with proof that the exact canonical `AdjudicationSet` was signed by the private key
corresponding to an independently trusted Ed25519 public key.

The signing message is domain-separated as
`mos-eisley/adjudication-signature/v1\0` followed by canonical adjudication JSON.
The signature envelope binds the adjudication digest, signer ID, public-key digest,
algorithm and 64-byte signature. Public keys and signatures use canonical base64;
noncanonical encodings and incorrect lengths fail closed. The implementation uses
the [Cryptography Ed25519 interface](https://cryptography.io/en/stable/hazmat/primitives/asymmetric/ed25519/),
whose verification operation raises on an invalid signature.

A `GradingTrustPolicy` names at least two human adjudicators, assigns each a unique
32-byte public key, and binds the grading rubric. Duplicate identities and key reuse
are rejected. The policy is trusted input: distribute and review it independently
of the signed grading files. Its hash is included in every authentication receipt.

Private keys stay in each grader's environment. Mos Eisley's library
`sign_adjudication` helper accepts raw 32-byte private-key material for integration
with a grader-controlled signer, but the controller CLI has no key-generation or
signing command. Give the controller only the signed envelope and public trust
policy. It verifies complete finding coverage while permitting explicit unresolved
decisions for the later resolution stage:

```console
mos eval-authenticate-adjudication \
  --grading-batch private/holdout-grading.json \
  --signed-adjudication grader-a/signed-adjudication.json \
  --trust-policy trusted/human-graders.json \
  --output private/grader-a-authenticated.json
```

The output is an exclusively created private artifact containing the signed
adjudication and hashes of the grading batch and trust policy. It can be reverified
with `verify_authenticated_adjudication`; the private key is never stored. Changing
the adjudication, signer, rubric, batch, key, signature, or policy invalidates the
chain.

## Limits

Authentication proves possession of the trusted private key over exact bytes. It
does not prove who physically controlled that key, whether a human actually graded
the packet, whether the completion timestamp is accurate, whether graders were
independent, or whether judgments are semantically correct. Key enrollment,
rotation, revocation, secure hardware and policy distribution remain operator
responsibilities. Python cannot guarantee erasure of private-key bytes supplied to
the signing helper.

Authentication receipts are consumed by
[`eval-resolve-adjudications`](DUAL_GRADE_RESOLUTION.md), which requires two
authenticated graders and a disjoint signed resolver for any conflicts. The older
`eval-agreement` and `eval-compile` commands remain offline rehearsal surfaces;
the dual-grade artifact is accepted only by the dedicated
[`eval-compile-dual`](DUAL_LINEAGE_OBSERVATIONS.md) path, whose distinct observation
schema is not accepted by scoring and explicitly reports
`promotion_eligible: false`.
