# G606-04 operating-gate handoff package

Status: **offline candidate package complete; target-host gate open**, 2026-09-28.
This package prepares the O01–O10 and C01–C09 operating-gate review defined in
the [G6-06 plan](G6_06_BOUNDED_ROLLOUT_ASSESSMENT_PLAN.md) and checked by the
[G606-04 validator](../tools/g6_06_operating_gate.py). It supplies an exact
fault inventory and unfilled input templates. It contains no target-host run,
approved ceilings, source review, G6-05 go, cohort release or dispatch authority.

## Candidate identity and files

The local package is
`private/g60604-candidate-20260928T0104Z` (operator-local and excluded from Git).
The directory is mode `0700` and files are mode `0600`; Git ignores it. Its
`candidate-inventory.json` SHA-256 is
`e583b8240661397d235f765a66065857ac686f4d1de977f97935f17fd0fd6e07`.
Transfer that digest through the chosen custody channel before using the
inventory. The bundled `verify-candidate.py` SHA-256 is
`0d74d2ff8a682d8e436f6a7d74322bbaa5dc0224b801e638a607b12f39559acb`.
The inventory fixes the current validator, host-drill, manifest and synthetic
test source hashes and the hashes of every candidate JSON file. The
`fault-matrix.json` SHA-256 is
`f449b9e726ec9c2a1cad80308baba2e396cc66010fa28a2445e49ba31fa5df50`.

| File | Purpose |
|---|---|
| `fault-matrix.json` | All 35 required C faults in protocol order, with code-owned status and count caps, full-exposure and stop-checkpoint flags. It is a candidate inventory, not the frozen protocol. |
| `manifest-inputs.json` | Unfilled `CohortManifest` for the exact owner, task/session roster, stage, build, host, witness and assignment bounds. |
| `cohort-protocol-inputs.json` | Unfilled `CohortDrillProtocol` with all 35 oracle rows and literal zero paid calls and one-entry final-read bound. |
| `cohort-evidence-inputs.json` | All 35 observation slots, marked `not_run`, with no source or result digests. |
| `anchor-inputs.json` | Unfilled, separately custodied `FrozenOperatingGateAnchor`. |
| `review-packet-inputs.json` | O01–O10 and C01–C09 review slots, all `not_reviewed`. |
| `candidate-inventory.json`, `verify-candidate.py` | Handoff hashes, synthetic preflight metadata and a source/template consistency check. |

The five `*-inputs.json` files are deliberately **invalid** under their strict
contracts. `null` means an external decision or observation is missing; it is
never a value to infer from the synthetic fixture. The `not_run` and
`not_reviewed` markers must be replaced with actual dispositions, including
`fail`, `unavailable` or `reject` when applicable. Do not turn an unfavorable
or absent observation into `pass` or `accept` to complete a packet.

From the repository root, verify the candidate and run the offline tests:

```sh
uv run --frozen python private/g60604-candidate-20260928T0104Z/verify-candidate.py
uv run --frozen python -m unittest -q \
  tests.test_g6_06_operating_gate tests.test_routing_host_drills
```

At preparation, verification reported 35 unrun faults, 19 unreviewed cases
and five rejected templates; the 20 synthetic tests passed. The tests exercise
joins and denials with constructed metadata. They are not target-host
observations or independent source reviews.

## Freeze and execution order

1. Complete the prerequisites under their own custodians: independent
   G606-03 reproduction, G6-01–G6-04 decisions, G5 qualification, accepted
   G6-05 O01–O10 target-host evidence and G6-05 go. Enroll the exact broker
   build, target host, witness deployment and epoch. The G6-05 host protocol
   and evidence must be available as strict `HostDrillProtocol` and
   `HostDrillEvidenceIndex` files. A matching digest is an inventory pointer;
   inspect its underlying source under the approved access procedure.
2. The owner and operations/security reviewers approve one exact manifest,
   resource ceilings, observation cadence, retention, stop and alert deadlines,
   test topology and reviewer separation. Fill `manifest-inputs.json` from
   those records. Set `max_assignments` no higher than the named roster,
   `max_concurrent` no higher than assignments, and the request maximum equal
   to the accepted O protocol. No numeric ceiling from the synthetic fixture
   is approved for a real host. Keep paid provider calls at zero and use an
   inert endpoint without provider credentials.
3. Freeze the detailed C fault barriers and expected **source-state artifact
   digests** before any C observation. Fill the 35 oracle rows in
   `cohort-protocol-inputs.json` from the candidate matrix and approved
   ceilings. For full-exposure rows, set minimum retained exposure at least
   equal to the approved request maximum. `test_protocol_sha256` must bind the
   exact executable fault procedure and oracle inputs, not merely this matrix.
   The O evidence must be assembled before C protocol freeze; the C protocol
   must freeze inside the O protocol's validity window.
4. A separate custodian freezes `anchor-inputs.json` after the C protocol but
   **before the first C observation**. It binds the manifest, qualification,
   G5/G6 decisions, G6-05 go, build/host/witness, O protocol/evidence, C
   protocol and expected reviewer. Record actual UTC times and an expiry that
   covers review. Later changes to any bound input require a new protocol and
   anchor, never an oracle edited after seeing a result.
