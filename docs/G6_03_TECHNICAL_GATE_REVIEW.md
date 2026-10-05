# G6-03 one-use transaction technical review

Status: **technical review completed; independent G6-03 gate open**,
2026-09-27. This is a source and synthetic fault review of the
[G6-03 transaction specification](G6_03_ONE_USE_BROKER_TRANSACTION_SPEC.md),
not an enrolled independent reviewer decision or production broker approval.
The [G6-01](G6_01_TECHNICAL_GATE_REVIEW.md) and
[G6-02](G6_02_TECHNICAL_GATE_REVIEW.md) gate decisions are still open.
Runtime preflight continues to deny dispatch.

## Reviewed snapshot and verification

The reviewed repository HEAD was
`c6a427805a5eaf692de462c0f88ed42a4be5b8d0`. These G6-03 source files
had no uncommitted changes and matched the [G6-01 through G6-04 review
packet](G6_01_TO_G6_04_INDEPENDENT_REVIEW_PACKET.md):

| Artifact | SHA-256 |
|---|---|
| [G6-03 specification](G6_03_ONE_USE_BROKER_TRANSACTION_SPEC.md) | `24a2f8746cfd70c6ed2e9dd5410e6a63a7091b58fc39291eaca93e870f237c3d` |
| [Transaction source](../src/mos_eisley/run/routing_transaction.py) | `869ae2996b81f447194d66f2901abfa6f093ce4fab14c891b9412274b4c09644` |
| [Transaction tests](../tests/test_routing_transaction.py) | `b51555ff8287608d018feabaa3c6b25900f8c03a4928cc99d673a941b366fc4b` |
| [G6-04 witness source](../src/mos_eisley/run/witnessed_admission.py), for handoff inspection | `c9c6ebd6197cf84fe948ee8918b8eeb45394baedd84bfc2087e0adb98799a1e7` |

I inspected the attempt-key derivation, request/profile checks, private SQLite
open and commit rules, unique claim/reservation/intent rows, stop and monitor
reads, inert transport entry, settlement and read-only recovery in source. I
also inspected the [G6-04 witnessed transaction
path](../src/mos_eisley/run/routing_transaction.py) to separate the later
atomic admission work from the original G6-03 function. No protected sampling
or outcome store was read.

`uv run --frozen python -m unittest tests.test_routing_transaction tests.test_witnessed_admission`
passed **48 tests** in 17.950 seconds. Ruff and Pyright passed on the
transaction source and focused tests. The separate G6-06
[audit-outage suite](../tests/test_cohort_audit_outage.py) passed **10 tests**
as supplemental evidence; it does not change the G6-03 primary entry point.

## Source assessment and exact claim

`execute_offline_routing_transaction` checks the supplied selection,
preflight window, request/profile/transport identity and monitor before a
single local budget reservation. `SyntheticRoutingBudget.reserve` uses one
`BEGIN IMMEDIATE` transaction for task, session and cohort totals. The
synthetic witness then commits one claim keyed by the attempt and request
digests. The store commits a hash-only `OfflineSendIntent` before a final
witness/monitor read and the one `InertRoutingTransport.send` call. The store
uses private regular files, SQLite rollback journaling, `synchronous=EXTRA`,
unique attempt and claim keys, and a private writer token inside this process.

The tested safety claim is **at most one local inert transport entry per attempt
after one durable intent**, with no recovery send. A failed or uncertain send
retains the full maximum exposure. A stop committed before claim denies;
one observed after claim but before transport abandons the unsent attempt;
one committed after the final read can leave the already claimed entry in
flight. This is the claim-commit race rule proposed by G6-01, not a zero-arrival
promise. A local `settled` row proves fixture processing, not provider
authorship, delivery or final billing.

The primary function is deliberately an **offline simulator**. It receives a
constructed `RoutingRuntimePreflight` and `ExactRouteSelection`; it does not
rebuild the complete G5/promotion/activation/control source chain or verify an
authenticated witness receipt. Its `SyntheticRoutingWitness` claims are local
unsigned rows. The later `execute_offline_witnessed_routing_transaction`
reverifies `RoutingRuntimeSources`, checks a signed synthetic receipt and
uses checkpointed atomic control/budget admission. Both functions require the
exact inert transport type; neither is a credential-owning production broker.

## T01–T15 acceptance trace

