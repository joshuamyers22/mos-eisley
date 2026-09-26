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
freshly sealed campaign is required for three-slot acceptance. The corrective
route selects Sonnet 5 with thinking disabled for the critic, keeps Opus 5.5
adaptive for the judge, and uses a 1,000-token response cap after observing
both completed judges use fewer than 400 output tokens. The prepared replacement
has a $0.675000 aggregate reservation. This correction has offline tests but no
new live result.
