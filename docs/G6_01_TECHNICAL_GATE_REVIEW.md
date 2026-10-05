# G6-01 technical gate review and independent signoff record

Status: **technical review completed; G6-01 gate not accepted**, 2026-09-27.
This is a source-and-contract review of the [G6-01 draft](G6_01_ROUTING_OPERATIONAL_CONTRACT_DRAFT.md),
not a signature from an enrolled independent security reviewer. The draft was
prepared in the same project workflow as this review. No independent reviewer,
operations owner or witness operator has been recorded as accepting it. No
provider send, cohort release or change to [runtime preflight](ROUTING_RUNTIME_PREFLIGHT.md)
is authorized by this record.

## Review basis and result

The reviewed G6-01 draft has SHA-256
`f64ded3c112111be999187a119b9059d1383bf7fc0fc15bb823b6e71c6163f78`.
The current repository HEAD was `805a5161a003c40e3c0c15adb32e62d939f1ea66`;
the draft, resolver, transaction, witness and their three focused test files
matched the hashes in the [G6-01 through G6-04 review
packet](G6_01_TO_G6_04_INDEPENDENT_REVIEW_PACKET.md). The review compared the
draft with [plan §26.4](mos-eisley-plan.md#264-delivery-order-and-accountable-gates),
the [R3 operational gate](adaptive-reasoning-routing.md#delivery-gates),
the preflight contract, and the indexed offline source and fault tests. It did
not inspect protected G5 outcome or sampling stores, real keys, a deployed
witness, a target host or provider traffic.

The focused command
`uv run --frozen python -m unittest tests.test_exact_route tests.test_routing_transaction tests.test_witnessed_admission`
passed **58 tests** in 18.272 seconds. Those tests use synthetic authority,
local fixture stores and inert transport. A passing suite supports review of
the proposed safety model; it does not authenticate signers, custody,
independent checkpoint retention, stop latency or provider behavior.

**Assessment:** the draft identifies the main trust boundaries and the
claim-commit stop race without claiming impossible atomicity with a provider.
The offline implementation exercises its central one-use and fail-closed
properties. The G6-01 exit is nevertheless **open** because mandatory operating
choices, independent roles and a prospective acceptance protocol have not
been recorded. This is a gate-blocking readiness finding, not a claim that the
synthetic tests failed.

## Contract review

| Boundary | Source observation | Limit or required decision |
|---|---|---|
| Authority | The draft requires a complete independently sourced policy, promotion, activation and control chain at admission. The [offline witnessed transaction](../src/mos_eisley/run/routing_transaction.py) calls `verify_routing_runtime_sources` before its witnessed claim. Preflight retains literal dispatch denial. | Real source custody and independently distributed trust roots are unestablished. A saved preflight or receipt cannot authorize a send. |
| Exact route | The [resolver](../src/mos_eisley/run/exact_route.py) performs pure exact selection; tests reject unsupported effort and changed catalog/route identity. The transaction checks the frozen request before an inert entry. | The initial exact route/fallback, execution profile and current catalog/price/conformance/drift sources are not owner approved. Candidate ID alone does not bind full tools or output limits. |
| One use and spending | The [G6-04 fixture](../src/mos_eisley/run/witnessed_admission.py) combines one-use claim with task/session/cohort headroom and an independent simulated checkpoint. The inert broker commits an intent before entry and recovery is read-only. | Fixture SQLite and local keys do not resist coordinated rollback or prove a broker-only credential path. The actual witness and budget lineage must be selected and reviewed. |
| Stop | The draft makes witnessed claim commit the proposed authorization point. The final read can abandon an unsent attempt; a stop after that read can race a provider arrival. | Owner and operations must approve that in-flight bound and a measured maximum stop latency, or specify and test a fenced send guard. No numeric limit is recorded. |
| Audit and recovery | The draft requires bounded, owner-scoped before-send evidence and conservative partial-state inventory. Synthetic tests cover missing local outcomes, held exposure and failure at commit cuts. | Actual audit sink, retention, alert delivery, on-call identity and cross-store recovery procedure are not selected or accepted. |

## F1–F9 negative-evidence trace

These are representative synthetic pointers, not a claim that every production
oracle was independently witnessed. The reviewer must inspect exact assertions,
state snapshots and failpoint ordering before accepting a row.

| Draft case | Indexed synthetic evidence | Remaining gate evidence |
|---|---|---|
| F1 rollback | `test_witness_control_ahead_of_local_anchor_denies_before_claim`; `test_rollback_of_witness_database_is_detected_by_checkpoint` | Independently retained real high-water state and restore drill. |
| F2 stop before claim | `test_stop_before_and_after_admission` | Actual stop signer and witness delivery. |
| F3 stop after claim | `test_stop_after_admission_abandons_unsent_intent` | Approved hold and in-flight rule. |
| F4 stop after final read | `test_stop_after_final_check_allows_one_claimed_entry` | Owner-approved latency and, if required, fenced send design. |
| F5 duplicate claim | `test_two_processes_claim_one_attempt_and_compete_for_scope`; `test_threaded_duplicate_has_one_local_entry` | Broker/worker identity separation and target-host race drill. |
| F6 process cuts | `test_process_kills_preserve_exact_checkpoint_boundary`; `test_process_kills_preserve_partial_state_without_retry` | Selected host filesystem and real witness recovery. |
| F7 timeout/cancel | `test_transport_failure_is_uncertain_and_full_hold`; `test_cancellation_after_entry_is_uncertain` | Actual SDK/proxy retry configuration and delivery uncertainty inventory. |
| F8 settlement then outcome loss | `test_checkpointed_settlement_survives_local_outcome_write_failure` | Independent audit/settlement reconciliation. |
| F9 required-path outage | `test_monitor_and_checkpoint_outage_at_final_read_abandon`; `test_monitor_outage_at_admission_and_final_check` | Actual witness, audit, monitor and ledger outages and alert response on target topology. |

The tests are named in the indexed
[transaction](../tests/test_routing_transaction.py) and
[witness](../tests/test_witnessed_admission.py) suites. F9 audit-sink and
on-call behavior is not established by these focused suites. The later
[G6-05 O01–O10 drill package](G6_05_INERT_TARGET_HOST_DRILL_PACKAGE.md)
prepares the target-host exercises but has not run them.

## Gate-blocking findings

| ID | Severity | Finding and exact closure evidence |
|---|---|---|
| G601-01 | Blocker | The first owner/cohort, eligible task types/stages, maximum assignments, time window, per-task/session/cohort exposure and exact fallback are unset. Josh Myers is the project decision owner, but no scope decision is recorded. Freeze one signed scope and budget envelope; no numeric value is inferred here. |
| G601-02 | Blocker | Signer identities, independent custodian and witness operator, enrolled genesis, checkpoint/quorum, clock, claim lifetime, network topology and rollback lineage are unselected. Record the actual authority separation and independently retained latest-state design; a broker-writable second SQLite file is insufficient. |
| G601-03 | Blocker | The proposed claim-commit stop contract has no owner/operations acceptance, maximum stop latency, on-call path or decision about fenced sends. Record the accepted in-flight bound and recovery policy, then freeze its race oracle. |
| G601-04 | Blocker | No named independent security reviewer, accepted G6-01 protocol, evidence retention rule or bounded verification resource ceiling is recorded. A test run performed before those choices cannot retrospectively supply their approval. Record the independent reviewer, protocol digest, resource ceiling and dated accept/reject finding. |
| G601-05 | Blocker | The exact fallback, immutable execution-profile mapping, required before-send audit/alert path and operator recovery responsibilities are still proposed rather than frozen. Owner, operations and security must approve their contract and safe failure mode. |

Target-host isolation, provider retry behavior and actual witness fault drills
remain G6-05 work after the design gate. They are not represented here as
completed G6-01 evidence. G5 qualification remains a later prerequisite to
live routing, not a substitute for freezing G6-01's operating contract.

## Independent decision to be recorded

The enrolled independent reviewer and operations owner should review the
source/artifact hashes, findings and approved choices above. Record each
identity and separation basis, exact reviewed draft/protocol digests, evidence
source, decision time, `accept` or `reject`, every unresolved finding and the
next review trigger. The project decision owner must separately accept the
cohort, spending, fallback and stop envelope. An absent field means **open**.

| Decision field | Current value |
|---|---|
| Independent security reviewer and separation basis | Open |
| Operations owner, witness operator and signer custodians | Open |
| Owner-approved cohort, budget, fallback and stop contract | Open |
| Frozen acceptance protocol, failpoints and resource ceiling | Open |
| Review of G601-01 through G601-05 and dated accept/reject decision | Open |

Until those entries and closure evidence exist, **G6-01 is not closed**.
G6-02 through G6-04 remain offline fixtures awaiting their own sequential
reviews; G6-05 qualification and G6-06 rollout remain blocked. Sampling
receipts are metadata only, and this report neither reads protected sampling
or outcome stores nor infers missing probabilities, groups, labels or splits.
