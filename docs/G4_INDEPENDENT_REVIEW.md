# G4 independent implementation-review evidence gate

This offline gate verifies a separately creator-enrolled critic/judge review of the
**exact** final G4 implementation. It does not call a provider, sign on anyone's
behalf, dispatch a child, change Git, or authorize release. The review subject is
reconstructed from a currently passing, fully replayed final creator/reviewer
whole-suite receipt, the original approved plan bytes, and the full trusted Git
base-to-final binary patch. The plan hash must match the signed creator approval;
the patch is recomputed from the authenticated base and source commits. A missing,
oversized, non-UTF-8 or stale input fails closed. A change to either final suite,
the plan, or Git invalidates the review record.

The creator signs a domain-separated, at-most-24-hour review authority for that
subject and an exact roster. The roster requires at least two critics from two
declared provider families and one judge. Every critic and judge has a distinct
enrolled Ed25519 key and identity, disjoint from the creator, custody, VCS and
coding-child keys. The complete roster must return signed assessments. At least
the policy quorum must be completed and citation-valid before the judge decision
is considered. Each critic signs the exact subject and authority; the judge signs
the ordered hashes of **all** critic artifacts. Deterministic adjudication uses
the existing shared `judge_verdict` rules. Missing quorum, wrong role/key, stale
subject, unsupported citation, unknown finding ID, forged signature or altered
judge input fails closed. Upheld blockers yield `reject`; non-blocking material
findings yield `revise`. A replayed record is positive only for `accept`.

`mos g4-assemble-independent-review` consumes the external signed authority,
ordered critic artifacts and judge artifact plus the final-suite inputs and
approved plan. It writes one mode-0600 record outside Git. The companion
`mos g4-verify-independent-review` reconstructs the subject and all signatures
and compares the entire record. Neither command accepts a private key or makes a
network call. Assembly and verification return nonzero on a non-accept verdict.

These signatures authenticate **who attested**, not that the signer actually
operated a named provider, had independent training lineage, read every byte or
performed an independent human review. Provider-family values are enrolled claims;
the gate does not reconstruct raw G2 broker/spend evidence. The record explicitly
keeps `independent_human_review_proven=false` and
`acceptance_authorized=false`. Production use still needs accountable external
reviewer/key custody, separately approved live calls and spending, any renewed
correction chain, and the applicable G3 quality gate before creator acceptance
or launch. See the [threat model](G4_INDEPENDENT_REVIEW_THREAT_MODEL.md),
[verification record](G4_INDEPENDENT_REVIEW_VERIFICATION.md), and
[final-suite contract](G4_FINAL_WHOLE_SUITES.md).
