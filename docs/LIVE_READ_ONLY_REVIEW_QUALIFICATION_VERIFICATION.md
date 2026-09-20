# Agentic Verification Loop: live read-only review qualification

## Objective and authority

- Requirement, issue, or project-brief link: `docs/ROADMAP.md` G2,
  `docs/REVIEW_CAMPAIGN_CEREMONY.md`, and `docs/REVIEW_LAUNCH_ADMISSION.md`
- User journey or operational outcome: qualify and admit one exact
  bounded critic/judge review without turning fixtures, local signatures, or prior
  calibration evidence into broader provider or routing authority.
- Invariants and non-goals: three precommitted fixed attempts; phase/local approvals;
  one consistent Joshua Myers signer with explicit self-review risk acceptance; exact current
  guidance/runtime/spending; complete cleanup and evidence; no retries, automatic
  release, scoring, provider-authorship claim, public CLI, or global activation.
- Risk class: high-risk
- Implementation owner: Josh Myers
- Verifier or accountable approver, if required: Joshua Myers as the single accountable
  operator under ADR-0005; no independent human approval is claimed
- Commit/revision and starting worktree state: GitHub `main`
  `fa0faafb6f29421e46429001be3932b614f392f0`; guidance branch created from that ref

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Exact qualified review profile | Blocking | Fresh campaign review and launch-conformance reconstruction | All three slots qualify and launch role/quorum/runtime scope matches exactly |
| Correctness and failure handling | Blocking | Fixed-slot failures, timeout/cancellation cleanup, no-retry receipts, ledger and crash inspection | Missing/failed/uncertain evidence stops later work and never becomes success |
| Security/privacy/data integrity | Blocking | Single enrolled key/custody record, explicit self-review acknowledgement, signed decisions, private permissions, exact hashes, secret/data review | Credential and prompt access occurs only after all current gates; no key/bearer/raw error is retained |
| Financial authority | Blocking | Dedicated ledgers, conservative full allowances, exact settlement/uncertain state, separate launch ledger | No unreserved call, double reservation, automatic release, or campaign-ledger reuse |
| Maintainability/operability | High | Current policies, immutable SDK/image, bounded deadlines, recovery and cleanup evidence | Every operation is inspectable and revocable before the next provider boundary |

## Budget and stopping rules

- Maximum iterations: three fixed conformance attempts plus one exact launch decision;
  failed or missing fixed slots are not replaced within a campaign. After the two
  failed campaigns and a successful replacement-key authentication check, Joshua
  Myers granted one single-use exception for one final, wholly new campaign. This is
  not general retry authority: neither prior seal or ledger may be reused, and failure
  of the final campaign ends the qualification.
- Elapsed-time or review window: bounded by the sealed campaign, phase, observation,
  and launch-policy expiries
- Compute/cost ceiling, if material: owner-approved aggregate maximum USD 5.00
  (`5,000,000` micro-USD) across qualification and launch; the exact reviewed bundle
  and separate launch envelope must fit within it
- Pass rule: all blocking rubric rows pass through fresh reconstruction and the
  consistent schema-2 Joshua Myers signature; production launch remains unavailable
  without the final decision
- Diminishing-return rule: the fixed campaign ends after its three slots; no additional
  attempts are authorized to improve the narrative
- Escalation/domain-input trigger: evidence is ambiguous, a ledger is nonempty/blocked,
  policy expires, runtime differs,
  or remote receipt/invoice state is uncertain
