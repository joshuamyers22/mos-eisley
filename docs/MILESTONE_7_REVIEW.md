# Per-finding adjudication and agreement review

Scope: attribution contracts, complete finding coverage, duplicate handling,
unresolved outcomes and descriptive two-grader comparison.
Reviewer: implementing assistant self-review; no human grading experiment or
independent statistical review was conducted.

## Findings and corrections

| Impact | Finding | Implemented control |
|---|---|---|
| High | Aggregate totals permit omitted or untraceable grading decisions | Require a disposition, rationale, index and content hash for every emitted finding |
| High | Several outputs can inflate recall for one expected defect | Derive detections from the union of matched expected IDs |
| High | Disputed or unlabelled defects could be silently treated as clean | Unresolved dispositions block observation compilation |
| Medium | Duplicate references can hide false positives or form cycles | Only reference an earlier matched finding; reject chains and unmatched targets |
| Medium | Same grader or different rubrics produce misleading comparisons | Require distinct IDs, identical rubric digest and matching human/fixture method |
| Medium | Identical abstentions can inflate apparent agreement | Treat unresolved findings as conflicts even when both graders abstain |
| Medium | Empty output comparisons can claim perfect reliability | Return a null finding-agreement rate when there are no emitted findings |
| Medium | Comparison silently picks a favored grader | Preserve both source digests and complete conflicting decisions; no automatic resolution |

## Validation

Tests cover complete compilation and CLI paths, missing/extra finding indices,
content tampering, invalid labels, duplicate references, schema migration,
unresolved findings, exact label comparison, zero-finding reports, provenance
checks and refusal to overwrite saved reports.

## Remaining limits

- Raw grader IDs, rationale and timestamps are self-asserted. A later Ed25519
  authentication layer binds exact human adjudications to enrolled keys, but key
  ownership, timestamp accuracy and separate delivery remain operator assertions.
- Agreement is descriptive. There is no kappa, confidence interval, pre-registered
  acceptance threshold, population reliability claim or independence attestation.
- A plausible rationale can still support a wrong label. The implementation
  enforces structure, attribution and coverage, not semantic correctness.
- Single-grader compilation remains supported for offline rehearsal. Mandatory
  dual-authenticated grading and resolution before promotion are not implemented.
- Reports do not infer live-model quality. Automatic routing remains disabled.

Next milestone: isolated live evaluation and budget enforcement, alongside
authenticated grading and dispute-resolution controls before policy promotion.
