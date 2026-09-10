# Milestone 84 adversarial review: installed-wheel F5 completion

## Disposition

Accepted as completion of OpenAI live-conformance boundary F5 and of the 23
required execution positions. Rejected as the aggregate gate report, proof of an
OpenAI request or response, provider billing, completion of calibration conversion,
grading, scoring, quality, promotion, routing activation, or authority for another
provider request.

## Retained evidence

The controlled operation used Mos Eisley 0.1.0 from a separately installed wheel
with SHA-256
`6da01d8b82f5ac1de884be8c83e4daf351fdba84cfe7a0bdc3cbc7675d1bde17`.
The imported module resolved inside the dedicated wheel environment rather than the
source checkout. The real offline worker used immutable local image
`sha256:711d60232e9f7c49da6a5e26ef2ec0b663f182f2f22b02731e679dc1dab74efe`,
built from merged commit `9b788ae7306a875937d9c1167bed0b15bc7983d5`.

The independent authorizer signed exact conformance authorization payload
`fcb4077d726d4c924b49d28c3121066c9efa53511814573fb869393db5647f25`.
The installed-wheel harness refused to run while an OpenAI credential was
available. Its no-network transport returned the precommitted synthetic count of
100 input tokens, then blocked only after the production broker had admitted the
request and the spending controller had persisted a held reservation. No provider
request was attempted.

The independently persisted assignment authorization is
`a1da497479fa4ceb729c5c7c2f22233d0aa97100fa0b324826722d36fbaaebf3`.
Broker admission is
`414adef78d436f07fa4a78cb51d20cf6687cc2866b3db57b8daf6ee7d809f5d3`.
Reservation
`d61a95be7e621a2ebb49cc55c30aaeee37e094ca2769cc8a77c10c0e7c8dbf1c`
retains 635 micro-USD. The harness observed the exact held ledger entry and armed
watchdog before sending SIGKILL to its own launcher process. The launcher exited by
signal 9 and therefore did not execute its cleanup path.

The independent watchdog lease binds exact container
`890bb4c6c1190c86c590d8910bcdc34cf6d85fedd9c9c0b1650c76278a480e30`.
Its result reached `removed` on the first attempt and has SHA-256
`5166fca1bd66c9755ae6c82a6eb761830f2b0ca3f87077b930f6c73f5580a1a2`.
A separate read-only Docker lookup returned no matching container. The final
private verification record has SHA-256
`113d704d01741627421cad4ba9e203c76701a4e10ce15f4fdae1b0171837f613`.

Dedicated disposable ledger
`156724341d384d8746e90b240875633178d7fd0945f6a0d40562ef8be38e3635`
contains exactly one unresolved `held` entry, 635 micro-USD charged, and 9,365
micro-USD available. Exact entry
`e7eaea0ad124ca4be02e03febee9440740b4d42959ff61cf14f452756bfa6b60`
will never be released, reset, retried, or reused. Because the launcher died during
the in-flight boundary, no terminal audit outcome, spend receipt, or conformance
artifact exists. Read-only recovery therefore reports phase `admitted`, ledger
status `held`, and no success or failure outcome.

## Adversarial findings

| Attack or ambiguity | Disposition | Remaining boundary |
| --- | --- | --- |
| The launcher is killed before admission | Require persisted authorization, admission, reservation, held entry, ready marker, and armed watchdog before SIGKILL | These establish the pre-kill boundary order |
| Normal launcher cleanup is credited to the watchdog | Require launcher exit by SIGKILL, then bind the independent watchdog result to the exact lease and container | The launcher cannot execute `finally` after SIGKILL |
| Watchdog output alone proves container absence | Recheck the exact full container ID through the Docker daemon | Docker daemon and local host remain trusted |
| A partial audit is labeled success or terminal failure | Preserve recovery phase `admitted` with no outcome hash or status | Absence of outcome proves neither provider success nor failure |
| Held local exposure is presented as provider billing | Claim only conservative local reservation state | Provider request and billing remain unproven |
| Crash recovery permits retry or budget release | Preserve the full held charge and literal false retry and release authority | The disposable ledger is permanently excluded from reuse |
| The controlled transport is presented as OpenAI behavior | Require no credential to be available and fix `provider_request_sent=false` | F5 proves local launcher/watchdog behavior only |
| Completing 23 executions automatically closes the gate | Require an independently reviewed aggregate report over every exact lineage | Aggregate gate compilation remains outstanding |

## Gate progress

The 18-of-18 success matrix and boundaries F1 through F5 are complete: all 23
required execution positions now exist. The overall OpenAI live-conformance gate
remains open until an aggregate report reverifies the complete retained lineage and
fixes every unsupported downstream claim to false. No calibration conversion or
provider request is authorized by this milestone.
