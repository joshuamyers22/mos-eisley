# ADR-0010: One-human formal G4 review exception for `d7237f5`

- Status: proposed until Joshua Myers signs the exact exception artifact
- Decision owner: Joshua Myers
- Scope: integrated commit `d7237f5e8faf98322c5a3e330b40c674b1f1ac55` only

## Context

This real initial-child commit passed the protected creator and frozen reviewer
whole suites. Its first owner-attested, two-provider review returned `revise`
because critics saw hashes of the signed qualification chain rather than the
signed artifacts. That signed decision remains historical. A new frozen review
subject included the canonical signed lineage and verified test outcomes while
preserving the exact approved plan, complete Git diff, source commit, and final
suite receipt. The remediated subject has SHA-256
`c95f2f25ec6512a53125048e75c185715e9dacadb27f1526e33e44310269c163`.

An Anthropic critic, an OpenAI critic, and an OpenAI judge completed separately
authorized live calls on the remediated subject. The judge returned `accept` with
zero required changes. Joshua reviewed the findings and signed that exact
decision. The replayed single-operator review record has SHA-256
`7cfb78840f30de1d612ba8b27939f4166a03ad0b111fb4fc5b323e21a8cdec1c`.
Its own flags still deny independent human review and G4 acceptance.

The original independent-review contract requires distinct external critic and
judge signers. Joshua is the only human operator, so that contract is unmet.
ADR-0008 applies only to `f54e815` and cannot cover this commit.

## Exact exception

For this integrated commit only, Joshua may satisfy the **formal G4
implementation-review requirement** with the accepted, signed two-provider
single-operator record and replayed private live-call audits. Joshua must
separately sign a domain-separated exception naming the exact integrated
revision, remediated subject hash, review-record hash, and SHA-256 of this ADR.
The verifier must replay the final suites, critic and judge audits, review
verdict, owner signatures, and exception signature. This retrospective decision
does not recast the review as independent human judgment.

The original independent-review gate remains **unmet**. One operator controlling
multiple keys does not provide independent human review. Provider diversity and
model separation do not prove human independence. The review record and exception
must continue to report independence and acceptance as false.

The failed Anthropic token-count attempt before the successful review remains
visible. Its separate ledger has one blocked USD 0.104960 violation hold; the
successful review ledger has three settled entries totaling USD 0.058777.
This exception neither clears the old hold nor authorizes further spending.

This exception does not authorize G4 creator acceptance, Git merge, release,
production activation, or another provider call. Applicable G3 quality evidence,
the failed-call spend disposition, and a distinct accountable creator decision
remain separate gates. Future commits require their own formal review authority.

## Verification and risk

The exact verifier rejects another commit, subject, review record, amendment
digest, owner key, provider roster, verdict, or chronology. It must replay the
retained live audits so owner-attested observations alone cannot establish a
provider call. It preserves the original `revise` record and failed count claim.

The residual risk is concentrated authority: Joshua can authorize, operate,
review, and sign the same run. A mistaken or compromised owner may approve a
defect without a second human. This exception takes effect only after Joshua
reviews and signs its exact canonical artifact with the enrolled creator key.
