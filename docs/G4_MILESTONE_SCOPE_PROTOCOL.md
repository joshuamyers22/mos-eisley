# Proposed G4 milestone scope and acceptance protocol

**Status: prepared for owner review; not approved or executable authority.**
Prepared 2026-10-01 for Joshua Myers. Formal independent review remains on hold.
This proposal uses existing accepted tasks; it commissions no new child or study.

## Claim and boundaries

The proposed claim is that the G4 controller supports an executable, bounded
initial-child and correction workflow: exact plan/test approval, frozen blind
tests and controls, separate dispatch/spending/integration/test authority,
measured final suites, critic/judge review and separate creator acceptance.

The proposal uses **two representative task paths** to demonstrate components
of this workflow. It does not claim that either task demonstrated every stage,
or that their approvals can be combined into one retrospective task approval.
Joshua must explicitly decide whether these complementary paths suffice for the
milestone claim. No new task is required merely to produce a failure.

Controller source selected for assessment:
`6ec5f46e4150edc55457e5296269db66b1047097`.
The only change since the [closeout assessment](G4_MILESTONE_CLOSEOUT_ASSESSMENT.md)
snapshot is `.gitleaksignore`; this does not constitute new runtime verification.
Changes to controller code, policy or governing requirements invalidate affected
parts of this assessment and require an updated packet before acceptance.

| Included in the proposed qualification | Excluded claims and authority |
|---|---|
| Exact package/binding, controls, stale-input rejection and execution containment for G4 jobs | General production activation, unrestricted repository writes, merge or release |
| Approval before delegation, separate one-use authorities and retained spending/audit evidence | New provider calls, new spend, credential access or retries |
| Real initial-child path and real reproduced-failure-to-correction path | A single task covering both histories or a deliberately planted defect |
| Whole-suite and critic/judge evidence for the exact accepted task revisions | Transfer of task approval or review exceptions to another task or milestone |
| Applicable controller negative cases with revision-specific verification | Comparative quality, routing improvement, savings, study eligibility or population generalization |

