# G6-04 witnessed control and budget technical review

Status: **technical review completed; independent G6-04 gate open**,
2026-09-27. This is a source and synthetic fault assessment of the
[G6-04 design](G6_04_WITNESSED_CONTROL_BUDGET_SPEC.md), not an enrolled
independent reviewer decision or approval of a live witness. The
[G6-01](G6_01_TECHNICAL_GATE_REVIEW.md),
[G6-02](G6_02_TECHNICAL_GATE_REVIEW.md) and
[G6-03](G6_03_TECHNICAL_GATE_REVIEW.md) independent decisions remain open.
Runtime preflight still denies dispatch.

## Reviewed snapshot and verification

The reviewed repository HEAD was
`c6a427805a5eaf692de462c0f88ed42a4be5b8d0`. The G6-04 source files
had no uncommitted changes and matched the
[independent-review packet](G6_01_TO_G6_04_INDEPENDENT_REVIEW_PACKET.md):

| Artifact | SHA-256 |
|---|---|
| [G6-04 specification](G6_04_WITNESSED_CONTROL_BUDGET_SPEC.md) | `afc4fdd920215d7e93c3577135c7e391ab71382cbffe7338681e8f813692ced8` |
| [Witness and budget source](../src/mos_eisley/run/witnessed_admission.py) | `c9c6ebd6197cf84fe948ee8918b8eeb45394baedd84bfc2087e0adb98799a1e7` |
| [Witness and budget tests](../tests/test_witnessed_admission.py) | `3bec895720bf5cd07502815e6ae1f10fdee9927a171b4f16f1d3ad81f381a864` |
| [Integrated transaction source](../src/mos_eisley/run/routing_transaction.py) | `869ae2996b81f447194d66f2901abfa6f093ce4fab14c891b9412274b4c09644` |

I inspected signed bootstrap and policy binding, the witness journal and
checkpoint commit order, admission and settlement, broker receipt and intent
checks, final control/monitor read, and read-only inspection. No protected
sampling or outcome store was read.

`uv run --frozen python -m unittest tests.test_witnessed_admission` passed
**26 tests** in 11.234 seconds. The later G6-06
[route-change](../tests/test_cohort_route_change.py) and
[audit-outage](../tests/test_cohort_audit_outage.py) suites passed **15 tests**
as supplemental cohort evidence. Ruff passed and Pyright reported zero errors
on the G6-04 witness source, transaction source and focused tests. These are
local synthetic runs, not independent reproduction on an approved target host.

## Source assessment and exact claim

`SyntheticWitnessedAdmission.bootstrap` requires a signed enrollment, signed
budget policy, pinned signed genesis, distinct configured operator and budget
keys, and matching witness/checkpoint identities. `claim_with_budget` reads
the current checkpoint under the witness writer lock, checks signed control,
task/session binding, attempt uniqueness, unresolved limits and all three
cumulative ceilings, then commits one claim and full-exposure hold. The
witness database commits before checkpoint compare-and-swap; a receipt is
signed only after both steps succeed. A crash between them leaves a mismatch
that denies later reads and claims. Settlement is checkpointed and releases
headroom only for a validated `settled` charge; uncertain or violation rows
retain the full maximum. A violation blocks new cohort claims.

The integrated `execute_offline_witnessed_routing_transaction` rebuilds the
runtime source chain, compares local and witnessed control, checks the signed
receipt against the stored claim, commits one hash-only local intent, then
reads control/checkpoint and monitor before the single inert transport entry.
A stop before admission denies. A stop observed after admission abandons an
unsent attempt with the hold retained. A stop after the final read can leave
one claimed entry in flight. Recovery inspects consumed state; it does not
re-send.

The supported claim is **one checkpointed synthetic claim and atomic
task/session/cohort hold per accepted attempt, with at most one local inert
transport entry**. The checkpoint is another local SQLite file under the
same host's custody. It detects selected one-file rollback and ambiguous
commit cuts, but does not resist coordinated restoration of all files or
prove independent service identity, durable quorum, network authentication,
clock trust or operator separation. A signed fixture receipt is not live
routing authority or provider delivery evidence.

## W01–W15 acceptance trace

