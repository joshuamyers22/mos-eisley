# G606-05 assessment source-review handoff package

Status: **offline candidate package complete; independent assessment open**,
2026-09-28. This package prepares the later-window source review in the
[G6-06 plan](G6_06_BOUNDED_ROLLOUT_ASSESSMENT_PLAN.md) and the
[G606-05 validator](../tools/g6_06_assessment_sources.py). It carries source
kind definitions, missing-input inventory and deliberately unfilled review
templates. It contains no actual cohort, protected outcome or sampling data,
source-custody decision, assessment decision or next-cohort authority.

## Candidate identity and files

The local package is
[`private/g60605-candidate-20260928T0115Z`](../private/g60605-candidate-20260928T0115Z).
Its directory is mode `0700`, files are mode `0600`, and Git ignores it. The
`candidate-inventory.json` SHA-256 is
`099d1677fbcb0d2a1506df208ce9f98fd39d93ffc87f8df0cbf909687c02a063`.
Transfer that digest through the chosen custody channel before relying on the
package. The bundled `verify-candidate.py` SHA-256 is
`8503c330a8bace7a946e4111cc8783b7cb2ff945d5ed24705aab6f95860861a9`.
The inventory pins the G606-05 validator, R6 and closeout contracts, synthetic
test source and each candidate JSON file. The `source-kind-matrix.json` SHA-256
is `46cd5f581c4eec2e921a53a7d74fd1d024b313c73cb63e36ee02be26f164aec0`.

| File | Purpose |
|---|---|
| `source-kind-matrix.json` | Exact ordered nine descriptive source kinds and two additional registered-comparison kinds, with digest reference and coverage rule for each. |
| `required-inputs.json` | Eight missing CLI inputs in order, plus an unset upstream signed-handoff reference and false close/follow-up/review claims. |
| `anchor-inputs.json` | Unfilled, separately retained `FrozenAssessmentSourceAnchor`. |
| `descriptive-reviews-inputs.json` | Nine unreviewed `AssessmentSourceReviewIndex` rows. |
| `registered-comparison-reviews-inputs.json` | Eleven unreviewed rows, including baseline registration and comparison design. |
| `candidate-inventory.json`, `verify-candidate.py` | Handoff digests, synthetic preflight metadata and a consistency check against current contracts. |

The anchor and both review-index templates are **invalid** under the strict
contracts. Each `null` is an unavailable external source or decision;
`not_reviewed` is deliberately outside the accepted decision enum. Actual
`reject` and `unavailable` decisions must remain visible and will block the
`reviewable` screen. Never replace missing, unknown or disputed source facts
with fabricated zero counts, labels, splits or probabilities.

From the repository root, verify the candidate and rerun its preflight:

```sh
uv run --frozen python private/g60605-candidate-20260928T0115Z/verify-candidate.py
uv run --frozen python -m unittest -q \
  tests.test_g6_06_assessment_sources \
  tests.test_cohort_r6_assessment_handoff \
  tests.test_cohort_r5_close_followup
```

At preparation, verification found nine descriptive or eleven comparative
source kinds, eight missing input artifacts and three invalid templates. The
23 synthetic tests passed. These tests use constructed metadata and establish
neither source custody nor an assessment of real outcomes.

## Required custody and freeze sequence

1. Complete a real R5 close under the original manifest and frozen cutoff.
   Preserve the complete assignment roster, no-dispatch and failed tasks,
   claim/intent links, settled charges and full uncertain exposure. Wait until
   the registered follow-up due time. Pending, missing or disputed follow-up
   stays in the restricted source workflow and blocks a positive assessment;
   no replacement draw or denominator repair is allowed.
2. Obtain strict `FrozenCloseoutProtocol`, `CohortCloseoutPacket`, reproduced
   `OfflineR5CloseResult`, registered `FrozenR6AssessmentAnchor`, reviewed
   `OfflineR6AssessmentPacket`, and reproduced
   `OfflineR6AssessmentResult`. The latter must match the base R6 screen with
   `r5_reproduction_checked: true`. Verify the separate G606-02 signed R5/R6
   handoff and retain its exact digest; the G606-05 screen merely joins that
   reference and does not authenticate it. Do not derive registration or
   expected source digests from a later favorable result.
