# G6-03 one-use broker transaction: implementation design and synthetic faults

Status: **offline implementation and synthetic fault suite added; independent gate open**,
2026-09-26. This specifies and records the inert-provider G6-03 slice of the
[G6 plan](G6_ACTIVATED_ROUTING_PROJECT_PLAN.md). It does not authorize a live
dispatch. [G6-01](G6_01_ROUTING_OPERATIONAL_CONTRACT_DRAFT.md) still needs owner,
operations and independent security approval; [G6-02](G6_02_EXACT_ROUTE_RESOLVER_SPEC.md)
provides only a pure selection. The [runtime preflight](ROUTING_RUNTIME_PREFLIGHT.md)
continues to say `dispatch_authorized: false`.

## Scope and required decisions

Build an offline, one-attempt transaction around a synthetic monotonic witness,
the existing [spend ledger](SHARED_SPENDING.md), a durable local intent store and
an inert transport. The transaction must prove at most one **local transport
invocation** for one attempt. It cannot prove exactly one provider arrival or
billing event. Live witness operation, cumulative budget enforcement, key
custody and target-host drills belong to G6-04/G6-05.

The [offline transaction module](../src/mos_eisley/run/routing_transaction.py)
and [synthetic fault tests](../tests/test_routing_transaction.py) implement this
slice. The executable entry point is `execute_offline_routing_transaction`;
`inspect_offline_routing_transaction` is read-only. Its exact concrete
`InertRoutingTransport` cannot contact a provider, and its profile accepts only
the empty inert provider-option set and synthetic fixture capability evidence.
`SyntheticRoutingWitness`, `SyntheticRoutingBudget` and
`SyntheticRoutingMonitor` are local test fixtures. They do not establish real
attestation, independent persistence, monitor operations or production budget
enforcement. The live broker API and actual provider-option mapping must be
reviewed and implemented in later gates.

Before implementation is accepted, record a named implementing owner and
independent reviewer, an acceptance protocol using the test matrix below, and
a resource ceiling for fixtures, concurrent workers and process-kill runs. The
owner must approve the attempt identity and abort/hold policy. The operating
owner must approve the control race rule and maximum stop latency before any
live broker is built. The proposed rule here uses **witness claim commit** as
the authorization linearization point: a stop committed before it denies the
claim; one committed after it blocks subsequent claims, while the claimed
attempt may be in flight. A final check abandons an unsent attempt if it sees
stop. That check cannot prevent a provider arrival after a concurrent stop. A
stronger promise requires a separately reviewed fenced send guard or lease with
specified failure and latency behavior.

## Trusted boundary and proposed interfaces

Add `src/mos_eisley/run/routing_transaction.py` with strict versioned contracts.
Keep `RoutingRuntimePreflight` and `ExactRouteSelection` non-authorizing. The
credential-owning broker is the sole caller of this module and of the provider
transport. No task worker, repository content or model output can call a send
method or obtain a credential, writable ledger, witness client or intent store.

