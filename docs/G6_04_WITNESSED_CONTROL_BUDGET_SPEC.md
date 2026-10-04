# G6-04 witnessed control and budget admission: offline implementation design

Status: **offline implementation and synthetic fault suite added; independent
gate open**, 2026-09-26. This is the G6-04 design and implementation handoff in
the [G6 plan](G6_ACTIVATED_ROUTING_PROJECT_PLAN.md). The
[synthetic admission service](../src/mos_eisley/run/witnessed_admission.py),
[broker integration](../src/mos_eisley/run/routing_transaction.py), and
[fault tests](../tests/test_witnessed_admission.py) implement this offline
contract. They are not a live witness deployment or routing authorization.
[G6-01](G6_01_ROUTING_OPERATIONAL_CONTRACT_DRAFT.md) still needs
operating approval; [G6-03](G6_03_ONE_USE_BROKER_TRANSACTION_SPEC.md) has an
inert-provider transaction but uses local synthetic witness and budget stores.
The [current preflight](ROUTING_RUNTIME_PREFLIGHT.md) and signed activation
policy retain their literal dispatch/activation denials. No G5 policy is yet
qualified.

## Decision and safety boundary

Replace the G6-03 fixture's separate `budget.reserve()` and `witness.claim()`
steps with **one witnessed admission** that checks current signed control,
three cumulative budget scopes and one-use attempt identity in a single durable
state transition. A separately retained monotonic checkpoint must detect a
copied, replaced or rolled-back admission database before any later claim.
Keep the credential-owning send and durable before-send intent in the G6-03
broker boundary. An admission receipt is evidence for that boundary, not a
provider bearer or permission granted by a saved preflight JSON file.

The offline implementation may use three private SQLite files in separate
fixture directories for the broker transaction store, witness state and
checkpoint. These simulate distinct failure domains; they do not prove real
operator separation or rollback resistance if all files can be restored
together. The live service's operator, persistence/quorum technology, enrolled
root, network authentication, clock source, fencing, stop latency and target
host have to be approved before G6-04's live gate. An external service controlled
by the same broker OS identity does not close the rollback threat.

The proposed control linearization point remains the **committed witnessed
admission**. A stop committed before admission denies. A stop committed after
admission blocks later attempts, but that attempt may be in flight. A linearizable
final read immediately before the inert transport abandons an unsent attempt
when it sees any newer control, stop, rollback alarm or outage. A stop racing
after the final read can still precede provider arrival. If operations require
zero arrivals after stop, they must approve a fenced send guard with an explicit
latency and failure contract; this design does not claim that stronger property.

## Existing contracts and exact handoff

| Current source | Reuse and gap |
|---|---|
| [`RoutingControlAnchor`](../src/mos_eisley/run/activation_control.py) | Verifies signed control, enrolled signers, strict sequence/time advance, append linkage and monotone revocations in one intact private database. It cannot authenticate its first state or detect whole-database rollback. |
| [`RoutingRuntimePreflight`](../src/mos_eisley/run/routing_preflight.py) | Rebuilds the G5/promotion/activation chain and checks the latest local anchor, but is short-lived, non-authorizing and can race a new control. Rebuild from independently supplied sources at broker admission; never promote its denial fields. |
| [`SpendLedger`](../src/mos_eisley/run/spend_ledger.py) | Has serialized worst-case holds and conservative settlement for one local ceiling. It has no atomic task/session/cohort policy and a copied ledger can reset exposure. Do not call three separate ledgers and call the result atomic. |
| [`routing_transaction.py`](../src/mos_eisley/run/routing_transaction.py) | Establishes exact request binding, deterministic attempt key, intent-before-inert-send, no retry and read-only recovery. Its synthetic witness and budget are deliberately local. Retain these invariants while replacing steps 1–2 with the single admission port below. |

`SignedRoutingActivationControl.control` supplies `sequence`, `issued_at`,
`valid_until`, `emergency_stop` and sorted, grow-only revocation sets. Its
`activation_authorized` field is literally false and must remain so. The
witness stores/verifies the complete signed control and
`AnchoredRoutingControl.anchor_entry_sha256`, not just a caller-supplied
sequence or digest. It independently pins `RoutingControlAnchorPolicy` and
`RoutingActivationAuthorityPolicy` digests. The existing local anchor must
match the witnessed latest anchor entry at admission and recovery. A local
anchor read lock alone does not protect against a witness-host stop.

## Proposed contracts and authority placement

