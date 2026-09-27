# G6-06 bounded rollout and assessment plan

Status: **offline cohort controller and closeout packet fixtures complete;
live release and cohort assessment open**, 2026-09-26. This is the G6-06 handoff in the
[G6 project plan](G6_ACTIVATED_ROUTING_PROJECT_PLAN.md). It defines the first
owner-scoped production cohort and its stop, close and assessment procedure; it
does not authorize a provider send or report a cohort outcome. The
[G6-05 qualification gate](G6_05_OPERATIONS_EXACT_CANDIDATE_QUALIFICATION_PLAN.md)
is open, the [G5 study](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md) has qualified no
policy, and the current [preflight](ROUTING_RUNTIME_PREFLIGHT.md) denies dispatch.

## Decision boundary

G6-06 begins only after an exact G6-05 packet has a real **go** decision,
independent source and custody review, and current route, witness and control
evidence. The [offline G6-05 packet validator](../src/mos_eisley/run/routing_qualification.py)
can make a packet `reviewable` but cannot supply that decision. A separately
recorded owner/operator release must bind the G6-05 decision digest, one cohort
manifest digest, exact broker build and deployment identity, a validity window,
and the permitted initial phase. No saved preflight, signed eligibility receipt,
or release packet is a bearer for a worker or an alternate send path. The
credential-owning broker still verifies every attempt at use.

The first cohort uses **one named owner, one frozen complete policy, one reviewed
measurement path and one bounded task population**. The owner chooses task types,
stages, maximum eligible assignments, maximum concurrent attempts, per-task,
per-session and cohort exposure, maximum unresolved exposure, start and end
times, support coverage, stop latency, route freshness, alert thresholds and
follow-up window before release. No numeric default in this design is a spending
or traffic authorization. The fixed reviewed route and full review remain the
safe operating mode outside this exact cohort.

