# G6-01 activated routing: threat model and operational contract draft

Status: **draft for owner, operations and independent security review**,
2026-09-26. This is a proposed contract for [G6-01](G6_ACTIVATED_ROUTING_PROJECT_PLAN.md),
not a frozen acceptance protocol or dispatch authorization. No production
signer, external witness, cohort, budget or qualified G5 policy is identified
here. The [G5 study](G5_WHOLE_TASK_STUDY_PREREGISTRATION.md) is unsealed; the
[runtime preflight](ROUTING_RUNTIME_PREFLIGHT.md) has literal
`dispatch_authorized: false`.

## Decision to be made

G6 permits one owner-scoped, bounded task attempt to use one exact route from a
G5-qualified frozen policy after independent promotion, activation eligibility,
current operational evidence and a witnessed control check. The trusted broker,
not model output or a stored preflight JSON file, makes the final decision and
owns the provider credential and send. The first rollout retains the policy's
fixed measurement components and has no online exploration or policy mutation.

The decision owner must choose the first cohort, permitted stages, maximum tasks,
time window, per-task/session/cohort spend, fallback behavior, acceptable stop
latency and on-call operator before live design approval. These are intentionally
unset. A route or fallback without current exact evidence is ineligible; if none
remains, admission stops.

## Existing foundations and their limits

| Foundation | Reusable property | G6 gap |
|---|---|---|
| [Routing promotion](ROUTING_PROMOTION.md) and [activation eligibility](ROUTING_ACTIVATION_ELIGIBILITY.md) | Authenticated exact policy chain and distinct activation-role signatures | Signatures do not establish real custody, independent judgment or source truth; both artifacts deny runtime activation |
| [Local control anchor](ROUTING_RUNTIME_PREFLIGHT.md) | Pinned policy and latest local signed sequence, monotone revocations within one intact database | First-state authenticity and whole-database rollback require an external latest-state witness; preflight may race a control update |
| [Model registry](../src/mos_eisley/core/registry.py) | Capability catalog | `resolve` may lower unsupported effort and return `substituted=True`; a G6 resolver must require exact identity and effort |
| [Shared spending](SHARED_SPENDING.md) | Serialized worst-case reservation and conservative held/uncertain states | Local ledgers can be cloned or bypassed; a G6 session/cohort scope and broker-only paid path need enforcement |
| [Skill provider transaction](SKILL_RUNTIME_PROVIDER_TRANSACTION.md) | Durable before-send intent, one invocation, no automatic retry/release, read-only recovery | It is bound to skill runtime authority; it is not a general G6 routing dispatcher or an external witness |

## Trust boundaries

```text
untrusted task, model output, repository and optional worker
                 | bounded task intent, no provider credential
                 v
trusted controller -> exact policy/feature decision -> trusted G6 broker
                                                       | verify full chain,
                                                       | current routes/spend,
                                                       | witness and one-use claim
                                                       v
                                          credential-owning provider transport
                                                       |
                                                       v
                                                   provider

independent signers -> signed promotion/activation/control evidence
external monotonic witness -> latest control and claim state
restricted audit/monitor -> stop operator and independent assessment
```

The broker and its configuration, provider transport, local filesystem/SQLite,
trusted clock, OS identity, authority-policy distribution and witness client are
inside the proposed trusted computing base. The provider and network may time out,
duplicate responses or give uncertain delivery. Model output, repository content,
worker claims, copied receipts and optional telemetry are untrusted inputs. The
worker never receives provider keys, signer keys or a writable control/ledger
handle. Separate OS identities or an equivalent enforced boundary are required
before claiming resistance to same-user process or filesystem interference.

## Blocking invariants

1. **Authority.** Recompute the complete frozen-policy, holdout, promotion,
   activation and preflight chain from independently supplied sources at admission.
   Reject stale, changed, revoked or incomplete evidence. A receipt alone is not
   a bearer. Only a separately reviewed broker operation may authorize a send.
2. **Exact route.** Bind owner, task, stage, attempt, policy version, selected
   candidate and request digest to provider, backend, model, effort, client,
   prompt/skill, toolset, capabilities and fixed output/context limits. Check the
   current catalog, conformance, price and drift evidence for that exact tuple.
   Reject `substituted=True`, nearby models, lower effort, changed tools and
   unqualified fallback. A new decision with fresh eligibility and before-send
   evidence is required if the selected route becomes unavailable.