Add `run/witnessed_admission.py` for strict versioned, canonical contracts and
an offline `SyntheticWitnessedAdmission` adapter. Refactor the offline G6-03
orchestrator behind an `AdmissionPort` interface; preserve its existing
`execute_offline_routing_transaction` fixture API as a compatibility adapter.
The new offline path accepts only an inert transport and synthetic admission
adapter. A future credentialed implementation must be separately reviewed.

| Contract or operation | Required fields and behavior |
|---|---|
| `WitnessEnrollment` (proposed) | Lineage/epoch ID, independently enrolled witness signing key and checkpoint identity, exact anchor/activation-authority policy digests, first signed anchor-entry digest and control sequence, approved owner/cohort scope-policy digest, issue/expiry and distinct operator signatures. Domain-separate from existing activation signatures. No broker-generated genesis. |
| `CohortBudgetPolicy` (proposed) | Owner/cohort IDs; valid window; trusted task/session enrollment source; maximum tasks, sessions and attempts; per-task, per-session and cohort ceilings in integer micro-USD; maximum unsettled entries; price-policy/profile digests and no-reset rule. Signed under a separately enrolled budget authority. Changing ceilings or scope identity starts a new reviewed lineage that carries forward prior exposure. |
| `WitnessedAttempt` | G6-03 attempt key, immutable owner/cohort/task/session/stage/attempt IDs, exact request and envelope digests, selected candidate/policy/promotion digests, maximum exposure, budget-policy digest and expected witnessed control/anchor digest. A trusted controller supplies task/session membership; the worker cannot invent IDs or split a task into fresh scopes to evade a cap. |
| `Checkpoint` | Witness epoch, monotonic generation, canonical state digest and predecessor digest, retained outside the witness database. `compare_and_swap(previous, next)` accepts exactly one successor; an ambiguous result stops writes until read-only reconciliation. An authenticated linearizable `read_current()` cannot be served from a stale cache. |
| `WitnessedAdmissionReceipt` | Signed witness identity/epoch, generation, unique attempt and claim IDs, request/envelope/budget-policy digests, exact task/session/cohort scope IDs, full reserved micro-USD, signed control sequence and anchor-entry digest, commit time and short expiry. Return only after witness DB commit **and** checkpoint acknowledgment. Verify the receipt against enrolled key and local expected values before intent commit. It is one-use metadata, not a bearer. |
| `claim_with_budget(attempt, expected_control, now)` | One serializable transaction: verify enrollment/checkpoint, current signed control and revocations, task/session membership, route/policy freshness and all scope headroom; reject duplicate attempt or changed request; insert one full-exposure row and unique claim; increment generation. Return the receipt only after the checkpoint CAS succeeds. No automatic retry on timeout. |
| `advance_control(signed_anchor_entry, now)` | Independently verify control signature, enrolled signer, anchor ID, previous-entry digest, strictly increasing sequence/issued time and grow-only revocations. Commit control and checkpoint through the same ordered writer. A stop is accepted without broker availability; later clear requires a new signed, witnessed state and fresh activation review. |
| `settle_exact(receipt, validated_usage, status)` | Match immutable attempt/reservation identity. Settle once to reviewed cost only for validated usage; otherwise retain full exposure as `uncertain` or `violation`. A violation blocks new admissions. Settlement may proceed after a stop but cannot authorize a new send. Checkpoint every mutation before releasing headroom. |
| `inspect_attempt` / `inspect_scopes` | Read-only authenticated views of claim, reservation and checkpoint generation. No claim, top-up, retry, refund, reset or synthesized missing result. Cross-owner inspection denies without disclosing existence. |

The proposed offline call boundary is:

```python
def claim_with_budget(
    *,
    attempt: WitnessedAttempt,
    expected_control: AnchoredRoutingControl,
    current_preflight: RoutingRuntimePreflight,
    now: datetime,
) -> WitnessedAdmissionReceipt: ...


def read_current() -> WitnessedState: ...
def settle_exact(
    *,
    receipt: WitnessedAdmissionReceipt,
    charged_microusd: int,
    status: SettlementStatus,
) -> None: ...
```

The broker must rebuild the full preflight from independently supplied sources
and compare its exact policy, promotion, control-anchor and selected candidate
digests to the attempt. The witness verifies the signed control and scope
policy independently; neither a copied preflight nor a caller's route-capability
boolean substitutes for those checks. The offline fixture may use synthetic
keys and synthetic task membership, but the interface must require the same
inputs and fail closed when any are absent. The actual witness must never
receive prompt text, tools, model responses, credentials or sampling outcomes.

