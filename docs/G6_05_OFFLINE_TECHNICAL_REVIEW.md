# G6-05 offline qualification technical review

Status: **offline technical review completed; G6-05 qualification gate open**,
2026-09-27. This review assesses the
[qualification plan](G6_05_OPERATIONS_EXACT_CANDIDATE_QUALIFICATION_PLAN.md),
its metadata validator and the
[inert target-host drill package](G6_05_INERT_TARGET_HOST_DRILL_PACKAGE.md),
with later G605-05/G605-06 handoffs and a signed owner-decision/R2 join.
It is not an audited G5 review, an independently observed host drill, a G6-05
owner decision or dispatch approval. The G6-01 through G6-04 independent
decisions are open; G5 has qualified no policy. Runtime preflight still denies
dispatch.

## Reviewed snapshot and verification

Repository HEAD was `c6a427805a5eaf692de462c0f88ed42a4be5b8d0`.
The current worktree includes the G605-02 through G605-06 offline implementations
and the end-to-end readiness-to-R2 binding rehearsal;
the exact reviewed artifact hashes are:

| Artifact | SHA-256 |
|---|---|
| [Qualification plan](G6_05_OPERATIONS_EXACT_CANDIDATE_QUALIFICATION_PLAN.md) | `6d518d7c39c8d74493aafce5f92d7d69565744cf125cd815710bc3ec5230547d` |
| [Packet validator](../src/mos_eisley/run/routing_qualification.py) | `580039b37a179baa6e1b1a15d71b7b21a82435a4b5ff4a44dcc10abf1a432f16` |
| [Packet and handoff tests](../tests/test_routing_qualification.py) | `643ef445abe75c93b9bf7c7379b56dd4ef39576cd037f8ed7d9f095e735e62e1` |
| [Host drill package](G6_05_INERT_TARGET_HOST_DRILL_PACKAGE.md) | `739a7774d8db3fc02d2eb237c818d1253eca10f183254cddf5396da8e5ad333c` |
| [Drill index validator](../src/mos_eisley/run/routing_host_drills.py) | `641561cbb30c6a87e81b62be9d6f3da6cb7b2a3415d97d7f35612fcc1be7f342` |
| [Drill index tests](../tests/test_routing_host_drills.py) | `afb12c5df03ffdaaeb94c6d4180e266486f6f278d4938015aaf5796bf71c7125` |
| [Source-evidence handoff package](G6_05_SOURCE_EVIDENCE_HANDOFF_PACKAGE.md) | `ce0885227f99a83546440d719444825a8854c0917c637a83854450008e1d643b` |
| [Source-evidence handoff validator](../src/mos_eisley/run/routing_source_handoff.py) | `81516cc75b4e8a12cc885978867e51a19c0758828b223dc7ebe876e488d7213c` |
| [Decision-readiness package](G6_05_DECISION_READINESS_PACKAGE.md) | `37faa519ec6add7aeda295ebafc1ede60b5fbf49f4d94db042456371e9935dba` |
| [Decision-readiness validator](../src/mos_eisley/run/routing_decision_readiness.py) | `b7543da53ea019b9dc46b219c5fb72a70fd9e57869f51bc7b9b174dfa02ff92c` |
| [Signed owner-decision and R2 handoff](G6_05_OWNER_DECISION_R2_BINDING.md) | `22801bc611ae8767a118517ca05921907e55e19896ee87a0008886c68d71bcf3` |
| [Owner-decision contract](../src/mos_eisley/run/routing_owner_decision.py) | `1775899b5fca7143ac1b2f3c3d1c04db3f96a33e9a4f929063cc357a72a4e232` |
| [R2 entry join](../src/mos_eisley/run/cohort_entry.py) | `f8b65ebacfd8a1f345dcf69dc163a56702c9327f9a90435b1b0ed2ad080f2f9d` |
| [R2 synthetic tests](../tests/test_cohort_r2_entry.py) | `c9a553326aa321df330dc7def8346a96c53c0b4a5a62ee18a99cbbb9fee91128` |
| [R3 synthetic handoff tests](../tests/test_cohort_r3_attempt.py) | `63c84717704bcb545deed525fe197fa177ea72890c24a2de116020123b5d6837` |

