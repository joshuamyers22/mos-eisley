# Milestone 81 adversarial review: installed-wheel F2 completion

## Disposition

Accepted as completion of OpenAI live-conformance boundary F2. Rejected as proof
that OpenAI inspected or rejected a particular request body, proof of provider
billing, completion of F3 through F5, overall exit-gate completion, calibration
conversion, grading, scoring, quality, promotion, routing activation, or authority
for another provider request.

## Retained evidence

The operation used Mos Eisley 0.1.0 from a separately installed wheel with SHA-256
`6da01d8b82f5ac1de884be8c83e4daf351fdba84cfe7a0bdc3cbc7675d1bde17`.
The imported module resolved inside the dedicated wheel environment rather than the
source checkout. The isolated worker used immutable local image
`sha256:711d60232e9f7c49da6a5e26ef2ec0b663f182f2f22b02731e679dc1dab74efe`,
built from merged commit `9b788ae7306a875937d9c1167bed0b15bc7983d5`.

The independent authorizer signed conformance authorization payload
`f19b0576522be558de6a85c3f1254e1cabab4d515486c6a7659778d03bee3e40`.
After explicit local consent, the installed command supplied a deliberately invalid
disposable credential to the live OpenAI input-token-count boundary for the exact
blinded request. The official SDK classified the terminal failure as
`authentication_error`; the broker retained stage `token_count` after 1,498 ms.
Generation was never requested.

The independently persisted assignment authorization is
`43c67406e1698bccbc401426278285c919906c6e81af777a2875e69a1754a8f2`,
the terminal outcome is
`c44cac0621f94234ee5029c3ccfc2dde9250924f1f2f7de0899fb3037d51cc14`,
and the canonical status-`error` artifact is
`ee6cb8800a13985b38978d16b2d6cc54809fca23e6a1aa8930b0f466cb3bb3fa`.
It contains no provider response hash, request ID, usage, critique, or cost and fixes
retry, automatic release, live-result, and promotion eligibility to false.

Dedicated ledger
`e00ec143a109677ce9e4be5cb7c0858e2e5099820b24e00843cd33b9ba0115a8`
remained at zero entries, zero charged, 10,000 micro-USD available, no unresolved
exposure, and unblocked. Exact prospective entry
`7ea6593d432e90c480f9f0216fd59f8f7c2f3392947eb3095046309d3fbfb966`
is absent. Neither a spend reservation nor spend receipt exists. The one container
lifecycle reached `removed` on its first cleanup attempt.

## Adversarial findings

| Attack or ambiguity | Disposition | Remaining boundary |
| --- | --- | --- |
| A simulated error is presented as a live boundary result | Bind the installed wheel, immutable image, independently signed exact request, real endpoint attempt, terminal audit, and artifact | Local host, network path, and OpenAI SDK remain trusted |
| Authentication classification proves the request body was inspected | Retain `provider_body_inspection_proven=false` | F2 proves only contact with the authentication boundary |
| Absence of local spend proves provider billing state | Claim only that no local reservation or ledger entry exists | Provider billing remains unreconciled and unproven |
| An invalid credential leaks into evidence | Retain only coarse enums and verify the disposable value is absent from the attempt tree | Process memory and remote logs are outside local evidence |
| A failed token count is retried or reaches generation | Retain a single terminal outcome, no generation response, and literal false retry authority | No further request is authorized by this result |
| F2 completion enables conversion or routing | Keep every downstream authority false | F3 through F5 and a reviewed aggregate gate report remain mandatory |

## Gate progress

The 18-of-18 success matrix and controlled boundaries F1 and F2 are complete. F3
ambiguous post-reservation failure, F4 controlled invalid structured response, and
F5 launcher-death/watchdog evidence remain. The overall OpenAI live-conformance gate
therefore remains open and authorizes no calibration conversion or provider request.
