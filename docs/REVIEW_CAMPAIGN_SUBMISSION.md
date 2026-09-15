# Offline campaign evidence assembly

`review-campaign-evidence-append` creates a new evidence submission for the next
fixed campaign slot. It checks separately retained file hashes, requires the exact
observation from the selected unsigned preview, and freshly verifies the signature
and every supplied slot before writing output. It does not load keys, sign records,
dispatch calls or resume a stopped campaign.

## Select and verify one completed slot

Retain the owning host's exact completion and the
[observer handoff preview](REVIEW_OBSERVER_HANDOFF.md). An enrolled independent
observer must assess the actual runtime, custody and proposed claims before signing
the exact contained observation through the existing signing boundary. This command
consumes that separately signed record; a preview alone cannot qualify.

Independently select the seal hash and exact raw file hashes for the completion,
preview wrapper and signed observation. Select worker lifecycle directories in
critic order followed by the judge. Completion paths remain host-reported hints;
the command uses the explicitly selected directories. Use trusted, stopped,
same-owner evidence directories and trusted parent paths during inspection.

```sh
mos review-campaign-evidence-append \
  --campaign-dir /private/sealed-campaign --expected-seal-sha256 SEAL_SHA \
  --completion /private/completion.json --expected-completion-sha256 COMPLETION_SHA \
  --preview /private/unsigned-preview.json --expected-preview-sha256 PREVIEW_FILE_SHA \
  --signed-observation /private/signed-observation.json \
  --expected-signed-observation-sha256 SIGNED_FILE_SHA \
  --lifecycle-directory /private/critic-lifecycle \
  --lifecycle-directory /private/judge-lifecycle \
  --output /private/submission-1.json
```

The preview hash identifies the full retained wrapper file, not its contained
`observation_sha256`. Input files are bounded, duplicate JSON keys are rejected,
and exact raw hashes are checked before evidence verification. The completion must
match the preview's canonical completion hash and independently selected seal.

## Append subsequent slots

For each later completion, select its own completion, preview, signed observation
and lifecycle directories. Also supply the previous submission and its independently
retained raw hash:

```sh
  --previous-evidence /private/submission-1.json \
  --expected-previous-evidence-sha256 PREVIOUS_FILE_SHA \
  --output /private/submission-2.json
```

Both previous-evidence arguments are required together. Slots must form a contiguous
prefix of the sealed three-attempt campaign. Gaps, replacement of existing slots,
cross-campaign submissions and future filled slots are rejected. Verification
reconstructs all supplied results, runtime evidence, historical approvals, observer
signatures and dedicated-ledger accounting on every append. A valid signature does
not excuse changed artifacts or earlier evidence that no longer verifies.

Output is canonical `CampaignEvidenceSubmission` JSON, created exclusively with
mode 0600 in an existing directory outside the campaign and all planned run
directories. Existing files and previous submissions are preserved. Ledgers and
runtime artifacts are not updated. Standard output reports the new submission hash,
appended index, qualifying count and acceptance status.

A successful append returns exit code 0, including a valid partial submission whose
status is `incomplete`. Invalid input or verification returns 2 without a new
submission. The separate [campaign review command](REVIEW_CAMPAIGN_CEREMONY.md)
returns 1 for incomplete acceptance; its purpose is to assess the whole campaign.
Only all three qualifying slots produce `accepted`. Acceptance grants no provider
dispatch, retry, resume or live activation authority.

## Validation

Synthetic tests exercise the actual CLI through all three slots, input substitution,
missing hash pairs, slot gaps and replacement, invalid signatures, changed runtime
evidence, private output and preservation of prior files. Fixture signatures do not
establish independent production custody or live runtime assessment. Those operating
requirements and reviewed launch admission remain outstanding.
