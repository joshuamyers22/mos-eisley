# G4 negative-case inventory

**Status: focused enforcement checks performed; remaining blockers retained.**
Prepared 2026-10-01 at controller revision
`6ec5f46e4150edc55457e5296269db66b1047097`, plus the uncommitted receipt fix, protected-anchor integration and regressions, under the
[proposed scope/protocol](G4_MILESTONE_SCOPE_PROTOCOL.md).
All cases from [plan §26.5](mos-eisley-plan.md#265-required-adversarial-acceptance-matrix)
are retained below. Formal independent review remains on hold.

## How to read this inventory

- **Verified:** the specified focused check or offline probe passed in this worktree;
  its stated limits still apply. This is not complete milestone qualification.
- **Source:** concrete existing assertions cover the described scenario; a fresh
  result on the selected controller revision remains required.
- **Partial:** related checks or accepted task evidence exist, but do not cover
  the complete required adversarial scenario.
- **Gap:** no adequate scenario evidence established by this assessment. This is
  not a claim that no relevant test exists anywhere in the repository.
- **Outside:** excluded from the proposed narrow claim; neither passed nor
  waived. If the capability is required by G4 or an applicable dependency, the
  case returns to the acceptance scope and needs its own evidence.

**D** means the accepted dependency correction task; **T** means the accepted
duration initial-child task. Their revisions, artifacts, approval limits and
measured final suites are pinned in the scope/protocol and
[closeout assessment](G4_MILESTONE_CLOSEOUT_ASSESSMENT.md). Successful real task
paths support feasibility; they do not replace negative fixtures. Regression
links identify source assertions, not a new pass or a provider quality claim.

## Reading and approval

| ID | Required negative case | Evidence / required denial | Status and remaining work |
|---|---|---|---|
| R1 | Early reveal | T's plan approval precedes coding, but its critics already saw creator tests. A sealed-reader boundary must deny early disclosure. | Outside Stage-0 claim; no sealed-reader early-reveal proof. |
| R2 | Creator tests/history leak | T's blind reviewer custody precedes child implementation; this does not prove reader-channel leak prevention. | Outside Stage-0 reading claim; custody alone is insufficient. |
| R3 | Missing second commitment | Two critics are not two earlier sealed reading commitments. Must refuse the reading gate without the second exact commitment. | Outside Stage-0 claim; no qualifying commitment evidence established. |
| R4 | Stale clause/test revision | [Changed plan/tests/base/task rejection](../tests/test_reviewer_plan_test_review.py#L91) mutates each signed packet input and expects rejection. | Source; T supplies operational approval ordering. Fresh selected-revision result needed. |
| R5 | Steering after approval | [Packet changes](../tests/test_reviewer_plan_test_review.py#L91) and [changed child offer](../tests/test_reviewer_coding_broker.py#L551) reject changed approved context/persona/brief before provider count or spend. | Verified for the exact frozen request boundary. No general human conversation/steering-channel guarantee is claimed. |

## Binding and execution

| ID | Required negative case | Evidence / required denial | Status and remaining work |
|---|---|---|---|
| B1 | Unchanged assertions with altered fixtures/oracles | [Oracle mutation](../tests/test_reviewer_test_package.py#L176) and [fixture mutation](../tests/test_reviewer_test_package.py#L188) reject changed data while assertion bytes remain unchanged. | Verified for both declared data kinds; inventory completeness remains a separate binding requirement. |
| B2 | Fake adapter | [Adapter restrictions](../tests/test_reviewer_implementation_binding.py#L297) reject wrapper, monkeypatch, substituted result, exception translation, discovery/interception authority and missing direct symbol; [surface enforcement](../tests/test_reviewer_implementation_binding.py#L341) rejects bypass imports. | Source; fresh result needed. |
| B3 | Empty/skip/xfail collection | [Runtime suppression probes](../tests/test_reviewer_test_execution.py#L472) cover empty, all-skipped, expected-failure known-good and mixed assertion/expected-failure known-bad suites, plus forged passing receipts. | Verified after fixing receipt creation and replay to require zero expected failures. Historical D/T suites had none. |
| B4 | Wrong tree | [Source/package drift](../tests/test_reviewer_implementation_binding.py#L208) rejects modified source; [candidate admission](../tests/test_reviewer_candidate_execution.py#L224) rejects changed input/source before execution. | Source; exact task trees do not qualify another tree. |
| B5 | Flaky test | [Correction bridge probes](../tests/test_reviewer_initial_correction.py#L89) reject a later pass, changed failed IDs, infrastructure error, unexpected success and different executed inventory. | Verified for nonmatching reproduction. Two matching runs cannot prove a test is never flaky; a signed flaky disposition also denies correction. |
| B6 | Hostile subprocess/resource exhaustion | Actual offline [resource probes](../tools/verify_g4_negative_containment.py) exercised denied child-process creation, memory exhaustion, excess output and deadline expiry under immutable image restrictions. | Verified: four probes passed and all four cleanup records report removed. See the gap-resolution work note for exact identities. |

## Correction

| ID | Required negative case | Evidence / required denial | Status and remaining work |
|---|---|---|---|
| C1 | Valid quote with irrelevant requirement | [Correction bridge fixture](../tests/test_reviewer_initial_correction.py#L89) establishes a present type quote satisfied by a stable result and an unsupported lexicographic oracle. Its signed nonimplementation/unresolved decision is denied despite creator approval and complete citation hashes. | Enforcement verified against that adjudicated fixture; recognizing relevance remains a trusted judgment, not a quote-membership algorithm. |
| C2 | Wrong test oracle | [Signed disposition denial](../tests/test_reviewer_initial_correction.py#L89) rejects `test_defect` even with a separately signed matching creator grant; B1 prevents data drift. | Enforcement verified; correctly diagnosing an unchanged wrong oracle remains adjudication-dependent. Do not claim automated oracle correctness. |
| C3 | Absent invariant | [Signed disposition denial](../tests/test_reviewer_initial_correction.py#L89) rejects `plan_gap` despite creator acquiescence. | Enforcement verified; recognizing an unstated requirement remains adjudication-dependent. Clause/citation hashes alone do not prove applicability. |
| C4 | Partial quorum | [Review quorum](../tests/test_reviewer_independent_review.py#L179) denies a missing completed critic; [correction coverage](../tests/test_reviewer_initial_correction.py#L89) denies matching two-failure receipts when triage covers only one. | Correction coverage verified; final review quorum included in the reviewer regression batch. |
| C5 | Author acquiescence | [Correction bridge probes](../tests/test_reviewer_initial_correction.py#L89) use enrolled judge and creator signatures: creator approval cannot override test-defect, plan-gap, flaky, infrastructure or unresolved dispositions. No claim is created. | Enforcement verified. An incorrectly signed implementation-defect judgment is a separate trusted-review quality risk. |
| C6 | Repeated unresolved failure | [Bounded cycles](../tests/test_reviewer_correction.py#L588) retain failed completion, reject missing/forged history and leave acceptance false; cycle 3 is rejected. | Verified for controller termination bounds and nonacceptance; no semantic resolution is inferred from exhaustion. |
| C7 | Resumed budget reset | [Initial bridge](../tests/test_reviewer_initial_correction.py#L89) denies zero carried reservation/expired task deadline; [next cycle](../tests/test_reviewer_correction.py#L588) denies zero carried use and an enlarged original ceiling despite valid signatures. | Verified against retained history; privileged rollback of all local state remains S2. |

## Measurement

These cases remain required for a future authorized measurement claim. No study
or sampling-store inspection is performed in this preparation (§26.6).

| ID | Required negative case | Status / required future evidence |
|---|---|---|
| M1 | Future features | Outside; deny features unavailable at the prospective decision time. |
| M2 | Same-task split leakage | Outside; validate declared groups/splits without inferring missing assignments. |
| M3 | Holdout in cache/notes | Outside; demonstrate holdout access isolation in the applicable audited workflow. |
| M4 | Selective labels/age-out | Outside; retain prospective labeling/censoring rules and test selective omission. |
| M5 | Never-raised escaped bugs | Outside; require an outcome ascertainment mechanism beyond raised findings. |
| M6 | Zero successes | Outside; demonstrate defined uncertainty/stop behavior with no successes. |
| M7 | Unattainable sample size | Outside; apply prospective feasibility/stop rules rather than claiming sufficient evidence. |

## Routing

No routing benefit or qualified exploration claim follows from D/T. These cases
are outside the proposed claim, not blanket exemptions for routing dependencies.

| ID | Required negative case | Status / required future evidence |
|---|---|---|
| O1 | Missing/zero-support propensity | Outside; refuse unsupported comparisons, never reconstruct missing probabilities. |
| O2 | Changed eligibility after selection | Outside; bind and reject changes to the prospective eligible set. |
| O3 | Unqualified exploration | Outside; deny exploration without qualification and separate execution authority. |
| O4 | Effort/budget substitution | Outside routing claim; test selected configuration substitution. G4 exact offer rejection is related, not routing proof. |
| O5 | Stale catalog/freshness | Outside; reject expired catalog/qualification inputs at selection/send. |
| O6 | Partial feedback/cost | Outside; retain missingness/uncertainty rather than treating absent feedback as zero cost or success. |

## Dispatch and storage

| ID | Required negative case | Evidence / required denial | Status and remaining work |
|---|---|---|---|
| S1 | Revocation between preflight/send | Exact hold withdrawal during count denies generation. [Remote revocation](../tests/test_protected_spend_anchor.py#L184) also denies generation after count; both live brokers require a protected guard. | Client enforcement verified. Real service revocation/atomic-admission qualification remains open. |
| S2 | Copied or rolled-back anchor | Unanchored storage audit demonstrated replay. [Protected service fixture](../tests/test_protected_spend_anchor.py#L61) denies the grant after copying/restoring local storage and constructing a new guard. | Protected remote anchor required by Joshua; client fixture verified, actual protected service persistence/IAM gate open. No local fallback. |
| S3 | Duplicate/uncertain dispatch | [Second instance](../tests/test_reviewer_coding_broker.py#L564) keeps one provider call; [failed send](../tests/test_reviewer_coding_broker.py#L635) keeps full uncertain hold and forbids retry; [integration claim](../tests/test_reviewer_initial_correction_integration.py#L97) rejects duplicate use. | Source for these boundaries; preserve uncertainty until exact authorized reconciliation. |
| S4 | Cross-owner aggregate access | [Owner/cap substitution](../tests/test_protected_spend_anchor.py#L97) is denied; [concurrent scope cap](../tests/test_protected_spend_anchor.py#L118) admits only one affordable hold. | Client/service-contract fixture verified. Real authenticated owner enrollment and access isolation remain deployment gates. |
| S5 | Reset with stale dependent policy | [Epoch change](../tests/test_protected_spend_anchor.py#L79) invalidates old bindings while preserving remote held exposure; missing anchor denies live G4 dispatch. | Client enforcement verified. Real remote epoch/reset history preservation must be qualified. |

## Context reduction

General context reduction is outside the proposed G4 task-path claim. Included
G4 artifact checks below are related protections, not complete reducer proof.

| ID | Required negative case | Status / evidence boundary |
|---|---|---|
| X1 | Mutable/missing full artifact | Outside reducer claim; [package integrity](../tests/test_reviewer_test_package.py#L376) is related G4 evidence. Full-artifact retention/retrieval needs its own trace. |
| X2 | Digest mismatch | Source for G4 through [package drift](../tests/test_reviewer_implementation_binding.py#L208); outside complete reducer qualification. |
| X3 | Hidden omitted range | Outside; require visible exact omission ranges and retrieval evidence. |
| X4 | stdout/stderr reorder | Outside; byte bounds in isolation do not prove preservation of stream ordering. |
| X5 | Meaningful duplicate collapse | Outside; test distinct semantically meaningful repeated events. |
| X6 | Stale file-read cache | Outside; G4 source revalidation does not establish general read-cache freshness. |
| X7 | Superseded instruction revival | Outside; require instruction-version lineage and precedence fixtures. |
| X8 | Retrieved prompt injection | Outside; test retrieved data cannot gain instruction/authority status. |
| X9 | Cross-owner memory/cache hit | Outside; prove owner-scoped storage/retrieval denial. |
| X10 | Compaction lineage break | Outside; prove exact predecessor and pending-state continuity. |
| X11 | Hard-cap false completeness | Outside; prove truncation cannot be reported as full retained context. |

## Task lifecycle

This inventory distinguishes concrete G4 checks from a complete multi-session
checkpoint/continuation qualification, which is outside the proposed claim.

| ID | Required negative case | Evidence / required denial | Status and remaining work |
|---|---|---|---|
| L1 | Changed branch/dirty tree after checkpoint | [Candidate admission](../tests/test_reviewer_candidate_execution.py#L224) and [post-run drift](../tests/test_reviewer_candidate_execution.py#L305) reject changed source. | Partial for G4 freshness; outside complete checkpoint/branch continuation proof. |
| L2 | Stale test success | [Post-run drift](../tests/test_reviewer_candidate_execution.py#L305) rejects source mutation and retains consumed claim. | Source for that G4 receipt boundary; no stale checkpoint-success reuse proof. |
| L3 | Lost pending work/steering | Must preserve pending work and owner steering across checkpoint/continuation. | Outside; no complete lifecycle trace established here. |
| L4 | Missing checkpoint evidence | Must refuse continuation claiming evidence it cannot retrieve/verify. | Outside; task artifacts are not lifecycle checkpoints. |
| L5 | Concurrent or duplicate continuation | [Duplicate broker](../tests/test_reviewer_coding_broker.py#L564) and [concurrent spend](../tests/test_spend_ledger.py#L310) cover calls/reservations. | Partial for G4; outside general concurrent continuation proof. |
| L6 | Uncertain-effect replay | [Failed send](../tests/test_reviewer_coding_broker.py#L635) prevents retry and retains uncertainty. | Source for provider dispatch; outside other effect/continuation replay claims. |
| L7 | Reset spend/review counters | [Review reservation](../tests/test_reviewer_review_spend.py#L17) rejects duplicate reservation, changed request and exhausted allowance; [ledger integrity](../tests/test_spend_ledger.py#L288) denies implicit replacement. | Partial; complete resumed review-counter/reset scenario remains unestablished. |
| L8 | Expired approval revived by a new session | [Validity checks](../tests/test_reviewer_candidate_execution.py#L224) deny expired approval independently of the tested caller. | Partial; no actual new-session revival fixture established. Never extend historical grants. |

## Context selection

All seven cases are outside the proposed task-path claim. If context selection
is included as a required G4 dependency, each needs controller-specific evidence.

| ID | Required negative case | Status / required evidence |
|---|---|---|
| Q1 | Temporary checkpoint loaded as ambient memory | Outside; distinguish temporary task state from approved durable memory. |
| Q2 | Unaccepted fact promoted on closure | Outside; reject promotion without applicable acceptance. |
| Q3 | Nested guidance broadens authority | Outside; preserve owner authority and instruction precedence. |
| Q4 | Required rule/tool omitted to fit | Outside; refuse context packing that removes a required instruction or capability. |
| Q5 | Unrelated schemas enter request | Outside; test selected task schema set and unwanted additions. |
| Q6 | Optional profile teardown interrupts another task | Outside; test task-scoped ownership and teardown isolation. |
| Q7 | Byte counts mislabeled as provider tokens | Outside general selection claim; T's retained renewed provider count is task evidence, not a unit-confusion negative fixture. |

## Closeout work and result recording

[Gap-resolution work](G4_NEGATIVE_CASE_RESOLUTION_WORK_NOTE.md) closed concrete
enforcement holes and found a storage replay blocker. Remaining decisions concern
semantic review applicability/quality beyond injected adjudications (C1–C3),
external grant revocation and protected storage/epochs (S1/S2/S5),
and aggregate owner isolation (S4). Joshua requires a protected remote anchor;
its client checks pass against synthetic fixtures, but actual service deployment
and qualification remain blockers. No trusted-local exception was approved. Ordinary G4 source freshness, spending and replay parts of L1–L8
remain applicable even when general lifecycle qualification is excluded.
Excluded rows must be checked against L2/L3 dependencies before approval; this
inventory does not unilaterally remove §26.5 requirements.

For each applicable case, the eventual verification record must retain:

1. Case ID, exact requirement and attack/mutation scenario.
2. Controller revision and test function or fault-job digest.
3. Exact starting artifact/tree/policy identities and expected denial/stop.
4. Observed result and concise receipt/log reference, including failures/skips.
5. Evidence limits, accountable disposition and any required revalidation.

The initial source-only preparation was followed by focused regression checks,
four actual offline container probes and a synthetic storage replay audit.
The later protected-anchor fixtures verify the client contract, not a deployed
DynamoDB service. See the work note for results and limits. No study, independent review, provider
request or milestone acceptance occurred. No sampling registry, labels or outcome stores were
accessed. Preparing this inventory does not change D/T's accepted scopes.
