# G4 milestone closeout assessment

G4 has accepted evidence for a real connected correction task and a separate
real initial-child task with plan/test review before delegation. This assessment
finds that the evidence supports those task scopes, but **full G4 milestone
closeout is not ready for approval**. Formal independent review remains on hold,
the combined milestone acceptance scope has not been approved, and the assessed
evidence contains no passing publication gate for the merged controller revision.

## Scope and decision authority

- Prepared: 2026-10-01, for Joshua Myers, the accountable project decision owner.
- Assessment owner: Codex. This document is an evidence assessment, not an owner
  acceptance, independent review, authority amendment, or release decision.
- Repository snapshot: `09a5e42365c07d37a98cd0a0aa3c910e5d618ca6`.
- Task evidence: dependency-ordering correction and duration-literal initial child.
- Required invariants: preserve exact historical artifacts and their scope;
  distinguish signatures from complete runtime replay; retain unknowns; leave
  formal independent review on hold; grant no provider call or spending.
- Guidance: [verification guide](AGENTIC_VERIFICATION_GUIDE.md),
  [work-note template](../templates/WORK_NOTE.md), and
  [verification-loop template](../templates/AGENTIC_VERIFICATION_LOOP.md).
- Verification budget: one source/metadata assessment and one document review;
  no new task execution, provider requests, study execution, or full test rerun.
- Completion criterion: an evidence-linked exit-criteria matrix, explicit gaps,
  and an ordered handoff. Assessment completion does not close the milestone.

