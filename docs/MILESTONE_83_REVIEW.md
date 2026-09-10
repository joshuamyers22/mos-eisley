# Milestone 83 adversarial review: installed-wheel F4 completion

## Disposition

Accepted as completion of OpenAI live-conformance boundary F4. Rejected as proof
of an OpenAI response, provider authorship, provider billing, real token accounting,
completion of F5, overall exit-gate completion, calibration conversion, grading,
scoring, quality, promotion, routing activation, or authority for another provider
request.

## Retained evidence

The controlled operation used Mos Eisley 0.1.0 from a separately installed wheel
with SHA-256
`6da01d8b82f5ac1de884be8c83e4daf351fdba84cfe7a0bdc3cbc7675d1bde17`.
The imported module resolved inside the dedicated wheel environment rather than the
source checkout. The isolated worker used immutable local image
`sha256:711d60232e9f7c49da6a5e26ef2ec0b663f182f2f22b02731e679dc1dab74efe`,
built from merged commit `9b788ae7306a875937d9c1167bed0b15bc7983d5`.

The independent authorizer signed exact conformance authorization payload
`20645429198674bf74229005fc78805f47aee358ba01fcca91c42af0c2a1b7b9`.
The installed-wheel harness refused to run while an OpenAI credential was
available. Its no-network transport returned a syntactically valid Responses
envelope with the precommitted synthetic usage of 100 input and 20 output tokens,
but the output text was deliberately invalid `Critique` JSON. No provider request
was attempted.

The independently persisted assignment authorization is
`d575a9b6cdc99fd78ba160878aa9255429239c8a3d1f9310c65a93c77b7db230`.
Terminal audit outcome
`0955e1b82225476fc75fb033d8f9e8fb72d2ff98daf1a15dac1780f1cfd56c8b`
records `response_received`; the response hash is
`3a1034b648e1c6de05def3b031ccfd88accba49a0a248c1b852a1f2399d99c4f`.
The strict compiler rejected that response and retained status-`error` artifact
`16304946b61a491af26010f35350c2b24d1ced3b08f3a54f04b64ba11363098d`
with `invalid_response` at `validation`. It contains no provider request ID, usage,
critique, completed-result eligibility, retry authority, automatic release, or
promotion eligibility. The final private verification record has SHA-256
`bf066fcafe26749b412068aaf613f2b30895ae31e9dcb00b1a39556f4c367935`.

Reservation
`67baaf6b9825d35837813a57957a5739eefd55d94688cc4c2c9faebb7029d7cc`
held a maximum 635 micro-USD before the controlled response. Spend receipt
`954bf0bad92ee966771d321b3b4cdeeaba2f7e2e0aa4ac6f8f2f1498ca78f2b0`
settled the precommitted synthetic usage at 44 micro-USD. Dedicated disposable
ledger `a89d76056904c1eb7702b52deea22c5706be1592e8b6d17279bb5ae2d7da4233`
therefore contains one settled entry, 44 micro-USD charged, 9,956 micro-USD
available, no unresolved exposure, and no block. Exact entry
`72e961039e2e7e23d3e3192e078a99216d56f6a480a5bc5661db6d05305803b7`
will not be reused for a successful probe. The one container lifecycle reached
`removed` on its first cleanup attempt.

## Adversarial findings

| Attack or ambiguity | Disposition | Remaining boundary |
| --- | --- | --- |
| A controlled local response is presented as OpenAI-authored | Fix `provider_request_sent=false`, require no credential to be available, and label the response synthetic | F4 proves local validation only |
| A synthetic response ID is presented as a provider request identity | Exclude the request ID from the failure artifact | Provider request identity and authorship remain unproven |
| Synthetic usage and local settlement are presented as provider billing | Disclose fixed inputs and claim only local spend-controller behavior | Provider billing remains unreconciled |
| A response hash implies valid content | Bind the bytes while retaining `status=error`, `invalid_response`, and null critique and usage | The hash proves identity, not validity |
| Validation failure is promoted as completed conformance | Keep completed-result, retry, automatic-release, and promotion authority false | No quality or routing claim exists |
| A failure ledger is recycled into the success matrix | Preserve it as a separately committed disposable ledger even though its entry settled | It is excluded from all successful probes |
| Container cleanup is inferred from normal return | Require the exact lifecycle record to report `removed` | F5 still tests launcher death and watchdog recovery |
| F4 completion opens the gate | Keep every downstream authority false | F5 and a reviewed aggregate gate report remain mandatory |

## Gate progress

The 18-of-18 success matrix and boundaries F1 through F4 are complete. Only F5
launcher-death/watchdog evidence remains before an aggregate gate report may be
considered. The overall OpenAI live-conformance gate remains open and authorizes no
calibration conversion or provider request.
