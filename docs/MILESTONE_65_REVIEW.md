# Milestone 65 adversarial review: second Sol/medium live conformance success

## Disposition

Accepted as the second consecutive authenticated success for the exact
`gpt-5.6-sol` / `medium` profile under the frozen OpenAI live-conformance gate.
Rejected as profile or overall gate completion, provider-authorship proof, billing
reconciliation, quality evidence, complete-batch conformance, grading, scoring,
promotion, routing activation, or authority for another request.

## Retained evidence

The live run on 2026-09-08 remained bound to the second private campaign manifest
commitment
`c16548cebc197d4515a8cb01226201e1db23412de4c1b92d3bd5ec2e1853b5c8` and shared
ledger `3a70da17b19c50af40722f1746e3ab9b0a0eb5ce32851a89029cfe9a656bfae7`.
The exact conformance-policy digest was
`851ac4475539bba434f0b6ed004b7b1164e76ae3dc7e9c2bfb93ee0affb4962f`, and the
independently signed transfer-and-spend authorization digest was
`e14704155abc57b4a41fdcc0ffa3766a96dcfb8d780405a7492076f41d2ae4ae`.

The zero-retry broker finished with a strict response and settled 4,712 micro-USD
against the 14,240 micro-USD maximum. Usage was 393 input tokens and 157 combined
visible/reasoning output tokens, including 132 reported reasoning tokens; measured
latency was 6,887 ms. The artifact digest is
`0374bb0cb8fb5637e4f0fcca2fac60dac70527e9aaf505a7653636407e7daf1b`, its retained
provider-response digest is
`6ad4bcb032db6f5ad070485c3c3986005f2532ad719cd6716d0c2f69d3bd1e13`, and the
observer-signed record digest is
`47996c433dbe52b3190676bef9feb269224bc9116c2e5187b7b47c0c4d3a4ccd`.
Fresh authentication produced receipt digest
`5847b091dde250c619f9c95e855f38f22ed40d3746f9cd5ae30f8ec2ee57427a`.

The first no-send preparation for this sequence had authorization digest
`4605f11869cdf6e5d47826ca21cca14126f03537246da426973a84f39e6835cb` and expired
before signature. It accessed no credential, reserved no spend, and made no provider
request. Its private directory was archived before the canonical attempt path was
regenerated with the same sealed assignment and fresh time-bounded policies.

No prompt, response content, reasoning, credential, signing key, or raw provider body
is published by this record. Private artifacts retain the complete verification
lineage.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| An expired authorization is silently reused | Reject signing after expiry, retain the expired preparation, and derive a fresh exact authorization | Host clock and private archival custody remain trusted |
| Regeneration changes the committed assignment | Rebind the same manifest sequence, sample, request, model, effort, ledger entry, caps, and maximum | The local regeneration implementation remains trusted |
| An unexecuted preparation is counted as a provider failure or omitted provider attempt | State that it ended before credential access, reservation, or send and distinguish it from live chronology | The no-send facts rely on retained local evidence |
| Two Sol/medium successes complete the profile | Count exactly 2 of 3 and preserve every downstream denial | One further precommitted consecutive Sol/medium success remains |
| A local settlement is presented as provider billing | Report only the controller's 4,712 micro-USD settlement and keep reconciliation false | Separate aggregate billing evidence remains required |
| A successful response establishes quality or routing suitability | Keep grading, scoring, quality, conversion, promotion, and routing false | Later authorized evaluation and holdout gates remain required |

## Gate progress

This receipt advances the frozen matrix to 11 of 18 authenticated successes overall.
Luna/low and Terra/medium are complete at 3 of 3, Sol/medium is 2 of 3, and Sol/high,
Astra/high, and Astra/max are each 1 of 3. The second campaign ledger has five settled
entries, 14,717 micro-USD charged, 285,283 micro-USD available, and no unresolved or
blocking state. Seven precommitted successes and five failure-boundary results remain
before calibration conversion can be considered.
