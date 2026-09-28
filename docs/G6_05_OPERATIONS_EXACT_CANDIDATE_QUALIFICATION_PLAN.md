# G6-05 operations and exact-candidate qualification plan

Status: **offline packet validator and synthetic tests added; evidence and
independent gate open**, 2026-09-26. This is the G6-05 handoff in the
[G6 project plan](G6_ACTIVATED_ROUTING_PROJECT_PLAN.md), not a qualification,
activation decision, or permission to dispatch. The [G5 whole-task study](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md)
is unsealed and has qualified no policy. [G6-01](G6_01_ROUTING_OPERATIONAL_CONTRACT_DRAFT.md)
and the independent gates for [G6-02](G6_02_EXACT_ROUTE_RESOLVER_SPEC.md),
[G6-03](G6_03_ONE_USE_BROKER_TRANSACTION_SPEC.md), and
[G6-04](G6_04_WITNESSED_CONTROL_BUDGET_SPEC.md) remain open. The current
[runtime preflight](ROUTING_RUNTIME_PREFLIGHT.md) retains literal dispatch
denials.

## Qualification decision and scope

G6-05 qualifies **one exact frozen candidate policy and one operating
configuration** for a later G6-06 release decision. It must establish both the
statistical/evidence claim for the policy and the independent operational facts
needed by a credential-owning broker. A passing synthetic suite is prerequisite
engineering evidence; it cannot certify real custody, provider observations,
host isolation, durability, or stop latency.

The packet is bound to a single owner/cohort, task and session enrollment source,
eligible task types and stages, policy and route digests, provider/client versions,
host and broker build, signer and witness deployments, route-observation method,
spending ceilings, expiry, fallback rule, alert path, and stop contract. Changes
to any bound identity or security-relevant value require a new packet and review.
G6-05 does not send paid traffic or begin a cohort rollout; that is G6-06.

Josh Myers is the project decision owner in the G6 plan. Before qualification
starts, the owner must record the implementing owner, operations owner, witness
operator, enrolled signers and custodians, independent statistical/evidence
reviewer, and independent security reviewer. The same person or shared credential
cannot be counted as independent roles. A role that is still vacant blocks the
gate; this plan does not fill it by inference.

## Freeze an exact qualification packet

Create a versioned, access-controlled packet with a public index of artifact
digests and non-sensitive metadata. The packet index is an inventory, not a
signature or a bearer. Retain the underlying private evidence under its approved
custodian; do not copy prompts, transcripts, model responses, tool output,
sampling labels, probabilities, split assignments, or outcomes into an
operational or sampling artifact. A prospective sampling receipt is metadata
only and cannot establish eligibility or reveal holdout assignment. Use the
applicable audited G5 workflow when G5 evidence is actually produced.

Freeze these fields before the first target-host exercise:

| Field | Required value and source |
|---|---|
| Decision scope | Owner/cohort ID, task types and stages, start/end window, exact fixed fallback or fail-closed action, maximum task count and exposure. Owner signs the scope; the operator accepts it. |
| Candidate | One `FrozenCandidateRoutingPolicy` digest, sealed study and plan digests, complete selected and policy-fallback `RouteCandidate` identities, profile and feature partition, prompt/skill asset digests and client versions. No nearby model or lower-effort substitution. |
| G5 claim | Exact qualified population, policy bytes, registered estimand, gate thresholds, follow-up window, independent review decision, and once-used holdout report/claim digests. If any required G5 gate is missing or inconclusive, record no-go. |
| Authority | Independently distributed promotion, activation and control authority-policy digests; signer IDs, key fingerprints, custody locations and role separation; signed promotion decision and activation artifacts. Private key material stays outside the packet. |
| Witness and spend | Enrolled first signed control entry, anchor policy, epoch/checkpoint identities, witness operator and persistence/quorum design, task/session membership source, signed scope policy, task/session/cohort ceilings, unresolved-entry limit, retained exposure and recovery owner. |
| Exact routes | For every selected and eligible fallback route: provider, backend, model, effort, capabilities, prompt asset digest, client version, registry digest, catalog source, pricing basis and evidence, conformance/drift evidence, observation time and expiry. |
| Runtime | Broker build digest and deployment identity, OS/credential boundary, provider transport retry settings, monitor and restricted audit sinks, clock source, network/authentication path to witness, stop delivery and alert/on-call contacts. |
| Verification | Frozen test protocol and fault oracles below, target host, test isolation and resource ceiling, evidence retention, reviewer roster, severity rubric, and decision deadline. No unspecified paid rehearsal is authorized. |

