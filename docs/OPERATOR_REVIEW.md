# Operator-authorized three-model review

`mos operator-review` runs one guided, read-only Anthropic critic/judge review with
two exact terminal approvals. It uses the existing private worker broker, shared
full-envelope reservation, evidence-derived judge request, retained result and
cancellation cleanup. The operator chooses the author artifact and its model
identity. This declaration binds the exact reviewed diff but does not prove who
authored it. The route requires distinct author, critic and judge model IDs. It
does not require an additional human authorizer or observer.

For the current Anthropic key, a practical selection is GPT-6 as author, Claude
Sonnet 5 as critic and Claude Opus 5.5 as judge. Both Claude models passed separate
fixed credentialed API probes. A synthetic full review test exercises their
critic/judge roles, approval boundaries and shared ledger. On 2026-09-26, one
operator-approved live critic/judge run completed on the current source patch:
Sonnet produced one finding, Opus did not uphold it, and the retained verdict was
`accept`. The exact result hash was
`1cb0ce9c8cd8011927434eb193937ab5d660431adb7be7e94f44d09c46f69b35`.
That local run exercises the credentialed route; it does not establish the older
independently signed campaign gate.
The [Anthropic conformance closeout](ANTHROPIC_CONFORMANCE_CLOSEOUT.md) records
fresh local verification of all four attempts and the signed campaign extension.

## Prepare the exact inputs

Freeze a current paired critic/judge guidance packet and prepared review brief as
described in [guided reviews](PROJECT_GUIDANCE_REVIEW.md). The `brief.diff` field
must contain the exact author artifact to review. Select an immutable Docker
image digest containing the installed runtime; the worker has no network or host
mounts. The same image is used for both roles.

Create an `OperatorReviewIdentity` JSON file with `author_provider`,
`author_model`, `author_artifact_sha256` and `max_total_microusd`. The artifact hash
is SHA-256 of the UTF-8 bytes of `prepared.source_brief.diff`. The maximum is at
most 1,000,000 micro USD ($1). The chosen dedicated ledger ceiling must not exceed
that maximum. The author declaration is checked against the guided brief before
any approval or credential load.

Create a `ReviewLaunchConfiguration` JSON file as in
[launch preview](REVIEW_LAUNCH_PREVIEW.md). Select a schema-2 Sonnet 5 critic
spending policy at the reviewed $2 input / $10 output / $2.50 cache-write rates per
million tokens, and a schema-2 Opus 5.5 judge policy at $4 / $20 / $5. Pin each
policy to the provider, model, current pricing source, UTC validity window, input
and output token ceilings, and per-call cost. Select an explicit one-provider
`ReviewPolicy`; the default two-provider policy is not relaxed automatically.
The configuration's aggregate allowance must fit the dedicated ledger and the
operator's $1 cap, including a full deferred judge allowance.

Run the read-only `review-launch-preview` first and inspect the requests and
spending. Then use the same input files in one interactive command:

```sh
mos operator-review \
  --config private/review/configuration.json \
  --identity private/review/operator-identity.json \
  -C /path/to/workspace \
  --guidance-storage private/guidance \
  --prepared private/review/prepared.json \
  --expected-prepared-sha256 PREPARED_SHA256 \
  --guidance-policy private/guidance-policy.json \
  --expected-guidance-policy-sha256 POLICY_SHA256 \
  --spend-ledger private/review/spend.sqlite \
  --review-dir private/review/run-1 \
  --key-file private/anthropic-api-key \
  --image-id sha256:EXACT_IMAGE_DIGEST
```

At each pause, type `show` to inspect the full escaped preview, then type
`approve <printed-hash>` or `cancel`. The critic approval reserves the full
critic/judge envelope. The judge approval binds the findings reconstructed from
the critic response; it uses the held judge allowance. The key file is read only
after the relevant exact local approval, and every token-count and generation
operation checks the current guidance, request bytes, model, price policy and
controller deadline again. The provider SDK makes no automatic retries.

The command prints the result hash, total ledger charge and unresolved-entry
count. Review artifacts and model responses stay in the selected private run
directory. A completed local result does not claim independent provider
authorship, external observer assessment, billing reconciliation or repeated
conformance. The older signed campaign gate retains its separate meaning.

## Add the independently signed campaign

The same command can run a slot from a separately sealed three-attempt campaign.
Supply `--campaign-dir`, `--expected-seal-sha256`, `--campaign-slot`,
`--authority-policy` and `--completion-output` together with the options above.
For slots 1 and 2, also supply `--previous-evidence` and
`--expected-previous-evidence-sha256` for the accepted prefix. The command prints
each exact signed scope and prompts for an independently signed authorization
file before each local phase approval. It writes the completed handoff outside
the run and seal directories. The independent observer must still assess and sign
each slot before the next one starts; use the existing campaign observation,
evidence append and review commands. All three committed allowances must fit the
operator identity's selected cap. No signer keys are loaded by this command.

No signed live tranche has been run. Independent authorizer and observer
enrollment, a new sealed commitment and campaign spending approval are pending.
