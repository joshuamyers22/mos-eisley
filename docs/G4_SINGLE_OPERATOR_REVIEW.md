# G4 owner-attested two-provider review evidence

This offline path records one human operator's review of the exact post-suite G4
subject using critics from at least two declared provider families. For the first
qualification the intended critic families are **OpenAI and Anthropic**; the
owner is the sole Ed25519 signer. This is a separate schema and CLI from the
[independent-review gate](G4_INDEPENDENT_REVIEW.md). It cannot satisfy that
gate's distinct critic/judge signer requirement.

For integrated commit `f54e815` only, [ADR-0008](adr/0008-g4-one-human-formal-review-exception.md)
proposes an exact owner-signed alternative formal implementation-review
requirement using the replayed live evidence. The original independent-review
gate and independent-human claim remain false.

The owner signs an at-most-24-hour authority tied to the G4 provenance policy,
the reconstructed subject, an ordered critic roster, each exact citation-bound
request hash, the quorum policy, and an exact judge provider/model. The authority
requires explicit self-review-risk acceptance and denies provider dispatch and
acceptance. Both the provenance policy and the authority must be in single-
operator mode. The sole owner key signs the final decision after the critic and
judge observations exist.

`mos g4-assemble-single-operator-review` reconstructs the subject from the
approved plan, full trusted Git diff and passing final creator/reviewer suites.
It checks the owner authority and final-decision signatures, exact ordered
critic request hashes, two-family completed quorum, citation units, derived
judge request, observed chronology, all observation hashes, and the shared
deterministic verdict. `mos g4-verify-single-operator-review` replays the same
inputs against current Git and compares the entire record. Both commands make
no provider call and accept no private key. The assembled record is private and
mode 0600. A non-`accept` content verdict returns a nonzero exit status.

The critic and judge observation hashes are **owner-attested references**. This
offline gate does not replay provider/broker audits or prove that the named
providers returned the claimed bytes. It always retains
`independent_review_evidence_passed=false`,
`independent_human_review_proven=false`,
`provider_operation_proven=false`, and `acceptance_authorized=false`. A positive
`single_operator_review_evidence_passed` means only that the supplied,
owner-signed, citation-valid two-family record adjudicated to `accept`.

For the current qualification, the exact subject is `5cb27a5c…`; bounded
OpenAI and Anthropic critic requests are in the private preparation folder.
The owner's non-generating Anthropic Models API checks returned HTTP 200,
including an exact `claude-sonnet-5` model lookup. No
Anthropic review transport, live critic/judge call, shared spending grant,
provider audit, signed one-signer authority, or final decision exists yet.
Actual provider use requires a separate exact transfer/spending decision and
credentialed conformance. The current G4 provenance policy expires at
2026-09-27T03:59:00Z; any later run needs renewed lineage and authority.
