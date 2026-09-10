# Milestone 55 adversarial review: first Terra/medium live conformance success

## Disposition

Accepted as one authenticated success for the exact `gpt-5.6-terra` / `medium`
profile under the frozen OpenAI live-conformance gate. Rejected as provider-authorship
proof, billing reconciliation, quality evidence, complete-batch conformance, grading,
scoring, promotion, routing activation, or authority for another request.

## Retained evidence

The live run on 2026-09-08 remained bound to the private campaign manifest commitment
`de6cab4d2bc1ad9df7319bf1edd002e3cdeb44596cd8dfc8a4dffb8086665ccc` and shared
ledger `890cd5473e7aad939edeae29a568ce1b44c614a091e4ac5404e96fa422f4467e`.
The exact conformance-policy digest was
`1c65cc2051b32a43088feffff5740d139f56728d49888779ee7e7c2d66148c7e`, and the
independently signed transfer-and-spend authorization digest was
`ffd1f1397660954c5cbfa788da132cfe057839720bf7ec0030b8e0e629ffccab`.

The zero-retry broker finished with a strict response and settled 3,468 micro-USD
against the 8,144 micro-USD maximum. Usage was 384 input tokens and 225 combined
visible/reasoning output tokens; measured latency was 6,642 ms. The artifact digest is
`8cb2651222ac92f15b1ddc9e650b07db98035e16641038d55dff2f5579b60c8e`, its retained
provider-response digest is
`55623474107a1612031ef017affaccaf6a84b905b848f19022f9a4bacd5d2371`, and the
observer-signed record digest is
`9cc6463713aabe0ab05668fbf9f524e44a3c35a6e40cb7c821c7626fb3012bb1`.
Fresh authentication produced receipt digest
`fffa00ba00a4ccc98f12b49a9879b535ace1ebf0af4efc8a9124408ca7806ab6`.

No prompt, response content, reasoning, credential, signing key, or raw provider body
is published by this record. Private artifacts retain the complete verification
lineage.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A successful HTTP call is called conformance | Require the prepared policy, independent execution signature, explicit consent, exact broker audit, settled ledger, observer signature, and fresh authentication | The observer and local host remain trusted |
| An expired preparation is silently omitted | Retain the expired unsigned no-send package and state that it never crossed the credential boundary | Private evidence custody is local |
| One result is generalized to the profile or batch | Count exactly one of three required consecutive Terra/medium successes | Two new precommitted Terra/medium successes and all other gate work remain |
| Local cost is described as provider billing proof | Report only the controller's 3,468 micro-USD settlement and keep billing reconciliation false | Separate aggregate billing collection and reconciliation remain required |
| Response ID or TLS transport is treated as provider authorship | Preserve response and transport digests while fixing provider authorship false | Stronger external/provider evidence is not available here |
| Successful output enables routing | Keep grading, scoring, conversion, quality, promotion, and activation false | Full live gate, calibration, holdout, and promotion gates still apply |

## Gate progress

This receipt advances the frozen matrix to 2 of 18 authenticated successes overall:
Luna/low is 1 of 3 and Terra/medium is 1 of 3. Sol/medium, Sol/high, Astra/high, and
Astra/max remain 0 of 3. Four probes remain in the initial sealed campaign; even if
all four succeed, 12 further precommitted successes and five failure-boundary results
remain before calibration conversion can be considered.
