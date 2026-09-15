# Proposed launch conformance check

`review-launch-conformance-check` compares a freshly prepared guided launch with
independently pinned campaign evidence. It verifies every supplied campaign slot
again and requires the exact critic identities and role profiles, judge profile,
review quorum, whole-review duration, installed OpenAI SDK version and selected
immutable worker image. A successful check supports a separate launch review.
It does not enable live launch, access keys, create reservations or dispatch calls.

## Explicit inputs

Use the same current workspace, guidance, spending and unused run-directory inputs
as [launch preview](REVIEW_LAUNCH_PREVIEW.md). Also independently select the exact
raw configuration hash, retained campaign seal hash and raw evidence-submission
hash. [Evidence assembly](REVIEW_CAMPAIGN_SUBMISSION.md) can produce the submission;
an old acceptance report cannot replace it.

```sh
mos review-launch-conformance-check \
  --config /private/launch.json --expected-config-sha256 CONFIG_FILE_SHA \
  --workspace /work/project --guidance-storage /private/guidance \
  --prepared /private/prepared.json --expected-prepared-sha256 PREPARED_SHA \
  --guidance-policy /private/policy.json --expected-guidance-policy-sha256 POLICY_SHA \
  --spend-ledger /private/launch-spending.sqlite --review-dir /private/new-review \
  --campaign-dir /private/sealed-campaign --expected-seal-sha256 SEAL_SHA \
  --evidence /private/submission-3.json --expected-evidence-sha256 EVIDENCE_FILE_SHA \
  --image-id sha256:EXACT_IMAGE_DIGEST --json
```

Configuration and evidence file hashes are checked before launch preparation.
Existing guidance checks bind the selected prepared brief and current owner policy;
existing spending admission validates pricing, output caps and available capacity.
The check does not create a missing ledger or run directory. Use a separate launch
ledger so the completed campaign's dedicated accounting remains intact.

The SDK version is read from the installed package. `--image-id` selects the intended
immutable worker image; this offline command does not run Docker or independently
measure a future worker. Passing a label cannot attest to runtime execution. Actual
dispatch must still enforce the reviewed SDK/image and current admission conditions.

## Scope and fresh verification

The proposed brief and per-run identities may differ from the three historical
probes. Critic identities, model, reasoning effort, system-prompt hash, token/byte
limits, judge role, quorum and duration must match exactly. Spending availability
and current guidance are checked for the proposed launch independently. A campaign
for an explicitly selected one-provider experiment cannot qualify a stronger or
different review policy; the command never relaxes quorum automatically.

The campaign verifier checks the current policy window and observation age, all
historical approvals and observer signatures, reconstructed results, runtime and
cleanup evidence, ordering and complete dedicated-ledger accounting. Changed or
missing supplied artifacts fail even if an earlier invocation returned accepted.
Use trusted, stopped, same-owner evidence directories and trusted parent paths.

Standard output contains the configuration hash, new launch-preview hash, seal hash,
canonical submission hash, selected runtime and nested fresh `conformance` result.
The preview hash changes with each preparation's new in-memory identities. The
canonical submission hash identifies parsed canonical JSON; the independently
supplied evidence-file hash identifies the exact input bytes. No raw prompt or
observation content is printed by this command.

Exit 0 requires all three campaign slots to qualify and the launch profile to match.
Exit 1 reports a matching profile with incomplete evidence. Invalid inputs, stale
guidance, corrupt evidence, expiry or profile mismatch return 2. Every successful
report includes `launch_review_required: true` and false values for
`live_launch_available`, `credential_access_authorized`,
`provider_dispatch_authorized` and `reservation_created`. Reports are snapshots;
they are never cached dispatch authority or handles for resuming prepared work.

## Validation and remaining admission

Synthetic tests cover complete and partial evidence through the CLI, changed role
budgets, duration, quorum, SDK/image, configuration hashes, current guidance, input
substitution, evidence tampering, expiry and cached-report substitution. They verify
unchanged ledgers, no run-directory creation and no credential access. These fixtures
do not establish independent production custody or an actual live tranche.

Independent runtime assessment and commitment custody, authorized live attempts and
a separately reviewed launch-admission decision remain required. This comparison
does not prove remote provider authorship, reconciled billing or review quality.

[Exact launch admission](REVIEW_LAUNCH_ADMISSION.md) now enforces a separately signed
decision in the owning library flow. This check remains read-only and does not
create that decision, provide independent assessment or activate live execution.
