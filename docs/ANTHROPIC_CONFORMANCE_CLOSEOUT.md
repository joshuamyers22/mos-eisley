# Anthropic conformance closeout, 2026-09-26

The operator-approved Anthropic route completed one credentialed review of the
frozen integration patch. GPT-6 was the operator-declared author, Claude Sonnet 5
was the critic, and Claude Opus 5.5 was the judge. The author declaration binds
the patch hash; it is not independent authorship evidence. Exact local approvals
preceded both Anthropic phases. The retained verdict was `accept`, with result
SHA-256 `1cb0ce9c8cd8011927434eb193937ab5d660431adb7be7e94f44d09c46f69b35`.

The local closeout reread the four private controller directories and dedicated
ledgers. `inspect_review_controller` verified each retained start, envelope,
critic audit and model completion against its ledger. For the completed run,
`verify_retained_review_result` reconstructed the critic findings, judge transfer,
decision and final verdict against the result hash above. These checks used the
retained starts and judge preview as local pins; they are not independent custody
or observer attestations.

| Attempt | Controller terminal | Local evidence | Charged |
|---|---|---|---:|
| 1 | failed during critic phase | Critic audit and completion verified; no judge preview or transfer | $0.201576 |
| 2 | failed during critic phase | Critic audit and completion verified; no judge preview or transfer | $0.215128 |
| 3 | failed during critic phase | Critic audit and completion verified; no judge preview or transfer | $0.113768 |
| 4 | finished | Full result and spending inventory verified; verdict `accept` | $0.295932 |

The three failed attempts exhausted the critic output limit or failed the strict
response contract before judge dispatch. Their zero-charge, unused judge
allowances were separately reconciled after checking the failed terminals and
absence of a judge preview or transfer. The generic controller inventory reports
`spending_inventory_complete: false` for those three retired allowances because
it cannot infer a missing transfer target; the dedicated reconciliation receipts
and ledger entries explain them. All four ledgers are unblocked, have zero
unresolved entries and total $0.826404, below the selected $1 ceiling. This is
recorded provider usage, not invoice reconciliation.

The completed run establishes one local credentialed Sonnet critic and Opus judge
exchange through the broker, approval and spending path. It does not establish
independent phase authorization, observer authentication, repeated three-slot
conformance, remote provider authorship or live launch admission. A subsequent
signed campaign is recorded below.

## Signed campaign extension

The `operator-review` command now accepts a sealed campaign slot in addition to
its existing operator identity and exact local approvals. It uses the existing
signed `BrokeredReviewConformanceProbe` and `ReviewCampaignBinding`, requiring
separate enrolled authorizer signatures for critic and judge phases. It checks
the same distinct author/critic/judge models, the exact patch hash, the selected
spending cap, the sealed slot, runtime and current guidance. The sum of all three
committed allowances must fit the operator identity's cap. Later slots require a
separately pinned, freshly verified evidence submission for every earlier slot.
Before each slot, the command rejects unexplained entries or unresolved spending
in any committed ledger; future slots must still be unused.

Prepare three fresh Anthropic review configurations, guidance packets, run
directories and dedicated ledgers, plus an independently enrolled authority
policy and observer policy for each slot. Preview and seal the exact bundle with
`review-campaign-preview` and `review-campaign-seal`, then retain the seal hash
independently. For each slot, supply the existing operator-review options and:

```sh
mos operator-review ... \
  --campaign-dir /private/sealed-campaign \
  --expected-seal-sha256 SEAL_SHA \
  --campaign-slot 0 \
  --authority-policy /private/authority-policy.json \
  --completion-output /private/slot-0-completion.json
```

At each phase the command prints the exact signed scope and asks for an absolute
path to an independently signed authorization file. It verifies that signature
before the local `approve <hash>` prompt and rechecks it before credential and
provider use. It neither loads signing keys nor signs on behalf of an authority.
The enrolled authorizer can construct the exact statement with
`make_review_conformance_authorization` and sign it with
`sign_review_conformance_authorization` in a separate process, as specified by
[phase authorization](REVIEW_CONFORMANCE_AUTHORIZATION.md). The signer must use
the printed scope, current enrolled policy and a short UTC validity window; the
resulting `SignedReviewConformanceAuthorization` is the file supplied at the
prompt.
On success it exclusively writes a private `CampaignProbeCompletion` outside the
sealed campaign and run directories and prints its hash. For slots 1 and 2 add
`--previous-evidence` and `--expected-previous-evidence-sha256` for the accepted
prefix. An independent observer selects lifecycle records, reviews the completion
with `review-campaign-observation-preview`, signs an assessed observation, and
appends it with `review-campaign-evidence-append` before the next slot. Finally,
`review-campaign-review` freshly verifies all three signed slots and the ledgers.

