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
| 14 | Separate offline citation-fidelity correction | The final finding quoted exact multiline postimage code from one hunk, but unified-diff `+` markers made it absent from the raw patch | Raw-only citation validation rejected supported evidence before quorum | Add opt-in schema-2 content-bound raw/before/after hunk units; keep schema 1 byte-compatible and raw-only; never rewrite the failed receipts | Retained-shape, stale/invented/normalized/cross-hunk, full offline, package and container gates pass; no live authority follows |
| 15 | Separately authorized one-attempt citation retest | Fresh schema-2 requests each carried 54 units; both critics completed with zero findings and the judge returned `accept` | Post-result observation construction rejected one runtime/authorization comparison; phase signatures were process-local and no signed observation was produced | Preserve the freshly reconstructed result and terminal accounting, but grant no positive live-citation claim, qualification credit or retry | Result `f1e59022…` reconstructs; controller is finished; 13,161 micro-USD settled with zero unresolved entries; three containers removed |
| 16 | Separate offline citation/observation completion | The failed construction flattened three exchanges against two phase authorizations, while retained-path citation coverage exercised only an empty critique | Centralize semantic phase mapping; add a deterministic positive multiline postimage citation through broker, judge and retained reconstruction | Correct current orchestration without changing the immutable retest or creating an attestation, retry or live authority | Positive retained citation, two-critic mapping, malformed-shape and broad review regressions pass; `make check` passes 2,467 source and 1,848 installed-wheel tests with 89% coverage, and `make container` passes; the historical signed observation remains absent |
| 17 | Separately authorized observation-fix retest | Fresh commit `e34c8c8` requests each carried 34 schema-2 citation units; one critic returned an empty valid critique and the other duplicated `impact` | Strict decoding correctly rejects the malformed response, leaving only one valid critic and no quorum | Fail closed before judge/observation, retain accounting and cleanup, and consume the one-attempt authority without retry | Both critic containers removed; 7,867 micro-USD settled; 20,916-micro-USD judge reservation held; no retained result or signed observation; live outcome is inconclusive for both fixes |
| 18 | Separate offline structured-output and quorum correction | Official Responses API schema support, the retained duplicate-key response, and a three-critic fault replay | Prompt-only enforcement made malformed JSON avoidable, while the exact two-critic roster had no spare capacity | Apply capability-gated native strict schema without weakening local decoding, and use three separately admitted critics with threshold two for a future retest | One invalid critic plus two valid critics reaches an `accept` judge result without retry; `make check` passes 2,472 source and 1,851 installed-wheel tests with 89% coverage, and `make container` passes; no live authority follows |
| 19 | Separately authorized structured-output/quorum retest | Three native strict-schema critics, threshold two, conditional strict-schema judge, and corrected four-exchange observation construction at `fe8659b` | Every role completed and the observation was signed, but the judge upheld a generic object-normalization gap and missing deterministic observation coverage in the quorum regression; the standalone harness also omitted durable policy/phase-signature inputs for later observation authentication replay | Retain the successful in-process runtime evidence and `reject` verdict with its replay limitation; correct both code/test findings offline before any acceptance claim | Result `29f1faae…`; signed observation `11ae0b03…`; 17,191 micro-USD settled; zero unresolved entries; four containers removed; no secret-shaped retained text |
| 20 | Offline post-live correction | Q-008–Q-010, production Python/verification/threat/review guides, and immutable live evidence | No new blocking offline finding; one unrelated runtime-start fixture race passed on exact reproduction and the clean complete rerun | Normalize omitted/malformed object properties fail-closed, carry quorum-tolerated failures through signed observation, and verify before exclusive standalone-bundle retention | 164 focused review tests, 2,476 source tests, 1,852 installed-wheel tests, 89% coverage, and rebuilt container smoke suite pass; no live authority follows |
| 21 | Separately authorized deadline-correction retest | Fresh `b3357aa` guidance, ledger, process key and exact approvals; three strict-schema critics with threshold two; one conditional judge; complete standalone retention | One critic's exact quote was absent from its declared source unit and was retained as `invalid_evidence`; two valid empty critiques preserved quorum, the judge returned `accept`, and post-result authentication replayed successfully | Accept as positive G2 live-path and V-007 evidence while preserving the invalid slot and every historical campaign; do not treat one standalone attempt as the three-slot qualification campaign | Result `00904170…`; signed observation `ad040926…`; standalone evidence `ebf31e12…`; 24,032 micro-USD settled; zero unresolved entries; four containers removed |
| 22 | Corrected exact-artifact production qualification | Commit `3b32f14`, image `sha256:3f67fa22…`, bundle `62f23f3f…`, seal `ab71fca3…`, three exact phase/local/observation ceremonies, and fresh retained-evidence reconstruction | All three fixed slots qualified and returned `accept` with no findings or required changes. Slot 2 retained one `invalid_evidence` critic but preserved threshold-two quorum without retry. | Close the three-slot qualification gap and mark the G2 live read-only capability qualified; retain the separate launch-admission boundary | Evidence `fde095a1…`; result `0a276558…`; 32,226 micro-USD settled; zero unresolved entries; all 12 workers removed |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| Q-001 | `REVIEW_LAUNCH_ADMISSION.md`: a production launch requires current campaign custody, live assessment and an exact signed launch decision | Qualification evidence alone cannot authorize a target call | Closed for G2 qualification; blocking for launch | The `3b32f14` campaign now supplies retained production custody and live assessment, but no launch decision or launch ledger was created and the campaign window expired | A new current launch ceremony with a separate ledger and exact decision | Joshua Myers |
| Q-002 | No public live-launch CLI by design | A casual command cannot safely begin the review | High | Accepted; use the owning library ceremony until a separately reviewed product boundary exists | Exact admitted owning flow and retained evidence | Josh Myers |
| Q-003 | The owner requires Joshua Myers to hold every human role | No independent human can detect Joshua's mistaken or malicious self-approval | Accepted high risk | ADR-0005 explicitly changes the contract; schema 2 requires one shared signer and a signed self-review-risk assertion, while schema 1 remains separated | Positive full-path test, mixed-mode rejection, and no independence assertion in schema-2 decision | Joshua Myers |
| Q-004 | Final campaign critic responses canonicalized to 8,221 and 8,617 bytes while each sealed request allowed only 4,000 response bytes | Valid provider responses could not become verified critic evidence, so the sealed campaign could not reach quorum | Blocking historical campaign finding; code defect corrected offline | Accepted as the immutable terminal final-campaign failure. The corrected contract independently seals 8,000 text bytes and a 64,000-byte envelope, but cannot change or revive dispatched evidence. | Exact retained-shape replay and synthetic boundaries pass; no new live campaign is authorized | Josh Myers |
| Q-005 | Final-campaign evidence used an exact multiline postimage quote that is not an exact substring of raw unified-diff syntax | Supported evidence would still fail local validation after the response-budget correction | Blocking historical campaign finding; code defect corrected offline | Accepted as part of the immutable terminal campaign outcome. Schema 2 binds exact quotes to deterministic raw/before/after hunk units; schema 1 and retained artifacts are unchanged. | Retained-shape and adversarial citation regressions plus full offline/container gates pass; no new live campaign is authorized | Joshua Myers |
| Q-006 | The standalone citation retest retained an `accept` result but failed while constructing its post-result observer exchange, after its ephemeral phase signatures had ceased to be recoverable | No signed observation exists, so the retest cannot receive qualification credit despite a complete controller result | High historical evidence gap; code defect corrected offline | Accept as terminal for this one-attempt retest. Current code maps all critic exchanges to the critic-phase authorization and the judge to the judge-phase authorization, but it cannot recreate a lost signature or historical attestation. | Two-critic and malformed-shape regressions pass; historical signed observation remains absent | Joshua Myers |
| Q-007 | The observation-fix retest used two critics for threshold two and one provider answer duplicated `impact` | One malformed response prevented quorum before the judge and observation paths | High historical resilience gap; corrected offline | Preserve strict duplicate rejection. Capable models now receive native strict JSON Schema, and any future exact retest should separately admit three critics for threshold two without retry. | Capability/schema projection tests and one-invalid-of-three controller regression pass; live proof remains absent | Joshua Myers |
| Q-008 | The generic strict-schema normalizer only hardened object nodes whose `properties` member was already a dictionary | An arbitrary object-shaped schema could escape recursive normalization or fail later at the provider boundary | Blocking live finding; corrected offline | Missing properties now become an explicit empty strict object; present non-object values reject recursively without weakening local decoding | Direct nested schema regressions plus package/container gates | Joshua Myers |
| Q-009 | The original three-critic fault regression stopped after the judge and did not construct and authenticate a signed post-result observation | The complete claimed lifecycle lacked deterministic one-invalid-of-three observation coverage | High live finding; corrected offline | A failed critic remains visible but no longer invalidates an otherwise verified quorum/judge result; the regression now signs, authenticates, tampers, and replays the observation | Focused full-lifecycle regression plus package/container gates | Joshua Myers |
| Q-010 | The standalone retest retained the signed observation but not the authority policy, observation policy, or signed phase authorizations required for later `authenticate_review_probe` replay | The historical in-process construction/signing success cannot become independently replayable authentication evidence | High historical evidence gap; future harness corrected offline | Preserve the historical limitation; a new bounded bundle verifies before exclusive mode-0600 retention and contains every serialized authentication input plus exact external-artifact paths | Disk-only decode/authentication, duplicate/size/tamper/permission/placement regressions, and container gate | Joshua Myers |
| Q-011 | The accepted `b3357aa` retest was one standalone attempt rather than a sealed three-slot submission | The standalone evidence could not close formal qualification | **Closed:** the wholly fresh `3b32f14` campaign supplied three distinct qualifying slots and accepted reconstruction | Preserve the historical standalone result separately; use the new campaign only for its exact qualification claim | Evidence `fde095a1…`; result `0a276558…`; three authenticated observations | Joshua Myers |

