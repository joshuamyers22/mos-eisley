# Milestone 57 adversarial review: first Sol/high live conformance success

## Disposition

Accepted as one authenticated success for the exact `gpt-5.6-sol` / `high` profile
under the frozen OpenAI live-conformance gate. Rejected as provider-authorship proof,
billing reconciliation, quality evidence, complete-batch conformance, grading,
scoring, promotion, routing activation, or authority for another request.

## Retained evidence

The live run on 2026-09-08 remained bound to the private campaign manifest commitment
`de6cab4d2bc1ad9df7319bf1edd002e3cdeb44596cd8dfc8a4dffb8086665ccc` and shared
ledger `890cd5473e7aad939edeae29a568ce1b44c614a091e4ac5404e96fa422f4467e`.
The exact conformance-policy digest was
`2196959e22c5b4f3fe7944335a4fc64e91a61f4515ccd3dd1f85553c67b15b36`, and the
independently signed transfer-and-spend authorization digest was
`fd709f784025539127f20a6580aaf3133e3221c57b0eaeb495dddb79136105f6`.

The zero-retry broker finished with a strict response and settled 3,008 micro-USD
against the 14,240 micro-USD maximum. Usage was 392 input tokens and 72 combined
visible/reasoning output tokens; measured latency was 5,625 ms. The artifact digest is
`d727507e3055a1887a1363ea9c6650decbeb09366b1c75a26ebe5dc19a2db901`, its retained
provider-response digest is
`da5d354cad889ef9863dc3c9eb21879e60ce53432b6e6c543d463a9be493542e`, and the
observer-signed record digest is
`2056680d372187255085b248bbe1c102273e8106e082347c98be8f83b587ed27`.
Fresh authentication produced receipt digest
`d669d12e28f130ad7a6a65be4007700f3d8fa1f44b30b163df363f7119d8a28b`.

No prompt, response content, reasoning, credential, signing key, or raw provider body
is published by this record. Private artifacts retain the complete verification
lineage.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A high-effort route is inferred from model name alone | Bind and reverify the exact serialized request and `high` route in policy, authorization, artifact, and observation | Provider-internal effort execution is not externally proven |
| A short high-effort response is called low quality or efficient | Record exact usage only and keep quality and scoring false | Quality requires blinded labels and repeated empirical evaluation |
| One high-effort response establishes Sol/high reliability | Count exactly one conformance success for the profile | Two new precommitted consecutive Sol/high successes remain |
| Local settlement becomes billing proof | Report only the controller's 3,008 micro-USD settlement and keep billing reconciliation false | Separate aggregate billing evidence remains required |
| Response identifiers imply provider authorship | Retain response and transport digests while fixing provider authorship false | Stronger external/provider evidence is not available here |
| Four total successes are confused with gate completion | Report the exact 4-of-18 matrix and leave conversion and activation disabled | Fourteen successes and five failure boundaries remain |

## Gate progress

This receipt advances the frozen matrix to 4 of 18 authenticated successes overall:
Luna/low, Terra/medium, Sol/medium, and Sol/high are each 1 of 3. Astra/high and
Astra/max remain 0 of 3. Two probes remain in the initial sealed campaign; even if
both succeed, 12 further precommitted successes and five failure-boundary results
remain before calibration conversion can be considered.