At the time of the original closeout, no live signed attempt had been made.
Earlier operator-run evidence cannot be retroactively signed into a precommitted
tranche.

## Signed campaign attempt

A separate three-slot campaign was sealed on 2026-09-26 for source commit
`1c9ce6b7237e326ceb14c8838c9c51c0e27128fe`, with seal SHA-256
`4763300b542a27d61697159e41ddac618fff5cc5f0fb2c96229e1b5034aaa850`
and a $0.967500 maximum reservation. One operator held distinct enrolled
authorizer and observer Ed25519 keys; this establishes distinct cryptographic
roles, not independent human custody or assessment. Each live phase also had
an exact local approval before provider use.

Slots 0 and 1 completed Sonnet critic and Opus judge exchanges, received signed
observer records, and passed fresh campaign evidence review. Their ledgers
settled $0.115386 and $0.131696. In slot 2, Sonnet exhausted the 2,000-token
output limit in adaptive thinking and returned only two visible text characters.
The critic response could not satisfy the strict JSON contract, so the controller
failed before judge dispatch. Its critic settled $0.065500. The unused $0.215000
judge allowance was held pending manual release; it was never counted as settled
usage. At failure, total settled campaign charges were $0.312582, with
conservative exposure of $0.527582 including the held allowance. The private
failure closeout records metadata and exact artifact hashes without copying
prompts or responses.

After the operator explicitly approved a manual release, the slot 2 judge hold
was settled at $0. The controller terminal confirmed failure before judge
dispatch, and neither a judge preview nor judge run directory existed. The
ledger now has zero unresolved entries and $0.065500 settled for slot 2. The
private release receipt has SHA-256
`d0a6dd71ed1250dd3a2de2098b76f944cab915851b7654a6b41a532e0cafd0e4`.
The three-slot campaign total remains $0.312582 in settled usage; this is still
not invoice reconciliation.

`review-campaign-review` returned `incomplete` with two qualifying attempts
under evidence SHA-256
`9288441f74d6a1b2fd5adc692db49a5902cc8878e1ec8d032282a8757d3f0243`.
The consumed third slot cannot be retried under that seal. A separately funded,
freshly sealed campaign is required for three-slot acceptance.

Two replacement seals were attempted. The first failed before provider dispatch
because the local sandbox denied access to Docker. Both untouched reservations
were manually settled at $0 after operator approval; its receipt SHA-256 is
`20372a10dc33c570d8562b5c994c63790ceb74cf431f1996803a7736cc2fd19d`.
The second reached Sonnet with thinking disabled, but its unconstrained visible
reply exhausted the 1,000-token output cap in prose and failed the JSON contract.
The critic settled $0.044802; no judge was dispatched. The unused $0.150000
judge allowance was manually settled at $0 after operator approval, with receipt
SHA-256 `a344bd7aa01023dde783b5267c83bd4b790c39ab4036b6d99bf9da301d7f4955`.
Across these signed attempts, identified settled usage is $0.357384; this is
still not invoice reconciliation or three-slot conformance.

The next corrective route sends Anthropic's `output_config.format` JSON schema
for the critic and judge, keeps Sonnet 5 thinking disabled and Opus 5.5 adaptive,
and asks the critic for at most one concise finding. With a 24,000-token input
limit and 1,000-token output limit, its prepared three-slot reservation is
$0.630000.

That route was sealed under SHA-256
`98c1c1f63958ef6eee7e7ce02ff220a07bb94a326b86ae644e392daf8a1a4379`
for source commit `9b94fca`. Slots 0 and 1 completed Sonnet critic and Opus
judge exchanges, received signed observer records, and passed fresh campaign
evidence review. Their ledgers settled $0.125380 and $0.125842. In slot 2,
Sonnet returned a complete JSON response, but a required finding evidence
explanation was empty. Local contract validation failed before judge preview or
dispatch. The critic settled $0.050784. With the operator's explicit approval,
the unused $0.140000 judge allowance was settled at $0; its private release
receipt has SHA-256
`1d44b058f768f4991b18cd34de57b2dfb5408d4981a7e4e2f7625763e7dc6b1d`.
The slot 2 ledger has no unresolved entries. This seal has two qualifying
attempts and cannot be retried for a third.