## Exit

- Stop reason: passed the G2 qualification rubric after the wholly fresh `3b32f14`
  campaign. Historical failed and rejected campaigns remain immutable and separate.
- Rubric result and blocking findings: Q-011 is closed by three qualifying committed
  slots. Q-003 remains an explicitly accepted single-operator risk. Q-001 is closed
  for qualification but remains blocking for any target launch: no launch decision or
  separate launch ledger exists, and the campaign is not retained as launch
  authority. Q-004
  through Q-010 remain accurate historical findings and corrections; none is rewritten
  by the successful campaign.
- Full quality-gate command and result: the documentation-only reassessment ran
  `make check`; Ruff and Pyright passed. The source suite ran 2,431 tests and reached
  only 31 expected MCP HTTP/OAuth loopback-bind errors under the restricted sandbox,
  with four skips. The isolated MCP family then passed all 68 tests with four skips
  when granted localhost permission. No source or production image changed.
- Production-like replay/fault/rollback evidence, if applicable: the `3b32f14`
  campaign is live production-like evidence for the fixed three-slot path. It includes
  one tolerated invalid critic, three exact signed observations, accepted fresh
  reconstruction, zero unresolved entries and 12 removed workers. It is not a
  production launch.
- Remaining uncertainty, owners, and dates: the accepted campaign settled 32,226
  micro-USD locally with zero unresolved ledger entries. Actual provider billing is
  not reconciled, provider authorship is not claimed, and default provider retention
  remains an accepted risk rather than a ZDR claim. The campaign window is expired;
  no replacement qualification campaign is needed or authorized by this record.
  The accepted `3b32f14` campaign settled 32,226 micro-USD with zero unresolved
  entries under image
  `sha256:3f67fa22ae6ede838269a292ad507e6441d6a5d084fbf5a2c6077ea125be8653`
  and OpenAI SDK `3.11.0`. Historical unresolved accounting remains unchanged.
