# Milestone 60 adversarial review: second OpenAI conformance campaign commitment

## Disposition

Accepted as a public commitment to 12 private, deterministic, unexecuted
live-conformance attempts. Rejected as authority to transfer any blinded brief,
access a credential, reserve or spend money, contact OpenAI, retry, grade, score,
promote, convert calibration data, or activate routing.

## Committed preparation

The manifest remains bound to blinded batch
`dc9dbc076e3e55f45b1edc610f6c85f9b70e63ea76cecdc81aff955c423108cb`
and plan `e8ddb3fcaf04422b745f858a575a3dceb90789dc54a45c168250b4b83eeb1411`.
It binds the authenticated receipt for the first success in each profile:

- Luna/low: `b0aca18fd42887e78bf810a786c885b9000f5ff9e5c552c094296f43181ca90c`
- Terra/medium: `fffa00ba00a4ccc98f12b49a9879b535ace1ebf0af4efc8a9124408ca7806ab6`
- Sol/medium: `5d2c467024975e2561b2f13a00f2fc39bee12f1a80ff7da7a13a1f5eeef95b8e`
- Sol/high: `d669d12e28f130ad7a6a65be4007700f3d8fa1f44b30b163df363f7119d8a28b`
- Astra/high: `6206bef3a29209c6879e2223e3b48df6d3873c66b3022c3b02fa0928fa78b5cd`
- Astra/max: `99062d546d5f833097eb4ee70e4d52073d0b85542ee6d7f40226774e2d9cbf90`

For each exact profile, the selector takes the two lexicographically smallest batch
sample IDs absent from that authenticated set. The resulting 12 IDs are distinct and
remain private. Execution order is fixed by ascending profile cost, then effort,
grouped by profile and sample ID. The manifest's success ordinal is a target matrix
position, not a claim about an unobserved outcome. Any non-success stops the campaign;
unused commitments and every terminal disposition must remain retained.

Official model pages checked on 2026-09-08 list standard input/output prices per
million tokens of $0.20/$1.20 for
[Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), $2/$12 for
[Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra), $4/$20 for
[Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol), and $10/$50 for
[Astra](https://developers.openai.com/api/docs/models/gpt-6-astra). Every attempt is
capped at 1,000 input and 512 combined visible/reasoning output tokens. Per-attempt
ceilings are therefore 815, 8,144, 14,240, and 35,600 micro-USD respectively.

The 12-attempt worst case is 217,278 micro-USD. A fresh ledger with identity
`3a70da17b19c50af40722f1746e3ab9b0a0eb5ce32851a89029cfe9a656bfae7`
has an immutable 300,000 micro-USD ceiling and 82,722 micro-USD headroom. It had zero
entries and zero charged exposure at sealing. The private manifest SHA-256 commitment
is `c16548cebc197d4515a8cb01226201e1db23412de4c1b92d3bd5ec2e1853b5c8`.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Samples are cherry-picked after outcomes | Select the next two unused IDs per profile by a fixed lexical rule and commit all 12 before new provider outcomes | Git and private-manifest custody remain trusted; the public repository is not an external timestamp service |
| Prior successes are substituted or an observed ID is reused | Bind and revalidate all six authenticated receipts; require disjoint, unique new IDs | Private artifact custody and host execution remain trusted |
| The target success ordinal is presented as an outcome | State that it is only a matrix target and require authenticated completion before counting it | A failed attempt breaks the profile streak and cannot be relabeled |
| Private labels influenced discretionary selection | Remove discretion through the exact lexical rule; the sealer never reads the label map | The operator session inspected the private map during legacy tracing, so operator/label separation is not proven |
| Per-attempt budgets conceal aggregate exposure | Bind all 12 maxima to one fresh 300,000 micro-USD ledger and stop on any non-success | Provider activity outside this ledger and ledger rollback remain out of scope |
| Price drift invalidates the maximum | Bind exact rates, official sources, check date, token caps, and service tier | A price change requires a new commitment before another request |
| The commitment itself triggers paid execution | Fix credential, send, transfer, reservation, conformance, retry, grading, scoring, promotion, and routing authority to false | Every attempt still needs a fresh policy, independent signature, and explicit local consent |
| An early failure is omitted while later probes continue | Fix execution order and `stop_after_any_non_success=true`; retain unused commitments and terminal state | Resumption requires reviewed root cause, regression evidence, and a new public commitment |

## Next gate

Prepare only the first committed Luna/low attempt using fresh short-lived spend,
conformance, and authority policies. The operator must review its exact bounded
authorization, sign independently, and provide explicit local data-transfer consent.
Authenticate any successful observation before moving to the next sequence number.
Any non-success halts the campaign. All results remain non-scoreable, and the five
frozen failure-boundary tests still remain after the success matrix reaches 18 of 18.
