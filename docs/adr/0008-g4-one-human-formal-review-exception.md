# ADR-0008: One-human formal G4 review exception for `f54e815`

- Status: proposed until Joshua Myers signs the exact exception artifact
- Decision owner: Joshua Myers
- Scope: integrated commit `f54e815987c1e51941abf4c2f2138a7268dcf0a7` only

## Context

The exact integrated commit passed the creator and reviewer whole suites. An
Anthropic critic, an OpenAI critic, and an OpenAI judge then completed separate
live, one-use calls under exact creator-signed spending grants. Joshua Myers
reviewed the finding and judge rationale and signed the resulting `accept`
decision. The single-operator review record has SHA-256
`cb5fcb86a55a11e23c3dd0aba783daa4f0e051f8decbf9398977eb4fdecdc448`.
The existing independent-review contract requires distinct external critic and
judge signers. Joshua is the only human operator for this run, so that contract
cannot be satisfied honestly.

## Exact exception

For this integrated commit only, the accountable owner may satisfy the **formal
G4 implementation-review requirement** with the existing, signed, two-provider
single-operator record plus its replayed private live-call audits. The owner
must separately sign a domain-separated exception naming the exact integrated
revision, subject hash, review-record hash, and SHA-256 of this ADR. Its verifier
must replay the final-suite lineage, critic and judge audits, review verdict,
owner signatures, and exception signature before reporting that this alternative
requirement passed. The exception explicitly accepts that the review evidence
was produced before this decision; it does not recast it as a prospectively
authorized independent human review.

The original independent-review gate remains **unmet**. One operator holding
several keys does not provide human independence. Provider-family diversity and
model context separation do not prove independent human judgment. The signed
record must continue to report `independent_review_evidence_passed=false`,
`independent_human_review_proven=false`, and `acceptance_authorized=false`.
Existing failed Anthropic calls and conservative ledger holds remain visible;
this exception neither erases them nor grants new provider or spending authority.

This exception does not authorize a Git merge, release, production activation,
or G4 acceptance. Applicable G3 quality evidence and a distinct accountable
creator acceptance decision remain required. Future commits and G4 runs use the
original independent-review contract unless separately amended before review.

## Verification and risk

The verifier rejects another commit, subject, record, ADR hash, owner key,
provider roster, content verdict, or review chronology. It also rejects a
record that claims independent human review or acceptance. The live-audit
replay remains a separate required check so an owner-attested observation
alone cannot claim a verified provider call.

The residual risk is concentrated authority: Joshua can authorize, operate,
review, and sign the same run. A compromised or mistaken owner may approve a
defect without a second human catching it. The exception is effective only
after Joshua reviews and signs the exact artifact with his enrolled creator key.