`uv run --frozen python -m unittest tests.test_routing_qualification
tests.test_routing_host_drills tests.test_cohort_r2_entry
tests.test_cohort_controller tests.test_cohort_r3_attempt` passed **85 tests**.
Ruff passed and Pyright
reported zero errors on the focused validators and tests. I inspected
the strict schemas, canonical digests, route and evidence coverage, signature
checks, drill matrix, CLI boundary and source-to-source handoff. No protected
sampling registry, custodian mapping, label store or outcome store was read.

## Supported offline claim

`validate_offline_qualification_packet` checks a versioned packet at an
explicit UTC time. It binds an evidence index to the packet digest; requires
G6-01 through G6-04, Q1 through Q6, O01 through O10 and each declared
applicable G2/G3/G4 record; checks exact candidate IDs, route identity,
price ceiling and freshness; and checks drill summary counts and latency
against packet limits. Four distinct enrolled reviewer IDs and public keys
must sign `accept` decisions over the exact packet and evidence digests.
Missing, extra, failed, stale, tampered or mismatched metadata denies.
G605-03 evidence schema version 2 requires the exact drill protocol and index
digests. The packet validator now requires both drill objects, runs the joined
drill check, matches Q6 to the index digest and each O record to a
domain-separated digest of that case's indexed observations, and requires
identical drill totals, operator/checker IDs and collection order. Changing
the drill index changes the qualification evidence digest and invalidates the
four signed reviews until they are made again for that exact evidence.

`validate_inert_host_drill_index` requires every named O01–O10 fault, pins a
coarse expected status for each, binds the reported protocol/build/host/witness
identities, checks count ordering, one-entry/abandon/stop markers, measured
limits, source digest presence and separate named producer/checker IDs. Its
CLI rejects an incomplete index and emits only bounded assessment fields.
The G605-02 `validate_joined_inert_host_drill_index` composes that check with
the exact `OfflineQualificationPacket`. It denies changed packet, broker build,
target host, witness deployment and test-protocol identities; raised protocol
worker/crash/admission/latency ceilings; or a protocol/review outside the
packet's decision window. The CLI's `--qualification-packet` option selects
this joined check and marks the result `packet_checked`. A standalone CLI run
still checks only the drill index.
G605-04 protocol schema version 2 pins the exact request maximum to the
packet and enforces code-owned minimum claim, intent, checkpoint and retained
exposure conditions for relevant O02/O03/O04/O08 faults. Before and after
the O03 unacknowledged journal cut, the independent checkpoint cannot advance;
post-checkpoint and post-receipt cuts must retain the claim and full maximum.
Invalid price, timeout, cancellation, invalid usage and settlement failure
must retain full exposure. Outcome-write failure may instead show a valid
checkpointed settlement.
All assessments keep qualification and dispatch fields literally false; the
drill assessment also keeps `target_host_verified` false.

The exact claim is **metadata shape and internal consistency for a synthetic
packet and drill index**. Neither validator retrieves the referenced source
artifacts, authenticates a real host or witness, verifies role independence or
custody, checks a real provider catalog, measures a stop, or validates an
audited G5 claim. The synthetic `reviewable` result can be obtained from
self-constructed fixture evidence and keys. It is a review queue state, not a
qualification result.

## Q1–Q7 qualification trace

