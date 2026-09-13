# Offline review campaign ceremony

Three commands preview and retain a fixed three-attempt commitment, then freshly
review an explicitly selected evidence submission. They do not load credentials,
reserve spending, start workers, call providers, issue observer signatures or enable
live review. They wrap [repeated-probe acceptance](REVIEW_CONFORMANCE_ACCEPTANCE.md).

## Prepare and inspect the commitment

The host assembles a `ReviewCampaignBundle` from its three prepared controller
previews and `ReviewAcceptancePolicy`. Each `CampaignAttempt` includes the exact
`ReviewLaunchConfiguration`, critic preview, independent authority and observation
policies, and absolute path to an existing dedicated spending ledger. Serialize with
`canonical_bytes`. The bundle validates all three commitment hashes and role/quorum
profiles, reconstructs critic requests from the selected configuration and checks
the projected judge profile. Runtime remains the exact SDK/image pair in the policy.

```sh
mos review-campaign-preview --bundle /private/campaign-input.json
mos review-campaign-preview --bundle /private/campaign-input.json --show
```

The default output contains hashes, profile metadata and total planned allowance.
`--show` also prints the full bundle, including private review content; select an
appropriate local output destination. Neither command changes the bundle, ledgers
or planned run directories. Inputs are bounded to 8 MB and reject duplicate JSON keys.

Preflight requires current UTC policy windows, unexpired previews, distinct unused
absolute run directories with existing parents, and existing ledgers matching the
committed identities and policies. Dedicated ledgers must be empty and unblocked.
Each ledger must fund the sum of all campaign allowances assigned to it, including
the full deferred judge allowances; expected cheap outcomes cannot reduce funding.
Missing ledgers are never created by these commands.

## Seal and independently retain

After reviewing the exact bundle, copy its canonical `bundle_sha256` from the preview:

```sh
mos review-campaign-seal --bundle /private/campaign-input.json \
  --expected-bundle-sha256 BUNDLE_SHA --destination /private/sealed-campaign
```

Sealing rechecks the confirmation hash and preflight before creating a new directory
with mode 0700. `bundle.json` and `seal.json` are exclusive writes with mode 0600.
The destination must be outside every planned run directory. Existing destinations
are never overwritten; retain a partial directory after a failed write and use a
fresh destination for another ceremony.

Independently retain the returned `seal_sha256` and the committed bundle before
attempt execution. The seal binds the exact stored bundle bytes, acceptance policy
and local UTC timestamp. It explicitly reports `independently_timestamped: false`.
The local timestamp and empty-ledger check do not prove prior independent custody,
an honest host clock, or absence of unrecorded attempts. The operator must serialize
sealing, independent retention and dispatch; preflight is not a lock over execution.
Use trusted, stopped, same-owner directories and trusted parent paths for inspection.

This bundle does not recreate the original prepared controller's owned state after
a restart. Keep the prepared objects in the owning host for any separately authorized
probe. There is no paid CLI or resume mechanism in this ceremony. A
[probe](REVIEW_CONFORMANCE_PROBE.md) still requires its own exact critic and judge
signatures, local approvals, current guidance and fresh runtime/spending admission.
The owning host can now supply a [campaign binding](REVIEW_CAMPAIGN_DISPATCH.md)
to require the pinned seal and exact slot at approval and provider-use boundaries.

## Select and review evidence

After the attempts, assemble a `CampaignEvidenceSubmission` with the retained seal
hash and exactly three ordered slots. A completed slot contains independently
retained controller start and judge preview, both signed phase authorizations,
the signed observer record, expected result hash and absolute worker lifecycle
directories. Preserve missing slots as `null`; do not replace them with a later
successful attempt. Select these inputs independently rather than trusting a saved
acceptance report or deriving the trusted result hash from the files being reviewed.

Hash the exact evidence file bytes and retain that hash separately:

```sh
mos review-campaign-review --campaign-dir /private/sealed-campaign \
  --expected-seal-sha256 SEAL_SHA --evidence /private/evidence.json \
  --expected-evidence-sha256 EVIDENCE_SHA
```

The evidence hash is a raw-file hash; the preview's bundle hash is canonical JSON.
Review checks the evidence hash before ledger access, authenticates the independently
pinned seal and exact retained bundle, rejects starts before sealing, and reconstructs
all supplied attempts through the existing observer, runtime, result and ledger
verifiers. It does not write artifacts or change spending. A later change to runtime
records is rechecked even when an earlier review passed.

Exit status is 0 for three accepted attempts, 1 for an incomplete tranche, and 2 for
invalid input or unavailable files/ledgers. Acceptance applies only to this exact
profile and tranche. Reports grant no dispatch, retry or live activation authority.
Actual independently authorized live attempts, independent custody/runtime assessment
and a reviewed launch-admission decision remain required. Synthetic test successes
do not satisfy those gates.

## Validation

`tests/test_review_campaign.py` seals before three synthetic owned probes, then
exercises the CLI's complete and incomplete evidence paths. It covers exact hash
confirmation, private permissions, no credential access during preparation, unchanged
ledgers during review, post-outcome sealing, configuration substitution, duplicate
keys, byte limits, cross-campaign evidence and fresh runtime tamper rejection.