Use only the exact enrolled authority-policy and witness roots from an
independently retained distribution channel. A repository file, CLI argument,
saved preflight, worker input, or packet index cannot replace that channel.
Record the packet digest and every later amendment; an amendment invalidates
prior positive drill results when it changes their tested boundary.

### Offline packet validator

The [offline validator](../src/mos_eisley/run/routing_qualification.py) and
[synthetic tests](../tests/test_routing_qualification.py) provide a strict
metadata-only rehearsal for this packet. `OfflineQualificationPacket` freezes
scope, one candidate, exact route identities and price ceilings, authority and
witness identifiers, runtime boundaries, prerequisite applicability and numeric
drill limits. Route entries contain identity fields and prompt-asset digests,
never inline prompt content. Their candidate digests require independent source
checking against the frozen policy. The packet's canonical digest binds a separate
`OfflineQualificationEvidence` index containing Q1–Q6, O01–O10, G6-01–G6-04
and every applicable G2/G3/G4 record, exact route observations, and measured
drill limits. Evidence schema version 2 also requires the exact drill protocol
and index digests. Q6's source digest must equal the index digest; each O01–O10
source digest must equal `drill_case_sha256` over that case's indexed fault
observations and protocol digest. The Q6/O records must use the protocol's
operator/checker IDs and be collected after the index was assembled. The
summary counts and latencies must match the index exactly. Missing, extra,
failed, stale or conflicting entries deny.

`validate_offline_qualification_packet` takes an explicit UTC time and an
independently supplied `OfflineQualificationReviewTrust`, the exact
`HostDrillProtocol` and `HostDrillEvidenceIndex`. It requires the joined
packet/drill check to be `reviewable`; a generic O-case `pass` record or a
standalone index result cannot substitute. Four distinct
operations, owner, security and statistical signatures must accept the exact
packet **and** evidence digest. The result is only `reviewable` or a bounded
set of denial reasons; its qualification and dispatch authority fields are
literal false. The included signing helper uses synthetic fixture keys. The
caller must obtain real trust roots and source evidence independently: this
validator does not read G5 stores, authenticate G5 outcomes, inspect external
catalog or pricing sources, or prove human independence, custody or target-host
behavior. A self-contained packet with four signatures cannot close G6-05.

## Evidence construction and review order

| Step | Producer and required evidence | Independent check and stop condition |
|---|---|---|
| Q1: G5 qualification | Audited G5 owner/custodian produces the sealed manifest identity, fixed candidate, use claim, whole-task report and registered gate decision with retained source digests. | Statistical/evidence reviewer verifies the declared sampling regime, group estimator, one-use holdout, missingness, all prespecified bounds and exact claim scope. No missing probability, group, label or split is inferred or repaired. Any absent or failed gate stops G6-05. |
| Q2: Promotion | Release authority signs the derived `RoutingPromotionDecision` under the exact frozen promotion policy and enrolled key. | Rebuild the full calibration/holdout source chain and run `verify_authenticated_routing_promotion`; require `promotion_ready: true`, exact policy/report digests and trust-disjoint signer. A signature over a different or failed decision stops. |
| Q3: Route readiness | Route evidence operator independently collects current catalog, price, conformance and drift evidence for each exact selected and policy-fallback route, including source/version, method, observation time, validity and normalized-cost calculation. | Reviewer inspects referenced evidence itself. Require every required exact route present and within its signed cost/freshness ceiling; fail on missing, extra, substituted, stale, inconclusive or unfavorable evidence. A signed assertion alone does not prove its source. |
| Q4: Activation evidence | Three distinct enrolled identities sign the exact `RoutingActivationPolicy`, `RoutingOperationalSnapshot` and fresh `RoutingActivationControlState`. Issue `RoutingActivationEligibility` and anchored runtime preflight from complete independently supplied sources. | Rebuild and verify the entire chain at an explicit UTC time. Match every digest, signer role, route identity, revocation set and expiry. Require current control and clear stop. Keep the resulting receipt's literal runtime/dispatch denials; it is evidence, not a send grant. |
| Q5: Deployment qualification | Operations installs the pinned broker build, keyless worker, credential-owning transport, independently operated witness/checkpoint and required monitor/audit path on the named target host. | Security reviewer inspects OS identity, filesystem, network, authority-root distribution, credential custody, retry behavior and call graph. The offline `SyntheticWitnessedAdmission` and `InertRoutingTransport` are not accepted as live implementations. |
| Q6: Exercises | Operations and witness operator run the target-host matrix below with inert transport and no provider credential, retaining timestamps, checkpoint generations, claim/intent counts, scope totals and alert records. | Independent reviewer observes failpoints and recovery from a separate identity. Any ambiguous state is charged at full possible exposure. Required negative case failure stops qualification. |
| Q7: Decision | Owner assembles the bounded evidence index, unresolved findings and proposed operating envelope. | Statistical/evidence and security reviewers separately sign accept/reject with exact packet digest and expiry. Operations signs runbook acceptance. Owner records go/no-go for G6-05; only a later explicit G6-06 release can authorize rollout. |

