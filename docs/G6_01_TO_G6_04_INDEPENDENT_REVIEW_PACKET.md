# G6-01 through G6-04 independent-review packet

Status: **assembled for independent review; all four gates open**, 2026-09-27.
This packet indexes the offline contracts, implementation and tests. It records
no owner approval, independent finding, operational acceptance or production
dispatch authority. The [G6 project plan](G6_ACTIVATED_ROUTING_PROJECT_PLAN.md)
and [G6-05 qualification plan](G6_05_OPERATIONS_EXACT_CANDIDATE_QUALIFICATION_PLAN.md)
remain the gate contracts. G5 has qualified no policy; runtime preflight denies
dispatch.

## Scope and source identity

Review in dependency order: G6-01 trust and operating contract; G6-02 pure
exact-route selection; G6-03 one-use inert transaction; G6-04 synthetic
witnessed control and atomic task/session/cohort admission. This is an offline
engineering review, not target-host qualification.

The candidate HEAD when this packet was assembled was
`805a5161a003c40e3c0c15adb32e62d939f1ea66` on
`docs/session-shape-lifecycle`. The ten files below had no uncommitted changes
when hashed. SHA-256 is over file bytes; this packet is not included. The
reviewer must rehash and record the exact reviewed commit/worktree. A changed
byte requires a new index and review of affected claims.

| Gate | Indexed file | SHA-256 |
|---|---|---|
| G6-01 | [Operational contract draft](G6_01_ROUTING_OPERATIONAL_CONTRACT_DRAFT.md) | `f64ded3c112111be999187a119b9059d1383bf7fc0fc15bb823b6e71c6163f78` |
| G6-02 | [Resolver specification](G6_02_EXACT_ROUTE_RESOLVER_SPEC.md) | `e9824de5e8bd32a0aa2beeb5acd7ffbf743ae7ac2b7f8b1eafed66670cfe9e8d` |
| G6-02 | [Resolver source](../src/mos_eisley/run/exact_route.py) | `e4bd2dbf72e4cbc9eea6eeda246920e7ec7c93a4af9ed85941d0a327d043c969` |
| G6-02 | [Resolver tests](../tests/test_exact_route.py) | `bbf9b667f3d4889774955b3145d3e79de13a8308c6318e7c3f51570ee176541e` |
| G6-03 | [Transaction specification](G6_03_ONE_USE_BROKER_TRANSACTION_SPEC.md) | `24a2f8746cfd70c6ed2e9dd5410e6a63a7091b58fc39291eaca93e870f237c3d` |
| G6-03 | [Transaction source](../src/mos_eisley/run/routing_transaction.py) | `869ae2996b81f447194d66f2901abfa6f093ce4fab14c891b9412274b4c09644` |
| G6-03 | [Transaction tests](../tests/test_routing_transaction.py) | `b51555ff8287608d018feabaa3c6b25900f8c03a4928cc99d673a941b366fc4b` |
| G6-04 | [Witness and budget specification](G6_04_WITNESSED_CONTROL_BUDGET_SPEC.md) | `afc4fdd920215d7e93c3577135c7e391ab71382cbffe7338681e8f813692ced8` |
| G6-04 | [Witness and budget source](../src/mos_eisley/run/witnessed_admission.py) | `c9c6ebd6197cf84fe948ee8918b8eeb45394baedd84bfc2087e0adb98799a1e7` |
| G6-04 | [Witness and budget tests](../tests/test_witnessed_admission.py) | `3bec895720bf5cd07502815e6ae1f10fdee9927a171b4f16f1d3ad81f381a864` |

The reviewed runtime boundary also depends on the [preflight
contract](ROUTING_RUNTIME_PREFLIGHT.md), [promotion](ROUTING_PROMOTION.md),
[activation eligibility](ROUTING_ACTIVATION_ELIGIBILITY.md),
[shared spending](SHARED_SPENDING.md), registry and policy models. Their source
chain must be independently checked for a live candidate in G6-05; this index
does not freeze or qualify them. A saved preflight, selection, admission receipt
or this packet is never a send capability.

## Evidence-to-gate matrix

| Gate | Offline evidence available | Independent check and decision still needed |
|---|---|---|
| G6-01 | The draft names trust boundaries, seven blocking invariants, witnessed claim as proposed authorization point, conservative recovery and F1-F9 negative oracles. | Owner and operations freeze actual cohort, roles, exact fallback, ceilings, stop latency and recovery. Security reviewer accepts or rejects the threat model, bootstrap, rollback and stop-race rule. Freeze acceptance protocol and resource ceiling. |
| G6-02 | `resolve_exact_route` is pure selection. R1-R11 fixtures exercise identity, sealed fallback, effort downgrade denial, catalog drift, feature derivation and preflight expiry. | Inspect for `ModelRegistry.resolve`, provider or ledger access; compare selected route with independently sourced policy and registry. Accept execution-profile handoff and focused protocol. G6-01 must close first. |
| G6-03 | `execute_offline_routing_transaction` uses inert transport, hash-only durable intent and local synthetic witness/budget/monitor. T01-T15 include duplicate, crash, stop, timeout, cap, bad response and recovery cases. Proven scope is at most one **local inert transport entry** per attempt. | Inspect exact envelope, unique keys, before-send ordering, zero retry, audit failures and read-only recovery. Determine which T01-T15 oracles have direct evidence. Accept attempt ID and retained-exposure rules, claim-commit stop race and fixture ceiling. |
| G6-04 | `SyntheticWitnessedAdmission` combines control and three cumulative budget scopes in one synthetic admission transition with separately simulated checkpoint. W01-W15 cover bootstrap, rollback, outage, stop races, atomic caps, uncertainty and settlement. | Inspect enrollment and scope-policy authority, checkpoint CAS, local-anchor comparison, receipt verification, final read and no-retry path. Review process-cut evidence from a separate identity. Approve real checkpoint/custody/recovery design before live claim. |

