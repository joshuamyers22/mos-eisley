# Milestone 82 adversarial review: installed-wheel F3 completion

## Disposition

Accepted as completion of OpenAI live-conformance boundary F3. Rejected as proof
of an OpenAI outage, provider receipt, provider billing, real token accounting,
completion of F4 or F5, overall exit-gate completion, calibration conversion,
grading, scoring, quality, promotion, routing activation, or authority for another
provider request.

## Retained evidence

The controlled operation used Mos Eisley 0.1.0 from a separately installed wheel
with SHA-256
`6da01d8b82f5ac1de884be8c83e4daf351fdba84cfe7a0bdc3cbc7675d1bde17`.
The imported module resolved inside the dedicated wheel environment rather than the
source checkout. The isolated worker used immutable local image
`sha256:711d60232e9f7c49da6a5e26ef2ec0b663f182f2f22b02731e679dc1dab74efe`,
built from merged commit `9b788ae7306a875937d9c1167bed0b15bc7983d5`.

The independent authorizer signed exact conformance authorization payload
`582c3e0f4455e11e65344c806b7527979d6b805b44178027483ca89150661dbd`.
The installed-wheel harness refused to run while an OpenAI credential was
available. Its no-network transport returned the precommitted synthetic count of
100 input tokens, allowed the production spending controller to admit the exact
request, and then raised one controlled `transport_error` at stage `response`.
No provider request was attempted.

The independently persisted assignment authorization is
`3ae79a0f3255f72943237a67213b15e029e82cd399312cc3c44afd0328907722`.
The terminal failed audit outcome is
`3e6b99a8e473ffecc28d940a3511f8f412d90a529f4790762dbc71534504b2ee`.
Reservation
`7aee410d8e0ff1118d0623f328c41377049792655d5e35d8f181b40c316c1914`
held 635 micro-USD; spend receipt
`93d0aef34a888b5e08bc5bfa809db86f11a9107829a1e4cbf66ca101318e805f`
classified the full retained amount as `uncertain`, without actual input or output
usage. No conformance artifact was published. The final private verification record
has SHA-256
`b093171fc65f1234ea406ba14d602ee45369276654e8261c5891e08541d4b768`.

Dedicated disposable ledger
`70bae33b7b19656582d5f36c1bf669c2194d82e0adb83aa3e8b5e603e6296de7`
moved from zero entries and zero charged to one unresolved entry and 635 micro-USD
charged, leaving 9,365 micro-USD available. Exact entry
`30afef8d476e3ed53b702f32ac58fd96e601c635739b180c2c2d9471587223b3`
is `uncertain`; it is neither released nor reusable. The ledger remains unblocked
because uncertainty is conservative exposure rather than a pricing violation. The
one container lifecycle reached `removed` on its first cleanup attempt.

## Adversarial findings

| Attack or ambiguity | Disposition | Remaining boundary |
| --- | --- | --- |
| A controlled local disconnect is presented as OpenAI behavior | Fix `provider_request_sent=false`, require no credential to be available, and describe the transport as synthetic | F3 proves local failure handling only |
| The synthetic token count is presented as real tokenizer evidence | Bind and disclose the fixed count of 100 solely as a deterministic reservation trigger | Real token accounting is not claimed |
| An uncertain local charge is presented as provider billing | Claim only conservative local exposure; actual usage fields remain null | Provider billing remains unreconciled |
| The ambiguous reservation is silently released or reused | Preserve the full charge and unresolved entry in a dedicated disposable ledger | The ledger is permanently excluded from success probes |
| A failed exchange publishes a conformance result | Require terminal failed audit state and verify the artifact path is absent | No quality or provider-response claim exists |
| The failed request is retried | Verify one count, one response-stage fault, and literal false retry and automatic-release authority | Any new execution requires a fresh commitment and authorization |
| Container cleanup is inferred from host return | Require the exact lifecycle record to report `removed` | F5 still tests launcher death and watchdog recovery |
| F3 completion enables conversion or routing | Keep every downstream authority false | F4, F5, and a reviewed aggregate gate report remain mandatory |

## Gate progress

The 18-of-18 success matrix and boundaries F1, F2, and F3 are complete. F4
controlled invalid structured response and F5 launcher-death/watchdog evidence
remain. The overall OpenAI live-conformance gate therefore remains open and
authorizes no calibration conversion or provider request.
