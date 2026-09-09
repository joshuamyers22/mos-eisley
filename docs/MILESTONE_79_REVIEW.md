# Milestone 79 adversarial review: installed-wheel F1 completion

## Disposition

Accepted as completion of controlled OpenAI live-conformance boundary F1. Rejected
as evidence of OpenAI behavior, completion of F2 through F5, overall exit-gate
completion, calibration conversion, grading, scoring, quality, promotion, routing
activation, or authority for any provider request.

## Retained evidence

The operation used Mos Eisley 0.1.0 from a separately installed wheel with SHA-256
`a7519afe7df26cc66ca94695e6e90be41723bb0b0e6b27c480af77f856702545`;
the imported module resolved inside that isolated wheel environment rather than the
source checkout. OpenAI SDK 2.54.0 was installed from the hash-pinned runtime lock.

The independent authorizer signed authorization payload
`9d8fd80cfa82952f5581b8fe4acd188134936b45450a727321d5dd0227466cba`.
It bound source policy
`ae921f5eaf46c023b23b07b55e578c7532362b9fedefc7d8b63e1bbfaa2011f6`.
The installed command was deliberately given target policy
`304ce847061259308de7e55ca6bccede82e1509dc1e9dbadf7e293836973834b`;
the two current policies differed only in `policy_id`. Signature validation
succeeded, exact-binding verification rejected the mismatch, and the command
retained canonical receipt
`6a0d132074a27272851ddc0affe08ba3ce096a59e0f7ff68dc450489080941bf`.

The dedicated ledger was
`5fa56e12fa183b0af7b18a4eb601560390e0b6b986e9c181272003ef5b9d95ad`,
with exact prospective entry
`fbf97ce06e1affba3e14688127af809047fb1bc300785a8577e4b6648b6502a0`.
Its retained before and after snapshots are identical: zero entries, zero charged,
10,000 micro-USD available, no unresolved entries, and unblocked. The exact entry is
absent in both observations.

## Adversarial findings

| Attack or ambiguity | Disposition | Remaining boundary |
| --- | --- | --- |
| Source checkout is mistaken for an installed-wheel run | Bind and recheck the wheel hash, installed version, and module path inside the separate environment | The local host and package installer remain trusted |
| A malformed or forged authorization is called an exact mismatch | Require successful enrolled-authority signature verification before the dedicated rejection type | Independent key custody remains external |
| Arbitrary policy drift creates the mismatch | Change only `conformance_policy.policy_id`; retain both policy hashes | Human review of the private contracts remains trusted |
| An API key was accessed despite no provider request | Remove both key variables and use the code path whose tested accessor occurs strictly after exact authorization verification | Process tracing was not independently hardware-attested |
| Hidden spend or execution state survives | Reverify the full ledger and absence of audit, assignment, artifact, and lifecycle paths | Filesystem and SQLite custody remain local trust assumptions |
| The verifier error implies the F1 command failed | Distinguish the completed receipt/invariant checks from the later summary-serialization defect; resume from the immutable receipt without rerunning | Private wrapper correctness is not production authority |
| F1 completion opens calibration | Keep every downstream authority false | F2 through F5 and a reviewed aggregate gate report remain mandatory |

## Reporting-wrapper incident

The first private verifier invocation ran the installed command once, parsed the
receipt, checked both ledger snapshots, and checked forbidden paths. It then raised
an `AttributeError` while attempting to serialize its final plain-dictionary summary
with the contract-only canonical serializer. No tracked production code was changed
and no second boundary invocation occurred. The ignored private wrapper was corrected to
serialize the summary as sorted compact JSON and to resume verification from the
existing receipt. The resumed verifier passed, and an independent ledger/status and
filesystem check agreed with the receipt.

## Gate progress

The 18-of-18 success matrix and F1 are complete. F2 live invalid-credential
rejection, F3 ambiguous post-reservation failure, F4 controlled invalid structured
response, and F5 launcher death/watchdog evidence remain. The overall OpenAI
live-conformance gate remains open and authorizes no calibration conversion or
provider request.
