# Milestone 62 adversarial review: completed Luna/low live-conformance profile

## Disposition

Accepted as the third consecutive authenticated success for the exact
`gpt-5.6-luna` / `low` profile and completion of that profile's frozen 3-of-3
requirement. Rejected as completion of the overall OpenAI gate, provider-authorship
proof, billing reconciliation, quality evidence, complete-batch conformance, grading,
scoring, promotion, routing activation, or authority for another request.

## Retained evidence

The live run on 2026-09-08 remained bound to the second private campaign manifest
commitment
`c16548cebc197d4515a8cb01226201e1db23412de4c1b92d3bd5ec2e1853b5c8` and shared
ledger `3a70da17b19c50af40722f1746e3ab9b0a0eb5ce32851a89029cfe9a656bfae7`.
The exact conformance-policy digest was
`9b8487d5a75f3bd0babc6e18424b8598821a94d319a8c4fd217271d605ccaefa`, and the
independently signed transfer-and-spend authorization digest was
`2f085d445da31d2442b71a6abdcf10ad48dd50088e237eed171968ac69fb0105`.

The zero-retry broker finished with a strict response and settled 314 micro-USD
against the 815 micro-USD maximum. Usage was 386 input tokens and 197 combined
visible/reasoning output tokens; measured latency was 6,254 ms. The artifact digest
is `9c1e026f1397b00aa3ffb64c6204895373723e0bfa90baa4865554461e8e8503`, its retained
provider-response digest is
`c523b1223e81dee35a6bcf9694848bd0d99de6d9b9b53f8d542bc3c4c53aafce`, and the
observer-signed record digest is
`d130b7265ac1540bfd8b6a4ed28af3b5f7f9419aed4cb1e4d28d1a83b51ea9d9`.
Fresh authentication produced receipt digest
`3cfd41447436a9604f23ead60f3f0b6106fbf1ff89bfc5123bb43cf7af7c0ada`.

No prompt, response content, reasoning, credential, signing key, or raw provider body
is published by this record. Private artifacts retain the complete verification
lineage.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Three results reuse one assignment | Reverify three distinct sample, request, authorization, artifact, response, and ledger lineages | Private artifact custody and the local host remain trusted |
| Nonconsecutive or omitted Luna failures are hidden | Bind attempts to the sealed campaign chronology and stop the campaign after any non-success | Manifest custody and chronological execution remain trusted |
| Profile completion is presented as overall gate completion | Mark only Luna/low 3 of 3 and overall progress 8 of 18 | Five profiles and all five failure boundaries remain incomplete |
| A local settlement is presented as provider billing | Report only the controller's 314 micro-USD settlement and keep reconciliation false | Separate aggregate billing evidence remains required |
| Successful structured output is called quality evidence | Keep grading, scoring, and quality false | A later authorized evaluation path remains required |
| A replacement credential is treated as durable project state | Attest no provider credential persistence and require a fresh environment injection for each live session | Operator environment and key custody remain trusted |

## Gate progress

This receipt advances the frozen matrix to 8 of 18 authenticated successes overall.
Luna/low is complete at 3 of 3; Terra/medium, Sol/medium, Sol/high, Astra/high, and
Astra/max are each 1 of 3. The second campaign ledger has two settled entries, 649
micro-USD charged, 299,351 micro-USD available, and no unresolved or blocking state.
Ten precommitted successes and five failure-boundary results remain before calibration
conversion can be considered.