3. After the R6 packet's review time, a separate custodian freezes
   `anchor-inputs.json` with exact canonical digests of the manifest, R6
   anchor/packet/result, closeout packet, canonical follow-up index, R6 evidence
   references and upstream handoff. Record named source reviewer, distinct
   final reviewer and custodian, UTC freeze time and expiry. Freeze this before
   source reviews are assembled; any changed input requires a new anchor and
   review cycle.
4. Under the approved restricted workflow, the named source reviewer inspects
   each underlying source against the **complete original roster** and its
   digest. The reviewer must differ from the producer, custodian, final R6
   reviewer, owner and operator. Record actual `accept`, `reject` or
   `unavailable` for each kind and the exact covered, unknown and disputed task
   counts. The source index contains only digests, counts, roles, incident
   status and dates; it contains no raw outcomes or unrestricted reviewer prose.
5. Use the nine-row template only for `descriptive_only`. Use the eleven-row
   template only for `registered_comparison`, and only when both baseline
   registration and comparison design were frozen **before cohort start**.
   Do not infer a missing registration, sampling probability, independence
   group, split, label or comparison design. Set comparison rows' covered task
   count to zero as specified by the contract; they review registration
   artifacts, while the nine task-scoped rows cover the full original roster.
6. Assemble the source index after every dated source review and before its
   expiry. Run the strict metadata screen from the repository root with the
   actual files and an explicit UTC assessment time:

   ```sh
   uv run --frozen python -m tools.g6_06_assessment_sources \
     <anchor.json> <r6-anchor.json> <r6-packet.json> <r6-result.json> \
     <closeout-protocol.json> <closeout.json> <r5-result.json> \
     <source-reviews.json> <new-private-assessment.json> \
     --now <UTC-ISO-time>
   ```

   The result is exclusive mode `0600`, with digest/count metadata and bounded
   denial reasons. `reviewable` means the supplied references and coverage
   rows join; it does not authenticate custody, review the restricted sources,
   grade outcomes, authorize a comparison, decide the cohort assessment or
   allow another cohort. Its authority fields remain false. An independent
   audited decision must make those determinations separately.

## Source-review checklist

Each of the nine base rows must bind the exact artifact digest, original-roster
digest and **all** assigned tasks, including no-dispatch, failed and cancelled
tasks. `covered_task_count` must equal the R6 assignment count; unknown and
disputed counts must be zero for this screen to be `reviewable`. If reality
does not meet that condition, retain the actual counts and blocked result.
The final disposition can still be `no_go` under the approved decision process.

| Kind | Source that the independent reviewer must inspect |
|---|---|
| `followup` | Canonical `FollowupSourceIndex(closeout.followups)` and each original task's dated follow-up reference after maturity; missing or disputed rows remain visible. |
| `quality` | Restricted, independently graded whole-task quality source for the complete roster, including no-dispatch and failures. |
| `damage` | Restricted damage and missed-defect review over the same roster, including adverse findings. |
| `completion` | Completion and noncompletion source for every assignment; no success-only denominator. |
| `all_task_latency` | Assignment-to-terminal timing for the complete roster and the registered treatment of missing terminals. |
| `whole_task_cost` | Settled charges, held/uncertain exposure and all rework under the registered whole-task definition. |
| `stop_incident` | Stop, alert and incident records; `incident_status` must match R6, and unresolved or severe incidents require `no_go`. |
| `missingness` | Presence, absence and dispute accounting for required events, outcomes and follow-up over the original roster. |
| `independent_review` | Dated final R6 review source and separation from owner, operator, source producer and custodian. |
| `baseline_registration` | For registered comparison only: inspect the pre-cohort baseline registration digest and date under its approved custodian. |
| `comparison_design` | For registered comparison only: inspect the pre-cohort design digest and approved analysis scope; do not reconstruct missing design fields. |

The first nine rows bind the closeout-derived follow-up digest and eight R6
evidence references. The last two are required together only for a registered
comparison. Source digests are pointers, not proof of contents or custody.
This package does not read or summarize a sampling registry, custodian mapping,
label store or outcome store. Sampling receipts remain metadata only and
grant no authority or holdout assignment.