| Case | Synthetic evidence inspected | Review limit |
|---|---|---|
| T01 request/authority drift | `test_request_and_transport_drift_denied_before_spend`, retry-setting and expired-preflight tests reject changed request/profile/transport before reserve. | The primary entry point cannot authenticate the full upstream authority chain or external route observations. |
| T02 concurrent duplicate | Thread and two-process tests produce one local entry and one consumed attempt. | Actual broker/worker identity isolation remains untested. |
| T03 conflicting attempt/cross-owner | Owner replay, changed request and local-copy tests deny through the orchestrator. | Direct synthetic `inspect_claim(attempt_key)` and budget `inspect(attempt_key)` have no owner/cohort argument; trust in access to those handles is assumed. Changed candidate and cross-owner direct-port checks are not explicit. |
| T04 three spending scopes | `test_each_budget_scope_can_deny_without_partial_reservation` and duplicate/cap tests exercise one local SQLite transaction. | Prior uncertain exposure and ledger outage are not separately covered in the G6-03 focused suite; local budget rollback can reset a fresh-attempt total. |
| T05 reserve crash | Process kills before and after reservation show absent versus held state; restart inspection does not send. | Local filesystem durability is not a target-host finding. |
| T06 witness denial/timeout | Stop-before-claim and witness-timeout tests retain the reservation with zero entry. | No authenticated witness, external outage or ambiguous signed receipt exists in this fixture. |
| T07 stop around claim | Stop-before-claim and stop-after-claim tests preserve the proposed in-flight bound. | Owner/operations acceptance of that bound and latency is open. |
| T08 claim-to-intent cut | Process kill after claim and intent-commit failure leave a consumed claim/hold with no entry. | Live cross-store recovery remains unqualified. |
| T09 intent-to-final-read cut | Process kill after intent and monitor outage at final read leave no entry or refund. | Separate required audit health is absent from this primary API. |
| T10 post-final-read race | Test records one inert entry after a stop injected following the final read. | It cannot prove zero provider arrival after stop. |
| T11 at-entry failure | Kill at transport entry, timeout and cancellation tests retain possible delivery/full uncertainty. | The entry log is a local test marker, not durable provider-delivery evidence. |
| T12 response/price mismatch | Wrong provider and price tests produce full-exposure violation; schema rejects malformed response objects. | Model/tier/usage variants are not all retained as focused negative tests. |
| T13 settlement/outcome write | Settlement and outcome-write failure tests show held intent or settled ledger with missing local outcome. | Independent billing/settlement source still needs review. |
| T14 local rollback | Restored old intent store cannot reclaim the same witnessed attempt. | Fresh-attempt budget reset and witness/checkpoint rollback belong to G6-04; same-attempt success is narrower. |
| T15 monitor/audit outage | Monitor outage is covered in G6-03. The later G6-06 audit suite covers separate audit/alert faults in the witnessed path. | `execute_offline_routing_transaction` has no required audit-sink input, so T15 is not complete for this entry point. |

The existing suite is substantive: it includes real subprocess cuts at SQLite
barriers, concurrent processes and read-only restart inspection. It does not
prove that a provider SDK, proxy, network or OS boundary has zero retries or
that all T01–T15 variants were exercised against a selected target host.

## Findings and disposition needed

| ID | Class | Finding and closure |
|---|---|---|
| G603-01 | Gate blocker | G6-01 and G6-02 independent decisions are open. The G6-03 implementation owner, independent reviewer, approved attempt/abort rule, frozen T01–T15 protocol and resource ceiling are unrecorded. Record these before formal acceptance. |
| G603-02 | Contract boundary | The specification describes a broker that verifies the full authority chain and authenticated witness claim; the primary offline function takes synthetic preflight/selection and an unsigned local claim. Accept only the narrower inert one-use claim, or amend the implementation/specification before calling the full contract satisfied. The G6-04 alternate path supplies synthetic source and receipt checks but no live authority. |
| G603-03 | Coverage gap | T15 promises audit-sink outage denial, but the primary G6-03 function has only a monitor. Preserve the later witnessed audit fixture as separately scoped evidence, or revise the G6-03 acceptance oracle. Do not count a local intent row as an independently operated audit sink. |
| G603-04 | Interface gap | The proposed witness/ledger inspection contract calls for owner-scoped access; direct synthetic inspection ports accept only an attempt key. The orchestrator checks its store/owner links, but a future exposed port must enforce owner/cohort authorization itself. Review that boundary before any live service. |
| G603-05 | Coverage item | Freeze or independently disposition the T03 changed-candidate/cross-owner-port, T04 uncertain/ledger-outage, and T12 model/tier/usage negative variants. Current tests demonstrate the core invariant but not each named fault. |
| G603-06 | Downstream live gate | Real signer custody, external monotonic witness/checkpoint, broker-only provider credential, hidden retry inspection, current route evidence, target-host fsync/crash behavior and measured stop latency are unestablished. These are G6-04/G6-05 and owner/operations decisions, not claims of this inert simulator. |

**Technical conclusion:** the indexed offline source and tests support the
one-use **local inert entry** and conservative-stop claims. No path examined
uses the G6-02 result alone as dispatch authority or automatically retries a
consumed attempt. The broader broker contract and independent G6-03 milestone
remain **open** pending G603-01 through G603-05 dispositions. G603-06 blocks
live use even if the offline gate is later accepted.

| Independent decision field | Current value |
|---|---|
| G6-01/G6-02 acceptance references | Open |
| Named implementing owner and independent reviewer; separation basis | Open |
| Frozen T01–T15 protocol, test/build hashes and fixture ceiling | Open |
| Approved attempt identity, hold/abort and stop-race rule | Open |
| G603-02 through G603-05 reviewed dispositions | Open |
| Dated accept/reject decision for this exact snapshot | Open |

Sampling receipts remain metadata only. This report contains no prompts,
transcripts, model responses, tool output, outcomes, sampling assignments or
inferred probabilities, groups, labels or splits.
