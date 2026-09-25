# G4 final creator/reviewer whole-suite gate

This offline gate permits one separately creator-signed pair of final test runs on
one authenticated candidate revision. It runs the complete protected creator-test
inventory and the frozen blind reviewer package in separate executions of the
same immutable no-mount, network-disabled image. It produces test evidence, **not**
independent implementation review, critic/judge quorum, correction completion,
provider authority, Git write authority or acceptance.

## Exact admission

The domain-separated `G4FinalWholeSuiteApproval` binds the authenticated
provenance, passing admitted candidate receipt, final Git revision, original
creator-suite approval claim, exact creator and reviewer packages, implementation
binding, two distinct candidate-role execution requests, image and a window of at
most 24 hours. The trust policy must enroll the creator signer. Inputs, both
claim stores and the lifecycle directory remain outside Git. One private
controller-owned mode-0700 store spends the candidate receipt identity once, before
either run; a crash or infrastructure failure consumes it and needs a new
candidate receipt and approval. There is no retry or host execution fallback.

The final creator package's declared tests must exactly equal every path in the
signed child assignment's protected creator-test inventory. It may include
Git-bound fixture files, but a path matching the collection test pattern cannot
be disguised as a fixture. Its plan, creator approval, rubric and interface
references must match the authenticated approvals. Every
package byte must equal the original base Git blob, final Git blob and clean
checkout file. This upgrades the earlier opaque creator-suite digest from a claim
to exact byte evidence; the new creator signature binds both identities. Direct
implementation imports in creator tests are allowed; reviewer tests retain their
separately validated direct-symbol adapter and cannot import implementation code
directly through that binding.

The two suites use the same bound implementation sources, dependency/build
identities, Git revision and image. The creator job sends its exact frozen package
and validated source bytes to the isolated worker; the reviewer job uses the
existing reviewer execution contract. Collection and execution counts, skip and
failure classifications, ordered test-ID digests and bounded output are retained
separately. The final reviewer test identities must equal those of the admitted
candidate run. Inputs and trusted read-only Git provenance are replayed after both
executions. A test failure can produce a non-passing receipt; an infrastructure,
identity or provenance failure produces no completed receipt.

## Commands and result

`mos g4-run-final-whole-suites` accepts the signed approval, candidate receipt,
provenance, controls, implementation binding, creator/reviewer packages and exact
requests, plus explicit repository/implementation roots, trusted Git and Docker
paths, two private claim stores, lifecycle root and a new output path. It writes
one private mode-0600 receipt and exits nonzero if either suite fails. The same
inputs, minus approval/requests/Docker and with the receipt path, go to
`mos g4-verify-final-whole-suites`; replay does not require the approval window to
remain open. Neither command accepts a signing key or makes a provider call.

The receipt's `final_suites_passed` is true only when **both** exact count
contracts and suite outcomes pass. It retains `independent_review_passed=false`
and `acceptance_authorized=false`. A real corrected candidate still needs its
renewed custody/Git/candidate and correction-completion evidence, an authenticated
critic/judge outcome, accountable independent review, and any applicable G3 gate.
See the [threat model](G4_FINAL_WHOLE_SUITES_THREAT_MODEL.md),
[verification record](G4_FINAL_WHOLE_SUITES_VERIFICATION.md), and
[roadmap](ROADMAP.md).
