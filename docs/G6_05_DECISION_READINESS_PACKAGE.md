# G605-06 offline decision-readiness package

Status: **offline Q7 decision queue prepared; G6-05 qualification open**,
2026-09-27. This package binds the [G605-05 source-evidence handoff](G6_05_SOURCE_EVIDENCE_HANDOFF_PACKAGE.md)
to named inspection outcomes, gate dispositions, operations acceptance and the
four signed qualification reviews. It checks metadata shape and order at an
explicit UTC time. It records no real source authentication, target-host
verification, G5 qualification, owner go/no-go or dispatch approval.

## Frozen decision inputs

The owner supplies the exact `OfflineQualificationPacket`,
`OfflineQualificationEvidence`, joined `HostDrillProtocol` and
`HostDrillEvidenceIndex`, `G605SourceEvidenceHandoff`, independently enrolled
`OfflineQualificationReviewTrust`, four `SignedOfflineQualificationReview`
objects, and one `G605DecisionReadinessPacket`. An independent reviewer supplies
the expected inspection-protocol, reviewer-roster, Q7 trust-root and technical-review digests
from an approved freeze record. A digest declared only inside the readiness
packet is insufficient.

The readiness packet contains only opaque IDs, SHA-256 digests, roles, status
and UTC times. It fixes `decision_state` to `pending`. Its source-inspection
rows must cover every handoff reference exactly once, bind that reference's
source digest and assigned checker, and cite a retained inspection record
digest. Missing, extra, rejected, unavailable, mismatched or expired rows deny.
The actual inspection record and source stay in the approved owner or audited
custodian system, outside this package.

The [`required_decisions`](../src/mos_eisley/run/routing_decision_readiness.py)
function enumerates these formal decision subjects:

| Decision slot | Required subject and reviewer |
|---|---|
| `G5-audit`, `Q1` | Exact G5 claim and Q1 source; statistical reviewer under the applicable audited workflow. |
| Applicable `G2/G3/G4`, `G6-01`–`G6-04` | Each frozen evidence-record source; enrolled independent security reviewer. Check actual applicability and gate acceptance outside this validator. |
| `G605-01`–`G605-04` | Exact packet for the prerequisite finding and independently frozen technical review for the three implementation findings; security reviewer records separate finding dispositions. |
| `G605-05` | Exact source-handoff digest; security reviewer records a source-authentication disposition after every source inspection. |
| `Q2`–`Q6`, `promotion`, `activation`, `exact-route`, `target-host`, `witness-custody`, `host-drills` | Frozen qualification record or relevant packet/drill digest; security reviewer inspects the actual chain, selected/fallback route, custody and target-host observations. |
| `operations-runbook` | Exact stop-runbook digest; operations reviewer records runbook and on-call acceptance. |

Every disposition has `accept`, `reject` or `unavailable`, an exact subject
digest, enrolled reviewer role and ID, separate producer ID, retained decision
record digest, time and expiry. A rejected or stale disposition denies. The
`unresolved_findings` list must be empty. An empty list is a declared fact for
independent checking; the validator cannot discover an omitted finding.

## Q7 ordering and owner handoff

Run the [offline validator](../src/mos_eisley/run/routing_decision_readiness.py)
with the same frozen packet, evidence and drill inputs used by G605-05. It
requires both the G605-05 handoff and the existing qualification metadata
validators to be `reviewable`. It verifies all source and decision slots,
exact digests, reviewer enrollment, freshness and four Ed25519 Q7 signatures.
All source inspections and finding/operations dispositions must precede the
four Q7 reviews, and the reviews must precede packet assembly. This ordering
prevents an earlier Q7 signature from being reused after a later disposition.

Example, with all JSON files and approved digest variables supplied by the
owner and independent reviewer:

```sh
uv run --frozen python -m mos_eisley.run.routing_decision_readiness \
  packet.json evidence.json drill-protocol.json drill-index.json \
  source-handoff.json review-trust.json signed-reviews.json readiness.json \
  --inspection-protocol-sha256 "$APPROVED_INSPECTION_SHA256" \
  --reviewer-roster-sha256 "$APPROVED_ROSTER_SHA256" \
  --review-trust-sha256 "$APPROVED_Q7_TRUST_SHA256" \
  --technical-review-sha256 "$APPROVED_TECHNICAL_REVIEW_SHA256" \
  --now 2026-09-27T12:00:00+00:00
```

Exit 0 means `ready_for_owner_decision: true` for the supplied metadata. Exit
1 reports bounded denial reasons. The CLI emits no source rows or inspection
records. `source_authenticated`, `target_host_verified`, `g5_qualified`,
`qualification_authorized` and `dispatch_authorized` remain literal false in
all results. The readiness result cannot enable G6-06 or a paid send.

The independent reviewer must retrieve and verify the retained inspection and
decision records, role/custody separation, audited G5 disposition, actual
promotion/activation chain, exact selected and fallback routes, witness and
checkpoint topology, O01–O10 host faults, stop/alert latency and unresolved
findings. A synthetic `accept` value or digest match is not that review. Any
missing or adverse source requires a no-go disposition and continued
fixed-route/full-review operation.

Only after those checks may the project owner create a separate signed G6-05
go/no-go record. It must bind the readiness digest, exact packet and evidence,
G5 claim scope, selected/fallback identities, broker build and target host,
witness roots, operating envelope and spend/time ceilings, on-call acceptance,
all dispositions and unresolved findings, decision time and expiry. The owner
must record **no-go** for any failed or incomplete gate. A G6-05 go still does
not release a cohort: G6-06 requires its own owner/operator release and entry
checks.
The [offline owner-decision contract and end-to-end R2 binding rehearsal](G6_05_OWNER_DECISION_R2_BINDING.md)
define that signed record's metadata and rerun this readiness screen against
its frozen inputs at R2. They do not record the actual owner's decision.

## Synthetic fault coverage

The [focused tests](../tests/test_routing_qualification.py) use synthetic
digests and keys. They deny missing/rejected/stale/rebound source inspections,
missing/rejected/mismatched decisions, early G605-05 disposition, a Q7 review
made before later evidence, changed technical freeze, unresolved findings,
expired readiness, rejected Q7 signatures, an attempted `go` state and embedded
source content. A complete synthetic fixture reaches only the owner-decision
queue. No protected sampling registry, custodian mapping, label store or
outcome store is read or summarized; no probabilities, groups, labels or splits
are inferred or repaired.
