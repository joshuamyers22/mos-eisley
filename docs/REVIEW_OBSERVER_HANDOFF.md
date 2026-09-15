# Offline observer handoff preview

`review-campaign-observation-preview` verifies a retained campaign completion and
explicitly selected runtime evidence, then prepares an unsigned observation proposal.
It does not load provider credentials or signing keys, dispatch calls, or authenticate
an observer. The output wrapper explicitly requires independent attestation.

## Select trusted inputs

Independently retain the campaign seal hash and the owning host's exact
`CampaignProbeCompletion` bytes. The [campaign runner](REVIEW_CAMPAIGN_RUNNER.md)
exposes the latest completion even when observer handoff is missing or cancelled.
Hash the retained completion file separately; do not derive trusted result or approval
pins from the evidence files under review. Select each worker lifecycle directory
independently, in critic order followed by the judge. The completion's host-reported
paths are hints and are not automatically used by this command.

```sh
mos review-campaign-observation-preview \
  --campaign-dir /private/sealed-campaign --expected-seal-sha256 SEAL_SHA \
  --completion /private/completion.json --expected-completion-sha256 COMPLETION_SHA \
  --lifecycle-directory /private/critic-lifecycle \
  --lifecycle-directory /private/judge-lifecycle
```

The command verifies the exact completion-file hash before accessing evidence. It
then checks the independently pinned seal, fixed slot, start chronology, judge role,
campaign SDK/image and both historical phase signatures. Each signature is checked
before runtime collection and again against its recorded operation intervals through
the existing observation verifier. Local controller, result, spending and worker
cleanup records are reconstructed against the trusted inputs.

Both completion JSON and input files are bounded; duplicate JSON keys and naive
timestamps are rejected. Missing or substituted runtime responses, cleanup records,
approval scopes and result pins cannot produce a preview. Use trusted, stopped,
same-owner evidence directories and trusted parent paths during inspection.

## Inspect and retain the unsigned proposal

Default output contains hashes and explicit denials of observer authentication,
signature creation, dispatch and live activation. `--show` includes the proposed
observation. `--output /private/unsigned-preview.json` explicitly writes the full
preview wrapper with mode 0600 and refuses to overwrite an existing file. Output
must be outside the campaign seal and all planned run directories; the command never
updates ledgers or existing evidence.

`completion_file_sha256` identifies exact input bytes; `canonical_completion_sha256`
identifies the parsed completion's canonical JSON. `observation_sha256` identifies
the proposed observation inside the wrapper. Its local `observed_at` value is the
preview time, so a fresh preview may have a different observation hash.

The contained observation lists the statements that an independent observer would
attest, including credentialed exchange, local approvals, current guidance, bounded
SDK transport and isolated-worker cleanup. Those proposed statements are not established
independent facts merely because local records pass verification. The wrapper reports
`observer_authenticated: false`, `signature_created: false` and
`requires_independent_attestation: true`; it is not a signed observation or an
acceptance receipt. No key-loading or signing option is provided.

An enrolled independent observer must assess the actual runtime, custody and claims
before deciding whether to sign the exact contained observation through the existing
domain-separated signing boundary. The owning host can then include that separately
signed record in a `CampaignAttemptSubmission`. The runner and
[campaign review command](REVIEW_CAMPAIGN_CEREMONY.md) freshly verify it before treating
the slot as qualifying. A preview alone cannot qualify a slot or start another probe.

Use [evidence assembly](REVIEW_CAMPAIGN_SUBMISSION.md) to combine the retained
completion, exact preview and separately signed observation into a new submission.
The command freshly verifies the whole supplied prefix before writing it.

## Validation and remaining gate

Tests verify no credential or signer use, unchanged ledgers, private exclusive output,
explicit lifecycle selection, changed input pins, wrong slots/results, invalid phase
signatures, runtime response substitution and malformed input. A separately signed
fixture proposal is checked through fresh partial-campaign acceptance. No live
observation or production signature is created by these tests.

Actual independent custody and runtime assessment, authorized live attempts and
reviewed launch admission remain required. This command assists inspection without
replacing those operating requirements.
