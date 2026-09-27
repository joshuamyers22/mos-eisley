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
