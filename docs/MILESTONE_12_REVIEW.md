# Dual authenticated grading review

Scope: offline comparison of two authenticated human adjudications and independent
conflict resolution. No provider calls, observation compilation, scoring promotion
or private-key CLI operations are included.

| Attack or failure | Implemented control | Residual boundary |
|---|---|---|
| A self-asserted or altered grade enters comparison | Reverify each domain-separated Ed25519 signature, exact batch coverage, rubric and independently supplied grading-policy digest | Policy enrollment and key custody are trusted |
| One person supplies both grades under aliases | Require distinct authenticated IDs and unique enrolled public keys | Separate keys do not prove separate people or non-collusion |
| A grader resolves their own dispute under another name | Require all resolver-policy IDs and public-key hashes to be disjoint from the complete grader policy | Organizational relationships and shared control are not detectable |
| A resolver signs an ambiguous or replayable decision | Bind batch, both policy digests, ordered authenticated-receipt hashes, recomputed agreement digest, rubric, identity, timestamp and decisions under a separate signature domain | No external timestamp, certificate or revocation log exists |
| A conflict is omitted, duplicated or padded with an agreed finding | Require exact equality between signed resolution keys and recomputed conflict keys; reject duplicate keys in the contract | A trusted resolver can still choose a wrong schema-valid label |
| Resolution refers to changed content or invalid labels | Recheck finding hashes and run normal exact adjudication validation over the combined final judgments | Dataset labels and rubric quality remain human-controlled |
| Resolution erases contrary evidence | Embed both complete authentication receipts, agreement report and signed resolution in the final artifact | Artifact retention policy remains operator-controlled |
| New artifact accidentally changes routing or scores | Literal `promotion_eligible=false`; no compiler or scorer accepts the artifact | A later integration needs a separate adversarial review |

During implementation, a negative policy-substitution test exposed that the first
draft signature did not bind the resolution trust policy. The policy digest was
added to `ResolutionSet`, placing it inside the signed bytes and preventing the
same signature from being reinterpreted under a changed resolver policy.

The main remaining integrity step is a reviewed compiler that accepts only this
reverified dual lineage, produces observations without discarding the originals,
and keeps promotion disabled until statistical and live-provider gates also pass.
