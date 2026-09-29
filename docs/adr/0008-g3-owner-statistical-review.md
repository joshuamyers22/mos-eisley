# ADR-0008: Owner-conducted G3 statistical review

- Status: accepted planning direction; review not performed
- Date and owner: 2026-09-26, Joshua Myers

## Context and options

The G3 label-inventory verification record originally names Joshua Myers as owner
and calls for a separate independent statistical/data reviewer. The owner has now
approved Joshua Myers to perform the G3 statistical-method review himself. The
study-package version 2 records this assignment and its owner-role overlap; its
local SHA-256 is `ee94e8f886ad886c699009e52136d404b4e989ed033f48a4d62e712917e05525`.
That digest identifies a review framework, not a completed review or cohort seal.

The alternatives are to keep G3 blocked until another statistical reviewer is
available, or to permit accountable owner review with explicit limits. Several
identities or signatures held by Joshua cannot create independent human judgment.

## Decision and consequences

Joshua Myers may conduct and sign the statistical-method review for the G3
session-policy utility study despite also being its owner and decision maker. This
is an **owner-conducted** exception to the earlier separate-person G3 statistical
review requirement. The report must disclose both roles. It may call its assessment
independent of an AI-authored method or scorer only when Joshua did not author or
change the specific method or code under review and had no predecision access to
the relevant study outcomes. It must never claim independence from the owner.

The review must identify the exact protocol, source and scorer revisions; inspect
the target estimand, sampling frame, independent groups, outcome definitions,
missingness, bound/interval method, multiplicity, joint feasibility and spend; and
record reproduced checks, findings, dispositions and an approve/revise/reject
decision before the applicable outcome boundary. If Joshua authored or changed a
method being assessed, that component needs a separately qualified reviewer or a
new prospective decision disclosing the additional self-review risk. A named role
or signed blank approval is not evidence that the review happened.

This exception does not waive two distinct label graders, physical grader
independence, resolver separation, holdout custody, known sampling probabilities,
independence-group validity, source/arm review, provider authorization, spending,
or any G5/G6 promotion or release gate. It grants no study execution or live
routing authority. The consequence is weaker human error detection at the G3
statistical-method boundary; a mistaken owner can approve his own study decision.
Retain that limitation in every G3 report and reconsider before a consequential
production savings or policy claim.

## Verification

Before accepting a G3 statistical review, check an exact signed report for the
role-overlap disclosure, method-authorship and outcome-access attestations,
reproduced calculations, reviewed code and input digests, all blocking findings,
and the decision. Reject a claim of separate human independence when Joshua is
both owner and reviewer. Reject missing or inferred probabilities, groups, labels,
splits, margins or costs. Reconsider this exception if Joshua is the method author,
the study expands beyond G3, the reviewer cannot inspect all gates, or an
independent statistical reviewer becomes available.