The existing [promotion](ROUTING_PROMOTION.md),
[activation eligibility](ROUTING_ACTIVATION_ELIGIBILITY.md), and
[runtime preflight](ROUTING_RUNTIME_PREFLIGHT.md) contracts define the source
chain. The [G6-02 resolver](../src/mos_eisley/run/exact_route.py) and
[G6-04 offline broker path](../src/mos_eisley/run/routing_transaction.py)
provide fixture evidence only. No production credentialed G6 send path or
external witness deployment is established by those modules.
The [G605-05 source-evidence handoff package](G6_05_SOURCE_EVIDENCE_HANDOFF_PACKAGE.md)
enumerates the exact source digest slots and independent inspection assignments
for this packet and the joined drill index. Its metadata result cannot
authenticate the underlying sources or close Q1–Q7.
The [G605-06 decision-readiness package](G6_05_DECISION_READINESS_PACKAGE.md)
binds source-inspection outcomes, finding and operations dispositions, and Q7
review signatures into an offline owner-decision queue. It grants no
qualification or dispatch authority.
The [owner-decision contract and R2 binding rehearsal](G6_05_OWNER_DECISION_R2_BINDING.md)
prepare a signed go/no-go record and a synthetic G6-06 entry join; no real go
has been issued.

## Target-host qualification matrix

The [inert target-host drill package](G6_05_INERT_TARGET_HOST_DRILL_PACKAGE.md)
now supplies a frozen O01–O10 fault index, metadata validator, run protocol and
synthetic denial tests. It prepares the actual target-host exercise but does
not execute it or close Q5/Q6. Its joined offline validator checks that the
protocol and evidence index stay within the exact qualification packet's
host/build/witness/test-protocol identities, ceilings and validity window;
the qualification validator now binds Q6/O01–O10 to that exact index. Source
artifacts and the actual host exercise still require independent review.
The drill protocol's version 2 request maximum must equal the packet's
maximum. Its code-owned O03/O04/O08 minimums reject missing post-claim state
and underreported full exposure, even when a frozen oracle requests weaker
bounds.

Use the packet's frozen route, ceilings, clock and failpoint oracles. Run each
case on the named host and witness topology with an inert endpoint, isolated
synthetic identities and zero paid sends. Record before/after witness generation,
control digest, task/session/cohort exposure, claim and intent count, transport
entries, audit/alert events, and read-only restart inventory. A drill passes only
when its state and timing meet the frozen oracle and the reviewer can reproduce
the conclusion from retained evidence.

