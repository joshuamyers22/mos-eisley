# G605-05 source-evidence handoff package

Status: **offline handoff package complete; source authentication open**, 2026-09-27.
This package prepares independent inspection of the exact G6-05 qualification
packet and inert host-drill index. It is a metadata inventory and denial screen.
It contains no inspected G5 source, real host observation, reviewer acceptance,
qualification decision or dispatch authority.

## Frozen inputs and generated inventory

Use one exact [qualification packet](G6_05_OPERATIONS_EXACT_CANDIDATE_QUALIFICATION_PLAN.md),
its `OfflineQualificationEvidence`, and the joined `HostDrillProtocol` and
`HostDrillEvidenceIndex`. Freeze an inspection protocol and reviewer roster
under separate SHA-256 digests before assignment. The independent reviewer
supplies those two expected digests to the validator from the approved freeze
record; the handoff's own declarations do not establish them. The
[`required_source_references`](../src/mos_eisley/run/routing_source_handoff.py)
function derives the exact sorted source slots from those objects:

| Slot | Required independent source work |
|---|---|
| `m.*` | Rehash the four frozen metadata inputs plus the inspection protocol and reviewer roster. |
| `p.g5-*`, `p.sealed-study`, `p.candidate-policy`, `q.Q1` | Use the applicable audited G5 custodian workflow; the statistical reviewer checks the sealed claim, report, use scope and Q1 evidence. No protected G5 store is opened by this package. |
| `p.G2/G3/G4.applicability`, `q.G2/G3/G4` when declared | Inspect each applicability basis and each required prerequisite decision. Check that omitted evidence corresponds to a properly reviewed inapplicability decision. |
| Remaining `p.*` | Inspect the frozen plan, feature partition, promotion and activation chain, control/preflight, witness/budget design, broker build, host/network/runbooks, task enrollment, verification protocol, rubric and retention policy. Rebuild signed chains under independently obtained roots. |
| `q.G6-01` through `q.G6-04`, `q.Q2` through `q.Q6`, `q.O01` through `q.O10` | Inspect each qualification record's cited source, producer/checker assignment, dates and exact claim. Q6 and O records must agree with the joined drill index. |
| `r.<candidate-id>.*` | For every selected or fallback route, inspect catalog and pricing at primary sources; independently inspect conformance, drift, method, prompt-asset digest, registry and capability evidence. Check route identity, freshness, price normalization and expiry before credential access. |
| `f.<case-id>.<fault-id>` | Observe each O01–O10 fault on the named inert target host from a separate identity. Inspect retained state, time, checkpoint, intent, claim, exposure, stop, audit and recovery evidence against the frozen oracle. |

The source ID is a bounded opaque key. The source digest is the expected digest
from the frozen input, not proof of source truth. `locator_id` identifies an
owner-controlled retrieval record without embedding a path, URL, credential or
source content. `custody_domain_id`, `custodian_id`, `producer_id`, `checker_id`,
`access_mode`, `check_method`, `checker_role`, capture time, expiry and status
make each inspection assignment explicit. The checker must have an identity
distinct from both producer and custodian. The independent reviewer must also
verify actual human and infrastructure separation; identifiers alone cannot
establish it. Preserve raw source and any audit record in the approved owner or
audited custodian store, outside this handoff and outside the repository.

## Assembly and review order

1. The owner freezes the exact packet, qualification evidence, drill protocol,
   drill index, inspection protocol and reviewer roster, retaining their
   canonical digests and expiry. A changed source or assignment makes a new
   handoff; do not silently replace a pointer.
2. The owner calls `required_source_references` with the four frozen objects
   and the two inspection/roster digests. Supply exactly one
   `SourceEvidenceReference` for every returned requirement, sorted by
   `source_id`. Mark unavailable or disputed sources as such. Do not fabricate
   a digest, repair G5 sampling metadata, or mark missing work available.
3. The statistical reviewer performs Q1 and audited G5 source review through
   the applicable audited workflow. The security reviewer inspects authority,
   route, custody and host evidence; an independent host observer witnesses
   each fault. Operations supplies source access and performs the inert host
   drill. Each reviewer records a separate, dated inspection outcome in the
   approved review system, bound to the handoff digest and exact source ID.
4. Run the offline validator at an explicit UTC time. Resolve every denial
   before source inspection is presented as complete. The validator checks
   metadata coverage, digest/method/role bindings, availability and expiry,
   the joined drill index, and exact packet/evidence/protocol/index binding.
5. After actual source checks, independently disposition G605-05 and the other
   open G6-05 findings. The [G605-06 decision-readiness package](G6_05_DECISION_READINESS_PACKAGE.md)
   prepares the Q7 signatures and owner-decision queue. The project owner's
   explicit qualification decision remains separate. A later G6-06 release is
   required for any cohort use.

Example invocation with owner-supplied metadata JSON:

```sh
uv run --frozen python -m mos_eisley.run.routing_source_handoff \
  packet.json qualification-evidence.json drill-protocol.json \
  drill-index.json source-handoff.json --now 2026-09-27T12:00:00+00:00 \
  --inspection-protocol-sha256 "$APPROVED_INSPECTION_SHA256" \
  --reviewer-roster-sha256 "$APPROVED_ROSTER_SHA256"
```

Exit 0 means `handoff_ready: true` for this metadata only; exit 1 lists bounded
denial reasons. `source_authenticated`, `target_host_verified`,
`qualification_authorized` and `dispatch_authorized` are always false. The
CLI prints no source references or source contents. It limits each input JSON
to 2 MB and strict schemas reject extra fields. Treat this result as an
inspection queue, not an acceptance receipt.

## Independent inspection record

For each source ID, the checker records the retrieved source's canonical digest,
retrieval time, source authority and revision, custody path, exact claim checked,
pass/fail/unavailable status and unresolved discrepancy in the approved review
system. The record binds the handoff digest and the checker identity. For Q1,
the audited G5 workflow controls access and disposition; this package never
reads the sampling registry, custodian mapping, label store or outcome store.
For Q3, the checker compares the actual selected and fallback route with the
frozen policy and primary catalog/pricing evidence. For Q5/Q6, the checker
compares the named host, OS and credential boundary, external witness and
checkpoint, independent audit/monitor source, before/after state and full
exposure at each fault. A claimed source digest, `pass` record or self-signed
review cannot replace source inspection or target-host reproduction.

The independent G605-05 disposition must name every failed, disputed, stale or
unavailable source and its owner; record the exact handoff digest, inspection
protocol, reviewer roster, per-source outcomes and residual findings; and say
accept or reject only after the actual inspections. This offline package has no
such disposition.

## Synthetic fault checks and boundary

The [focused tests](../tests/test_routing_qualification.py) construct only
synthetic digests and opaque IDs. They cover complete inventory, missing and
extra slots, rebound digests, unavailable/disputed/stale references, changed
packet, expired window, checker/custodian collision, forbidden embedded
content and CLI denial. Their successful fixture demonstrates that a handoff
can be queued for inspection; it does not authenticate a source, reproduce a
target-host fault or qualify a route. G605-05 remains open until independent
reviewers inspect the actual evidence and record a disposition.

Sampling receipts are metadata only. This handoff contains no prompts,
transcripts, model responses, tool output, outcomes, protected sampling data,
or inferred probabilities, groups, labels or splits.