The governing requirements are [plan §15.7](mos-eisley-plan.md#157-plan-review-creator-approval-and-delegated-implementation),
[§26.2](mos-eisley-plan.md#262-review-loop-contract),
[§26.4](mos-eisley-plan.md#264-delivery-order-and-accountable-gates),
[§26.5](mos-eisley-plan.md#265-required-adversarial-acceptance-matrix)
and [§26.6](mos-eisley-plan.md#266-continuous-production-study-and-calibration).
This proposal cannot waive them. If an excluded capability is required by the
owner's intended G4 claim or its L2/L3 dependencies, its cases become blockers;
resolve them or narrow the recorded claim explicitly. A narrowed qualification
must not be presented as unconditional full G4 closeout.

## Existing evidence, without transferring approvals

| ID | Accepted task and exact source | Contribution | Limit |
|---|---|---|---|
| D | Dependency ordering, `e90c3bbe3c795bb4788f2454c5fc9ba221ad7663` | Real initial child; two verified failing candidates; separately authorized correction child and integration; passing final creator/reviewer suites, 13/16 methods; accepted final review and creator acceptance | Does not establish duration's later dedicated pre-delegation plan/test critic/judge stage. Sole-human review amendment applies only to D. |
| T | Duration literals, `bf35cceabeaa7db10c074f077344b97507198b87` | Plan/test critic/judge and owner approval before child; frozen blind tests/controls; real initial child; separately authorized metadata addition; passing final suites, 17/18 methods; accepted final review and creator acceptance | No coding correction. First candidate infrastructure failure is not an implementation defect. Formal independent-review gate remains false. |

The retained source is identified by these artifacts. Full hashes and associated
review records are also indexed in the [closeout assessment](G4_MILESTONE_CLOSEOUT_ASSESSMENT.md#exact-retained-artifact-identities).

| Artifact | SHA-256 |
|---|---|
| D creator acceptance | `278a9e22d48318a05f7a12bf96a66dc636d0ff9f5efa66021a92e691c1a0ce44` |
| D final suites | `c46955a60e252037ea3e002640e1e31caeea928d19c9866c0a79b49998dc9ec8` |
| D quality scope | `05b05a47ec18665ef0bbf63d4413c46388d2dc150c462af59a1f076b57e2f32e` |
| D sole-human amendment | `1c475e3b8dbc17af51fc9c70ec47b72207318c73cc3efdf9fec062040ec4dce7` |
| T creator acceptance | `7d611859f163157cce0946726a7fe9e52639e75e34373494df9576db1339ff0d` |
| T pre-delegation plan/test approval | `390fad78eba7402bcd03956c78455ea231a0b24a7051ddef0d7b6ba7f7f862d6` |
| T final suites | `cff0a7d6dc53163f06f46068fcd9a39c2e50b36655173883bcd67f6febb8faa5` |

Use the [dependency review work note](G4_INITIAL_CORRECTION_REVIEW_WORK_NOTE.md)
and [duration work note](G4_PLAN_TEST_REVIEW_WORK_NOTE.md) for the retained private
artifact locations and earlier replay results. Public documentation retains
identities and concise facts, not blind test payloads or provider transcripts.
Both signed creator acceptances expressly exclude full G4 acceptance.

## Protected storage requirement added during gap resolution

On 2026-10-01 Joshua required a protected remote storage anchor and delegated
backend selection. The selected [DynamoDB-backed service design](G4_PROTECTED_STORAGE_ANCHOR_DESIGN.md)
places authoritative cumulative spend, epoch and grant-use state outside task
storage. The live G4 coding brokers now fail closed without a separately signed
protected binding and admitted service stages. Historical task schemas and
acceptances remain intact; they do not gain rollback-resistant evidence.

Synthetic guard fixtures pass, but no actual remote service is configured or
qualified. Real persistence, IAM owner separation, revocation and epoch/reset
fault receipts are mandatory before the protected-storage gate can close.
The earlier task histories continue to support operational path coverage; they
cannot substitute for that new deployment evidence. See the
[gap-resolution work note](G4_NEGATIVE_CASE_RESOLUTION_WORK_NOTE.md).

## Approval and experimental applicability

Duration's two plan critics saw creator tests. They are not the two sealed
readers who must precede those tests in the Stage-0 experimental profile.
This proposal excludes experimental eligibility; it does not mark that reading
requirement passed. If Stage-0 evidence becomes part of the approved claim,
prospective reader ordering must be demonstrated. Existing exposure cannot be
undone through a retrospective signature.

Under current §26.4 and §26.6, this narrow product qualification does not require
a prelaunch G3/G5 study. Studies remain deferred until production, and even then
require separate prospective protocol and execution authority. D's exact quality
scope decision is evidence for D, not a blanket milestone exception. Joshua's
eventual protocol decision must record applicability for the combined claim.

Joshua remains the sole verified human in the supplied task evidence. Machine
critics and a judge do not prove independent human review. D's signed alternative
cannot close T's formal review gate or the milestone gate. The reported Ron
Mexico review has no verified artifact in this assessment. Independent review
remains on hold until Joshua explicitly resumes it; no request is sent by this
protocol preparation.

## Ordered acceptance protocol

Each step produces evidence, not authority for the next step. Any required
execution or owner decision keeps its own applicable authorization boundary.

| Step | Required evidence and pass condition | Current state / responsible role |
|---|---|---|
| 1. Fix the claim | Exact controller revision, governing-source identities, task artifacts, applicable boundaries and explicit permission to use complementary paths. No approval transfer or comparative claim. | Proposed here; Joshua's protocol decision remains required. |
| 2. Reconcile the evidence packet | Verify artifact bytes/signatures/enrollment, task-to-source bindings, approval ordering, final-suite counts, review lineage and spending dispositions. Keep earlier failures and uncertainty visible. | Earlier task replays and assessment checks retained; engineering prepares the combined verification record. No new full replay is claimed here. |
| 3. Resolve the negative inventory | For every applicable case, retain exact scenario, denial/stop expectation, regression or fault receipt, source revision and observed result. Source links alone are insufficient. Any gap needs evidence or an accountable applicability decision. | [Inventory](G4_NEGATIVE_CASE_INVENTORY.md) prepared; partial and missing cases remain open. |
| 4. Verify the selected controller | Run required publication gate on the selected revision and record all failures/skips honestly. Run focused adversarial checks needed to close concrete inventory gaps. Revalidate after affected changes. | Prior batch results do not qualify this merged revision. Engineering gate remains open; no new runs authorized by this document. |
| 5. Close applicable implementation review | Verify exact subject/lineage and enrolled review authority, or obtain a prospective, explicit alternative for this claim. Preserve truthful human-independence status. | On hold. Joshua must resume review or direct preparation of an applicable alternative. |
| 6. Assess closeout | Clause-by-clause verdict using steps 1–5. Every unresolved blocker yields incomplete, not accept. State qualification limits and any narrower accepted scope. | Engineering assembles a reviewable closeout packet. |
| 7. Obtain milestone acceptance | Separate accountable owner decision bound to the exact closeout packet and controller revision, acknowledging applicable retained findings and limits. | Joshua; no milestone decision exists in the assessed evidence. |

Pass conditions for the operational task evidence are exact successful final
creator and reviewer suites with their approved counts and no unapproved
skip/xfail, exact accepted critic/judge lineage and separate creator acceptance.
For correction, require a reproducible implementation violation under unchanged
applicable requirements and valid test oracle, complete triage of blocking
failures, bounded cumulative resources and renewed exact candidate authority.
An infrastructure failure, test defect or new invariant cannot authorize coding
correction under the old plan merely because the author agrees.

Stop closeout on a digest/signature/source mismatch, unresolved uncertain effect,
stale approval, invalid control, empty or mismatched collection, missing quorum,
unresolved blocker, exceeded budget or missing applicable review. Preserve the
failed evidence. Do not retry, reset counters, alter frozen tests or broaden
authority to make the packet pass.

## Preparation verification and handoff

Selected guidance: the [work-note template](../templates/WORK_NOTE.md),
[verification guide](AGENTIC_VERIFICATION_GUIDE.md) and
[verification-loop template](../templates/AGENTIC_VERIFICATION_LOOP.md).
Risk: governance assessment; no executable policy change. Preparation budget:
source inspection, two documents and link/trace validation. No study stores,
sampling registries, labels or outcome stores are accessed; no evaluation
probabilities, groups or splits are inferred.

The original preparation inspected source without execution. The subsequent
gap-resolution work ran focused synthetic regressions and offline resource
probes, fixed receipt qualification and added protected-anchor enforcement.
No provider call or new milestone acceptance occurred.
The next work is to settle applicability and concrete inventory gaps, then obtain
revision-specific verification. Formal review stays held. These documents can be
reviewed now; acceptance and publication remain separate work.