3. **One use.** One durable task-attempt key maps to at most one provider-send
   intent. Commit the intent before the first operation that may transfer data.
   Concurrent workers, duplicate messages, restart and copied admission artifacts
   cannot create a second intent. The provider transport must have retries
   disabled. Once intent exists, no automatic retry or replacement grant is
   permitted even if delivery is unknown.
4. **Spending.** Reserve the maximum exposure in the owner/session/cohort scopes
   before a grant or send. A missing response leaves full exposure held or
   uncertain; a price/usage violation blocks new admissions. Budget pressure may
   cause stop, never a silent downgrade. No refund or cap reset is inferred from
   timeout, cancellation or missing provider output.
5. **Control.** A signed state must match the independently witnessed latest
   state, clear stop/revocation flags and meet policy freshness at admission.
   A local valid hash chain or short-lived preflight is insufficient on its own.
   The witness must reject rollback, cloning and false first-state bootstrap.
6. **Owner and evidence.** Decision, admission, send intent and terminal outcome
   retain bounded, owner-scoped hash/provenance records before their respective
   effects. Missing before-send evidence makes the attempt ineligible for
   inference, but does not justify erasing a possible spend. No raw task content,
   bearer or credential enters the selection aggregate or operational event.
7. **Stop.** New authorization stops when the signed control stop/revocation,
   witness, spend, monitor or route-freshness gate fails. An already committed
   provider call remains possibly in flight and must be inventoried; stop cannot
   retroactively cancel or prove non-delivery.

## Proposed witness and dispatch boundary

The recommended first design is a separately operated monotonic service with an
enrolled trust root. It durably records the current signed control sequence and
digest, rejects older/equivocal sequences and nonmonotone revocation sets, and
exposes an atomic **claim** keyed by owner, cohort, task attempt and exact request
digest. A claim returns an authenticated, short-lived, one-use result bound to
the latest control state. The broker must verify this result and durably consume
the claim with its local send intent. An unavailable or disagreeing witness
blocks admission. Merely copying the local SQLite anchor to another file or host
does not supply this property.

**Control-race contract to approve:** the witness claim commit is the proposed
linearization point for a new authorization. A stop committed before that point
denies the claim. A stop after it blocks later claims, while an already claimed
attempt may have been sent or may still be in flight. The broker should make a
final witnessed check immediately before the transport call and abandon an
unsent attempt if stop is observed, but this check alone cannot promise that no
provider request arrives after a concurrent stop. If operations require the
stronger guarantee, they must approve a fenced lease or send guard whose stop
latency and failure behavior are explicitly tested. G6-03 cannot claim atomic
revocation across a nontransactional provider API without that decision.

Bootstrap must begin from an independently witnessed genesis identity and first
signed control state. The witness operator retains the latest accepted sequence
and digest independently from the broker host. Restore/restart compares local
anchor and witness before any new claim; mismatch, lost witness state, clone or
unknown prior claim blocks sends. Key rotation uses a new reviewed trust-policy
lineage and witnessed transition. Emergency stop must be executable by an enrolled
control authority even when the broker host is unavailable; rollback and re-entry
need a new signed state, current route evidence and independent approval.

The witness API, persistence technology, quorum, clock source, network topology,
claim lifetime, operator and maximum stop latency are open design decisions. A
single service controlled by the broker's OS identity would not close the local
rollback threat.

## Proposed attempt state and crash recovery

| State | Durable fact | Send or retry rule |
|---|---|---|
| `proposed` | Bounded decision and exact request prepared | No provider send; changed eligibility requires a new decision |
| `reserved` | Unique maximum-cost reservation held | No send without current authority; reservation remains held after crash |
| `claimed` | Witness accepted unique attempt under one control state | No second claim; an unsent failure may still retain the hold |
| `intent_committed` | Local one-use marker, request hash, claim and ledger identity fsynced | At most one local transport invocation; recovery never retries |
| `finished` | Validated response and ledger settlement or conservative terminal failure | No new send; record full outcome lineage |
| `unknown` | Intent exists but transport or outcome cannot be proved | No retry or automatic budget release; operator inventory only |