| ID | Exercise | Required result |
|---|---|---|
| O01 | Start from the independently enrolled first signed state; try unknown genesis, duplicate epoch, substituted root and older valid local anchor. | Only enrolled genesis starts. Duplicate/reset and older or mismatched state deny before claim; independent checkpoint never decreases. |
| O02 | Concurrent same-attempt requests, changed request under same key, competing attempts at last task/session/cohort headroom, cloned broker writer. | One acknowledged claim and at most one durable intent for one attempt; no scope overspend, duplicate send, extra session or silent budget reset. |
| O03 | Crash before/after witness journal commit, checkpoint acknowledgment, receipt, local intent and transport entry; restart each cut. | No automatic re-claim, retry, refund or recovery send. Journal/checkpoint mismatch halts new admissions; ambiguous receipt retains full possible exposure. |
| O04 | Commit stop before claim, after claim, before final read and after final read; measure from operator action to witness acknowledgment and broker observation. | Earlier stop denies claim; observed later stop abandons unsent attempt. A stop after final read follows the approved in-flight rule. Measured worst case fits the owner-approved latency, or no-go; never claim zero provider arrivals without a fenced send design. |
| O05 | Remove witness, checkpoint, monitor, audit sink or trusted clock; partition broker from witness; restore each independently. | New admissions stop. Existing uncertain attempts remain inventoried and fully charged. Restoration alone does not clear a stop or resume dispatch. |
| O06 | Replay stale preflight/receipt, expired route observation, revoked policy/promotion, removed capability, changed provider/model/effort/client/prompt/toolset, and unavailable fallback. | Exact verification denies before credential access. A different route needs a new qualified decision and admission; no implicit substitution or lower effort. |
| O07 | Rotate/revoke a signer or witness key, restore an older witness DB, restore broker-local files, lose a checkpoint, and attempt a new epoch. | Unreviewed rotation/rebootstrap and mismatched state deny. Operator recovery uses retained high-water and full exposure; no deletion of an ahead row or invented checkpoint. New lineage needs signed, independently reviewed migration. |
| O08 | Provider-like timeout, cancellation, malformed usage/price and settlement/outcome-write faults against the inert endpoint. | At most one local transport entry; full uncertain or violation exposure when exact cost is unproved. Read-only inventory distinguishes witnessed settlement from missing local outcome. |
| O09 | Attempt cross-owner inspection, worker access to provider/witness keys, direct provider transport, and missing before-send audit. | Isolation denies access and any unbrokered path; no credential or raw task content appears in operational events. Missing required audit evidence stops new sends. |
| O10 | Run the stop, alert, on-call handoff, backup/restore, compromise and rollback runbooks with the named operators. | The right operator can stop without broker availability; alert reaches on-call within the approved window; recovery preserves checkpoint, claims, exposure and evidence; re-entry requires a fresh reviewed activation decision. |

The [G6-01 race contract](G6_01_ROUTING_OPERATIONAL_CONTRACT_DRAFT.md)
and [G6-04 fault matrix](G6_04_WITNESSED_CONTROL_BUDGET_SPEC.md) give the
minimum synthetic oracles. The target-host run adds independent service custody,
network failure, OS isolation, clock and operational response. Freeze numeric
latency, error budget, test ceiling and retention limits in the packet before
running it; this plan supplies no fabricated thresholds or live budget.

## Stop, rollback and re-entry

The operator stop path advances the signed, independently witnessed control and
blocks later admission. Disable the broker's new-admission path and preserve
already committed claims, before-send intents and full possible spend. A stop
can race a successful final read; the accepted in-flight behavior and measured
latency must match the frozen contract. If the owner requires zero arrival after
stop, qualify a separately fenced send guard before any rollout.

On rollback, outage, compromised key, disputed evidence, stale route or budget
violation: deny new admissions, retain an immutable incident inventory, quarantine
uncertain claims at full exposure, and fall back only to an independently eligible
fixed route through a new authorization. Do not restore an old witness/checkpoint
pair, clear a stop, create a fresh task/session ID, release a hold, or resend to
make a test pass. Recovery requires the operations owner and independent security
reviewer to compare the enrolled root, highest retained checkpoint, witness
journal, broker intents, audit and validated settlement; any ambiguity remains a
blocker until an approved reconciliation records it. Key or epoch replacement
requires a new signed and witnessed lineage carrying prior exposure.

## Acceptance record and exit gate

The G6-05 record must state the exact packet digest, target host/build, G5 claim
scope, selected route and fallback identities, all authority and witness roots,
spend/time ceiling, completed matrix cases, measured stop/outage results, open
findings, reviewers and expiry. Each evidence item has a producer, independent
checker, source digest, collection time and validity deadline. Mark each as
`pass`, `fail` or `unavailable`; missing, expired, inconsistent or disputed
evidence is not a pass. An exception cannot waive one-use, exact route, custody,
rollback, budget, audit or stop invariants.

G6-05 passes only when the applicable G2/G3/G4 prerequisites and the G6-01
through G6-04 independent gates are closed; G5 qualification is valid for the
exact candidate; promotion and current activation chains verify; every selected
and eligible fallback route has inspected current evidence; real signer/witness
custody and target-host boundaries pass independent security review; every
required drill passes within the frozen ceilings; and operations accepts the runbooks. The
project owner then records an explicit G6-05 decision. Any failed or incomplete
condition records **no-go** and keeps fixed-route/full-review operation.
G6-06 still requires its own named-cohort scope, release decision, monitoring
window and later outcome assessment.