| Step | Offline evidence inspected | Remaining decision |
|---|---|---|
| Q1 G5 | Packet carries G5 claim, report, use-claim, population and estimand identifiers; validator requires a current `Q1` pass record. | The audited G5 source chain and statistical decision were not accessed or verified. No policy is qualified. |
| Q2 promotion | Packet pins promotion authority/receipt digests and a `Q2` record. | Validator does not rebuild or verify the promotion source chain or signer custody. |
| Q3 exact routes | Exact route metadata, catalog/pricing/conformance/drift digest fields, freshness and normalized-cost ceiling are checked. | Candidate and observation claims require independent source inspection; the packet's route list itself is not derived from the frozen policy. |
| Q4 activation | Authority, control-anchor and preflight digests plus a `Q4` record are required. | Validator does not rebuild the signed activation chain, current revocations or runtime preflight. |
| Q5 deployment | Packet names host/build, OS identities, credential custodian, witness, monitor, audit, clock and network policy; worker and broker OS IDs must differ. | No OS, network, credential, signer or witness deployment was inspected. |
| Q6 exercises | The packet validator requires the joined drill index; Q6 and all O01–O10 records bind its digest or per-case observation digest, and the summary must match. Code-owned fault minimums deny weakened post-claim and full-exposure summaries. | The join verifies metadata consistency, not source artifacts or target-host faults. See G605-05. |
| Q7 decision | Four domain-separated Ed25519 signatures over packet and evidence digests, distinct IDs/keys, dates and `accept` fields are checked. | Trust roots are caller supplied; human independence, evidence authorship, operations acceptance and the project owner's actual G6-05 decision are unverified. |

Declared prerequisite applicability is digest-bound: changing the G2/G3/G4
flags invalidates an existing evidence index and reviews. The validator cannot
decide whether a milestone was correctly marked inapplicable.

## O01–O10 drill trace

| Case | Metadata oracle represented | Source evidence still needed |
|---|---|---|
| O01 bootstrap | Enrolled, unknown, duplicate, substituted and older-anchor IDs are mandatory. | Actual enrolled root and rollback-resistant high-water. |
| O02 one-use/budget | Duplicate, changed request, last headroom and clone IDs; one-entry and count-order checks. | Per-scope totals and independent concurrent writer observation. |
| O03 crash cuts | Six journal/checkpoint/receipt/intent/entry IDs; post-commit claim, checkpoint and full-exposure minimums, plus no premature checkpoint advance. | Separate-process restart inventory and independent checkpoint evidence. |
| O04 stop race | Four ordered stop IDs; abandon/one-entry statuses. | Measured stop delivery and approved in-flight bound on the selected topology. |
| O05 outages | Witness, checkpoint, monitor, audit, clock and network IDs. | Actual failure isolation and conservative recovery. |
| O06 stale/route drift | Seven freshness, revocation, capability and fallback IDs. | Current exact-route and authority evidence before credential access. |
| O07 rotation/rollback | Six rotation, rollback, loss and epoch IDs. | Independent custody, high-water reconciliation and reviewed lineage. |
| O08 transport/settlement | Timeout, cancellation, usage, price and write-fault IDs; one local entry bound and full-exposure minimums except for a validated outcome-write settlement. | Independent usage, billing and settlement source inspection. |
| O09 isolation/audit | Owner, worker key, direct transport and audit IDs. | OS/credential separation and independently operated audit source. |
| O10 operations | Stop, alert, backup, compromise, rollback and re-entry IDs. | Named operator exercise, latency, incident inventory and fresh activation decision. |

The host-drill test's complete synthetic index is generated from the oracle
itself. That verifies parsing and denial behavior; it does not show an
independently observed host run. The source digest and expected-state digest
fields are pointers for later inspection, not proof that the observed state
matched the frozen postcondition.

## Findings and required disposition

