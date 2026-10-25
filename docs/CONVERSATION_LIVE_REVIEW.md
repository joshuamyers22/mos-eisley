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

## Connect an exact Git scope

Create the canonical scope artifact with `mos review-scope ... --output PATH`.
Use that scope's exact source brief when preparing project guidance with
`mos guidance-review prepare`; the prepared critic brief also includes the admitted
guidance. Select `git_scope` (the absolute artifact path) and
`expected_scope_sha256` (its exact byte hash) together in the live selection.
The existing exact campaign/profile and signed launch requirements still apply
to the prepared brief. Selecting a different diff never rebinds old authority.

With that selection, `/review --uncommitted`, `--base`, `--commit`, or explicit
`--file`/`--range` presets acquire the current scope and require it to match the
selected artifact and original source brief exactly. Bare `/review` uses the
same retained scope. Ambiguous, incomplete, stale, foreign-owner or different
workspace scopes fail before dispatch. Scoped live packets use schema 2; older
prepared-only schema-1 packets retain their canonical bytes and operating path.

`mos review-launch-preview` accepts the same `--git-scope PATH` and
`--expected-scope-sha256 HASH` pair. Its plain/JSON output and the conversation's
`conversation.review_launch` event share a version-1 projection: frozen
target/revisions, included files/ranges and omissions, critics and judge, effective
review/guidance policy identities, remaining task ceiling and conservative
reservation upper bound. Estimated cost remains explicitly unknown. The remaining
ceiling is bounded by configuration, available ledger funds and, for a selected
live launch, the owner's cap after campaign charges. Preview never reads keys,
reserves funds, creates a run, starts a container or contacts a provider.

The live child emits the same projection before its existing signed admission
flow. Source, configuration and prepared inputs are checked again at phase
approval and credential/provider use, and before displaying or publishing a
result. A changed input stops the attempt; it cannot produce accepted conversation
evidence or an automatic retry. Critics still receive only the frozen prepared
brief and persona, with the existing quorum, spending and isolation policy.
Review intent authorizes no edits, correction dispatch or outward posting.
The preview adds no confirmation prompt; separately required launch/phase
signatures and exact local approvals remain unchanged.

On `/review`, the conversation saves a frozen prepared brief and its non-secret
hashes. It rechecks the selected manifest, config, prepared review and campaign
bytes before starting `review-live`. The full-screen terminal temporarily yields
the terminal to that command so the owner can inspect the exact launch scope,
provide a separately signed launch decision, and provide signed phase decisions
and local approvals. The existing live-review admission flow checks current
guidance, campaign evidence, provider credentials, spending and containment. A
successful child writes a private completion receipt. The conversation checks the
receipt's selection and prepared hashes, the retained result and brief, and the
retained signed launch admission against the selected configuration, campaign,
evidence, image, ledger and output directory before publishing the result.

The conversation never saves a credential, signer key, approval file, operating
path, or permission to run the next call. An interrupted or cancelled attempt is
consumed and is never restarted by `resume`. A queued review needs the same
selection and current policy when resumed. A failed launch leaves its dedicated
run and ledger for inspection; no result is presented as a successful review.
Paid conversational dispatch requires an interactive full-screen terminal because the signed
owner ceremony reads from that terminal. The existing `mos review-live` command
remains the separate non-conversation operating path; plain/JSON launch previews
remain inert. `mos exec --json` emits its preview through the versioned event
stream and keeps child diagnostics on stderr, preserving its terminal result.

## Review and approval presentation

Ctrl-O inspects the selected non-secret packet in the conversation, including its
complete prepared/configuration/campaign/manifest hashes and frozen brief.
Alt-PageUp/Down scrolls details; Ctrl-G closes the companion without changing the
composer draft or focus. The companion does not sign or approve a launch.

The separate critic and judge prompts show action, scope, approval reason,
destination, spending/time limits and the exact approval SHA-256. `show` prints the
complete request as escaped JSON; `approve <hash>` still requires the full exact
hash. `cancel` declines that approval; it does not send that phase. The existing
signed launch/phase decisions, one-use dispatch and expiry checks still apply.

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