The governing sources are [plan §15.7](mos-eisley-plan.md#157-plan-review-creator-approval-and-delegated-implementation),
[§26.2](mos-eisley-plan.md#262-review-loop-contract),
[§26.4](mos-eisley-plan.md#264-delivery-order-and-accountable-gates), and
[§26.5](mos-eisley-plan.md#265-required-adversarial-acceptance-matrix).
These references are evaluated at the repository snapshot above. Later source
changes require reassessment of affected criteria.

## Accepted task evidence

| Evidence | Dependency correction task | Duration initial-child task |
|---|---|---|
| Accepted source revision | `e90c3bbe3c795bb4788f2454c5fc9ba221ad7663` | `bf35cceabeaa7db10c074f077344b97507198b87` |
| Implementation path | Real initial child, two reproduced failing candidates, separately authorized correction child and integration | Real initial child, integration, separately authorized dependency metadata addition; no coding correction |
| Final creator suite | 13 executed, passed; no failures, errors, or skips | 17 executed, passed; no failures, errors, or skips |
| Final blind reviewer suite | 16 executed, passed; no failures, errors, or skips | 18 executed, passed; no failures, errors, or skips |
| Final review | Accepted Anthropic/OpenAI critics and OpenAI judge; separate signed owner decision | Accepted Anthropic/OpenAI critics and OpenAI judge; separate signed owner decision |
| Creator acceptance | One connected initial-child-to-correction task qualification | One duration initial-child task |
| Human review | Signed alternative formal requirement and sole-human evidence amendment, limited to this exact task | Single-operator review evidence; formal independent-review gate remains false |
| Full G4 milestone accepted | False | False |

The [connected-review work note](G4_INITIAL_CORRECTION_REVIEW_WORK_NOTE.md)
records the dependency lineage, accepted review, reconciled spending, quality
scope and creator acceptance. Its historical early preparation sections do not
override its later verified evidence. [ADR-0012](adr/0012-g4-connected-deps-one-human-review.md)
and [ADR-0013](adr/0013-g4-connected-sole-human-review-evidence.md) remain limited
to the dependency task; their private owner signatures establish their effective
decisions despite the documents' original preparation-status headings.

The [duration work note](G4_PLAN_TEST_REVIEW_WORK_NOTE.md) records plan/test
approval before the child, frozen tests and controls, metadata integration,
passing final suites, accepted review and separate creator acceptance. Its first
candidate infrastructure failure is not a reproduced implementation defect.

## G4 exit criteria

Statuses describe the evidence available for closeout, not new grants or a
claim that the current controller release is qualified.

| Criterion | Evidence and assessment | Status |
|---|---|---|
| Execution containment and trusted VCS/E2 dependency | Both task histories contain isolated dispatch, exact owned-path integration and signed VCS records. The metadata addition has separate authority. These are task-level operational evidence, not general production activation. | Supported for the accepted tasks; current controller qualification remains open |
| Immutable reviewer package, implementation binding and known controls | Both task histories retain frozen reviewer packages, implementation binding and known-good/known-bad controls. Final receipts identify exact jobs and measured collection/execution counts. | Supported for the accepted tasks |
| Creator plan/test approval before initial coding | Duration's signed plan/test approval predates its initial assignment. The dependency task's connected qualification does not establish this later dedicated critic/judge plan-review stage. | Demonstrated by duration; do not retrofit it onto dependency |
| Genuine failure reproduction and bounded correction | Dependency demonstrates two failing initial candidates and separately authorized correction, followed by passing candidate and final tests. Duration required no coding correction. | Demonstrated by dependency |
| Final creator and reviewer whole suites | The retained receipts report 13/16 and 17/18 passing methods respectively, with matching collection and execution counts and no skips. | Demonstrated for both final task revisions |
| Final critic/judge result and creator acceptance | Both tasks have accepted review and separately signed scoped creator acceptance. Machine agreement does not prove independent human review. | Demonstrated within each accepted task scope |
| Applicable implementation review requirement | Dependency has an exact signed sole-human alternative. Duration has no verified independent human review or transferable formal exception. Ron Mexico's reported review has no supplied signed artifact; the owner placed this work on hold. | Open and on hold for broader closeout |
| L2/L3 and required negative cases | Controller implementations and their regression records cover binding, one-use dispatch, stale inputs, correction and isolated execution. §26.5 requires a clause-to-test/receipt inventory; this assessment does not establish complete coverage of every required case for the current revision. | Partial evidence; complete trace required |
| Stage-0 independent readings | §15.7 makes the two-reader ordering part of the Stage-0 experimental profile. The two plan critics in duration saw creator tests and cannot serve as those earlier sealed readings. No such reader receipts were identified in the assessed task evidence. | Scope-dependent gap; no study eligibility claimed |
| Applicable G3 quality gate | The current §26.4 limits the dependency to comparative claims or dependent capabilities; §26.6 defers G3/G5 study execution until production. Dependency's signed narrow applicability decision is valid only for its exact claim. | No prelaunch study required for narrow product qualification; combined claim scope still needs an explicit determination |
| Publication quality for the assessed controller | Verification recorded before the subsequent main merge: 2,598 tests with four skips and six transient errors; all six passed on focused rerun; 87% coverage; static/export/build checks passed; 1,908 installed-wheel smoke tests passed. No uninterrupted passing `make check` was recorded, and this does not qualify the newer merged snapshot. | Open for the current merged revision |
| Accountable full milestone decision | Both signed task acceptances explicitly deny full milestone acceptance. There is no signed combined milestone acceptance in the assessed evidence. | Open |

Combining the two task records supports a component-coverage argument. It does
not create one retrospectively approved end-to-end task: the dependency task
does not gain duration's earlier plan review, and duration does not gain
dependency's correction lineage or human-review amendment. The milestone
protocol must explicitly determine whether separate representative task paths
are sufficient. The current G4 exit table does not, by itself, prescribe one
new task that must deliberately fail.

## Remaining closeout decisions

| Item | Required action or evidence | Owner and boundary |
|---|---|---|
| Combined milestone scope | Freeze a proposed product-qualification claim and identify the exact controller revision, task artifacts and applicable criteria. Decide whether these separate accepted paths meet the claim. | Codex prepares; Joshua approves the eventual milestone protocol |
| Negative acceptance coverage | Map each applicable §26.5 case to a concrete existing regression, fault receipt or documented gap; mark experimental/measurement cases separately. | Engineering assessment; no new study or sampling access |
| G3 applicability and Stage-0 scope | State whether closeout excludes comparative quality, routing, savings and experimental eligibility. Apply current §26.6's prelaunch study boundary and identify any remaining protocol evidence. | Joshua owns any new scope decision; old commit-specific exceptions do not transfer |
| Current revision verification | Resolve the recorded timing-related failures as needed, and obtain the required publication gate for the selected merged controller revision. | Engineering gate; do not reuse prior-revision successes as fresh results |
| Formal implementation review | Resume only on explicit owner instruction. Then verify any supplied Ron Mexico artifact against its exact reviewed subject and enrolled authority, or prospectively approve an applicable alternative. | On hold by Joshua; reported completion alone is not verified evidence |
| Final milestone acceptance | After the applicable gaps are resolved, prepare a separate owner decision bound to the full closeout packet. | Joshua; this document cannot supply the signature |

The follow-up [proposed scope/protocol](G4_MILESTONE_SCOPE_PROTOCOL.md) and
[negative-case inventory](G4_NEGATIVE_CASE_INVENTORY.md) are now prepared at
controller revision `6ec5f46e4150edc55457e5296269db66b1047097`. They identify
source coverage and gaps; they are not approved protocol or fresh passing tests.
The original snapshot and assessment findings above remain historical.

**Next smallest action:** resolve the proposed applicability decisions and concrete
negative-case gaps, then obtain verification for the selected controller revision.
Keep the implementation-review item on hold. No new coding child is required
solely to manufacture a correction; commission another task only if the selected
protocol reveals a concrete missing operational requirement.

Merge, release and production activation remain separate decisions. G5
simplification and routing/savings claims do not follow from this assessment.

## Evidence verification and limits

This assessment directly checked canonical artifact hashes and enrolled-owner
Ed25519 signatures for both creator acceptances, dependency's quality-scope
decision and sole-human amendment, and duration's plan/test approval. It checked
that duration's plan/test approval predates its initial assignment. It inspected
the two retained final receipts for their source revision, suite-success flags,
counts and zero failure/error/skip results.

Earlier task workflows performed full runtime/claim/Git/audit replay before
acceptance. This assessment references those recorded results; it does not claim
a new complete replay of every provider response, Git binding or container job.
Public-key enrollment, signature validity and matching hashes authenticate the
retained artifacts; they do not independently establish physical key custody or
human independence. Raw reviewer payloads and blind test sources were not copied
into this document. Sampling registries, custodian mappings, labels and outcome
stores were not accessed. No probability, independence group or split was inferred.

The checkout advanced during preparation. The assessment uses the pinned merged
snapshot above and did not modify the unrelated `.gitleaksignore` edit. The prior
publication verification applies to the earlier controller batch, not to these
concurrent changes.

### Exact retained artifact identities

| Artifact | SHA-256 |
|---|---|
| Dependency creator acceptance | `278a9e22d48318a05f7a12bf96a66dc636d0ff9f5efa66021a92e691c1a0ce44` |
| Dependency quality scope | `05b05a47ec18665ef0bbf63d4413c46388d2dc150c462af59a1f076b57e2f32e` |
| Dependency sole-human amendment | `1c475e3b8dbc17af51fc9c70ec47b72207318c73cc3efdf9fec062040ec4dce7` |
| Dependency final whole-suite receipt | `c46955a60e252037ea3e002640e1e31caeea928d19c9866c0a79b49998dc9ec8` |
| Duration creator acceptance | `7d611859f163157cce0946726a7fe9e52639e75e34373494df9576db1339ff0d` |
| Duration plan/test approval | `390fad78eba7402bcd03956c78455ea231a0b24a7051ddef0d7b6ba7f7f862d6` |
| Duration final whole-suite receipt | `cff0a7d6dc53163f06f46068fcd9a39c2e50b36655173883bcd67f6febb8faa5` |

### Governing source identities

These SHA-256 values identify Git blob contents at the pinned repository snapshot.

| Source | SHA-256 |
|---|---|
| `docs/mos-eisley-plan.md` | `5fb19117a7c6d7d2b401bd50e7b061fdfff2c4951ebbd258712a668862316ee4` |
| `docs/ROADMAP.md` | `41ff6a66bbe80749db322623fb98a50cbfbb49f9d5376a830a0e47b2a18c56cb` |
| Duration work note | `39ffb1f905954b19bb8c3659b8cd28fc1b600190c0df6af7d43adb77634ec0a4` |
| Dependency review work note | `100456c05079c3a05a04aee99d124b35f66acc6be4e6177209dcb0a0f7a9d594` |

## Assessment completion

The closeout assessment is prepared. Its remaining items are explicit and it
does not request a signature or start the held independent-review workflow.
No full G4 acceptance, new spending, source integration or release is authorized.