| ID | Class | Finding and closure |
|---|---|---|
| G605-01 | Gate blocker | G5 qualification, applicable G2/G3/G4 evidence, G6-01 through G6-04 independent decisions, named distinct operational/review roles, actual witness/custody topology and target-host exercise are absent. The owner and independent reviewers must supply these through the plan's audited and operational workflows before a G6-05 decision. |
| G605-02 | Offline addressed; independent review open | `validate_joined_inert_host_drill_index` now checks the exact packet, identities, ceilings and window, and preserves the standalone index denials. Five synthetic tests cover exact/narrower bounds, every listed identity and raised ceiling, stale/extended windows and CLI mismatch. Rehash and independently reproduce this worktree before accepting the closure. A standalone index check remains insufficient. |
| G605-03 | Offline addressed; independent review open | Evidence schema version 2 requires the protocol/index digests; `validate_offline_qualification_packet` requires and checks both objects, Q6 and each O record, exact summary/roles/timing and the joined drill result. Five synthetic tests cover missing/changed digests, all case links, summary/role/time drift, an invalid index and re-signing after index change. Independently rehash and reproduce this worktree before accepting closure. The metadata join does not authenticate the source observations. |
| G605-04 | Offline addressed; independent review open | Protocol schema version 2 pins request maximum and code-owned O02/O03/O04/O08 minimums. The validator now rejects zero post-receipt claims, missing intents or checkpoint advances, premature journal checkpoint advance and underreported full exposure even when an oracle is weakened. Three new synthetic tests cover weakened protocol bounds and missing observed state, including every full-exposure fault. Rehash and independently reproduce; source truth still needs G605-05 inspection. |
| G605-05 | Offline handoff prepared; source authentication open | The [source-evidence handoff package](G6_05_SOURCE_EVIDENCE_HANDOFF_PACKAGE.md) enumerates G5, prerequisite, packet, route, qualification and every drill-fault source slot; binds an inspection protocol, reviewer roster, custody and checker assignments; and denies incomplete, stale, disputed or rebound metadata. Its validator does not open an underlying source or prove that a digest corresponds to a claimed observation. Independent source review, role/custody checks and target-host reproduction must be recorded outside these validators; do not promote `handoff_ready` or `reviewable` to `go`. |
| G605-06 | Offline decision queue and end-to-end R2 join prepared; owner decision open | The [decision-readiness package](G6_05_DECISION_READINESS_PACKAGE.md) binds source inspections, finding and operations dispositions, exact packet/handoff/review digests and Q7 signature order. The [owner-decision/R2 handoff](G6_05_OWNER_DECISION_R2_BINDING.md) adds a domain-separated signed go/no-go contract and reruns G605-06 at synthetic R2 against its frozen inputs and qualified scope. All assessments remain metadata-only and authority fields stay false. The actual Q7 owner decision, operations runbook acceptance, statistical/security signoff on real evidence, stop latency, current exact routes and G6-06 release are unperformed. Keep the explicit no-go/fixed-route state until each separate gate is satisfied. |

**Technical conclusion:** the validators are useful fail-closed metadata screens
for the stated synthetic inputs, and their authority fields stay false. The
G605-02 packet/protocol, G605-03 evidence binding, G605-04 fault-oracle and
G605-05 source-inventory, G605-06 decision-queue and end-to-end signed
owner-decision/R2 binding gaps are addressed offline.
Source authentication and the actual
independent gate decisions still prevent treating `reviewable` as a complete
G6-05 evidence packet. The **offline technical review is
complete**; G6-05 qualification remains **open** and no target-host or live
send is authorized.

| Independent decision field | Current value |
|---|---|
| Audited G5 claim and prerequisite decisions | Open |
| G6-01 through G6-04 independent accept/reject references | Open |
| G605-02 through G605-04 independent reproduction and dispositions | Open |
| G605-05 independent source inspection and handoff reproduction | Open |
| G605-06 independent readiness reproduction and owner decision | Open |
| Target host, witness/checkpoint custody, source inspections and O01–O10 results | Open |
| Distinct operations, owner, security and statistical reviewers; dated decisions | Open |
| Explicit G6-05 owner go/no-go for an exact candidate and operating envelope | Open |

Sampling receipts remain metadata only. This review contains no prompts,
transcripts, model responses, tool output, outcomes, protected sampling data,
or inferred probabilities, groups, labels or splits.