G6-03 models separate local budget reservation and witness claim. G6-04
supersedes that ordering for a later broker: the
[offline witnessed transaction path](../src/mos_eisley/run/routing_transaction.py)
must call one witnessed claim that checks control and all three budgets before
intent or transport entry. Review both entry points and record discrepancies
between the specs and fixtures. Neither is a credentialed broker.

The [G6-01 technical gate review](G6_01_TECHNICAL_GATE_REVIEW.md) records the
source assessment and gate blockers. It is not an enrolled independent security
decision; the G6-01 decision field below remains open.
The [G6-02 technical gate review](G6_02_TECHNICAL_GATE_REVIEW.md) records the
pure resolver assessment and R1–R11 coverage gaps. It is not an enrolled
independent G6-02 decision; that decision field also remains open.

## Reproduction record and proposed limits

Run from the repository root against the rehashed snapshot:

```sh
uv run --frozen python -m unittest \
  tests.test_exact_route \
  tests.test_routing_transaction \
  tests.test_witnessed_admission
```

Assembly run on 2026-09-27: **58 tests passed** in 17.785 seconds with no
provider call or paid send. This is a local synthetic run, not independent
reproduction or a G6-05 target-host drill. Test count does not establish that
every specification row has independent coverage. The reviewer records the
exact command, environment/build, counts, observed negative oracles and
findings. An oracle that cannot be shown from source and test evidence stays
open even if the suite passes.

Freeze exact failpoints, expected claim/intent/transport counts and budget
totals before the next reviewed pass. G6-03 proposes at most 16 concurrent
workers, 40 process-kill runs, 200 synthetic transaction cases and zero provider
calls/paid spend. G6-04 proposes at most 16 workers, 50 process-kill cases, 250
synthetic admissions and zero provider calls/paid spend. These are **fixture
ceilings**, not live traffic or spending authority. G6-01/G6-02 owner,
reviewer and resource ceilings remain unset. A broader campaign needs a new
reviewed protocol.

## Open findings and required dispositions

| ID | Gate | Missing decision or evidence | Required disposition |
|---|---|---|---|
| P01 | G6-01 | First cohort, stages, fallback, budget/window, on-call and stop latency unset. | Owner and operations freeze scope and decide whether claim-commit in-flight behavior is acceptable or a fenced send guard is required. |
| P02 | G6-01/G6-04 | Real signer separation, custody, enrolled genesis, witness operator, checkpoint/quorum, clock and rollback-resistant storage unselected. | Security and operations owners document and exercise topology. Synthetic SQLite cannot close this. |
| P03 | G6-02/G6-03 | Selection does not pin exact tools, output limits or provider options; execution profile is fixture-only. | Review production profile mapping, authority binding and exact request constructor. Unknown mapping denies. |
| P04 | G6-03/G6-04 | Inert transport proves a local entry bound only; no target-host evidence for SDK retries, credential/OS isolation, network or durable audit. | Security reviewer inspects live call graph and target host; run G6-05 O01-O10 with inert endpoint before provider credential enablement. |
| P05 | G6-04 | Stop after final read can race provider arrival; ambiguous CAS and retained spend need operator recovery. | Approve in-flight bound, stop deadline and read-only reconciliation; exercise on selected topology. |
| P06 | G6-01 through G6-04 | Named implementers/reviewers, frozen acceptance protocols and approval signatures unrecorded. | Record distinct roles, exact evidence digests, findings and dated decisions below. Never backdate. |

New blockers need source location, severity, reproducer, owner and resolution
evidence. A code or contract change invalidates its indexed hash and requires
review of dependent claims.

## Independent decision record

Complete only after source inspection and relevant reproduction. Rejection or
return for revision is valid; an absent entry stays **open**. Keep private
evidence with its approved custodian and cite only bounded digests and safe
status here.

| Required field | Current value |
|---|---|
| Reviewed commit/worktree and rehash result | Open |
| G6-01 implementing owner, operations owner and independent security reviewer; separation basis | Open |
| G6-02 through G6-04 implementers and independent reviewers; separation basis per gate | Open |
| Frozen acceptance protocol and fixture resource ceiling per gate | Open |
| Reproduction command/build, negative oracles, call graph and discrepancy findings | Open |
| G6-01 accept/reject: scope, threat model, race rule, stop latency, fallback and witness plan | Open |
| G6-02 accept/reject: resolver and execution-profile handoff | Open |
| G6-03 accept/reject: one-use ordering, retained exposure and inert fault evidence | Open |
| G6-04 accept/reject: witnessed admission fixture and live witness requirements | Open |
| Remaining findings, owners, deadlines and G6-05 handoff | Open |

Gate order is strict: G6-02 follows G6-01; G6-03 follows G6-01/G6-02; G6-04
follows G6-03 and approval of an actual witness design. Even accepted offline
gates do not supply G5 qualification, real custody, route observations,
target-host drills or G6-05 go. G6-06 requires a separate owner/operator
release. Until then, preflight denial and fixed-route/full-review operation
remain in force.

Sampling receipts remain metadata only. This packet contains no sampling
registry, custodian mapping, labels, outcomes, prompts, transcripts, model
responses or tool output. Missing probabilities, independence groups, labels
and splits must not be inferred from it.
