# Milestone 63 adversarial review: second Terra/medium live conformance success

## Disposition

Accepted as the second consecutive authenticated success for the exact
`gpt-5.6-terra` / `medium` profile under the frozen OpenAI live-conformance gate.
Rejected as profile or overall gate completion, provider-authorship proof, billing
reconciliation, quality evidence, complete-batch conformance, grading, scoring,
promotion, routing activation, or authority for another request.

## Retained evidence

The live run on 2026-09-08 remained bound to the second private campaign manifest
commitment
`c16548cebc197d4515a8cb01226201e1db23412de4c1b92d3bd5ec2e1853b5c8` and shared
ledger `3a70da17b19c50af40722f1746e3ab9b0a0eb5ce32851a89029cfe9a656bfae7`.
The exact conformance-policy digest was
`bd9558e55bbe3126e19d028ab38fe7c0cd9e8a70d2626dd4b748141d8ac0d9bd`, and the
independently signed transfer-and-spend authorization digest was
`49262c86a5c434fde0dc8ddf7a4a0a9d9236db18679c84deaecab321d14317f4`.

The zero-retry broker finished with a strict response and settled 2,590 micro-USD
against the 8,144 micro-USD maximum. Usage was 377 input tokens and 153 output tokens,
including zero reported reasoning tokens; measured latency was 5,024 ms. The artifact
digest is `bde54aed69961111f4825aea6035cf349b2ae423e7e5316aac061448e87ba58a`, its retained
provider-response digest is
`c225c7074665047676ae248aa0c2c724cf0f8eec30be0f075fa23252f21259e4`, and the
observer-signed record digest is
`c9644aa514ac5a65ee12c540d67b1e722f578f930ce56d12e76899d570f3c9c2`.
Fresh authentication produced receipt digest
`42bddd03c84c017cdc2bdce6130ceeaa78bcb14f5434d9e22083cfa71d8258ac`.

No prompt, response content, reasoning, credential, signing key, or raw provider body
is published by this record. Private artifacts retain the complete verification
lineage.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| The second Terra result substitutes the first | Reverify a distinct sample, request, authorization, artifact, response, and ledger lineage | Private artifact custody and the local host remain trusted |
| Zero reported reasoning tokens proves no hidden reasoning occurred | Preserve the provider usage field without inferring provider-internal behavior | The provider's accounting semantics are externally opaque |
| Two Terra/medium successes complete the profile | Count exactly 2 of 3 and preserve every downstream denial | One further precommitted consecutive Terra/medium success remains |
| A local settlement is presented as provider billing | Report only the controller's 2,590 micro-USD settlement and keep reconciliation false | Separate aggregate billing evidence remains required |
| A fast successful response establishes quality or routing suitability | Keep grading, scoring, quality, conversion, promotion, and routing false | Later authorized evaluation and holdout gates remain required |
| A campaign success authorizes its successor | Require a fresh policy, independent signature, and explicit consent for the next attempt | Operator and authorization-key custody remain trusted |

## Gate progress

This receipt advances the frozen matrix to 9 of 18 authenticated successes overall.
Luna/low is complete at 3 of 3, Terra/medium is 2 of 3, and Sol/medium, Sol/high,
Astra/high, and Astra/max are each 1 of 3. The second campaign ledger has three
settled entries, 3,239 micro-USD charged, 296,761 micro-USD available, and no
unresolved or blocking state. Nine precommitted successes and five failure-boundary
results remain before calibration conversion can be considered.