5. On the named host, run every C fault against inert transport. After a
   forced cut, have the checker read witness/checkpoint, roster, claims,
   intents, audit, monitor, route and alert from a separate identity. Preserve
   raw diagnostics under their approved custodian. The index contains only a
   source digest, safe status, counts, exposure, checkpoint generations and
   timestamps. Record failed and unavailable rows; do not omit them. Each
   observation must occur after anchor freeze and before evidence assembly.
6. Independently inspect the underlying O and C source artifacts. Complete
   all 19 case-review rows against the exact `case_observations_digest` of
   their observations. The reviewer must differ from both O and C operators.
   Review must follow evidence assembly, be dated, and remain valid at screen
   time. A rejected or unavailable source stays in the packet.
7. Run the strict screen with actual input files and explicit UTC review time:

   ```sh
   uv run --frozen python -m tools.g6_06_operating_gate \
     <anchor.json> <manifest.json> <host-protocol.json> \
     <host-evidence.json> <cohort-protocol.json> <cohort-evidence.json> \
     <reviews.json> <new-private-assessment.json> --now <UTC-ISO-time>
   ```

   The output is exclusive mode `0600` and reports only digest/count metadata
   and bounded reasons. `reviewable` is a structural metadata result. An
   independent decision must authenticate host/build, source custody,
   reviewers and prior gates before any owner/operator release. The output's
   target-host, review, go, release, dispatch and assessment authority fields
   remain false.

## C01–C09 source-review runbook

The matrix fixes the exact 35 fault IDs. Counts in observation rows are **new
events in that fault run**, so a pre-existing assignment or claim is preserved
and inspected separately. One-entry rows permit exactly one local inert
transport entry; no row proves provider delivery or billing finality. Every
source review must compare the frozen expected state to the independently
observed state, not simply trust the index's digest.

| Case | Required faults | Source observations and blocker |
|---|---|---|
| C01 entry gate | `missing_go`, `changed_manifest`, `changed_build`, `unsigned_release` | Compare G6-05 go, manifest/build and signed owner/operator release to assignment, claim and audit snapshots. Each mismatch must deny with zero new assignment or claim. |
| C02 scope | `outside_owner`, `duplicate_task`, `fresh_session` | Inspect owner-scoped roster, original task/session binding and witnessed claim history from separate identities. No new assignment or second claim, and no cross-owner disclosure. |
| C03 concurrency and budget | `last_slot`, `concurrent_claim`, `killed_assignment`, `ambiguous_claim` | Record concurrent barriers, roster before/after, three-scope headroom, claim/intent/entry counts and independent checkpoint. Last-slot races fit approved caps; killed assignment stays in roster; ambiguous claim retains the full request maximum. |
| C04 outage and stop | `audit_outage`, `alert_loss`, `stale_clock`, `stop_inflight` | Preserve audit/monitor/clock/alert failure records, stop acknowledgment, checkpoint and in-flight inventory. New admissions deny; held exposure remains. The stop checkpoint advances and measured stop/alert latency fits frozen limits. |
| C05 route change | `route_before_claim`, `route_after_claim`, `route_after_final_read`, `stale_fallback` | Compare signed exact-route observations and fallback qualification with claim, intent and local entry. A changed or stale route cannot silently substitute. A consumed attempt never retries; after final read only the already claimed entry may occur. |
| C06 stop and re-entry | `stop_before_claim`, `stop_after_claim`, `stop_after_final_read`, `recovery_reentry` | Check signed stop, independent witness high-water, on-call acknowledgment and elapsed time at each barrier. Stop persists through recovery; re-entry needs a new reviewed activation and release. Preserve full uncertainty for post-claim cuts. |
| C07 close and follow-up | `early_close`, `missing_followup`, `cancelled_task`, `replacement_draw` | Compare original roster, close cutoff, no-dispatch/failure/cancellation, restricted follow-up references and missingness. No replacement draw or favorable denominator; unknown or disputed outcomes remain unknown in their approved store. |
| C08 rollback | `witness_rollback`, `local_rollback`, `audit_rollback`, `combined_rollback` | Read enrolled roots, independent checkpoint high-water, local journal, intents, audit and full exposure after restore. Any older or missing state blocks another admission; original claims and assignments stay visible. |
| C09 frozen cohort | `changed_rubric`, `changed_policy`, `early_assessment`, `unregistered_claim` | Compare frozen rubric/policy/protocol digests and pre-cohort registration reference with later requests. No retuning, premature positive assessment or unregistered comparison claim. Keep protected outcome and sampling sources in their approved workflows. |

The validator checks the matrix, metadata bindings, limits, observed status,
new-event counts, retained exposure, stop-checkpoint advance and dated review
digests. It does not inject faults, authenticate a host or source, inspect
restricted records, prove reviewer independence, or approve a live cohort.
The G606-04 gate remains open until those observations and decisions exist.

Sampling receipts are metadata only and grant no authority or holdout
assignment. Neither this packet nor its index contains prompts, transcripts,
model responses, tool output, protected outcomes, labels, sampling
probabilities, independence groups or splits. Missing values remain unknown.
