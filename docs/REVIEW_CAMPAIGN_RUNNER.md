# Owned campaign sequencing and observer handoff

`OwnedReviewCampaign` invokes the three prepared, sealed campaign probes in fixed
slot order. It waits for independently supplied observer evidence after each probe
and freshly verifies every supplied slot before invoking the next probe. Missing
evidence stops the campaign; invalid evidence fails it. The runner never signs
observations or supplies critic/judge approvals.

## Prepare the owning host

Prepare, seal and independently retain the exact campaign commitment as described
in the [operator ceremony](REVIEW_CAMPAIGN_CEREMONY.md). Construct three distinct
`BrokeredReviewConformanceProbe` objects with [campaign bindings](REVIEW_CAMPAIGN_DISPATCH.md)
for slots 0, 1 and 2. The runner requires the same absolute campaign directory and
independently retained seal hash, exact ordered previews and fresh prepared probes.
Construction performs read-only checks; it creates no spending reservations or workers.

Supply those probes and an asynchronous observer callback to `OwnedReviewCampaign`.
The host must own and await `run()`, including cancellation cleanup. Every probe
continues to require its separate signed and local critic/judge approvals and fresh
campaign, guidance, runtime, payload and spending checks at provider use.

## Independent observer handoff

After a completed probe, the callback receives a `CampaignProbeCompletion`: the
fixed slot and seal hash, trusted controller start and judge preview, both phase
authorizations, expected retained-result hash and captured worker lifecycle paths.
These are host outputs for independent assessment, not proof of an honest host or
remote provider authorship. The callback must arrange actual independent observation
and return a `CampaignAttemptSubmission`, or return `None` when evidence is unavailable.
It must own any asynchronous work it starts and cooperate with cancellation.
An [offline observer preview](REVIEW_OBSERVER_HANDOFF.md) can now verify a separately
pinned completion and explicitly selected lifecycle records to prepare unsigned
claims for independent assessment. It never signs or automatically completes handoff.

The submission must match the owning probe's start, judge, authorizations and result
hash. The observer independently selects lifecycle paths; the runtime verifier
checks their records against signed evidence pins. The runner then uses the existing
campaign reviewer to reconstruct the supplied probe and all earlier accepted slots.
It checks prior slots again immediately before invoking the next probe. Final
acceptance requires the complete three-attempt evidence and dedicated-ledger accounting.
Per-probe approvals may pause after invocation; the runner does not lock evidence
files against other processes during those pauses.

Observer waits default to 120 seconds, may be explicitly set above zero through 600
seconds, and are capped by campaign expiry. A missing or timed-out observer stops
with an incomplete result while the policy remains valid. An expired policy or
invalid submission fails validation. If a callback suppresses timeout cancellation,
the runner still refuses its late result and does not start the next probe. Explicit
cancellation likewise cannot be turned into permission to continue.

## State, retention and failure

`phase` reports prepared, running, awaiting observer, accepted, incomplete, failed or
cancelled. The object is one-use, including after decline, failure or cancellation;
a competing `run()` call cannot take over the active observer pause. Provider failures
preserve the probe's conservative spending and await worker cleanup. Cancellation
propagates through the currently owned probe or callback before the runner returns.

`submission` returns a fresh snapshot of slots that passed verification when they
were added; missing slots remain `None`. It is not a cached acceptance authority:
independently retain it and use the [campaign review command](REVIEW_CAMPAIGN_CEREMONY.md)
for later decisions. `last_completion` remains available after missing, invalid or
cancelled observer handoff, allowing the host to retain exact completed-probe inputs.
The runner does not persist these snapshots itself, resume after process death,
replace failed slots, or retry provider calls. Hosts retain evidence in their selected
private storage; crash recovery remains read-only inspection.

## Validation and live gate

Tests exercise all three synthetic probes, separately signed fixture observations
and fresh final review, plus wrong ordering, unbound probes, decline, missing/invalid
observations, result substitution, earlier evidence tampering, timeouts, cancellation
and competing calls. `tools/smoke_review_campaign_runner.py` repeats the full ordered
handoff and active cancellation with real offline Docker workers and fake providers.

The library is paid-capable only through the existing explicitly approved probes.
There is no paid CLI or automatic live activation. Independent commitment custody,
actual authorized live attempts, independent runtime assessment and reviewed launch
admission remain required; fixture observations do not satisfy that gate.
