# Milestone 61 adversarial review: second Luna/low live conformance success

## Disposition

Accepted as the second authenticated success for the exact `gpt-5.6-luna` / `low`
profile under the frozen OpenAI live-conformance gate and as the first completed
attempt from the second campaign. Rejected as provider-authorship proof, billing
reconciliation, quality evidence, complete-batch conformance, grading, scoring,
promotion, routing activation, or authority for another request.

## Retained evidence

The live run on 2026-09-08 remained bound to the second private campaign manifest
commitment
`c16548cebc197d4515a8cb01226201e1db23412de4c1b92d3bd5ec2e1853b5c8` and shared
ledger `3a70da17b19c50af40722f1746e3ab9b0a0eb5ce32851a89029cfe9a656bfae7`.
The exact conformance-policy digest was
`7c4ed0f59a70f22effce72d54d41b1b78f24e2dc49730fd471ea3773ac29b58a`, and the
independently signed transfer-and-spend authorization digest was
`1be5949c25bf13d2d67f0cea41669a71c0dafbe63be7527f7c9e7674fc64b4f8`.

The zero-retry broker finished with a strict response and settled 335 micro-USD
against the 815 micro-USD maximum. Usage was 377 input tokens and 216 combined
visible/reasoning output tokens; measured latency was 13,302 ms. The artifact digest
is `8fe97b3e140d390f1be885cf9092c1d31725f4759a3026f9199eb1f31002c957`, its retained
provider-response digest is
`7ca7822805e52c6446549eb4a76c4a363f8dd780b3a28d122d167592e97deaea`, and the
observer-signed record digest is
`7cda4ac80d72f5fbbcc5e512488e7ba3bf43844eb17f6642480cc114dc19224a`.
Fresh authentication produced receipt digest
`4008ed22573c71a0eea6b70fd366586765c71db3e8c16e6fe264fae0acb78f9d`.

No prompt, response content, reasoning, credential, signing key, or raw provider body
is published by this record. Private artifacts retain the complete verification
lineage.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A committed target ordinal is treated as a success before execution | Count it only after strict broker completion, observer signature, and fresh authentication | The observer and local host remain trusted |
| One prior Luna result is duplicated or substituted | Reverify a distinct sample, request, artifact, ledger entry, and campaign commitment | Private artifact custody remains trusted |
| A local cost estimate is called provider billing | Report only the controller's 335 micro-USD settlement and keep reconciliation false | Separate aggregate billing evidence remains required |
| Two Luna/low results establish the profile gate | Count exactly 2 of 3 and preserve every downstream denial | One further precommitted consecutive Luna/low success remains |
| Response identifiers imply provider authorship | Retain response and transport digests while fixing provider authorship false | Stronger external/provider evidence is not available here |
| A credential exposed after the run is silently ignored | Treat it as compromised, revoke it before continuation, and confirm no project file contains a persisted copy | Revocation is operator-attested; local shell or service history remains outside this proof |
| The exposed credential invalidates the completed exchange | Separate the post-completion incident from the already terminal, authenticated request lineage | All later live attempts require a fresh replacement credential |

## Gate progress

This receipt advances the frozen matrix to 7 of 18 authenticated successes overall:
Luna/low is 2 of 3, while Terra/medium, Sol/medium, Sol/high, Astra/high, and Astra/max
are each 1 of 3. The second campaign ledger has one settled entry, 335 micro-USD
charged, 299,665 micro-USD available, and no unresolved or blocking state. Eleven
precommitted successes and five failure-boundary results remain before calibration
conversion can be considered.
