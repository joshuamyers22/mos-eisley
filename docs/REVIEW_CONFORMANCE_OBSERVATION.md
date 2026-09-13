# Authenticated review probe observations

One completed [review probe](REVIEW_CONFORMANCE_PROBE.md) can now be described by an
independent observer, signed with Ed25519 and authenticated against the complete
retained review chain. Authentication confirms the enrolled observer's signature
and locally reconstructible provenance. It does not establish provider authorship,
billing reconciliation, repeated conformance or permission for live review launch.

## Independent inputs

The host selects and retains `ReviewObservationPolicy` before execution. It pins the
exact full critic preview and authority policy, an observation window and maximum
observation age. Callers must select this trusted policy independently of the signed
record; this library does not prove when the host registered it.

After completion, `make_review_probe_observation` requires the separately retained
critic preview, controller start, judge preview, both phase authorizations and final
result hash, plus the selected reviewer and ledger. It also requires the observer's
`ReviewObservedExchange` for every critic in roster order, followed by the judge.
Each exchange supplies the exact model-request hash, count and generation start/end
times, and distinct hashes of transport and worker-cleanup evidence.

The observer supplies these measurements and evidence pins independently. A verdict,
local timestamp or successful test does not supply them automatically. The evidence
hashes are opaque references: this module does not parse their contents, attest that
Docker or a remote provider produced them, or establish their custody. The observer
must inspect the matching evidence before signing, and consumers must retain access
to it for independent review.

## Reconstructed checks

The builder checks the exact policy, preview and authorization bindings; every
exchange must fit entirely inside its historical phase authorization and controller
deadline, with a maximum 60-second call interval. Critic calls may overlap. Judge
counting must follow completion of every critic generation. Observation time must
follow all exchanges and fall inside the selected observation-policy window.

The controller must be recorded as finished with complete, settled spending. The
builder verifies the independently pinned start, judge preview and result, and
reconstructs the complete broker/model/evidence/verdict chain. Every critic and the
judge must have succeeded; an infrastructure-error verdict cannot be observed as
a successful probe. Charged spending is reconstructed from this review's entries,
without including unrelated ledger spending or claiming reconciled billing.

## Signature and historical verification

`sign_review_probe_observation` signs canonical observation bytes with a distinct
review-observation domain separator. Only an observer enrolled in the selected
authority policy can authenticate the record. Authorizer and observer keys and
identities remain disjoint. The runtime does not automatically sign for an observer.

`authenticate_review_probe` verifies the signature, age and independently supplied
policy/context, then repeats local reconstruction. A signature cannot override
changed result bytes, request evidence, spending, scope or missing terminal records.
Evaluation-observation modes and signatures do not substitute for review records.

Historical authentication may occur after phase authorization expires, within the
observation age limit. It verifies the authorization at the observed execution
times and grants no new dispatch permission. Verification is read-only and
repeatable; it neither reserves nor releases spending and never loads credentials.

The result explicitly reports `observer_authenticated` and `local_artifacts_verified`
as true. Provider authorship, reconciled billing, repeated conformance, retries and
live activation remain false. SDK use, credentials, local consent, current guidance
and actual worker isolation/cleanup are signed observer attestations, not facts
proved solely by the retained local review artifacts.

## Remaining conformance work

This increment implements an authenticated record for one successful probe. A
review-specific acceptance policy for repeated probes, collection and inspection
of independent runtime evidence, and explicitly authorized live runs remain
outstanding. Failure/cancellation observations require their own semantics; this
success-only format cannot certify an incomplete run. Live launch remains unavailable.

The tests use synthetic signatures, timing and evidence pins around fixture review
execution. They cover identity separation, signature/domain and policy substitution,
historical expiry and age, execution ordering, missing evidence, result tampering,
infrastructure errors and read-only reconstruction. No live observation was created
or provider call made during implementation.