| Case | Evidence inspected | Review limit |
|---|---|---|
| W01 signed bootstrap | Signed-genesis bootstrap starts at generation zero with no claims; second create fails. | Synthetic keys and local checkpoint do not establish independent enrollment custody. |
| W02 bad bootstrap | Wrong genesis linkage and invalid enrollment signatures fail. Source pins the policy, key, first entry and window. | Focused tests do not enumerate wrong witness key, changed scope/anchor policy, older first state and duplicate lineage separately. |
| W03 local anchor rollback | Advancing witnessed control ahead of the local anchor denies before claim. | The test does not restore an older intact local database from a separate broker identity. |
| W04 witness rollback/clone | Old witness or checkpoint copy mismatches; a cloned witness writer cannot advance the shared checkpoint. | Both SQLite files are locally restorable together; no real independent high-water service is tested. |
| W05 stop around claim | Before-claim stop denies; after-claim stop abandons the unsent intent and retains its hold. | Stop delivery latency and independent stop entry are unmeasured. |
| W06 stop after final read | A stop injected after final check permits one previously claimed inert entry. | Owner and operations have not approved the in-flight bound or a fenced-send alternative. |
| W07 witness/checkpoint outage | Checkpoint CAS failure leaves an ahead journal that halts; final-read checkpoint outage abandons. | Distinct witness outage after receipt and ambiguous CAS acknowledgment are not separately exercised in the focused suite. |
| W08 process cuts | Subprocess kills cover before DB commit, after DB commit, after checkpoint and before receipt. Broker exceptions after admission/intent retain the claim and prevent retry. | After-receipt, after-intent and transport-entry cuts are exceptions or other-suite simulations, not subprocess kills with independent restart oracles. |
| W09 atomic caps | Each of the three ceilings denies at one micro-USD below maximum; equality admits. Two processes compete for the last headroom. | Scope arithmetic is bounded fixture arithmetic, not an approved live budget. |
| W10 exposure/settlement | Held and uncertain exposure count in full; checkpointed settled saving reopens headroom; violation blocks claims. | Operator reconciliation and external billing authorship are unqualified. |
| W11 concurrent claims | Two processes submitting the same attempt produce one claim; two different attempts competing for a full scope produce one winner. | Processes share one local witness lock and host. |
| W12 changed attempt/scope | Changed request under the same attempt, cross-owner inspection and unenrolled session deny. Source pins task/session bindings, digests and maximum. | Focused tests do not separately mutate route/policy, task mapping, owner, maximum or a newly minted session under the same attempt. |
| W13 stale/revoked route | Expired preflight and fabricated selection deny; later cohort route-change tests deny missing, stale or removed observations. Source checks control, policy and receipt windows and signed revocations. | No focused matrix for each expiry/revocation. Route observation is outside `claim_with_budget` and optional for a non-cohort broker call. |
| W14 settlement faults | Timeout and price violation retain full exposure; settlement checkpoint failure halts; checkpointed settlement remains visible when local outcome write fails. | Cancellation and invalid usage variants are not separately exercised in this focused suite. |
| W15 monitor/audit outage | Focused monitor and checkpoint final-read faults abandon. Later cohort audit/alert tests deny missing/unhealthy required paths and abandon on loss. | Audit and alert inputs are optional outside enrolled cohort mode; the focused G6-04 path alone does not satisfy a mandatory audit-sink oracle. |

The focused suite covers the central ordering invariant and several real
subprocess cuts. Its passing count does not imply that every specified fault
variant or proposed ceiling was frozen and reproduced by an independent
reviewer.

## Findings and required disposition

| ID | Class | Finding and closure |
|---|---|---|
| G604-01 | Gate blocker | G6-01 through G6-03 independent decisions remain open. Record the G6-04 implementing owner, distinct reviewer and separation basis, frozen W01–W15 protocol, exact test/build hashes, fixture ceilings and dated accept/reject decision. |
| G604-02 | Contract boundary | The design says the witness checks route freshness. `claim_with_budget` validates candidate membership in a current supplied preflight, but has no independently obtained route observation. The broker's route probe is optional outside cohort mode. Require and bind a current trusted observation at the intended boundary, or explicitly narrow the accepted G6-04 claim and make this a mandatory downstream gate. Removed capability and policy-revocation oracles need independent reproduction. |
| G604-03 | Contract boundary | The design proposes a common `AdmissionPort` and authenticated read-only views. The implementation adds a separate witnessed transaction entry point; direct `read_current` is a local handle with no caller authentication, while scoped inspections check supplied owner/cohort IDs. Freeze the production port and caller-authentication contract before exposing it. |
| G604-04 | Coverage gap | Freeze and exercise W02 wrong-key/policy/lineage variants, W03 restored local file, W07 ambiguous and post-receipt outages, W08 true post-receipt/intent/entry process kills, W12 changed bindings and maxima, and W13 expiry/revocation variants. Record state, generation, three scope totals, intent and entry counts after each cut. |
| G604-05 | Coverage gap | W15 requires audit-sink failure to stop sends. The later cohort fixture makes audit and alerts required only when a cohort is enrolled. Decide the gate's scope and demonstrate required audit/alert health and final-read behavior at that scope; do not count an optional local sink as an independent durable audit service. |
| G604-06 | Live gate | Select and review actual independent enrollment custody, signed scope authority, trusted task/session source, checkpoint durability and fencing, witness operator and clock, read-only reconciliation, and stop latency. Exercise rollback and outage on that topology with an inert target-host transport before any live credential or routing authority. |

**Technical conclusion:** the indexed offline code and tests support a
checkpointed *local synthetic* witnessed admission, atomic three-scope holds,
conservative settlement and the stated one-entry stop race. The full G6-04
contract and independent milestone remain **open** pending G604-01 through
G604-05 dispositions. G604-06 blocks live use even if the offline fixture is
later accepted.

| Independent decision field | Current value |
|---|---|
| G6-01 through G6-03 acceptance references | Open |
| Named implementing owner and independent reviewer; separation basis | Open |
| Frozen W01–W15 protocol, build/test hashes and fixture ceiling | Open |
| Enrollment/scope schemas, authenticated port and checkpoint durability contract | Open |
| Stop-race and re-entry rule; G604-02 through G604-05 dispositions | Open |
| Dated accept/reject decision for this exact snapshot | Open |

Sampling receipts remain metadata only. This review contains no prompts,
transcripts, model responses, tool output, outcomes, sampling assignments or
inferred probabilities, groups, labels or splits.