- Rollback or abort condition: any substituted input, reused path/ledger, credential
  access before current gates, missing cleanup, duplicate dispatch, or broader authority
  claim

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Template and repository survey only | Current upstream template and GitHub `main` state | Blocking external custody and paid-run authority are absent | Stop before credential/spend/provider actions | Documentation/source inspection only |
| 2 | Explicit schema-2 single-operator contract | ADR-0005, threat review, schema/mode validators, positive full-path and mixed-mode tests | Independent-human-review control is intentionally removed; other gates remain | Record self-review risk, preserve schema-1 default, reject mixed modes | Focused single-operator tests pass |
| 3 | Immutable runtime preflight | Pinned Dockerfile build, image inspection and complete offline container smoke suite | Runtime is ready; real signing identity, credential custody, account data-retention review and exact transfer payload remain absent | Pin image `sha256:8f900b1597447922049b91f32d9f00709eeaa61be7121663961874bde811f8be` with host OpenAI SDK `3.11.0`; stop before ledger creation, secret access or dispatch | `make container` passed |
| 4 | One-process single-operator host | Python engineering and adversarial-review guides, threat-model update, native-Keychain precedent, phase/observation/launch signing contracts and credential-order tests | Inert library host is complete; production Keychain item, account retention review and exact transfer payload remain absent | Generate one ephemeral Ed25519 key in the owning process, read the named Keychain item only at admitted provider edges, reject signer substitution, redact failures and retain the no-public-live-CLI boundary | 9 focused tests and 356 review tests passed; `make check` and rebuilt `make container` passed |
| 5 | Account-retention decision and transfer inventory | Official OpenAI data-controls documentation, real Keychain metadata, exact request projection and spend normalization | No explicit ZDR/MAM setting was visible; default abuse-monitoring retention remains even with application-state storage disabled | Joshua accepted default retention; require `store: false`, foreground text-only requests and the exact field/content inventory in `LIVE_READ_ONLY_REVIEW_TRANSFER_REVIEW.md` | Source/test inspection only; no credential read, reservation or provider call |
| 6 | Dedicated spending scopes | Current official Luna pricing, schema-2 cache-write accounting, four distinct owner-private ledgers | No production guidance store, prepared brief or launch configuration exists; time-limited policies would be premature | Create three attempt ledgers plus one separate launch ledger at the exact conservative 62,748 micro-USD role-envelope total; stop before policies or reservations | Four status checks show empty, unblocked 62,748-micro-USD ledgers; aggregate USD 0.250992 |
| 7 | First sealed live campaign | Exact guided brief, three distinct previews, schema-2 Joshua Myers authority/observation commitments, bundle `98c004b7…`, seal `4c41d077…`, and explicit attempt-1 critic scope/local approval | Attempt 1 failed before judge preparation. No runtime SDK-operation record or provider response exists; one critic is `uncertain`, the other critic and judge allowance remain `held`. Both containers were removed; attempts 2–3 were never started. A 239-second broker failure is consistent with Keychain access exceeding the 120-second phase authorization, but this is not proven. | Fail closed, destroy the process-local key, retain all unresolved accounting, and make no retry or later-slot substitution | Controller terminal is `failed`; attempt-1 ledger retains 62,748 micro-USD across three unresolved entries; attempts 2–3 and launch ledger remain empty; Docker has no matching remaining container |
| 8 | No-network Keychain diagnostic | Separate explicit authority and the production Keychain loader only | Retrieval now succeeds, but this cannot identify the original delay or authorize provider use | Retain the original failure classification; require a wholly new campaign and exact approvals | Loader completed in 10,695 ms with no network call and no secret, length or digest output |
| 9 | Second sealed live campaign | New ledgers, refreshed 57,223-byte brief with exact failure evidence, current guidance, bundle `56e75b0d…`, seal `fa7a327b…`, and explicit attempt-1 critic scope/local approval | Both OpenAI token-count operations returned `authentication_error`; no critic generation or judge request ran and verified critic quorum was not met | Fail closed, destroy the process-local key, retain unresolved accounting, and require credential correction rather than retry | Both critic outcomes are authentication failures; two containers were removed; attempt-1 ledger retains 62,748 micro-USD unresolved; later ledgers are empty; Docker has no matching remaining container |
| 10 | Replacement-key authentication check | Corrected Keychain item and separate authority for exactly one synthetic input-token count | The prior authentication blocker is cleared, but no campaign authority follows | Preserve both failed campaigns; require a new commitment before any review content | `gpt-5.6-luna` counted 9 tokens in 7,678 ms; no generation, storage request, retry or secret output |
| 11 | Single-use final-campaign exception | Joshua Myers explicitly granted an exception after the replacement key passed the bounded authentication check | A third campaign would otherwise violate the no-replacement stopping rule | Permit exactly one fresh campaign with new ledgers, commitments, bundle and seal; preserve both prior campaigns, and stop qualification if the final campaign fails | Authority recorded before creating the new ledgers or any credential/provider access; no prior artifact is reusable |
| 12 | Final sealed live campaign | Fresh ledgers, 59,391-byte brief, bundle `eea43f90…`, seal `35da4356…`, exact critic scope `c79c3e0e…`, local approval `c57090f0…`, pinned image and SDK | Both OpenAI critic responses completed, but their canonical responses were 8,221 and 8,617 bytes against the sealed 4,000-byte response ceiling because retained encrypted reasoning is included. Both local completions failed, verified critic quorum was not met, and no judge prompt or observation followed. | Fail closed and consume the exception. Do not run attempts 2–3, launch, or any replacement campaign; retain the response-budget mismatch as a blocking defect. | Critic charges settled at 4,875 and 5,047 micro-USD; the 20,916-micro-USD judge reservation remains held; both containers are recorded removed; later ledgers remain empty |
| 13 | Separate offline response-budget correction | Exact retained shapes measured 4,243/2,680 visible UTF-8 bytes inside 8,617/8,221-byte canonical responses; synthetic exact-boundary and opaque-reasoning cases | The original 4,000-byte answer assumption was also insufficient for one valid response | Bind an 8,000-byte text cap and separate 64,000-byte canonical envelope while retaining the 4,096-token/spend ceiling; never rewrite the failed receipts | Both retained shapes parse and validate offline under the corrected profile; broad regression set passes; the terminal campaign remains failed and grants no live authority |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| Q-001 | `REVIEW_LAUNCH_ADMISSION.md`: production custody, live assessment, and decision remain outstanding | Local fixture evidence cannot authorize live review | Blocking | Accepted; requires real operational inputs, not a code workaround | Retained and signed campaign and launch evidence | Josh Myers |
| Q-002 | No public live-launch CLI by design | A casual command cannot safely begin the review | High | Accepted; use the owning library ceremony until a separately reviewed product boundary exists | Exact admitted owning flow and retained evidence | Josh Myers |
| Q-003 | The owner requires Joshua Myers to hold every human role | No independent human can detect Joshua's mistaken or malicious self-approval | Accepted high risk | ADR-0005 explicitly changes the contract; schema 2 requires one shared signer and a signed self-review-risk assertion, while schema 1 remains separated | Positive full-path test, mixed-mode rejection, and no independence assertion in schema-2 decision | Joshua Myers |
| Q-004 | Final campaign critic responses canonicalized to 8,221 and 8,617 bytes while each sealed request allowed only 4,000 response bytes | Valid provider responses could not become verified critic evidence, so the sealed campaign could not reach quorum | Blocking historical campaign finding; code defect corrected offline | Accepted as the immutable terminal final-campaign failure. The corrected contract independently seals 8,000 text bytes and a 64,000-byte envelope, but cannot change or revive dispatched evidence. | Exact retained-shape replay and synthetic boundaries pass; no new live campaign is authorized | Josh Myers |

