# Work Note: live read-only review qualification

- Status: qualification stopped unsuccessful; final-campaign exception consumed
- Owner: Josh Myers
- Started (UTC): 2026-09-19
- Last updated (UTC): 2026-09-20
- Review or delete by: completion or cancellation of the production qualification
- Related issue/incident/ADR: `docs/ROADMAP.md` G2; `docs/adr/0003-openai-first-provider.md`

## Objective and completion evidence

- Intended outcome: qualify one exact live read-only critic/judge launch using the
  already-implemented campaign, observer, conformance, and launch-admission gates.
- Required invariants: one consistent schema-2 single-operator signer across custody,
  phase authorization, observation and launch review; three fixed credentialed
  attempts; complete dedicated-ledger accounting; an explicitly self-reviewed and
  signed exact launch decision; no retry, automatic release, scoring, or global activation.
- Evidence that will show completion: a freshly accepted three-slot campaign, exact
  pinned evidence and Joshua Myers signatures, matching launch-conformance output,
  schema-2 signed production launch admission, and preserved audit/spend/cleanup data.

## Context retrieved

- `PROJECT_BRIEF.md`, `docs/ROADMAP.md`
- `docs/REVIEW_CAMPAIGN_CEREMONY.md`, `docs/REVIEW_CAMPAIGN_RUNNER.md`
- `docs/REVIEW_OBSERVER_HANDOFF.md`, `docs/REVIEW_CAMPAIGN_SUBMISSION.md`
- `docs/REVIEW_LAUNCH_CONFORMANCE.md`, `docs/REVIEW_LAUNCH_ADMISSION.md`
- `docs/PRODUCTION_TEMPLATE_SURVEY_2026-09-19.md`
- `docs/LIVE_READ_ONLY_REVIEW_QUALIFICATION_VERIFICATION.md`
- `docs/LIVE_READ_ONLY_REVIEW_QUALIFICATION_THREAT_MODEL.md`

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-19 | observation | GitHub `main` is `fa0faafb6f29421e46429001be3932b614f392f0`; it already includes brokered critic/judge flow, campaign sequencing/evidence, launch-conformance comparison, and exact signed launch admission. | GitHub ref plus roadmap and feature guides | Do not reimplement the older held-reservation boundary. |
| 2026-09-19 | decision | Treat remaining work as a high-risk production qualification ceremony and apply the current template's verification, threat-model, Python, work-note, and adversarial-review guidance. | Template survey and task records | Obtain the missing independent custody/reviewer roles and explicit paid-run authority. |
| 2026-09-19 | decision | Josh approved an aggregate provider-spend ceiling of USD 5.00 (`5,000,000` micro-USD) and nominated Ron Mexico for an independent role. No role separation, key custody, or credential access is inferred from the nomination. | User authorization in the active task | Assign Ron to one role and obtain a distinct launch reviewer or observer before preparing live authority. |
| 2026-09-19 | decision | Joshua Myers was nominated as launch reviewer, leaving Ron Mexico as campaign custodian/observer. These are nominations only; identity and disjoint key custody remain to be established. | User direction in the active task | Name a third, disjoint phase authorizer. |
| 2026-09-19 | decision | The owner proposed Joshua Myers also act as phase authorizer. The existing launch-admission contract rejects any launch reviewer sharing an identity or key with a phase authority or observer, so this configuration was not adopted. | `review_launch_admission.py`; `test_review_launch_admission.py` | Obtain a third person or explicitly revise the governance claim and its contracts before any live action. |
| 2026-09-19 | decision | Joshua Myers explicitly directed that one person—Joshua Myers—may perform every human role. ADR-0005 adopts schema-2 `single_operator`; the prior Ron Mexico nomination and third-person blocker are superseded for this campaign. | `docs/adr/0005-single-operator-review-authorization.md`; focused contract tests | Enroll one real Joshua Myers public key consistently; do not claim independent human review. |
| 2026-09-20 | verification | Built the repository's pinned `mos-eisley:local` worker and passed the complete offline `make container` gate. The selected immutable image ID is `sha256:8f900b1597447922049b91f32d9f00709eeaa61be7121663961874bde811f8be`; the installed host OpenAI SDK is `3.11.0`. | Docker image inspection and successful isolation/controller/approval/conformance/runtime/campaign/launch smoke output | Bind this exact SDK/image pair in the campaign and reject any later drift. |
| 2026-09-20 | preflight | No `OPENAI_API_KEY` or `MOS_OPENAI_KEY` value is present in the owning process, no public signing-key file was found under Joshua's SSH directory, and no production campaign/configuration input was found. Secret values were not read or printed. | Presence-only environment check and bounded public-file inventory | Obtain an externally controlled Ed25519 signing identity and inject the provider credential only into the final owning host after exact transfer approval. |
| 2026-09-20 | data-boundary review | Current official OpenAI documentation says API keys are secrets that should be loaded from an environment variable or server-side key manager. API inputs/outputs are not used for training by default, but abuse-monitoring logs may retain customer content for up to 30 days unless the account has approved retention controls. | Official OpenAI API authentication and data-controls documentation reviewed 2026-09-20 | Inspect the account's actual retention setting and exact prompt/instruction payload before any credentialed request. |
| 2026-09-20 | decision | Joshua approved a one-process operator host that generates the shared Ed25519 signing key only in memory and retrieves the provider credential from macOS Keychain. The host remains a library composition boundary, not a public live CLI, and implementation tests may use only synthetic credentials/providers. | User direction; Python engineering, verification-loop and threat-model guides; existing native-Keychain OAuth adapter | Implement the smallest host/keychain slice and prove late credential access, one-key identity, redacted failures and no secret retention before composing production artifacts. |
| 2026-09-20 | verification | Implemented the inert one-process host and native-Keychain credential adapter. Nine focused tests and all 356 review tests passed with synthetic credentials/providers; credential reads occur only after current phase approvals and retained fixture files contain no synthetic secret. | `review_single_operator.py`; `test_review_single_operator.py`; single-operator host guide and adversarial review | Do not invoke the real credential callback until the account and exact transfer reviews pass. |
| 2026-09-20 | verification | The clean `make check` rerun passed: Ruff, Pyright, 2,446 source tests with four skips and 89% coverage, export/build checks, and 1,839 installed-wheel tests. The first unrestricted run had one transient missing fixture timestamp; the exact case and complete rerun passed. | Full gate output and isolated reproduction | Preserve this flake evidence; do not represent the failed attempt as a pass. |
| 2026-09-20 | verification | Rebuilt the source-bearing worker image and passed the full offline `make container` suite. The current immutable image ID is `sha256:42aac38dc474addd64eec136fc20a33a84fee7534533bbc7645f74be37860f4c`; OpenAI SDK remains `3.11.0`. | Docker image inspection and successful container smoke output | Bind this exact SDK/image pair and reject drift at dispatch. |
| 2026-09-20 | verification | A metadata-only lookup outside the managed sandbox found one generic-password item in `login.keychain-db` with exact service `mos-eisley.openai.review.v1` and account `joshua-myers`. The password was neither requested nor displayed. | `security find-generic-password` without `-g` or `-w` | Keep the credential unread until account retention and exact transfer reviews pass. |
| 2026-09-20 | decision | The default project exposed no explicit ZDR/MAM selection. Joshua approved proceeding under the conservative default-retention assumption with `store: false` and only the exact bounded review content. | Official OpenAI data-controls documentation; `docs/LIVE_READ_ONLY_REVIEW_TRANSFER_REVIEW.md`; user approval in the active task | Freeze and inspect the actual campaign previews; this decision is not ZDR and does not authorize a substituted request. |
| 2026-09-20 | verification | Traced both provider operations for every role. Token counting and generation receive the same fixed role instructions and canonical role document; generation additionally receives only the bounded output/storage/evidence fields. No credential, path, signature, ledger, unrelated repository content, tool, file, image, web request or conversation state belongs in either body. | `model_reviewer.py`; `openai_responses.py`; `openai_spend.py`; existing provider/reviewer tests; transfer-review record | Create dedicated funded ledgers and the exact three-slot bundle, then inspect its full critic previews before sealing. |
| 2026-09-20 | decision | Selected the repository's previously qualified `gpt-5.6-luna` low-effort profile for campaign preparation. Current official rates are 200,000 input, 250,000 cache-write and 1,200,000 output micro-USD per million tokens. With 64,000 input and 4,096 output tokens, the conservative full allowance is 20,916 micro-USD per role and 62,748 per two-critic-plus-judge attempt. | Official GPT-5.6 Luna model page reviewed 2026-09-20; schema-2 `SpendPolicy` calculation | Create no expiring spend policy until the exact guidance/brief is ready. Recheck pricing before sealing and dispatch. |
| 2026-09-20 | verification | Created four distinct empty ledgers—three campaign attempts and one separate launch ledger—under `/Users/josh/.local/share/mos-eisley/live-review-qualification-20260920`. Every directory is mode 0700; every ledger is mode 0600, empty, unblocked and capped at 62,748 micro-USD. Their aggregate generation allowance is 250,992 micro-USD (USD 0.250992). | Ledger IDs `8c2d8800…`, `c549419d…`, `57678b52…`, `17504272…`; four fresh `spend-ledger-status` results | Build current critic/judge guidance and the frozen source brief before creating time-limited policies or campaign previews. |
| 2026-09-20 | execution | Frozen current guidance and source brief, sealed schema-2 campaign bundle `98c004b7…` as seal `4c41d077…`, and explicitly approved attempt 1 critic scope `7d4f5017…`. Both critic jobs failed before any runtime SDK-operation record or provider response was retained. One broker exchange reported `provider_error` after 239,305 ms; the other was cancelled without terminal broker accounting. The controller failed before judge preparation, attempts 2–3 remained unused, both worker containers were removed, and no matching Docker container remained. | Private bundle/seal, attempt-1 controller terminal, broker outcomes, lifecycle cleanup records and ledger status | Treat the exact campaign as failed and non-retryable. Diagnose the pre-dispatch Keychain delay outside a paid campaign before proposing a wholly new campaign. |
| 2026-09-20 | accounting | Attempt 1 conservatively retained its full 62,748-micro-USD allowance: one critic entry is `uncertain`, the other critic and unused judge allowance remain `held`; actual provider billing is not reconciled. Attempts 2–3 and the separate launch ledger remain empty. | Ledger `8c2d8800…` has three unresolved entries and zero available allowance; other ledgers have zero entries | Do not release, reset, reuse or describe the retained amount as actual billed spend. |
| 2026-09-20 | diagnostic | After separate explicit authorization, a no-network invocation of the production Keychain loader succeeded in 10,695 ms. It printed only success, elapsed time, `network_calls: 0` and `secret_output: false`; it printed neither the credential nor its length or digest. | Local Keychain-loader diagnostic; official OpenAI API-key handling guidance | Treat current Keychain retrieval as operationally ready, but do not retroactively claim the earlier 239-second failure cause or reuse the failed campaign. |
| 2026-09-20 | execution | After explicit authority for a wholly new campaign, created four new ledgers, refreshed the current guided brief, sealed bundle `56e75b0d…` as `fa7a327b…`, and approved attempt-1 critic scope `44979b92…`. Both token-count operations reached OpenAI and failed with `authentication_error` after 11,194 ms and 24,401 ms. No generation or judge request ran; the verified critic quorum was not met; later attempts stayed unused; both containers were removed. | Campaign-2 controller terminal, broker outcomes, runtime count records, cleanup records and ledgers | Treat campaign 2 as failed and non-retryable. Replace or correct the Keychain API key before preparing any other paid campaign. |
| 2026-09-20 | accounting | Campaign 2 attempt 1 conservatively retained its full 62,748-micro-USD allowance: both critic entries are `uncertain` and the unused judge allowance remains `held`. Its attempts 2–3 and launch ledger remain empty. Across both failed campaigns, 125,496 micro-USD is unresolved; actual provider billing is not reconciled. | Campaign-2 ledger `30c1f96a…`; prior ledger `8c2d8800…` | Do not release, reset, reuse or describe either retained amount as actual billed spend. |
| 2026-09-20 | verification | After Joshua replaced the Keychain password and separately authorized one minimal authentication check, `POST /responses/input_tokens` succeeded for `gpt-5.6-luna` with the synthetic text `credential authentication check`. It returned 9 input tokens in 7,678 ms, requested no generation or provider storage, used zero retries, and printed no secret data. | Private one-use credential-auth check; official OpenAI input-token API reference | Treat the replacement key as currently valid. This check does not revive either campaign or authorize another one. |
| 2026-09-20 | decision | Joshua Myers explicitly granted a single-use exception for one final, wholly new campaign after the replacement key passed the bounded authentication check. This does not authorize reuse of either failed seal, signing key, policy, reservation or ledger, and it does not create general retry authority. | User direction in the active task; qualification verification stopping rule | Create fresh private ledgers and an exact new offline bundle. Do not access the credential or provider until Joshua separately seals that bundle and authorizes its phase. If the final campaign fails, stop qualification. |
| 2026-09-20 | execution | Created four fresh ledgers, froze a 59,391-byte guided brief, sealed final bundle `eea43f90…` as `35da4356…`, and exactly authorized attempt-1 critics. Both OpenAI calls completed, but the canonical responses were 8,221 and 8,617 bytes against each request's sealed 4,000-byte response ceiling. Both model completions therefore failed locally, verified critic quorum was not met, and no judge, observation, later attempt or launch ran. | Final campaign controller terminal, broker responses, runtime records and model-completion receipts | Consume the single-use exception and stop qualification. Record the canonical-response budget mismatch as blocking; do not alter the sealed run or create a replacement. |
| 2026-09-20 | accounting | The final campaign settled its two critic entries at 4,875 and 5,047 micro-USD. The unused 20,916-micro-USD judge reservation remains held; attempt 1 reports 30,838 micro-USD charged/retained and 31,910 available. Attempts 2–3 and launch ledgers remain empty. With the earlier campaigns, 146,412 micro-USD is conservatively unresolved; actual provider billing is not reconciled. | Final ledger `63ec8aa…`, critic receipts and prior ledgers | Do not release or reuse the held entry. Treat 9,922 micro-USD as locally settled under the pricing policy, not as an invoice statement. |
| 2026-09-20 | cleanup | Both final-campaign critic containers have lifecycle result `removed`, and no matching remaining Docker container was found. The owning operator process exited, discarding its ephemeral signing-key reference. | Two lifecycle result records and filtered Docker inventory | Preserve private evidence; no campaign continuation or replacement is authorized. |
| 2026-09-20 | offline correction | Exact retained-shape inspection found 4,243/2,680 visible UTF-8 bytes inside the 8,617/8,221-byte canonical responses. Current code now independently seals an 8,000-byte answer cap and 64,000-byte canonical envelope while preserving the 4,096-token/spend ceiling; both historical shapes parse and validate offline. | `docs/REVIEW_RESPONSE_BUDGET_FIX_VERIFICATION.md`; focused/broad tests; private read-only replay | Keep every historical completion receipt and the terminal qualification result unchanged. This grants no campaign or provider authority. |

