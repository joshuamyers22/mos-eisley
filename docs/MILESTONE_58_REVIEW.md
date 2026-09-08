# Milestone 58 adversarial review: first Astra/high live conformance success

## Disposition

Accepted as one authenticated success for the exact `gpt-6-astra` / `high` profile
under the frozen OpenAI live-conformance gate. Rejected as provider-authorship proof,
billing reconciliation, quality evidence, complete-batch conformance, grading,
scoring, promotion, routing activation, or authority for another request.

## Retained evidence

The live run on 2026-09-08 remained bound to the private campaign manifest commitment
`de6cab4d2bc1ad9df7319bf1edd002e3cdeb44596cd8dfc8a4dffb8086665ccc` and shared
ledger `890cd5473e7aad939edeae29a568ce1b44c614a091e4ac5404e96fa422f4467e`.
The exact conformance-policy digest was
`c542282a1770bb151f939324e30b7b1cf20e2ce34ac144edbe7fc5fa4a7b6227`, and the
independently signed transfer-and-spend authorization digest was
`aa1ad495f43fc0041b63170e6bdbd341e9d66d4e1dd6ead6b52ede1d35817ce7`.

The zero-retry broker finished with a strict response and settled 18,050 micro-USD
against the 35,600 micro-USD maximum. Usage was 390 input tokens and 283 combined
visible/reasoning output tokens; measured latency was 9,569 ms. The artifact digest is
`f4c97cc7862c8be77c9c2b128560354d31953d5eef5ef97b3a352dd286eadfaa`, its retained
provider-response digest is
`bff96bbd3f6d2651383d18b5d6fc49f3f2d682e6fb5fab53d6ab4ef8bd9063e9`, and the
observer-signed record digest is
`3229235fba005d732343098849aa9163df023cdae6f1fc727c6135e1a2e50240`.
Fresh authentication produced receipt digest
`6206bef3a29209c6879e2223e3b48df6d3873c66b3022c3b02fa0928fa78b5cd`.

No prompt, response content, reasoning, credential, signing key, or raw provider body
is published by this record. Private artifacts retain the complete verification
lineage.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Model visibility is confused with a live Astra exchange | Require the exact broker artifact, settled audit, observer signature, and fresh authentication | The observer and local host remain trusted |
| High effort is inferred from the model label | Bind and reverify `high` in the exact request lineage | Provider-internal effort execution is not externally proven |
| A higher local cost is called provider billing | Report only the controller's 18,050 micro-USD settlement and keep reconciliation false | Separate aggregate billing evidence remains required |
| One Astra/high result establishes quality or reliability | Count exactly one conformance success and keep quality and scoring false | Two new precommitted consecutive Astra/high successes remain |
| Response identifiers imply provider authorship | Retain response and transport digests while fixing provider authorship false | Stronger external/provider evidence is not available here |
| Five successes are confused with campaign or gate completion | Report 5 of 18 and preserve every downstream denial | Astra/max, 12 further successes, and five failure boundaries remain |

## Gate progress

This receipt advances the frozen matrix to 5 of 18 authenticated successes overall:
Luna/low, Terra/medium, Sol/medium, Sol/high, and Astra/high are each 1 of 3.
Astra/max remains 0 of 3. One probe remains in the initial sealed campaign; even if
it succeeds, 12 further precommitted successes and five failure-boundary results
remain before calibration conversion can be considered.
