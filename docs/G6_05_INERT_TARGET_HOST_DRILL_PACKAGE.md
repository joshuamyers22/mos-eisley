# G6-05 inert target-host drill package

Status: **protocol and metadata validator ready; target-host run not performed**,
2026-09-27. This package turns O01–O10 of the [G6-05 qualification
plan](G6_05_OPERATIONS_EXACT_CANDIDATE_QUALIFICATION_PLAN.md) into a frozen,
reviewable inert exercise. It does not supply a target host, real witness,
independent custody, G5-qualified policy, G6-05 go or provider-send authority.
The [G6-01 through G6-04 review packet](G6_01_TO_G6_04_INDEPENDENT_REVIEW_PACKET.md)
still has open gates.

## Package and run boundary

The [drill index validator](../src/mos_eisley/run/routing_host_drills.py)
defines `HostDrillProtocol`, `HostDrillEvidenceIndex` and
`validate_inert_host_drill_index`. The [synthetic tests](../tests/test_routing_host_drills.py)
exercise complete, missing, substituted and over-limit indexes. The validator
checks metadata shape, all required fault IDs, protocol/build/host bindings,
expected versus observed status, bounded claim/intent/entry counts, checkpoint
monotonicity, retained exposure, timing and distinct named producer/checker IDs.
Its `reviewable` result means the **index is structurally ready for source
review**. `target_host_verified`, `qualification_authorized` and
`dispatch_authorized` remain literal false. It cannot inject faults, authenticate
a host, inspect restricted evidence, verify a person's independence or certify
that a source digest describes the stated observation.
`validate_joined_inert_host_drill_index` additionally takes the exact
`OfflineQualificationPacket` and rejects mismatched packet, build, host,
witness deployment or test-protocol identities; ceilings raised above the
packet; and a protocol or review outside the packet's validity window. Its
`packet_checked` field is true and authority fields remain false. The
standalone index check does not establish this packet binding.
Protocol schema version 2 also pins `request_maximum_microusd` to the packet's
exact request maximum. Code-owned fault minimums prevent an oracle from
lowering required claim/intent bounds or full retained exposure. Index checks
require a checkpoint advance for acknowledged post-claim cuts and no advance
before or after an unacknowledged witness-journal commit. O03 after-journal,
after-checkpoint, after-receipt, after-intent and at-transport rows retain the
full request maximum; O08 timeout, cancellation, invalid usage, invalid price
and settlement-fault rows do too. O08 outcome-write failure may show an exact
checkpointed settlement, so it has no unconditional full-exposure minimum.
These checks compare reported metadata; the independent reviewer must verify
the underlying source and actual ordering.
The qualification validator additionally requires the exact protocol/index,
matches Q6 to the index digest and O01–O10 to the `drill_case_sha256` of each
case's fault observations, and compares reported drill totals. Changing the
index changes the qualification evidence digest and requires new reviews.
Run the fixture checks with:

```sh
uv run --frozen python -m unittest \
  tests.test_routing_host_drills tests.test_routing_qualification
```

The actual exercise must use the named host and separately operated witness and
checkpoint topology from a frozen G6-05 packet. Use an inert provider endpoint,
no provider credential and zero paid sends. Pin the exact broker build, worker
and broker OS identities, clock, signer roots, route observations, monitor and
audit sink before the first fault. The operator and independent checker freeze
the protocol and its expected postcondition artifact digests **before** the
first run. Later changes start a new protocol; never rewrite an oracle after
seeing an outcome. The G6-05 packet's ceiling and retention policy control the
run. The protocol cannot raise them.

## Freeze, run and validate

1. Produce one strict `HostDrillProtocol` JSON file. Set the exact G6-05 packet
   digest, broker build digest, target host and witness deployment IDs, test
   protocol digest, operator/checker IDs, UTC window, worker/crash/admission
   ceilings, measured stop/alert deadlines and request maximum from the
   already approved packet.
   `paid_provider_calls` must be zero. The host/build/witness/test-protocol
   identities must match the packet; no protocol ceiling or expiry may exceed
   its packet limit or decision deadline. Include every `(case_id, fault_id)` in
   `REQUIRED_FAULTS` exactly once, in the module's declared order. For each,
   freeze an `expected_status`, expected-state artifact SHA-256, claim/intent/
   per-attempt transport-entry upper bounds and minimum retained exposure.
   `one_entry` requires exactly one observed local entry; `abandon` requires a
   consumed claim and no entry; `stop_acknowledged` requires a higher independent
   checkpoint generation. The module pins each named fault's status and the
   non-weakening claim, intent, checkpoint and full-exposure conditions.
2. On the named host, run each fault below against inert transport. At each
   barrier, the checker reads the witness/checkpoint, broker intent, independent
   audit and alert states from a separate identity. After a kill, restart with
   read-only inventory first; never re-claim, resend, refund or repair a row to
   manufacture a pass. Record actual generation before/after, per-attempt
   claim/intent/entry counts, full retained exposure, audit/alert counts and
   stop/alert latency. Preserve raw diagnostic material only in its approved
   owner-isolated store; place a digest and safe status in the index.
3. Produce `HostDrillEvidenceIndex` JSON with one observation for every frozen
   fault, sorted by `(case_id, fault_id)`. `pass` requires an evidence-source
   digest and distinct named producer/checker. Failed or unavailable faults
   remain in the index with their actual status. Never omit an unfavorable
   result. The index binds the packet, build, host, witness and protocol digest.