| Proposed interface | Contract |
|---|---|
| `RoutingExecutionProfile` | Independently reviewed, immutable mapping from role and output contract to structured-output requirement, exact tool catalog and schema digests, prompt/skill compatibility, provider options, endpoint class, output/context limits, data permission and cost ceiling. Unknown mapping denies. Pin its digest in the signed runtime authority lineage; a caller-supplied G6-02 `requires_structured_output` boolean is insufficient. |
| `RoutingRequestEnvelope` | Frozen owner, cohort, task, stage and attempt IDs; current policy, activation, control, preflight and selection digests; selected candidate ID and complete exact route; reviewed execution-profile digest; canonical `ModelRequest` digest; provider/backend/model/effort/client/prompt/tool-schema and provider-option digests; maximum output/context limits; cost policy and ledger IDs. Validate all fields against independently supplied authority and request bytes immediately before any claim or credential access. No implicit `ModelRegistry.resolve` substitution. |
| `WitnessPort` | `read_latest()` and atomic `claim(attempt_key, request_digest, expected_control_sequence, expected_control_digest)`; claim returns authenticated unique claim ID and committed control version or a definite denial. Duplicate, unknown, stale, rolled-back, timed-out or unverifiable results deny. A read-only `inspect_claim` supports recovery; it cannot issue another claim. The synthetic implementation is deterministic and separately persistent for process tests; it is not a production witness. |
| `BudgetAdmissionPort` | `reserve_exact(attempt_key, reservation_digest, maximum_microusd, task_scope, session_scope, cohort_scope)` atomically checks all three ceilings and returns immutable reservation IDs; `inspect` is read-only and `settle_exact` accepts only the original IDs and validated amount/status. The G6-03 fixture implementation uses one SQLite transaction for all scopes. The live implementation must have G6-04 anti-rollback enforcement. |
| `RoutingTransactionStorePolicy` | Pre-created private SQLite path, schema version, allowed owner/cohort, pinned witness identity, control anchor, spend ledger and response-store identities, maximum attempts and wait. Validate file identity and permissions; never silently create a replacement store. Use a rollback journal, `synchronous=EXTRA`, `BEGIN IMMEDIATE`, unique constraints and an fsynced commit before transfer. |
| `RoutingSendIntent` | Hash-only before-send record: unique attempt key, request/envelope/policy/selection/profile digests, candidate and control version, witness claim ID, ledger entry IDs, creation time and `may_have_transferred=true`. It contains no raw prompt, task text, credential, bearer, response or outcome. The intent is immutable; a separate bounded outcome row tracks later processing. |
| `RoutingTransport` | Exact `provider`, backend, client version and `automatic_retries: Literal[0]`; one `send(frozen_request)` call. Reject a retrying or identity-mismatched client before reservation. No wrapper, SDK or proxy may perform hidden retries. |
| `execute_routing_transaction(...)` | One broker-only async operation returning a strict `RoutingOutcome` or denial. It accepts verified authority sources, frozen envelope/request, current registry and observations, witness/ledger/store/transport handles and a trusted clock. It performs the ordering below; it never accepts a saved preflight or selection as a bearer. |
| `inspect_routing_transaction(...)` | Read-only recovery view joining local attempt, witness claim, ledger and outcome facts. It never sends, claims, reserves, retries, refunds, recreates a store or infers delivery. |

The existing [skill provider transaction](SKILL_RUNTIME_PROVIDER_TRANSACTION.md)
is the local-store and zero-retry reference: it records before send, charges
timeouts conservatively and recovers read-only. Its authority is skill-specific;
G6 needs a separate reviewed interface and witness claim. Reuse internals only
where the exact contracts remain valid.

### Identity and uniqueness

Define `attempt_key = SHA256(canonical(owner_id, cohort_id, task_id, stage_id,
attempt_id))` with domain separation and explicit schema version. The same
key is used for the store unique index, witness uniqueness and deterministic
ledger entry ID. The request digest is separately bound to the claim and intent.
An existing attempt with a different request digest is a conflict, never a new
attempt or replacement route. A legitimate next attempt needs an independently
authorized new attempt ID and its own task/session/cohort budget admission; the
broker cannot mint one to escape a consumed claim or cap. One exact fallback
requires a new decision and attempt identity under the approved policy.

The local store has `UNIQUE(attempt_key)`, `UNIQUE(witness_claim_id)` and
`UNIQUE(ledger_entry_id)`. Witness uniqueness is on attempt key, with request
digest equality required for inspection. The ledger reserves once for the
deterministic entry ID; a concurrent duplicate cannot create another hold.
Include owner and cohort in every query predicate and verify their equality to
the pinned store policy. Do not expose cross-owner records through a duplicate
or inspection response.

## Transaction ordering and durable states

The broker validates the complete frozen G5/promotion/activation/control chain,
current route evidence, reviewed execution profile, exact request, witness
identity, monitor health and full worst-case task/session/cohort headroom. It
also checks that transport retries are disabled. These are **admission checks**,
not permission from G6-02. Missing or stale evidence denies without send.

