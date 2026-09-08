# Milestone 56 adversarial review: first Sol/medium live conformance success

## Disposition

Accepted as one authenticated success for the exact `gpt-5.6-sol` / `medium`
profile under the frozen OpenAI live-conformance gate. Rejected as provider-authorship
proof, billing reconciliation, quality evidence, complete-batch conformance, grading,
scoring, promotion, routing activation, or authority for another request.

## Retained evidence

The live run on 2026-09-08 remained bound to the private campaign manifest commitment
`de6cab4d2bc1ad9df7319bf1edd002e3cdeb44596cd8dfc8a4dffb8086665ccc` and shared
ledger `890cd5473e7aad939edeae29a568ce1b44c614a091e4ac5404e96fa422f4467e`.
The exact conformance-policy digest was
`04930a711a85f6ff05d1882a528065aca8e49aea9589d04742e89523048d47d0`, and the
independently signed transfer-and-spend authorization digest was
`1bf25e696cb0f66f8a17d9965fe08c8d0685717c04b9499ce8d060a7744369f8`.

The zero-retry broker finished with a strict response and settled 8,448 micro-USD
against the 14,240 micro-USD maximum. Usage was 377 input tokens and 347 combined
visible/reasoning output tokens; measured latency was 9,300 ms. The artifact digest is
`465a463a1d025d8c60fe7604479028dfdc5e5ddad92e12e336144afe8039deaf`, its retained
provider-response digest is
`2c6c312a9857d3c089395307a66a9bbb5d39617ad3a220427cbdaebabe9becb2`, and the
observer-signed record digest is
`f412c1e95518e777f427e37247f1fda593f31a08e140a9a557bc67d167410d4c`.
Fresh authentication produced receipt digest
`5d2c467024975e2561b2f13a00f2fc39bee12f1a80ff7da7a13a1f5eeef95b8e`.

No prompt, response content, reasoning, credential, signing key, or raw provider body
is published by this record. Private artifacts retain the complete verification
lineage.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Sol visibility is treated as a successful Responses exchange | Require a strict artifact, response-received audit, settled ledger, observer signature, and fresh authentication | The observer and local host remain trusted |
| Current promotional rates silently alter the sealed request | Require the fresh spend policy to match the campaign's committed $4/M input and $20/M output rates | A future price change requires a new commitment, not mutation |
| One medium-effort response establishes Sol quality | Count exactly one conformance success and preserve quality, grading, and scoring as false | Two new precommitted Sol/medium successes and empirical scoring remain |
| Local settlement becomes billing proof | Report only the controller's 8,448 micro-USD settlement and keep billing reconciliation false | Separate aggregate billing evidence remains required |
| Response identifiers imply provider authorship | Retain response and transport digests while fixing provider authorship false | Stronger external/provider evidence is not available here |
| A third total success is confused with gate completion | Report the exact 3-of-18 matrix and leave conversion and activation disabled | Fifteen successes and five failure-boundary results remain |

## Gate progress

This receipt advances the frozen matrix to 3 of 18 authenticated successes overall:
Luna/low, Terra/medium, and Sol/medium are each 1 of 3. Sol/high, Astra/high, and
Astra/max remain 0 of 3. Three probes remain in the initial sealed campaign; even if
all three succeed, 12 further precommitted successes and five failure-boundary results
remain before calibration conversion can be considered.