## Bootstrap and monotonic state protocol

1. **Enroll once.** An independent operator distributes a signed enrollment
   packet and trust root to the broker and witness from an independently
   retained channel. It pins the first *signed* anchor entry, epoch, scope policy
   and checkpoint identity. The witness creates its private state only from
   that packet and an empty matching checkpoint. Unknown genesis, two genesis
   packets for one lineage, an unsigned local first entry or a changed key
   fail before admission. The offline fixture uses pre-created synthetic keys;
   it must test these denials and cannot claim real independence.
2. **Check before every mutation.** The witness obtains a single-writer lock,
   compares its complete durable state generation/digest to the independent
   checkpoint, verifies the enrolled epoch and only then evaluates control or
   budget admission. A broker-local anchor/ledger rollback cannot change this
   high-water mark. An intact but older witness DB, mismatched epoch, lost
   checkpoint, equivocal generation or copied service instance halts admission.
3. **Commit and acknowledge.** Commit the control/admission/settlement mutation
   in the witness journal, then CAS the independent checkpoint from old to new
   generation/digest while holding the writer fence. Return success only after
   CAS acknowledgment. If the process dies after journal commit but before CAS,
   the DB is ahead and recovery halts. If CAS succeeds but the response is lost,
   the claim/hold remains consumed; the broker inspects, never reclaims or sends
   from an uncertain receipt. If CAS result is ambiguous, halt writes and
   reconcile with read-only state inspection under an approved operator path.
   Never delete the ahead row or replay a claim to make stores agree.
4. **Compare on broker restore.** Before a new attempt, compare the pinned
   enrollment, latest witnessed anchor, local anchor, admission receipt and
   budget state. A missing or older local file, new file identity or a different
   policy digest denies. A copied broker transaction store cannot erase the
   witnessed attempt. A restored budget store cannot lower the witnessed
   cumulative exposure because the authoritative row lives with the claim.
5. **Rotate or re-enter only by review.** A new witness key, scope-policy
   lineage or cleared emergency stop needs a signed transition linked to the
   previous witnessed epoch, retained exposure and a new independent activation
   decision. No auto bootstrap, zeroed counter or alternate endpoint is a
   recovery path.

The live checkpoint must itself resist rollback, conflicting writers and
broker-host control. A second SQLite file on the same writable host is only a
fault-injection stand-in. Select and review a real independently retained
counter/quorum or equivalent before claiming rollback resistance.

## Atomic budget accounting and ordering with G6-03

One admission row contributes its current charge to all three scopes through
the same immutable owner/cohort/task/session IDs. `held`, `uncertain` and
`violation` contribute the full reserved maximum; `settled` contributes the
validated charge. Compute each scope's total with checked integer arithmetic
under the admission writer lock. Reject if `current_total + maximum > ceiling`
for **any** scope, if scope registration is missing/expired, if the maximum
does not match the reviewed request pricing profile, if unresolved-entry or
task/session/attempt count is exhausted, or if any violation blocks the cohort.
No prefix reservation survives a rejection. Savings from a settled row become
available only after its checkpointed settlement. A timeout, cancellation,
abandoned unsent intent or missing provider response does not free exposure.

The G6-04 sequence is: recompute authority and exact request; check local
anchor against witnessed latest; call `claim_with_budget`; verify signed receipt
and checkpoint generation; commit G6-03 hash-only send intent; perform a fresh
linearizable witnessed control/checkpoint and monitor read; enter the inert
transport once or abandon; settle conservatively; commit local outcome. This
replaces G6-03's **separate** local reserve and witness claim with one atomic
external admission. It does not make witness, local intent and provider I/O one
distributed transaction. Any uncertain cut consumes the attempt and keeps its
maximum exposure until a separately reviewed reconciliation; no automatic
retry, refund, fallback, lower effort or new session ID is permitted.

## Deterministic offline fault and race matrix

Build a fixed-clock harness with synthetic signed control/enrollment/scope
policy, separate witness/checkpoint SQLite processes, barriers at every
durable commit, the G6-03 inert transport and a recorded transport-entry
counter. Use two process identities and independent copies of broker-local
files. For each case assert the witness generation and claim count, exact
task/session/cohort totals, intent count, transport entries, terminal status
and read-only restart result. Tests must not touch live credentials or
sampling stores.

