# G6 activated routing project plan

Status: **design and offline implementation may start; production dispatch is
blocked** (2026-09-26). This plan records a work sequence, not an activation
decision. The [G5 whole-task study](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md) is
unsealed and has qualified no policy. The current [runtime preflight](ROUTING_RUNTIME_PREFLIGHT.md)
explicitly denies dispatch. Josh Myers is the project decision owner. Before each
implementation milestone, name its implementing owner, required independent
reviewer, frozen acceptance protocol and resource ceiling. Operational signers
and a witness operator must be named before their live gates.

## Objective and boundary

Allow a **G5-qualified, independently promoted, current exact policy** to select
one brokered route for one authorized task within a bounded owner-scoped cohort.
Every request must use the exact provider, backend, model, effort, capabilities,
prompt and client identity required by the signed policy, or take its explicitly
eligible fallback or fail closed. No path may lower effort through the existing
`ModelRegistry.resolve` substitution behavior.

The dispatcher must couple a fresh control/witness check, one-use authorization,
session spending admission and the actual broker send in a crash-conservative
transaction. A control change, duplicate, stale evidence, missing witness,
unavailable route or exhausted budget must prevent a new send. Monitoring may
stop or quarantine traffic; reactivation requires a new authorized decision.
Owner data isolation and the existing prohibition on cross-user aggregation apply.

Out of scope: training or qualifying a policy, replacing the G5 study, granting
G4 machine-write authority, within-cohort adaptation, or inferring missing
sampling groups, probabilities, labels or splits. Fixed reviewed routes and full
review remain the fallback operating mode until this plan's live gate passes.

## Entry decision

**Start now:** G6-01 planning: threat model, operating-model decisions,
exact-route contract, synthetic negative-test design and rehearsal plan. After
its implementation owner, reviewer, acceptance protocol and resource ceiling are
fixed, fixture-only resolver and transaction work can proceed while G2–G5
evidence matures. These steps have no production dispatch authority.

**Do not start live activation:** G5 has no sealed study or qualified policy;
promotion and preflight are non-executing evidence boundaries; actual key custody,
independent signer operations, external monotonic witness and exercised rollback
are not established. A passing fixture suite cannot fill those gaps.

## Decisions required before a live implementation

| Decision | Accountable authority | Acceptance evidence |
|---|---|---|
| Initial owner, cohort, eligible task types, duration and stop criteria | Product owner and operator | Signed scope with maximum tasks, spend and expiry; no ambient routing |
| Signer identities, separation, key custody, rotation and compromise response | Security/operations owners | Actual custody records and independent signing exercise; multiple keys held by one person do not establish independence |
| External monotonic witness and bootstrap/recovery | Security/operations owners | Independently retained latest control state; whole-database rollback and stale first-state tests fail closed |
| One-use transaction and broker boundary | Implementing owner and independent reviewer | Durable state-machine contract, send/recovery policy and fault-injection evidence |
| Route freshness, conformance, prices and drift sources | Provider and operations owners | Exact source/version, observation cadence and expiry for every selected and fallback route |
| Alerting, on-call stop and fixed-route fallback | Operations owner | Target-host stop, outage and rollback drill with retained evidence |

## Milestones and exit gates

| ID | Work | Exit evidence | Dependency |
|---|---|---|---|
| G6-01 | Freeze threat model and operational contract | Reviewed trust boundaries, authority separation, witness bootstrap/rollback model, failure states, cohort and resource ceiling | Existing routing plan and preflight |
| G6-02 | Implement strict exact-route resolution in isolation | Table-driven tests reject lower effort, model/backend/capability drift, absent fallback and stale catalog; no provider send | G6-01 |
| G6-03 | Design and implement one-use broker transaction with inert provider | Concurrent duplicate, revocation-at-send, timeout, cancellation, process crash and restart tests prove at most one authorized send or conservative stop; uncertainty remains visible | G6-01, G6-02 |
| G6-04 | Integrate witnessed control and budget admission | Bootstrap, witness outage/rollback, expired preflight, control race, cumulative session cap and exhausted-budget tests fail closed | G6-03; actual witness design approved |
| G6-05 | Qualify operations and exact candidate | G5 qualification; authenticated promotion; current activation evidence; real independent custody, route observations, signer/witness exercise and independent security review | G2/G3/G4 as applicable, G5, G6-04 |
| G6-06 | Run bounded rollout and assess | One named owner cohort, frozen policy and rubric, before-send records, monitored guardrails, stop/fallback drill and later-window outcome review | G6-05 and explicit owner/operator release decision |

The first work slice is **G6-01**. Its
[threat model and operational contract draft](G6_01_ROUTING_OPERATIONAL_CONTRACT_DRAFT.md)
is ready for owner, operations and independent security review; the exit gate is
still open. The [G6-02 exact-route resolver specification](G6_02_EXACT_ROUTE_RESOLVER_SPEC.md)
now has an offline implementation and synthetic tests; its independent gate
review follows G6-01 approval.
The [G6-03 one-use broker transaction](G6_03_ONE_USE_BROKER_TRANSACTION_SPEC.md)
now has an offline implementation, inert transport, synthetic witness/budget
fixtures and fault tests. Its independent gate review remains open. Do not
change existing preflight denial fields to make a test pass; dispatch authority
belongs to a separately reviewed trusted broker boundary.