| Step and durable state | Action and invariant | Failure or restart rule |
|---|---|---|
| 0. `prepared` | Freeze and canonicalize the envelope/request. Validate exact identity, authority and cost ceiling. No durable permission exists. | Deny on any mismatch. No send. |
| 1. `reserved` | Atomically reserve the full maximum exposure with deterministic ledger IDs, checking task, session and cohort ceilings in one budget admission. Record or correlate the local attempt identity. | If reservation status is unknown, deny and retain possible hold. Never allocate a new ledger or attempt ID. |
| 2. `claimed` | Ask the witness for one atomic claim at the expected latest signed control state. Verify response signature, identity, digest and freshness. | Definite denial stops. Timeout is ambiguous: inspect only; never re-claim automatically. The reservation stays held pending documented reconciliation. |
| 3. `intent_committed` | Under the local store lock, verify no previous intent, recheck envelope and claim, and commit the immutable hash-only intent with `may_have_transferred=true` before any operation capable of moving request bytes. | Commit failure stops before transport. Once committed, recovery never retries or automatically releases exposure. |
| 4. `pre_send_checked` | Read latest witnessed control and required monitor state immediately before transport entry. If stop, mismatch or outage is observed, mark the attempt abandoned without calling transport. | This cannot atomically fence a stop concurrent with the later send. Keep the claim consumed and hold until explicit reconciliation. |
| 5. `send_entered` | Invoke the zero-retry transport **once** with exactly the frozen request. No fallback inside this transaction. | Timeout, cancellation, crash or exception after entry means possible delivery: full exposure `uncertain`, no retry or automatic refund. |
| 6. `outcome_recorded` | Validate provider identity, model, tier, usage and price against the envelope. Settle only a valid response; mark mismatch or impossible cost as `violation` with full exposure. Persist outcome after ledger transition. | Ledger transition failure preserves full hold/uncertainty and blocks new admission. Outcome-write failure leaves recoverable incomplete local outcome, not a new send opportunity. |

Cross-store steps are not atomic. A process kill after reservation or claim
consumes the attempt identity; read-only recovery reports the partial state.
An unused, definitively unsent reservation may be released only through a
separate, reviewed reconciliation procedure with proof sufficient for the
approved budget policy. The initial G6-03 implementation does **not** release
it automatically. A local intent is conservatively marked transfer-possible
even if the final check later abandons it. The witness claim is never recycled.

`SpendLedger.reserve_many` already serializes worst-case holds and represents
`held`, `settled`, `uncertain` and `violation`. Its current single policy ceiling
does **not** implement the three-scope admission above. G6-03 must use a
synthetic multi-scope adapter or extend the ledger schema under separate review;
three independent `reserve` calls would leave unsafe partial admission. A
single local ledger file also cannot resist copying or rollback. G6-03 fixtures
must exercise all three caps and retained holds; G6-04 must bind aggregate
limits to an approved anti-rollback boundary. Any absent or exhausted cap
denies; it does not trigger lower effort or a hidden fallback.

### Send, stop and recovery claims

The testable safety claim is: for each attempt key, one durable local intent
precedes at most one local transport invocation, and no recovery path invokes
the transport. If the process dies at or after transport entry, delivery and
billing are unknown. A `finished` row proves local validation and ledger
processing only; it does not prove provider authorship, final billing or task
quality. A stop before witness claim must deny. A stop after claim may leave an
already claimed attempt in flight; the last check reduces that window but does
not change the approved linearization point. Report every possible in-flight
attempt to the operator and retain its spend exposure.

## Synthetic fault harness and acceptance oracles

Use synthetic keys and policy data, a fixed clock, a deterministic witness
whose claim and stop commits can be ordered by barriers, a real temporary
SQLite ledger/store and an inert transport that records entry before returning
or failing. For process-crash cases, run the broker in a subprocess and kill it
at named barriers **after durable commit**; restart inspection in another
process. Never use a live credential, provider endpoint or production cohort.
Assert exact attempt/claim/intent/ledger counts, local invocation count,
owner isolation and stored field allowlists, not merely an error string.
Proposed fixture ceiling for this slice: at most 16 concurrent workers, 40
process-kill runs, 200 synthetic transaction cases and zero provider calls or
paid spend. Record any broader campaign as a new reviewed verification pass.

