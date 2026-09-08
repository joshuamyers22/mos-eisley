# Milestone 64 adversarial review: completed Terra/medium live-conformance profile

## Disposition

Accepted as the third consecutive authenticated success for the exact
`gpt-5.6-terra` / `medium` profile and completion of that profile's frozen 3-of-3
requirement. Rejected as completion of the overall OpenAI gate, provider-authorship
proof, billing reconciliation, quality evidence, complete-batch conformance, grading,
scoring, promotion, routing activation, or authority for another request.

## Retained evidence

The live run on 2026-09-08 remained bound to the second private campaign manifest
commitment
`c16548cebc197d4515a8cb01226201e1db23412de4c1b92d3bd5ec2e1853b5c8` and shared
ledger `3a70da17b19c50af40722f1746e3ab9b0a0eb5ce32851a89029cfe9a656bfae7`.
The exact conformance-policy digest was
`42f879393d898e6fb479a8aba9393eb1e6e127bf63d304f75deb684e408f9a45`, and the
independently signed transfer-and-spend authorization digest was
`3a41ac046fe2669b5c9877c6454ecf0974591556394b91da3fd639378e253d6b`.

The zero-retry broker finished with a strict response and settled 6,766 micro-USD
against the 8,144 micro-USD maximum. Usage was 425 input tokens and 493 combined
visible/reasoning output tokens, including 276 reported reasoning tokens; measured
latency was 9,419 ms. The artifact digest is
`67872ea9202294a671af4ae3f7a05867798eb880a101e6df36bd133630e0bd45`, its retained
provider-response digest is
`9261a9c5583585b6f2ffc67746347dbc5c446b3e8122f44fa7a8f193b51d1f13`, and the
observer-signed record digest is
`a517f7c9b2b125695194b48d8aac5ebe9168fb7494d3dd71b7e3fa063a64e284`.
Fresh authentication produced receipt digest
`a998d737670a3f1acb698ebab20ea2578a4c690b3434f44479977b72488a25d3`.

No prompt, response content, reasoning, credential, signing key, or raw provider body
is published by this record. Private artifacts retain the complete verification
lineage.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Three results reuse or substitute one Terra assignment | Reverify distinct sample, request, authorization, artifact, response, and ledger lineages | Private artifact custody and the local host remain trusted |
| Reported reasoning tokens prove provider-internal reasoning quality | Preserve usage accounting without interpreting hidden behavior or quality | The provider's accounting and internal execution remain externally opaque |
| Terra profile completion is presented as overall gate completion | Mark only Luna/low and Terra/medium complete and overall progress 10 of 18 | Four profiles and all five failure boundaries remain incomplete |
| A local settlement is presented as provider billing | Report only the controller's 6,766 micro-USD settlement and keep reconciliation false | Separate aggregate billing evidence remains required |
| Three strict responses establish quality or routing suitability | Keep grading, scoring, quality, conversion, promotion, and routing false | Later authorized evaluation and holdout gates remain required |
| Completion authorizes the next profile automatically | Require a fresh policy, independent signature, and explicit consent for every Sol/medium attempt | Operator and authorization-key custody remain trusted |

## Gate progress

This receipt advances the frozen matrix to 10 of 18 authenticated successes overall.
Luna/low and Terra/medium are complete at 3 of 3; Sol/medium, Sol/high, Astra/high, and
Astra/max are each 1 of 3. The second campaign ledger has four settled entries,
10,005 micro-USD charged, 289,995 micro-USD available, and no unresolved or blocking
state. Eight precommitted successes and five failure-boundary results remain before
calibration conversion can be considered.