The [G6-04 witnessed control and budget design](G6_04_WITNESSED_CONTROL_BUDGET_SPEC.md)
now has an offline synthetic implementation and fault suite. It exercises atomic
claim and task/session/cohort admission, checkpoint ordering, signed bootstrap,
rollback detection, stop races and budget exhaustion. Independent review and
live witness decisions remain open.

The [G6-05 operations and exact-candidate qualification plan](G6_05_OPERATIONS_EXACT_CANDIDATE_QUALIFICATION_PLAN.md)
has an offline packet validator and synthetic denial tests for evidence coverage,
route freshness, digest binding, drill ceilings and signed review roles. Its
qualification gate remains open until G5, independent custody, real witness,
route observations, target-host drills and security review pass.

The [G6-06 bounded rollout and assessment plan](G6_06_BOUNDED_ROLLOUT_ASSESSMENT_PLAN.md)
has an offline cohort controller fixture with signed release phases, a durable
one-use assignment roster, witnessed assignment and concurrency caps, and
synthetic race, crash, rollback, stop and close tests. A metadata-only closeout
packet validator checks the original roster, claim/intent joins, retained
exposure, follow-up completeness and frozen assessment bindings. The C05 inert
rehearsal checks route disappearance before claim, after claim and after the
final check, plus exact fallback freshness without reusing a consumed attempt.
The C04 fixture adds a separate hash-only before-send audit journal, required
alert-health checks and read-only recovery joins under injected outages.
The C06 fixture reads a witnessed stop and conservative exposure after a
process restart, then verifies that restored dependencies and a renewed release
cannot reopen the stopped epoch. A new epoch requires explicit bootstrap.
The C07 fixture closes early after task failure or cancellation, retains
unknown follow-up in the original roster, and blocks closeout when a local
outcome write fails after one inert send.
The C08 fixture compares those stores and the witness against an explicitly
supplied high-water snapshot, then denies another inert send after coordinated
rollback while retaining conservative exposure.
The C09 fixture denies policy and rubric changes to the frozen cohort, early
assessment claims and favorable-subset packets without reading protected
outcomes or sampling assignments.
An R0 offline runner now executes the fixed G6-02 through G6-06 synthetic
suites, an integrated inert cohort path, signed stop and separate exact fallback
selection, and writes a bounded source-digest and suite-count index. Its local
pass does not close target-build or independent-review gates.
An R1 offline shadow fixture now resolves exact decisions under a witnessed
shadow-only release and records bounded metadata while leaving assignments,
claims, audit, intents and inert transport untouched. It does not begin an
actual shadow rollout.
An R2 offline entry validator now checks one proposed bounded-live release
against independently frozen G6-05, R0/R1 and on-call references, exact route
and witness state, required paths and conservative budget headroom. Synthetic
denial tests leave the shadow release and all dispatch state untouched. Its
`reviewable` result grants no release or dispatch authority.

An R3 offline per-attempt fixture now connects a reviewable R2 packet to a
separately applied synthetic release, witnessed assignment, exact-route claim,
durable intent, audit and one inert transport entry. Boundary faults retain
full possible exposure or deny before send. This does not implement live R3.
An R4 offline surveillance inspector now checks bounded assignment, claim,
intent, audit and inert-entry joins, conservative exposure, exact route and
required-path health, anchored safety metadata and signed stop acknowledgment.
Synthetic faults produce warning or hard-stop findings without granting stop,
release or dispatch authority.

The plan fixes the live monitor/stop/fallback requirements and later-window
assessment rubric. Actual rollout and assessment remain blocked by G6-05 and a
separate owner/operator release.

## Verification and stop rule

This is a high-impact routing and spending boundary. Set the per-task, per-session
and cohort cost ceilings, test-pass ceiling and independent review roster before
extended implementation. Each review pass must add a distinct source of evidence:
contract tests, concurrency/fault injection, production-like replay, security
inspection or an operational drill. Any substitution, duplicate send, unaudited
send, cross-owner access, stale control acceptance, budget escape, or inability to
stop is a blocker. Stop live rollout on any blocker, expired evidence, witness or
monitor outage, or breached guardrail. Preserve the last eligible fixed route or
fail closed according to the signed fallback policy. Re-entry requires corrected
evidence and a new independent activation decision.

This plan follows the staged gates, work register, independent verification and
rollback structure in the [production project template's GHP project plan](../../production-project-template/docs/GHP_INTEGRATION_PROJECT_PLAN.md).
The controlling routing requirements remain [plan §26.4](mos-eisley-plan.md#264-delivery-order-and-accountable-gates),
the [project review](PROJECT_REVIEW_2026-09-08.md), and the
[activation](ROUTING_ACTIVATION_ELIGIBILITY.md) and
[preflight](ROUTING_RUNTIME_PREFLIGHT.md) contracts.