| ID | Injected condition / ordered race | Required result |
|---|---|---|
| W01 | Correct signed enrollment and exact first anchor entry | One genesis epoch/checkpoint; zero claims and spend before admission. A second identical create is rejected, not a reset. |
| W02 | Unknown/older first state, wrong witness key or signer, changed anchor/scope policy, duplicate lineage | Bootstrap denied; no empty substitute database, claim or send. |
| W03 | Valid higher signed control; then restore broker-local anchor to an older internally valid copy | Witness latest remains higher; new admission denied before claim, even if local preflight was saved while current. |
| W04 | Copy/restore witness DB to an older generation while checkpoint stays current; clone two service writers | Both deny until independent recovery; checkpoint CAS permits at most one successor. No duplicate claim or budget reset. |
| W05 | Stop commits immediately before `claim_with_budget`; stop commits immediately after | Before: no claim/hold/send. After: one claim/hold; final read abandons if it observes stop. All later claims deny. |
| W06 | Stop commits after a successful final read but before inert transport entry | At most one previously claimed entry may occur, under the approved claim-commit rule; no later admission. Record possible in-flight send, never promise zero arrival. |
| W07 | Witness or checkpoint unavailable before admission, during CAS, after receipt, and at final read | No new send without acknowledged admission and successful final read. Ambiguous admission retains possible claim/full hold; no automatic re-claim or refund. |
| W08 | Kill before witness DB commit; after DB commit before checkpoint CAS; after CAS before receipt; after receipt before local intent; after intent; at transport entry | Each restart reports exact durable partial state. At most one claim/intent/local entry; no recovery send. DB/checkpoint mismatch halts admission. |
| W09 | Remaining headroom in each task, session and cohort scope is one micro-USD below the proposed maximum in separate fixtures | Atomic denial with no row/claim/checkpoint increment or send for each cap. Headroom exactly equal to the maximum admits once. |
| W10 | Prior held or uncertain row fills one scope; then valid settled saving; then pricing violation | Held/uncertain count in full; only checkpointed valid saving reopens headroom; violation blocks cohort despite arithmetic availability. |
| W11 | Two processes submit same attempt and two different attempts competing for the last scope headroom | Same attempt has one claim/hold; for different attempts only one fits. No partial task/session/cohort reservation. |
| W12 | Change request digest, route/policy, owner, task/session mapping or maximum under same attempt; mint new session for same task | Conflict/denial without disclosure or extra headroom. New trusted task/session enrollment is required, subject to maxima and retained exposure. |
| W13 | Expired/stale preflight, control, scope policy, receipt or route observation; removed capability or policy revocation | Denial at the appropriate boundary. No implicit alternate route; a fallback needs a new qualified decision and admission. |
| W14 | Settle timeout/cancel, invalid usage/price, witnessed-budget settlement failure and local outcome-write failure | Full uncertain/violation exposure on failure, no retry. A checkpointed settlement plus missing local outcome remains visible as two facts. |
| W15 | Monitor outage or unavailable audit sink before admission or at final read | Stop new sends. Existing possibly in-flight attempts remain inventoried and fully exposed until validated settlement. |

Use a bounded fixture ceiling of at most 16 workers, 50 process-kill cases,
250 synthetic admissions and **zero** provider calls or paid spend for this
offline pass. These are proposed verification limits, not live cohort budgets.
The reviewer should inspect each barrier's committed state from another process
before killing the writer. An in-memory fake alone cannot establish ordering.
Assert `transport_entries <= 1` per attempt, no entry without acknowledged
checkpointed claim and earlier durable intent, and no fresh admission when the
witness/checkpoint pair disagrees.

## Review exit and remaining live gate

The offline implementation uses signed synthetic enrollment and scope policy,
separate local SQLite witness and checkpoint stores, process-level crash cuts,
and an inert broker transport. The local checkpoint exercises rollback and
compare-and-swap failure behavior; it does not establish independent custody
or resistance to restoring all fixture files together. Independent review must
freeze the enrollment and scope-policy schemas, checkpoint durability contract,
attempt/session identity source, exact failpoint oracles and fixture ceiling,
and inspect the call graph for any live transport or credential path. The live
gate also needs named independent operators and real custody,
an approved monotonic checkpoint deployment, stop-latency/fencing decision,
current G5 qualification and activation chain, target-host rollback/outage
drills, and an independent security review. Until then this document grants
no dispatch authority.
