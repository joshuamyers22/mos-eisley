# ADR-0013: Sole-human review evidence for the connected dependency task

- Status: prepared; effective only when Joshua Myers signs the exact amendment
- Date: 2026-09-30
- Owner and sole human reviewer: Joshua Myers
- Scope: corrected commit `e90c3bbe3c795bb4788f2454c5fc9ba221ad7663`

## Context and options

Joshua Myers requested that one human reviewer suffice to prove review evidence.
ADR-0012's approved alternative review and this task's creator acceptance have
completed. The human evidence is Joshua's enrolled, separately signed review
decision over the exact two-provider critic observations and judge adjudication.
The options are retaining a distinct-human requirement or accepting verified
sole-human review. Joshua selected sole-human review for this task.

## Decision and consequences

For this exact task, verified Joshua Myers review satisfies the human-review
evidence requirement. On a valid owner amendment signature, report
`human_review_evidence_proven=true`, `human_review_requirement_met=true`, and
`reviewer_count=1`. The requirement does not demand a second human.

This supersedes the distinct-human requirement for evaluating this task from
the amendment's signed effective time. Historical signatures and evidence remain
unchanged. The amendment does not backdate approval or turn Joshua into a person
independent of himself: `independent_human_review_proven=false` remains accurate.
The original distinct-signer gate's historical result remains false. Use the new
human-review fields when reporting whether the amended requirement is met.

Joshua accepts concentrated authority and the absence of a second human's
challenge. Two model-provider critics and their judge are supporting machine
evidence, not additional humans. Changed evidence invalidates this amendment's
application and requires another exact owner decision. Joshua may supersede this
policy through a new signed amendment; historical artifacts remain retained.

## Verification and scope

The separately signed amendment binds this document, the exact corrected commit,
review subject, accepted review record, Joshua's review decision, quality scope,
and creator acceptance. Replay the signed creator acceptance, connected lineage,
frozen tests, provider responses/audits, measured spending and owner signatures.
Require the accepted review and amendment signatures to use Joshua's enrolled
creator identity, and the amendment time to follow creator acceptance within the
trust policy's validity window. Reject altered hashes, wrong keys, changed source,
invalid chronology or a claim that independent human review was proven.

The amendment makes no claim about full G4 milestone acceptance, representative
quality, savings or G3 empirical completion. It grants no provider calls, spending,
source write, merge, release or production activation. No sampling or holdout
metadata is used.