- Human/domain approval, if required: Joshua Myers explicitly approved single-operator
  governance and the USD 5.00 aggregate ceiling on 2026-09-19
- Durable facts promoted to tests, ADRs, docs, or `PROJECT_MEMORY.md`: G2
  qualification completion, the exact accepted campaign, the retained launch
  boundary, single-operator risk and prior correction history.

## Diagnostic resource accounting (optional)

- Iterations and elapsed time: one source-survey pass, two contract-review passes,
  one host/adversarial-review pass, three sealed formal campaigns, one no-network
  Keychain diagnostic, one bounded replacement-key authentication check, and five
  separately authorized standalone attempts including the V-007 timeout precursor
  and accepted deadline retest
- Aggregate tokens/cost, when policy permits: the final campaign used 29,313 input
  tokens, including 29,307 cache-write tokens, and 2,161 output tokens. Its two critic
  charges settled locally at 9,922 micro-USD; 146,412 micro-USD remains conservatively
  unresolved across the original campaigns. The accepted standalone retest used
  84,439 input, 84,427 cache-write and 2,434 output tokens and settled 24,032
  micro-USD with zero unresolved entries. None of these figures is an invoice
  reconciliation.
- Accepted versus rejected findings: Q-011 is closed; Q-001 remains only as a launch
  gate. Q-004 through Q-010 retain their historical dispositions; Q-003
  single-operator governance risk and the documented memory-zeroization limitation
  remain accepted.
- Escaped defects or regressions discovered later: unknown
