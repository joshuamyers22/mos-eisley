# Dual authenticated grading and conflict resolution

Mos Eisley can verify two route-blind human grades and, when they disagree,
require a third cryptographic authority to resolve every conflict. The resulting
`DualGradingResolution` retains both complete authentication receipts, the exact
agreement report, the signed resolution set and the derived final judgments.
Original grades are never overwritten.

This is an offline integrity gate. It makes no provider calls and its output has
literal `promotion_eligible: false`. `eval-compile` and `eval-score` do not accept
this artifact yet, so this milestone cannot silently alter model selection.

## Trust separation

Supply the original `GradingTrustPolicy` plus a separately distributed
`ResolutionTrustPolicy`. Both policies bind the same rubric. Every enrolled
resolver identity and public key must be disjoint from every enrolled grader
identity and key, including graders who did not participate in this comparison.
The two submitted grading receipts must also have different authenticated IDs and
keys.

These checks prove key separation, not organizational independence. The operator
must still control enrollment, key custody, packet isolation, conflict assignment,
rotation and revocation.

## Resolution contract

The controller reverifies both adjudication signatures, their complete grading
coverage, batch digest, rubric and grading-policy digest before comparing labels.
If all labels agree, supplying a resolution is prohibited and the left grade's
judgments become the derived result. Both signed originals remain embedded.

When conflicts exist, `ResolutionSet` must contain exactly one decision for every
`(sample_id, finding_index)` in the recomputed agreement report—no missing, extra
or duplicate decisions. A decision may choose either submitted label or another
valid rubric label. Normal adjudication validation then rejects unknown expected
IDs, changed finding hashes, invalid duplicate targets and unresolved outcomes.

The resolution message is domain-separated as
`mos-eisley/conflict-resolution/v1\0` followed by canonical resolution JSON. Its
signed contents bind all of the following:

- grading batch, grading trust policy and resolution trust policy digests;
- ordered hashes of both authenticated grading receipts;
- the recomputed agreement-report digest;
- resolver ID, rubric, completion timestamp and every conflict decision.

Ordering is intentional. Reversing the left and right receipts invalidates an
existing resolution instead of changing the interpretation of a signature.
The resolver timestamp cannot predate either declared grader timestamp. This only
rejects internally impossible chronology; none of these self-declared timestamps
is an external proof of time.

Private keys remain with graders and resolvers. The library helpers
`sign_adjudication` and `sign_resolution_set` accept raw 32-byte private-key
material for integration with signer-controlled processes. The controller CLI
accepts only signed artifacts and public-key policies; it does not generate or
store private keys.

```console
mos eval-resolve-adjudications \
  --grading-batch private/holdout-grading.json \
  --left-authenticated private/grader-a-authenticated.json \
  --right-authenticated private/grader-b-authenticated.json \
  --grading-trust-policy trusted/human-graders.json \
  --resolution-trust-policy trusted/conflict-resolvers.json \
  --signed-resolution resolver-a/signed-resolution.json \
  --output private/holdout-dual-resolution.json
```

Omit `--signed-resolution` only when the independently recomputed report contains
no conflicts. The output is exclusively created with mode 0600 and can be checked
again with `verify_dual_grading_resolution` against independently supplied batch
and policy artifacts.

## Residual limits

Signatures authenticate bytes and enrolled keys. They do not prove physical
identity, human authorship, timestamp accuracy, non-collusion or grading quality.
An authorized resolver remains able to choose a wrong but schema-valid label. The
artifact exposes that decision and its lineage for audit; it does not make it true.
The trust policies are operator-controlled inputs and have no external certificate,
revocation log or transparency service.

No statistical promotion claim follows from resolving disagreement. Calibration,
inter-rater monitoring, held-out scoring and the remaining production gates still
apply. Until a later reviewed compiler consumes this lineage directly, single-grade
`eval-compile` remains only an offline rehearsal surface.