## Exit

- Stop reason: the final-campaign exception was consumed and the final campaign failed
  closed in attempt 1 because both canonical critic responses exceeded the sealed
  response-byte ceiling. Verified critic quorum was not met; the judge, observation,
  attempts 2–3 and launch were not started. All three campaign process-local signing
  keys are gone, none of their artifacts may be reused, and no replacement campaign
  is authorized.
- Rubric result and blocking findings: Q-003 remains accepted by the accountable owner;
  Q-001 remains open. The campaign has zero qualifying attempts and establishes no
  live conformance or production-launch authority. Q-004 is corrected in current code
  but remains the immutable failure classification for the sealed final campaign.
- Full quality-gate command and result: `make check` passed on the clean rerun: Ruff
  and Pyright passed; 2,446 source tests passed with four skips and 89% coverage;
  export verification, sdist/wheel builds, and 1,839 installed-wheel tests passed. The
  first unrestricted run had one transient missing fixture timestamp after 2,446 tests;
  the exact test and complete rerun passed.
- Production-like replay/fault/rollback evidence, if applicable: existing synthetic and
  Docker coverage is documented in the feature guides; it is not production evidence
- Remaining uncertainty, owners, and dates: final-campaign critic charges settled
  locally at 9,922 micro-USD total; its unused 20,916-micro-USD judge reservation and
  the two earlier 62,748-micro-USD attempt allowances leave 146,412 micro-USD
  conservatively unresolved. Actual provider billing and the minimal token-count check
  are not reconciled. The final campaign failed and no replacement is authorized.
  Default retention is an accepted risk, not a ZDR claim.
  The current
  final campaign used worker image
  `sha256:42aac38dc474addd64eec136fc20a33a84fee7534533bbc7645f74be37860f4c`
  with OpenAI SDK `3.11.0`.
- Human/domain approval, if required: Joshua Myers explicitly approved single-operator
  governance and the USD 5.00 aggregate ceiling on 2026-09-19
- Durable facts promoted to tests, ADRs, docs, or `PROJECT_MEMORY.md`: latest delivery
  state, single-operator host boundary and template-use rule recorded in
  `PROJECT_MEMORY.md`

## Diagnostic resource accounting (optional)

- Iterations and elapsed time: one source-survey pass, two contract-review passes,
  one host/adversarial-review pass, three sealed campaigns, one no-network Keychain
  diagnostic and one bounded replacement-key authentication check
- Aggregate tokens/cost, when policy permits: the final campaign used 29,313 input
  tokens, including 29,307 cache-write tokens, and 2,161 output tokens. Its two critic
  charges settled locally at 9,922 micro-USD; 146,412 micro-USD remains conservatively
  unresolved across all campaigns, and neither amount is an invoice reconciliation.
- Accepted versus rejected findings: Q-001 launch qualification remains blocking;
  Q-004 canonical response budgeting is corrected offline but remains the historical
  terminal campaign finding; Q-003 single-operator governance risk and the documented
  memory-zeroization limitation are accepted
- Escaped defects or regressions discovered later: unknown
