# G6-05 owner-decision contract and G6-06 R2 binding rehearsal

Status: **offline signed-decision contract and end-to-end synthetic R2 join complete;
actual owner go and live R2 release open**, 2026-09-27. This handoff follows
the [G605-06 decision-readiness package](G6_05_DECISION_READINESS_PACKAGE.md).
It specifies one signed G6-05 owner decision and rehearses its exact join to a
proposed G6-06 bounded-live entry. A synthetic signed `go` is a fixture, not
an audited G5 qualification, source authentication, target-host acceptance,
cohort release or dispatch grant.

## Signed decision and independently frozen anchor

[`G605OwnerDecision`](../src/mos_eisley/run/routing_owner_decision.py) fixes the
owner's `go` or `no_go` status; exact qualification packet, evidence, source
handoff, decision-readiness, technical-review and G5 claim digests; owner,
cohort and signer IDs; policy, selected and fallback candidate IDs; broker
build, host and witness epoch; approved task types, stages, assignment/concurrency and
task/session/cohort/request ceilings; stop-latency limit; issue and expiry.
The decision cannot contain prompt text, task content or source records.
The schema rejects unsorted or duplicate fallback/stage lists, selected route
as fallback, an impossible request maximum, a concurrency cap above assignments,
and invalid UTC windows.

The owner signs the canonical decision bytes with Ed25519 under the dedicated
`mos-eisley/g605-owner-decision/v1` domain. The digest used by G6-06 is the
SHA-256 of the **signed record**, so replacing the decision or signature
changes the go reference. `G605OwnerDecisionTrust` names the owner and signer
and carries an independently enrolled public key and validity window. The
separate `FrozenG605OwnerDecisionAnchor` carries the expected G6-05 digests,
trust digest and expiry. The anchor must come from an approved independent
freeze record; copying values out of the proposed owner decision does not
establish trust. Real owner signing and source inspection occur outside this
repository.

The offline verifier checks the signature, owner/signer match, external
digest bindings, current windows and explicit `go` status. A signed `no_go`,
invalid signature, changed trust root, stale record or changed readiness digest
denies. Its `go_reference_reviewable` result says only that the signed metadata
can be considered for the later R2 join. Its G5, qualification and dispatch
authority fields are literal false.

```sh
uv run --frozen python -m mos_eisley.run.routing_owner_decision \
  signed-owner-decision.json owner-trust.json frozen-anchor.json \
  --now 2026-09-27T12:00:00+00:00
```

The CLI emits only a bounded assessment and returns 1 for a denied reference.

## R2 exact binding

The existing [`validate_offline_r2_entry`](../src/mos_eisley/run/cohort_entry.py)
is a standalone synthetic metadata screen. The new
`validate_joined_offline_r2_entry` runs it and also verifies the signed G6-05
owner record. For a synthetic entry to be `reviewable`, all three go digests
must be identical: the independent R2 anchor, the R2 packet's go reference,
and the signed owner record. The proposed cohort release must carry that same
digest. The qualification packet digest in the R2 anchor and go reference must
equal the separate owner-decision anchor.

The join compares the owner-signed owner/cohort, policy, exact selected route,
broker build, host and witness epoch with the R2 go reference and frozen cohort
manifest. It checks decision issue/expiry against the release; approved stages
and assignment/concurrency caps against the manifest; and approved
task/session/cohort/request ceilings against the witnessed budget policy.
Missing owner record or witness state, a no-go, stale or tampered signature, changed go digest,
different route, narrower owner envelope or a release extending beyond the
owner decision blocks entry. Both joined and standalone results keep
`owner_release_authorized` and `dispatch_authorized` false. The result's
`signed_owner_decision_checked` flag distinguishes the joined check from the
standalone metadata screen.

## End-to-end readiness-to-R2 screen

`validate_end_to_end_offline_r2_entry` reruns the standalone R2 gate, the
signed owner-decision join and `validate_g605_decision_readiness` at the same
explicit UTC instant. It takes the frozen G6-05 qualification packet and
evidence, joined host-drill protocol and index, source-evidence handoff,
readiness packet, Q7 trust and signed reviews, and independently expected
inspection protocol, reviewer roster, review trust and technical-review
digests. A changed, stale, rejected or incomplete input blocks R2 even when
the owner decision still carries the original readiness digest.

The screen recomputes packet, evidence, handoff and readiness digests and
compares them with the independent owner anchor. It binds the G5 claim and
technical-review freeze, requires owner signing after readiness assembly,
and bounds owner expiry by readiness, qualification deadline and qualified
scope. It compares the signed owner/cohort, policy, selected and fallback
routes, broker build, host, witness epoch, task types, stages, assignment and
spend ceilings, and stop limit with the qualified packet. It binds the exact
ordered task/session roster, witness enrollment, budget policy, promotion
receipt and preflight to the current synthetic cohort. The roster digest uses
canonical JSON under `g605-task-enrollment-v1` and carries no task content.

The result sets `readiness_checked: true`; `reviewable` is still only a
metadata assessment. Neither that result nor the earlier standalone or signed
join grants owner release or dispatch authority. For an actual R2 decision,
independent reviewers still need to inspect source and decision records,
verify the audited G5 claim and G6-05 findings, and obtain the owner's real
signed decision under enrolled custody. The G6-06 owner/operator release,
current witness/control/route checks and per-attempt admission remain separate
gates.

The [G6-06 R3 offline fixture](../tests/test_cohort_r3_attempt.py) now reruns
this full screen immediately before its synthetic release transition. A later
readiness, source, trust, roster or owner-decision fault blocks that transition
even if the standalone R2 metadata check remains reviewable. This fixture
guard supplies no production release authority.

## Synthetic rehearsal

The [R2 tests](../tests/test_cohort_r2_entry.py) build a full synthetic
G605-06 evidence, drill, handoff, inspection and Q7 chain before signing the
owner decision and freezing the shadow release. They exercise a matching
end-to-end chain; rejected or expired readiness, Q7 reviews and source
references; changed independent trust and technical roots; route evidence,
task roster, qualified policy, owner decision time and envelope faults; and
the earlier signed-go and R2 denial cases. Every denied case leaves the shadow
cohort, witness claims, audit and transport untouched.
No protected sampling registry, custodian mapping, label store or outcome store
is read or summarized. Sampling receipts remain metadata only, with no
inferred probabilities, groups, labels or splits.