| ID | Injection | Required oracle |
|---|---|---|
| T01 | Invalid authority, stale route, request digest/tool/prompt/effort/output limit/provider option mismatch, or retrying transport | Denial before reservation, claim, intent and send; no substitution or changed request reaches transport. |
| T02 | Two threads and two processes submit identical attempt/envelope concurrently | One ledger ID, at most one witness claim and intent, at most one transport entry. Loser observes consumed/conflict state. |
| T03 | Same attempt key with changed request, owner, cohort or candidate; cross-owner inspection | Conflict/denial; no second hold, claim or send and no cross-owner disclosure. |
| T04 | Task, session or cohort cap already exhausted; earlier held/uncertain exposure; ledger unavailable | No claim, intent or send; original exposure remains. No new ledger file or attempt ID is silently allocated. |
| T05 | Kill before and after reservation commit | Before: zero effects. After: one held reservation, zero claims/intents/sends; restart is read-only and never retries/releases. |
| T06 | Witness definite denial, outage, timeout or ambiguous reply after reservation | Zero intents/sends; held exposure. Timeout inspection reports ambiguity and never issues a second claim. |
| T07 | Stop commits immediately before claim; stop commits immediately after claim | Before: witness denies, zero sends. After: at most one claim; final check observes stop and abandons when ordered before it; no later claim succeeds. |
| T08 | Kill after claim commit and before intent commit; fail local intent fsync/commit | Claim consumed, held exposure, zero sends. Restart inspection correlates claim without manufacturing intent or sending. |
| T09 | Kill after intent commit before final check; final witness/monitor check fails | One intent, zero sends, conservative hold; restart neither retries nor refunds. |
| T10 | Stop races after successful final check and before transport entry | Behavior follows claim-commit rule: at most one already claimed local entry, no later claims. Record possible in-flight send; test does not assert impossible zero provider arrivals. |
| T11 | Kill at transport entry; timeout, cancellation or exception after entry | Exactly one local entry at most; full exposure uncertain; restart reports possible delivery and performs no send. |
| T12 | Wrong model/tier/provider, missing or invalid usage, price breach | No valid settlement; full exposure `violation`, stop new admission, one local send at most. |
| T13 | Valid response; then ledger settle failure; then separate run with outcome-write failure after settlement | Valid path settles once. Ledger failure retains conservative exposure. Outcome failure reports settled ledger plus incomplete outcome without retry or fabricated response. |
| T14 | Copy/restore local intent store or ledger to older state; witness reports the same attempt already claimed or control ahead | Broker denies another send for that attempt on identity/state mismatch and requires operator reconciliation. Broader ledger rollback and fresh-attempt budget escape remain G6-04 tests. |
| T15 | Required monitor or audit sink unavailable at admission or final check | Admission/unsent attempt stops under approved fail-closed policy; no silent continuation; in-flight attempt remains inventoried. |

Check each cut point with an invariant oracle: `transport_entries <= 1`,
`intent_count <= 1`, no entry without an earlier durable intent and claim,
and no reserve/claim/intent/send for a mismatched envelope. Verify subprocess
barriers with a second process reading committed rows before the kill; an
in-memory mock alone cannot establish crash ordering. Repeat tests with a
corrupt store, stale witness epoch and unknown bootstrap state; all must deny.
Only the selected host, real witness and actual SDK/transport can later support
claims about filesystem durability, external rollback resistance and hidden
network retries.

## Evidence, privacy and review exit

The before-send operational record contains IDs, bounded status and digests
only. Keep raw request and response in the separately governed owner-scoped
response store when needed; never put prompts, transcripts, model responses,
tool output or outcomes into a sampling artifact. Treat sampling receipts as
metadata only and do not infer probabilities, independence groups, labels or
splits. A transaction record is not evaluation eligibility evidence by itself.

The G6-03 offline implementation is available for independent review against
the exact attempt identity, request envelope, witness/store API, ordering and
fault oracles above. The **milestone gate** remains open until a named owner and
reviewer approve its acceptance protocol and resource ceiling, confirm the
broker-only call graph and accept the synthetic test evidence. G6-04 must then
resolve external witness bootstrap,
anti-rollback cumulative budget admission, signed stop semantics and target-host
drills before any production authority is considered.
