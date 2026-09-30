# Explicit live review in a conversation

`mos chat --live-review-selection PATH` and `mos resume --live-review-selection
PATH` connect `/review` and `Review this change.` to the signed `review-live`
path. This is an **operator-selected, one-attempt review** of the prepared brief
named in `PATH`. Ordinary chat still uses the recorded preview. No review runs for
ordinary messages.

The selection is a private JSON file with mode
`conversation_live_review_selection` and schema version `1`. It carries the exact
arguments already required by `mos review-live`: `config`,
`expected_config_sha256`, `identity`, `workspace`, `guidance_storage`, `prepared`,
`expected_prepared_sha256`, `guidance_policy`,
`expected_guidance_policy_sha256`, `spend_ledger`, `review_dir`, `key_file`,
optional `openai_key_file`, `image_id`, optional `docker`, `campaign_dir`,
`expected_seal_sha256`, `evidence`, `expected_evidence_sha256`,
`authority_policy`, `launch_authority_policy`, and `completion_output`. All paths
must be absolute. Use a new review directory, ledger and completion file for each
attempt. Keep the selection and credential files private; the selection contains
paths, not key material.

On `/review`, the conversation saves a frozen prepared brief and its non-secret
hashes. It rechecks the selected manifest, config, prepared review and campaign
bytes before starting `review-live`. The full-screen terminal temporarily yields
the terminal to that command so the owner can inspect the exact launch scope,
provide a separately signed launch decision, and provide signed phase decisions
and local approvals. The existing live-review admission flow checks current
guidance, campaign evidence, provider credentials, spending and containment. A
successful child writes a private completion receipt; the conversation checks it
against the retained result and frozen brief before publishing the summary and
result in session history.

The conversation never saves a credential, signer key, approval file, operating
path, or permission to run the next call. An interrupted or cancelled attempt is
consumed and is never restarted by `resume`. A queued review needs the same
selection and current policy when resumed. A failed launch leaves its dedicated
run and ledger for inspection; no result is presented as a successful review.
The command requires an interactive full-screen terminal because the signed
owner ceremony reads from that terminal. The existing `mos review-live` command
remains the separate non-conversation operating path.

## Qualification and release boundary

The 2026-09-27 G2 campaign qualifies only its exact focused brief, models,
effort, SDKs, image, limits, quorum and custody. A new arbitrary workspace diff
or release image is outside that qualification. An operator must prepare and
qualify the exact intended review profile, then sign a fresh launch for each
target call. A saved conversation, a test fixture, or this terminal integration
does not extend the campaign's scope.

For v1 release review, run the installed artifact from the frozen candidate and
exercise the complete `/review` journey, cancellation, save/resume and retained
evidence under the exact candidate image and profile. Record the new campaign,
launch, spend, cleanup, supported-platform and release-checklist evidence before
the owner's production decision. The existing G2 closeout and this offline
integration do not supply that release decision.