Across the signed attempts, identified settled usage is $0.659390. This is
recorded provider usage, not invoice reconciliation. No signed campaign has
passed the three-slot gate. The response schema has since been tightened with
nonempty string patterns for the required review fields, including the failed
explanation field. The change has local tests but no live conformance result;
a fresh seal and separately approved spending are required for another
three-slot attempt.

A later seal,
`72af8a223910bdd024ac3224bc3e4fde2161cb5b7733c8b9d51d974409c3a0a2`,
was approved for a new three-slot campaign. Its first critic request reached
the Anthropic API, which returned `invalid_request_error` without a model
response or usage receipt. The controller failed before judge preview or
dispatch. The $0.070000 critic reservation remains **uncertain** at its full
amount; it is conservative local exposure, not identified settled usage or an
Anthropic invoice charge. With the operator's explicit approval, the separate
unused $0.140000 judge allowance was settled at $0. Its private release receipt
has SHA-256
`f5b3fd83a222cc1a89ed001de8dc9c02fc646de133097ff883d44f3c16907725`.
The slot ledger has one unresolved entry: the critic uncertainty. Identified
settled usage across signed attempts remains $0.659390; conservative exposure
including this uncertain critic is $0.729390. The retained error category does
not identify which request field Anthropic rejected. The next source change
restores the nullable `suggested_fix` schema form that succeeded earlier while
retaining nonempty patterns on required fields. That change is an unproven
compatibility correction until another live result is obtained.

That correction was attempted in a separate sealed campaign,
`5434311f8d71db8aa2752c544d6c369b09ae1949b1ed388a17c2c12b8738e452`.
Its first critic request was accepted by Anthropic. Sonnet returned 1,000 output
tokens and stopped at the configured limit. The strict review contract could
not accept the truncated critic result;
the controller failed before judge preview or dispatch. The critic settled
$0.050758 in the local ledger. With the operator's explicit approval, the
unused $0.140000 judge allowance was settled at $0; its private release receipt
has SHA-256
`2252f5ff030479eea83e7e52e9e0eae114226d4b0908a4e877cdfcf5a6756d29`.
The slot ledger has no unresolved entries. Identified settled usage across the
signed attempts is now $0.710148, plus the earlier $0.070000 uncertain critic
reservation, for $0.780148 in conservative exposure. The next offline
configuration raises the output limit to 3,000 tokens while retaining a
single-finding prompt and a per-campaign reservation bound.

The 3,000-token configuration was sealed under SHA-256
`76f601c2b50b3276b89b35be7f038debca40f868c8947437946ba2d527be00b8`.
Its first critic request again stopped at the output limit, with 3,000 tokens
and a $0.070754 local settlement. The controller failed before judge preview or
dispatch. With explicit operator approval, the unused $0.180000 judge allowance
was settled at $0; its private release receipt has SHA-256
`0d571580d88ee8ad054cac3706af44b439285a30ce20d1989bf25ecdf199ae00`.
The slot ledger has no unresolved entries. Identified settled usage across
signed attempts is $0.780902, plus the earlier $0.070000 uncertain critic
reservation, for $0.850902 in conservative exposure.

An offline inspection then found that the pinned isolated worker image
`sha256:347fc7e99c253ebcb5eb53e890f3410cf39c1364fcaa0b8e0c9df85bcf46dc80`
did not contain `review_json_format`, despite the host source passing its tests.
The Dockerfile copies and installs `src` into a no-mount worker image; the
worker therefore ran older Anthropic translation code and did not send the
host's structured-output schema. This explains why increasing the output limit
did not constrain the critic response. A new image was built from the current
source as
`sha256:419dd600b3d708987982deb4a631280c44bb1b28ccd920f03ddfa8d6b9e1e809`.
An offline check inside that image verified the Anthropic SDK version, the
`structured_output` model field, and translation to `output_config.format` with
the required `schema_version` property. That image has not yet produced a live
signed campaign result.
