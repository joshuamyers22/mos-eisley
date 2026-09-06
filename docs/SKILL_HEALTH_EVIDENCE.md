# Post-selection skill health and drift evidence

Mos Eisley can derive a short-lived, non-executing eligibility artifact for the
exact current skill-default pointer. The artifact is evidence for a future runtime
preflight. It does not read skill instructions into a request, call a model, activate
a skill, mutate configuration, or roll anything back.

Issuance requires two domain-separated Ed25519 signatures from distinct trusted
keys:

1. a policy signature over the exact default pointer and installed bytes, historical
   holdout reference, measurement protocol, latest release-control entry, validity
   limits, independent-group floor, and numeric health/drift thresholds; and
2. an observation signature over the exact pointer and bytes, measurement protocol,
   empirical evidence-bundle digest, post-selection observation window, group counts,
   and measured quality, cost, and latency values.

Both health signers must be independent of every default selector, installer,
release controller, promoter, grader, and resolver in the reverified source lineage.
The health-authority policy is an independently distributed trust root and pins the
default store, default authority, promotion authority, and release-control anchor.

The verifier reconstructs the complete promotion and release-control lineage,
requires the control message to remain the latest local anchor entry, verifies every
default-store revision and installed package, and identifies the exact current
pointer. Candidate bytes are accepted only while the release is allowed; nominated
rollback bytes are accepted only while the release is revoked.

The observation uses integer parts-per-million values for statistical rate bounds and
integer cost/latency values. Mos Eisley recomputes two gates instead of trusting signed
`passed` booleans:

- **absolute health:** the post-selection detection lower bound, clean false-positive
  upper bound, completion lower bound, cost coverage/delta, latency delta, and group
  counts must still pass the original pre-registered holdout gate; and
- **reference drift:** those measurements may not deteriorate from the authenticated
  promotion holdout report by more than the separately signed tolerances.

Evidence must start after the pointer was committed, finish no later than the
verifier's explicit UTC clock, remain within the signed freshness limit, and cover at
least the larger of the historical and newly signed independent-group floors. The
eligibility expires at the earliest authority, policy, observation, release-control,
or configured lifetime boundary. Consumers must reverify it from all sources; the
standalone JSON is not self-authenticating.

```console
mos eval-issue-skill-health-eligibility \
  --signed-health-policy trusted/signed-skill-health-policy.json \
  --signed-health-observation private/signed-skill-health-observation.json \
  --health-authority-policy trusted/skill-health-authorities.json \
  --default-store private/skill-default.sqlite \
  --output private/skill-health-eligibility.json \
  ...complete evaluation, release, installation, and default sources...
```

Private keys are never accepted by the CLI. Library signing helpers exist for tests
and external custody integrations. Production policy authors and observers should
independently construct and review their payloads before signing.

## Deliberate limits

The observation is an authenticated attestation, not a measurement runner. Mos Eisley
does not fetch or inspect the evidence bundle or measurement protocol identified by
their digests. A signature proves who asserted the measurements and what exact bytes,
window, and protocol they covered; it does not prove that sampling, grading, or
independence claims were honest. A production collector must preserve the registered
paired estimand and complete raw lineage.

Weak historical studies remain weak references. In particular, very small samples can
produce confidence bounds saturated at `-1` or `1`, leaving little or no sensitivity
for rate-based drift detection. The independent-group floor prevents the new
observation from silently using fewer groups but cannot repair an underpowered
historical baseline.

The local default and release-control databases can still be rolled back or cloned by
their owner without an external monotonic witness. Clock integrity, evidence
collection, trust-policy distribution, signer custody and organizational independence,
and alert delivery remain external responsibilities.

`runtime_preflight_eligible: true` means only that this evidence may be presented to
the separately authorized, non-sending
[runtime preparation](SKILL_RUNTIME_PREFLIGHT.md). Every policy, observation, and
result fixes runtime dispatch, activation, configuration mutation, and automatic
rollback to false. Preparation can reconstruct the selected prompt into a private
artifact, but no shipped component sends it to a provider.