G6-06 is an operational pilot. Its monitored outcomes can stop or quarantine
traffic and describe the cohort. A claim that the routing policy improves cost,
quality or latency over another policy requires a separately reviewed
prospective comparison under [plan §26.6](mos-eisley-plan.md#266-continuous-production-study-and-calibration)
and the [G5 study protocol](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md). Do not call
an early stopped pilot a successful efficacy result, use a favorable subset as
a new holdout, or alter the frozen policy within the cohort.

## Freeze the rollout manifest and release record

The owner and operator create a versioned, access-controlled manifest before
any cohort assignment. Retain its digest in an independently controlled
append-only release record. A changed field requires a new manifest, review
and release; the broker cannot silently widen the active cohort. If a
comparative study is proposed, its prospective sampling design and access
controls are an additional prerequisite. Sampling receipts are metadata only;
they neither grant admission nor reveal holdout assignment. Missing sampling
probabilities, groups, labels and splits remain unknown and are never inferred
or repaired.

| Manifest section | Required frozen content |
|---|---|
| Authority and identity | Named decision owner, operations/on-call owner, independent security reviewer, exact G6-05 go record and expiry, signer and witness trust-root digests, broker build, target host, credential-owning identity and release window. |
| Cohort | One owner/cohort ID, eligible task/stage types, trusted task/session enrollment source, inclusion/exclusion rule, maximum assignments and concurrency, start/end and support window; no cross-owner pooling. |
| Policy and route | Exact G5-qualified policy, promotion, activation, execution-profile and rubric digests; candidate IDs, provider/backend/model/effort/client/prompt-asset and capability digests, current catalog/price/conformance/drift sources, signed fallback or fail-closed rule. |
| Exposure | Full worst-case request amount, task/session/cohort ceilings, maximum unresolved rows, settled/held/uncertain accounting rule, cost/pricing basis and alert/headroom levels. No new session to escape a cap. |
| Monitoring | Versioned text-free event schema, required before-send and outcome joins, independent monitor and audit health checks, dashboard cadence, alert thresholds, missingness and clock-skew limits, on-call escalation and stop deadline. |
| Follow-up and assessment | Exact rubric and independently graded outcomes, ascertainment and follow-up window, fixed cohort cutoff, completeness requirements, denominator and unknown-outcome handling, assessment date, comparison claim type if any, reviewer roster and later-window reporting rule. |
| Operations | Signed stop and rollback procedure, witness/checkpoint recovery owner, fallback drill, incident inventory, backup/restore evidence, retained exposure rule, re-entry requirements and evidence retention/deletion schedule. |

The release record contains an explicit `no-go`, `shadow-only` or
`bounded-live` owner/operator decision with the manifest digest, approved
maximums, expiry and independent reviewer acknowledgment. `shadow-only` may
compute a route decision but cannot claim, reserve, invoke transport or affect
the user's task. `bounded-live` requires every G6-05 gate and the live broker
boundary to be independently accepted. A release changes neither G5 policy
bytes nor G6-04 witness state by itself; runtime admission remains per attempt.
Withdrawal or expiry stops new assignments.

### Proposed live controller contract

Implement strict, versioned, immutable `CohortManifest` and
`SignedCohortRelease` contracts outside the task worker. The manifest pins the
fields above and its canonical digest. A release has `manifest_sha256`,
`g6_05_go_sha256`, exact broker build/host and witness epoch, phase, issue and
expiry times, signer identities and signatures, and a unique release sequence.
The broker obtains the independently enrolled owner/operator keys and highest
release sequence from a protected channel. A stale, unknown, superseded,
revoked or changed release denies. Release signatures are domain-separated
from promotion, activation and witness signatures; neither signer receives
provider credentials. A `shadow-only` release has no claim/send capability.

Before route selection or any live attempt, the trusted controller records the
task's owner and cohort membership and atomically consumes an **assignment
slot** keyed by the original task ID. That witnessed assignment is the immutable
intent-to-treat roster entry even if selection later fails or no send occurs.
Its serializable transition enforces maximum assignments and exact owner,
cohort, policy and phase. A duplicate is idempotent only for the same frozen
assignment; a changed owner or policy is a conflict. An ambiguous assignment
is inspected read-only, never redrawn or replaced.

The later one-use claim references that witnessed assignment. The real witness
admission must check active concurrency, maximum attempts, unresolved rows and
three spending scopes in one linearizable transition with the claim, or an
independently reviewed equivalent fencing protocol must prove the same limits
under concurrent workers and crashes. A local in-memory counter or three
separate ledgers cannot enforce this contract. A crash between assignment and
claim leaves a counted **no-dispatch assignment**, not a missing cohort member.
An ambiguous claim retains possible full exposure and is inspected read-only;
it is never retried as a fresh task.
Completion decrements active concurrency only after a checkpointed terminal
disposition that excludes a possible in-flight send. An uncertain state keeps
the slot until independently reviewed reconciliation proves it can close; its
full possible spend remains held. No new assignment follows release expiry,
stop or cohort close.

### Offline controller fixture

The [synthetic cohort controller](../src/mos_eisley/run/cohort_controller.py)
uses the [checkpointed witness](../src/mos_eisley/run/witnessed_admission.py)
for shadow enrollment, separately signed bounded-live and closed releases,
one-use task assignments, atomic assignment and concurrency caps, and
assignment-bound claims. The [synthetic tests](../tests/test_cohort_controller.py)
cover stale and invalid releases, shadow denial, duplicate and competing
assignments, settled and uncertain claims, stop, close, checkpoint rollback,
and process kills at assignment commit boundaries. The G6-05 go digest in this
fixture is a binding value only: the fixture does not validate a real G6-05
decision, qualify a route, grant provider credentials, or implement the live
monitoring and later-window assessment gates below.

### C04 offline audit and alert outage rehearsal

The [inert transaction fixture](../src/mos_eisley/run/routing_transaction.py)
requires a separate synthetic, hash-only before-send audit row and a healthy
required-alert path for an enrolled cohort. Both paths are checked before claim
and at the final pre-transport read. A read-only inventory joins witnessed
assignments and claims to local intents and audit rows without opening the
outcome table. The [C04 tests](../tests/test_cohort_audit_outage.py) cover missing
paths, outages before and after claim, alert acknowledgment loss, missing audit
rows, local intent rollback and recovery with full retained exposure. An outage
after the final read retains the approved one-entry in-flight bound. The local
SQLite audit and boolean alert fixture do not establish independent custody,
actual alert delivery, clock quality or target-host stop latency.

### C05 offline route-change rehearsal

The [inert witnessed transaction](../src/mos_eisley/run/routing_transaction.py)
requires a synthetic exact-route observation probe for an enrolled cohort. It
checks the selected route and observation window before claim and again after
intent, immediately before inert transport entry. The
[C05 tests](../tests/test_cohort_route_change.py) remove or stale the route
before claim, after claim and after the final check. Pre-claim loss leaves no
claim; post-claim loss abandons without transport and retains full exposure;
post-final-check loss may leave one in-flight entry under the approved bound.
The tests also show that a frozen fallback is only a new, exact resolver
selection: it cannot be plugged into a consumed attempt or a different frozen
policy. A fallback send would require fresh complete policy, preflight and
witness admission. The synthetic probe does not authenticate a real catalog,
conformance source, provider outage or target-host observation timing.

## Operating sequence

| Phase | Entry check and action | Exit evidence / stop condition |
|---|---|---|
| R0: fixture rehearsal | On the exact target build, run G6-02 through G6-05 negative suites and a complete inert task from selection through witnessed claim, intent, outcome and read-only recovery. Exercise a signed stop and fixed fallback with no paid send. | Independent reviewer matches source/build digests and observes one-use, three-scope spend, checkpoint, audit and stop invariants. Any mismatch is no-go. |
| R1: shadow-only | With a current `shadow-only` release, compute exact decisions for eligible owner tasks without dispatching, changing the served route, issuing a claim, or using a credential. Record only bounded decision metadata. | Compare candidate coverage, unavailable/fallback cases, route freshness and monitor health against the frozen manifest. Shadow observations cannot qualify a policy or expand scope. |
| R2: bounded-live entry | Owner and operator make a fresh `bounded-live` release after G6-05 go, reviewed R0/R1 evidence, exact route and witness checks, on-call readiness and verified budget headroom. Admit only the named owner/cohort and frozen task/session membership. | A failed entry predicate keeps the fixed/full-review path. No worker can switch itself from shadow to live. |
| R3: per-attempt operation | Require a prior witnessed assignment, then reverify complete policy/promotion/activation chain, exact route and current observations, owner/session membership, monitor and clock, latest signed/witnessed control and task/session/cohort headroom. Atomically claim full exposure, commit one hash-only intent, make the final witnessed check, then enter the zero-retry broker transport once. | Stale or changed evidence, missing audit, stop, outage, duplicate, cross-owner request or exhausted cap denies. After intent, uncertainty consumes the attempt and full possible exposure; never retry or silently switch route. |
| R4: live surveillance | Operations monitors required event completeness, claim/intent/send joins, cap/headroom, uncertain rows, stop acknowledgment, route and signer freshness, alert delivery and safety signals at the manifest cadence. | Any hard stop below disables new admissions. A warning threshold pages the named operator and follows the frozen escalation rule; it cannot autonomously raise a cap. |
| R5: close and follow-up | At the earliest of cohort cap, time expiry, operator stop or registered close condition, stop new assignment. Preserve the immutable cohort roster and original assignment/attempt IDs. Allow only conservative settlement and independently registered follow-up. | A closed cohort never reopens under the same release. Missing or disputed outcomes stay unknown; no replacement task or invented split/label. |
| R6: later-window assessment | After the registered follow-up matures, independently review the complete intent-to-treat roster, quality/damage/completion, all-task latency, full settled and uncertain cost, stop/incident history and missingness. Compare only against a prospectively registered baseline if that design exists. | Record `continue-fixed`, `no-go`, or a proposed new review cycle. No automatic enlargement or between-cohort promotion; any new policy needs fresh G5/G6 evidence and a new release. |

The runtime operation in R3 is a required **future live implementation**, not
the current [`execute_offline_witnessed_routing_transaction`](../src/mos_eisley/run/routing_transaction.py)
fixture. The latter accepts an inert transport and local synthetic witness.
G6-06 cannot begin R2 by changing that function's denial fields or replacing
its transport with a credentialed client.

## Required operational records and monitors

Use owner-isolated, versioned, bounded metadata. Before-send records are durable
before the first possible transfer. The independent audit sink records event ID,
owner/cohort and task/session/attempt keys or protected digests, phase, exact
policy/route/profile and control digests, witnessed claim/checkpoint generation,
maximum held amount, UTC event time and safe status/error code. It must support
read-only joins among assignment, claim, intent, transport entry, settlement,
terminal disposition and follow-up **without inventing a missing event**.
Prompts, transcripts, model responses, tool output, source diffs, labels,
outcomes and unrestricted reviewer prose do not enter operational events or
sampling metadata. Independently graded outcomes remain in the approved
restricted outcome workflow; the operational report cites only reviewed
aggregates and source digests.

| Signal | Denominator or invariant | Required action |
|---|---|---|
| Admission integrity | Every transport entry has one current acknowledged witnessed claim and earlier durable intent; at most one entry per attempt. | Any missing, duplicate or conflicting link is a hard stop and incident. |
| Spending | Full held/uncertain exposure plus settled charges against each task/session/cohort ceiling; count all attempts, failures and abandoned work. | Deny at ceiling; violation or unaccounted exposure is a hard stop. Do not refund uncertain spend from a quiet dashboard. |
| Control and dependency health | Latest signed local and independent witness state agree; route evidence, signer roots, clock, monitor and audit are current and available. | Any stale/missing/mismatched required source blocks new admissions. |
| Safety and quality | Independently adjudicated damage, missed defects, completion and follow-up status over **all eligible assigned tasks**, including no-dispatch/failure/cancellation. | Registered safety threshold breach or credible severe harm triggers stop; unknown outcomes do not count as clean. |
| Latency and cost | Assignment-to-terminal latency for all assigned tasks; whole-task cost includes held uncertainty and all rework. Report p50/p95 and cost per independently verified success only with nonzero verified successes. | Breached frozen operational ceiling triggers the registered stop/escalation rule; descriptive pilot metrics do not establish causal savings. |
| Coverage and drift | Selected route, qualified fallback, fail-closed and out-of-distribution counts over all eligible decisions; exact catalog/conformance/pricing observation age. | Route drift, unqualified fallback, lower-effort substitution or expired evidence stops new admissions. |
| Missingness and incidents | Required events, independent outcomes and follow-up present/missing/unknown by original assignment; alert acknowledgment and stop latency. | Missing required audit/monitor blocks admission; unresolved missingness blocks a positive assessment claim. |

Freeze numeric warning and hard-stop thresholds, observation cadence, queue
capacity, event-retention window and alert deadline before R2. Dashboard
availability alone is insufficient: the broker must fail closed on the required
monitor/audit path. Optional telemetry loss is counted and cannot be backfilled
into valid experimental evidence. Use the [G5 whole-task definitions](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md)
for any quality or cost comparison; do not substitute model-judge agreement or
success-only cost.

## Stop, fallback, rollback and re-entry

The operations owner can commit an emergency stop through an enrolled signer and
the independent witness without broker cooperation. Stop blocks later claims;
the approved G6-01/G6-04 final-read race contract governs an already claimed
attempt. Immediately disable new cohort assignment and broker admission,
preserve all claims, intents, checkpoint generations and possible spend, alert
on-call, and inventory potentially in-flight attempts. Cancellation does not
prove provider cancellation. No automatic replay, attempt-ID regeneration,
fresh session, refund or resume is permitted.

If the selected route is unavailable, use the **exact signed fallback only if
it is currently eligible and receives a new complete admission**. Otherwise
fail closed and retain the fixed/full-review workflow. Never lower effort,
substitute a nearby model or silently route a pending attempt. An outage of the
witness, checkpoint, required monitor, audit sink, trusted clock or route
observation blocks new paid sends; a restored dependency alone does not clear
the stop.

Rollback uses the independently retained high-water checkpoint and compares
the enrolled root, witness journal, broker intents, audit and validated
settlements. A copied or older internally valid database is a blocker, not a
reset opportunity. The security reviewer and operations owner record incident
resolution, conservative exposure and any invalidated evidence. Re-entry
requires a new signed control/activation decision, fresh route evidence, new
owner/operator release, and independent approval of any new epoch or ceiling.
No in-place policy refit or automatic traffic ramp is allowed.

## Synthetic rehearsal and target-host acceptance matrix

Before any R2 release, run the G6-05 target-host cases plus these cohort-level
cases with inert transport and zero paid spend. Freeze exact fixture ceiling,
clock, failpoints, expected records and reviewer before running. Inspect state
from a separate identity after each forced cut.

| ID | Scenario | Required observation |
|---|---|---|
| C01 | Missing/expired G6-05 go, changed manifest/build/route/rubric, unsigned or expired owner/operator release | No live assignment or claim; shadow cannot elevate itself. |
| C02 | Eligible task outside named owner, stage, window or enrollment; duplicate task or fresh session for consumed attempt | Denial without cross-owner disclosure, extra claim or reset of exposure. |
| C03 | Concurrent assignments at the last cohort slot, then claims at concurrency, unresolved and cohort-spend headroom; kill after assignment and before claim receipt | At most the frozen count/cap admits. An ambiguous assignment remains in the roster as no-dispatch; an ambiguous claim retains full exposure, with no partial budget reservation, reset or unrecorded send. |
| C04 | Audit/monitor outage, lost alert, stale clock/route, witness rollback or stop during an in-flight attempt | New admission stops; held/uncertain full exposure and exact possible in-flight state remain visible. |
| C05 | Selected route disappears before claim, after claim and after final read; fallback current/stale | Before claim, an independently eligible fallback needs a new decision and admission. Consumed attempts never retry; stale fallback fails closed. |
| C06 | Stop before claim, after claim and after final read; operator unavailable, recovery and later re-entry | Behavior matches approved in-flight bound; on-call latency is measured, stop persists, and no automatic re-entry occurs. |
| C07 | Close cohort early, delay/lose follow-up, fail/cancel a task, lose outcome write, attempt replacement draw | Intent-to-treat roster and missingness stay intact; no favorable denominator, success claim or silent replacement. |
| C08 | Roll back local or witness state and restore audit from an older copy; then request another send | Witness high-water mismatch or missing required audit links block admission and preserve original assignments, claims, intents and exposure. |
| C09 | Change rubric/policy or inspect early outcomes while attempting a later-window claim | Existing cohort remains frozen; no within-cohort retuning, reused holdout or unregistered positive assessment. |

The reviewer signs a result for each case against the exact manifest/build and
retains negative evidence as well as passes. Any failed hard invariant, missing
required record or unexplained discrepancy is a release blocker. A synthetic
pass does not replace real witness, credential, target-host or operator evidence.

## Closeout and assessment decision

The [offline closeout validator](../src/mos_eisley/run/cohort_closeout.py)
checks a metadata-only packet against an independently supplied frozen cutoff,
follow-up deadline and assessment protocol digest, plus one witnessed state and
checkpoint. It compares the packet's original task roster, claims, intent links,
local disposition metadata, retained exposure, follow-up statuses and required
evidence references. The [synthetic tests](../tests/test_cohort_closeout.py)
exercise no-dispatch and post-cutoff assignments, missing or replacement
follow-up, changed registration/release, missing or duplicate settlement links,
charge mismatch, retained held exposure and checkpoint mismatch. `reviewable`
means structurally ready for
independent source review; the validator cannot authenticate source custody,
read protected labels or outcomes, grade quality, establish a comparison, or
issue a positive assessment or dispatch decision.

At the registered cutoff, produce a bounded owner-scoped report with the
manifest/release digests, complete assignment and attempt counts, exact route
coverage, settled and held/uncertain spend, cap/headroom history, all-task
latency, independently graded quality and damage when available, missingness,
incidents/stops, protocol deviations and remaining follow-up. The independent
reviewer verifies the joins and denominator against the frozen roster and
records limitations. Unknown or disputed outcomes remain unknown. An assessment
before follow-up maturity is explicitly provisional and cannot be a positive
quality or savings claim.

The project owner and operations owner then record `no-go`, `continue-fixed`,
or `propose-next-cohort`. `propose-next-cohort` is a request for a fresh
independently reviewed manifest, qualified policy and release, not authority to
expand this one. A harmful signal, budget escape, duplicate or unaudited send,
cross-owner access, stale control acceptance, failed stop, missing required
follow-up, or failed registered gate yields no-go. No cohort volume, quiet
dashboard, lower spend or lower token count alone establishes policy benefit.

**G6-06 completes only after** one actual named cohort was released under a
closed G6-05 gate, operated within every frozen bound, passed stop/fallback
drills, closed without assignment repair, and independently assessed after the
registered follow-up window. This document completes the offline design only;
the live milestone and its decision remain open.