The exact durable ordering between external claim, local reservation and local
intent requires fault-injection review: these stores are not one distributed
transaction. Any partial state consumes its unique attempt identity and keeps
possible spend conservative. Read-only recovery correlates witness claim, local
intent, broker audit, provider outcome and ledger without fabricating a missing
event. A recovered `finished` record proves local processing, not provider
authorship, billing finality or independent task quality.

## Threats and required negative evidence

| Threat or failure | Required behavior and test |
|---|---|
| Model/repository changes route or request | Exact digest/role/owner binding rejects changed model, effort, prompt, toolset, output limit, request body and cross-owner claim before credential access |
| Catalog or provider drift | Missing/stale route observation, removed capability, changed client/model version and selected-route outage trigger eligible fixed fallback or stop with a new decision |
| Signer collusion or key substitution | Enrolled role/key separation and independently distributed authority-policy digests checked; custody and human independence assessed outside code |
| Local anchor or ledger copied/rolled back | Witness detects older/unknown control or claim state; no new send on mismatch; restore drill retains held exposure |
| Revocation and send race | Deterministic interleavings before claim, after claim, before local intent and at transport entry meet the approved linearization/stop contract |
| Concurrent duplicate or crash | Parallel claims, process kill after every durable step, restart and replay yield at most one local send intent and no automatic retry/refund |
| Provider timeout or cancellation | Burn authorization; hold/mark uncertain exposure; record possible in-flight send; cancellation does not imply provider cancellation |
| Budget or monitor outage | Admission fails closed under exhausted task/session/cohort cap, ledger violation, witness loss and required monitor loss; fixed fallback still obeys its own cap and authority |
| Missing or leaked audit | Before-send record absence prevents dispatch; logs contain no credential, bearer, raw content or cross-owner selection material; audit sink failure follows the approved fail-closed policy |

The candidate fault-injection matrix makes the expected stop point observable:

| Case | Forced interleaving or crash | Required observation |
|---|---|---|
| F1 | Restore local anchor or claim store from an older intact copy | Witness mismatch; zero new claims and sends |
| F2 | Stop commits before claim | Claim denied; no reservation is treated as a send |
| F3 | Stop commits after claim, before local intent | No new claim; abandon unsent attempt if final check sees stop; hold remains conservative |
| F4 | Stop races final check and transport entry | Behavior matches the explicitly approved claim/lease linearization rule; any possible in-flight send is recorded |
| F5 | Two workers claim the same attempt concurrently | Exactly one claim can commit; loser cannot reserve another attempt identity or send |
| F6 | Kill after reservation, claim and intent commits in separate runs | Each restart reports its exact partial state; no retry, duplicate intent or automatic release |
| F7 | Timeout/cancel after transport entry, before outcome | One local invocation at most; full uncertain exposure and possible delivery retained |
| F8 | Ledger settles, then outcome persistence fails | No new send; recovery shows settled ledger and incomplete local outcome without inventing a response |
| F9 | Witness, monitor, audit sink or ledger becomes unavailable | New admissions stop; existing in-flight attempt remains visible and conservatively charged |

Use synthetic keys, an inert transport, a controllable clock and process-level
fault injection first. Production-like drills must repeat the relevant cases on
the selected host and witness deployment. A passing simulator does not certify
signer custody, provider delivery or target-host durability.

## Review packet and exit decision

To freeze G6-01, the owner and independent reviewer must approve: the first
cohort and exact route scope; named signer/witness/operator roles and real key
custody; witness bootstrap, rollback, claim and stop semantics; exact fallback;
spending and time ceilings; the state machine and ambiguous-send policy; an
executable race/crash test matrix; safe audit/retention and on-call recovery;
and a bounded verification budget. The reviewer should compare this draft with
[plan §26.4](mos-eisley-plan.md#264-delivery-order-and-accountable-gates),
[R3](adaptive-reasoning-routing.md#delivery-gates), and the
[production project template's verification guidance](../../production-project-template/docs/PRODUCTION_BLUEPRINT.md).

Until those decisions are recorded and independently reviewed, G6-01 remains a
draft. G6-02 may use synthetic fixtures to test exact resolution only after its
own owner, reviewer, acceptance protocol and resource ceiling are fixed. Nothing
in this draft changes the existing preflight or authorizes traffic.