4. Run the metadata check from the repository root:

   ```sh
   uv run --frozen python -m mos_eisley.run.routing_host_drills \
     protocol.json evidence.json --qualification-packet packet.json \
     --now 2026-09-27T12:00:00+00:00
   ```

   Use the actual explicit UTC review time. Exit 0 means structurally
   `reviewable`; exit 1 means the index failed. Invalid JSON or a schema error
   also fails the run. The command prints only bounded assessment fields and
   digests, never source artifact contents. A run without
   `--qualification-packet` checks the index alone and cannot close the
   G605-02 packet/protocol binding finding.
5. The independent security reviewer and operations owner inspect the **source
   artifacts** and host topology, reproduce fault ordering, compare the source
   digests, and record pass/fail/unavailable for each O01–O10 in the G6-05
   packet. Only their separate, dated decision can supply real drill evidence.
   A passing index alone cannot turn O01–O10 into accepted G6-05 records.

## Required fault points and acceptance oracles

Each fault ID is mandatory. The frozen protocol supplies the exact postcondition
digest and numeric bounds; the table below states the minimum meaning of a
passing source review. Counts are per original attempt unless stated otherwise.

| Case | Fault IDs | Required source observation |
|---|---|---|
| O01 | `enrolled_genesis`, `unknown_genesis`, `duplicate_epoch`, `substituted_root`, `older_anchor` | Only the independently enrolled signed first state starts. Duplicate/reset, wrong root and older valid local anchor deny; checkpoint high-water does not decrease. |
| O02 | `duplicate_attempt`, `changed_request`, `last_headroom`, `cloned_writer` | Exactly one claim/intent/local entry for the same attempt at most; changed request conflicts; task/session/cohort last headroom and cloned writer cannot create a second charge or entry. |
| O03 | `before_journal`, `after_journal`, `after_checkpoint`, `after_receipt`, `after_intent`, `at_transport` | Kill at each durable cut and inspect from another process. Ambiguous claims retain full exposure; no restart path reclaims, refunds or sends. DB/checkpoint mismatch blocks new admission. |
| O04 | `before_claim`, `after_claim`, `before_final_read`, `after_final_read` | Stop before claim denies. A stop observed at final read abandons an unsent attempt. After final read, at most the already claimed entry may occur; measured worst-case acknowledgment and observation fit the frozen bound. |
| O05 | `witness_outage`, `checkpoint_outage`, `monitor_outage`, `audit_outage`, `clock_outage`, `network_partition` | Each required-path outage denies new admission. Preserve in-flight inventory and full uncertain exposure. Restoring a dependency does not clear a stop. |
| O06 | `stale_preflight`, `stale_receipt`, `expired_route`, `revoked_policy`, `removed_capability`, `route_drift`, `unavailable_fallback` | Every stale, changed or missing exact-route/authority input denies before credential access. No lower effort, nearby model or unqualified fallback. A different eligible route needs a fresh decision and admission. |
| O07 | `signer_rotation`, `witness_rotation`, `witness_rollback`, `local_rollback`, `checkpoint_loss`, `new_epoch` | Unreviewed root/epoch changes and restored old state deny. Recovery compares independent high-water with claims, intents, audit and exposure; it never deletes an ahead row or invents a checkpoint. |
| O08 | `timeout`, `cancellation`, `invalid_usage`, `invalid_price`, `settlement_fault`, `outcome_fault` | Against inert endpoint, at most one local entry. Unproved cost remains fully uncertain or violation; read-only inventory distinguishes witnessed settlement from missing local outcome. |
| O09 | `cross_owner`, `worker_key_access`, `direct_transport`, `missing_audit` | Cross-owner inspection and worker credential/witness access deny; direct unbrokered transport is blocked. Missing before-send audit blocks the send; operational events contain no raw task content or credential. |
| O10 | `operator_stop`, `alert_handoff`, `backup_restore`, `compromise`, `rollback`, `reentry` | Named operator stops without broker cooperation; on-call alert fits frozen deadline; backup/restore and incident inventory preserve high-water, claims and exposure. Re-entry needs fresh reviewed activation, never restoration alone. |

For each case, the checker records the exact command/fault barrier, source build,
process identities, before/after snapshots, elapsed clock readings, expected
and observed counts, discrepancy and source artifact digest. A pass requires
the independent reviewer to verify these facts and the approved host isolation;
a digest by itself is an inventory pointer. Record safety violations as
findings, not exceptions to the oracle. No row may claim provider delivery,
billing finality or policy benefit from inert transport.

## Handoff to G6-05

The indexed drill result may support Q5/Q6 and O01–O10 only after separate
source and custody inspection. A real G6-05 go still requires all prior G6
gates, G5 qualification, authenticated promotion/activation, current exact-route
observations, independent signer/witness custody, target-host security review,
accepted runbooks and a separate owner decision. If any required fault fails,
is unavailable, lacks source evidence or exceeds the frozen ceiling, record
**no-go** and keep fixed-route/full-review operation.

Sampling receipts are metadata only. Do not place prompts, transcripts, model
responses, tool output, outcomes, labels, sampling probabilities, groups or
splits in the drill index. Missing sampling fields remain unknown.