## Handoff

- Current state: all three sealed campaigns failed in attempt 1 and are non-retryable.
  The single-use final-campaign exception is consumed, every owning process exited,
  and no production launch authority exists. The final failure is a local mismatch
  between the 4,000-byte canonical-response ceiling and canonical responses that
  retained encrypted reasoning. Current code corrects that contract offline, but the
  sealed campaign and qualification remain terminally failed.
- Next smallest safe action: stop the live qualification. A separate offline change
  may correct and adversarially test the response-budget contract, but this work note
  grants no new provider run or campaign replacement.
- Required operational inputs: none for this closed qualification. Any future live
  qualification would require new owner direction and a newly reviewed plan; it cannot
  reuse these seals, ledgers, policies, reservations or process keys. Single-operator
  mode accepts self-approval risk and must never be described as independent human
  review.
- Checks already run: current GitHub refs and exact template/repository documents were
  inspected; focused host tests and 356 review tests pass; the clean full gate ran 2,446
  source tests with four skips and 89% coverage, verified exports, built both
  distributions, and passed 1,839 installed-wheel tests. The sandboxed run could not
  bind local sockets; the first unrestricted run exposed one transient fixture miss;
  the exact test and full unrestricted rerun passed. The rebuilt container suite passed.

## Close and promote

- Outcome and verification: schema-2 `single_operator` permits Joshua Myers to hold
  every human review role, and the offline implementation gates pass, but live
  qualification failed and production launch remains unauthorized.
- Durable fact promoted to `PROJECT_MEMORY.md`: schema-1 remains separated by default;
  schema-2 explicitly accepts the absence of independent human review.
- Decision promoted to ADR/documentation: `docs/adr/0005-single-operator-review-authorization.md`.
- Regression test, issue, or improvement-plan link: `tests/test_review_single_operator.py`,
  `docs/SINGLE_OPERATOR_REVIEW_HOST_REVIEW.md`, and the launch-contract review.
- Temporary artifacts removed: package smoke-test environments were automatically
  removed; normal `dist/` gate outputs remain ignored build artifacts.
