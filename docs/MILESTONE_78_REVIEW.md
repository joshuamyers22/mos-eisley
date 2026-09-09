# Milestone 78 adversarial review: F1 retained-evidence boundary

## Disposition

Accepted as implementation and automated verification of a retained
precredential-rejection receipt in the real `openai-conformance` command. Rejected
as operational completion of F1, completion of the OpenAI live-conformance exit
gate, provider evidence, calibration conversion, grading, scoring, promotion,
routing activation, or authority for any provider request.

## Implemented boundary

An authentic signed authorization that is expired or differs from the current exact
policy binding raises a dedicated internal rejection before credential lookup. When
the operator supplied a fresh non-overlapping receipt path, the command writes a
canonical F1 receipt containing the exact batch, assignment, request, policy,
authority, signed-authorization, ledger, application-version, and SDK-version
identities. The receipt includes equal before/after ledger snapshots and literal
denials for every downstream side effect and claim.

The command refuses receipt issuance if the spending ledger changed, the exact
ledger entry exists, an audit or normal output exists, a container lifecycle was
created, the receipt target already exists, its parent is absent, or it overlaps
trusted input or mutable execution state. Invalid signatures and malformed contracts
fail through the ordinary error path and cannot be relabeled as the narrower F1
condition.

## Adversarial findings

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| A generic validation error is presented as proof of precredential rejection | Mint the receipt only from the dedicated authentic-authority expiry/binding exception | The local host and installed code remain trusted |
| A tampered signature mints favorable evidence | Verify authority enrollment and Ed25519 signature before classifying the F1 rejection | Key custody and authority review remain external |
| A failed run silently altered spend state | Bind equal full ledger snapshots and require the exact entry absent both before and after | Operational artifact custody remains required |
| The receipt overwrites or aliases trusted state | Require a fresh target with an existing parent and reject overlap with every input, ledger, audit, lifecycle, and normal output | Filesystem integrity remains a host assumption |
| Source-level control flow is mistaken for an operational result | Keep F1 open despite passing unit and CLI tests | A reviewed installed-wheel run must retain the receipt |
| Passing F1 enables conversion or routing | Fix all downstream authorities to false | F2 through F5 and a separate gate report remain mandatory |

## Verification

The focused authorization and conformance CLI suites pass. The CLI test uses a
validly signed authorization against a different current policy binding, asserts
exit code 2, parses and rehashes the retained receipt, compares both ledger snapshots,
checks the exact ledger entry is absent, verifies audit/assignment/artifact/lifecycle
paths were not created, and independently mocks the credential accessor and broker
dispatcher to prove neither was called. Ruff and strict Pyright pass. Full-suite and
coverage results are recorded with the implementation commit.

## Next gate action

Build and install the reviewed wheel, prepare an independently signed short-lived
authorization, let it expire (or use a separately reviewed exact-binding mismatch),
then invoke `openai-conformance` with the new receipt option and no usable provider
credential. Reverify the receipt hash, ledger invariants, and absent execution paths
before marking F1 complete. No provider send is needed for F1.
