# Bind a sealed campaign to an owned probe

`BrokeredReviewConformanceProbe` accepts an optional `ReviewCampaignBinding` that
restricts an already prepared probe to one exact slot in an independently pinned
[campaign seal](REVIEW_CAMPAIGN_CEREMONY.md). Construction checks the binding without
reading credentials, reserving spending or starting workers. Standalone probes retain
their existing signed/local admission path; campaign hosts must supply the binding.

## Owning host integration

Prepare all three envelopes and exact controller previews, then preview, seal and
independently retain the campaign commitment. Keep the prepared envelopes and their
owning configuration in memory. For each selected slot, construct the probe with its
original envelope, reviewer, policy, containers and approval callbacks, plus:

```python
campaign = ReviewCampaignBinding(
    campaign_directory="/private/sealed-campaign",
    expected_seal_sha256=independently_retained_seal_sha256,
    attempt_index=0,  # fixed zero-based slot: 0, 1 or 2
)
```

The probe's total duration, critic requests and spending envelope must reproduce
the exact committed preview. Current SDK/image and the complete current authority
policy must match the sealed values. Both the prepared envelope and every critic
must use the sealed ledger path and policy; copying a ledger with the same identity
to another path does not satisfy this binding. The owning reviewer's projected judge
profile is checked before the first critic can spend, and the actual judge preview
is checked again before judge approval and dispatch.

The host must still obtain separate independent signatures and local approvals for
critics and judge. A seal cannot supply either approval. The host owns and awaits
`probe.run()`, including cancellation cleanup, and independently retains start,
judge preview, signatures, result hash and lifecycle paths for subsequent observation.

## Rechecks and failure behavior

Admission rereads the independently pinned seal and exact bundle before requesting
authorization, after the signature loader returns, and after each local approval.
The existing provider guard invokes the same campaign check before credential
loading, after the key loader returns, immediately before SDK operations and after
each awaited count or generation. Current guidance, signatures, spending and exact
payload checks continue to apply at those boundaries.

Provider timeouts also respect the earliest campaign, observation-policy,
authority-policy and preview expiry. An expired or changed seal, changed runtime,
rotated authority policy, substituted ledger or changed judge configuration blocks
further dispatch. A late failure preserves held or uncertain spending and awaits
owned cleanup. A cancelled, declined or consumed probe has no automatic retry.

This is a host admission restriction, not an independent attestation that it ran.
Existing evidence verification still reconstructs the actual records and requires
the independently selected observer inputs. The binding does not reconstruct owned
state after a restart, sequence the three attempts, lock other processes, or prove
prior commitment custody. Execute the fixed slots in order and retain each observer
record before starting the next slot, as required by the acceptance chronology.
This binding introduces no paid CLI or live review activation.

An [owned campaign runner](REVIEW_CAMPAIGN_RUNNER.md) now provides optional fixed-order
sequencing with independently verified observer handoff between probes. It uses this
binding without replacing any phase approval or enabling live review activation.

## Validation and remaining gate

Tests run all three bound synthetic probes through fresh campaign evidence review.
They also cover missing signatures, wrong seal/slot, changes during signature and
local approval, key loading, token counting and generation, judge admission,
runtime/policy/path substitution, deadline limits, cancellation and one-use behavior.
`tools/smoke_review_campaign.py` repeats successful execution and cancellation with
real offline Docker workers and synthetic provider responses.

Actual independently authorized live attempts, independent custody and runtime
assessment, and reviewed launch admission remain required. This implementation and
its fixture observations do not satisfy that live gate.
