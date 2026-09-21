# Work Note: structured review output and quorum resilience

- Status: offline correction verified; awaiting immutable commit
- Owner: Joshua Myers
- Started (UTC): 2026-09-20
- Last updated (UTC): 2026-09-21
- Review or delete by: close after offline verification and promote durable facts
- Related issue/incident/ADR: live citation-observation retest quorum failure; ADR-0007

## Objective and completion evidence

- Intended outcome: reduce avoidable malformed critic responses by applying native
  strict JSON Schema to capable review models, and prove that a three-critic roster
  with a two-critic threshold can survive one invalid response without a retry.
- Required invariants: duplicate keys and all other malformed responses still fail
  closed locally; one exchange per role; no automatic repair or retry; prompt-only
  behavior remains available for models without structured-output capability; no
  provider call, credential access, or live authorization during implementation.
- Evidence that will show completion: exact canonical-to-OpenAI projection tests,
  schema-1/schema-2 critic and judge schema tests, malformed-output regressions, a
  three-critic/two-quorum controller regression, and the repository quality gates.

## Context retrieved

- `AGENTS.md`, `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`
- `docs/mos-eisley-plan.md` G2 and `docs/ROADMAP.md` G2
- `docs/PYTHON_ENGINEERING_GUIDE.md`
- `docs/AGENTIC_VERIFICATION_GUIDE.md`
- `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`
- `docs/MODEL_REVIEWER.md`, `docs/OPENAI_CONFORMANCE.md`
- OpenAI Structured Outputs guide and GPT-5.6 Luna model documentation
- `src/mos_eisley/providers/model_reviewer.py`
- `src/mos_eisley/providers/openai_responses.py`
- `src/mos_eisley/run/openai_conformance.py`

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-20 | observation | The live reviewer embeds a JSON Schema in instructions but omits the provider-native `text.format` constraint. The existing conformance path already sends a recursively strict schema. | model reviewer, OpenAI adapter, conformance builder | share the strict-schema policy and project it through the canonical request |
| 2026-09-20 | observation | The failed retest used exactly two critics for a threshold of two, so one malformed answer necessarily prevented quorum. Existing policy supports up to eight critics and does not require a retry. | retained retest record and `ReviewPolicy` | prove three critics with threshold two tolerate one invalid response |
| 2026-09-20 | implementation | Added one optional provider-neutral strict JSON Schema contract, capability-gated reviewer construction, exact Responses API projection, and one shared recursive normalizer. Local duplicate-aware decoding and the one-exchange rule are unchanged. | source plus 52 focused tests | run controller and broad gates |
| 2026-09-20 | correction | Strict OpenAI schemas require nullable properties to be present. Schema-2 instructions now require `source_unit: null` for spec/constraints citations instead of omission; schema 1 still excludes the field entirely. | exact recursive schema and prompt tests | complete offline gates |
| 2026-09-20 | verification | A deterministic three-critic run with one invalid response and two valid responses reaches the judge and returns `accept` without retry. | controller regression; 19 controller and 372 broad review tests pass | finish complete package/container gates |
| 2026-09-20 | verification | The unrestricted complete gate and rebuilt offline container gate pass. The sandbox-only complete run failed solely because 31 localhost fixtures could not bind sockets. | 2,472 source tests, four skips, 89% coverage, 1,851 installed-wheel tests, all container smoke tests | close offline work and require an exact committed revision before live preparation |
| 2026-09-20 | live review | The retest at `fe8659b` completed three strict-schema critics, judge, and in-process observation signing, but returned `reject`. It exposed conditional object hardening and missing one-invalid-of-three observation coverage; audit also found incomplete standalone replay retention. | `docs/LIVE_REVIEW_STRUCTURED_OUTPUT_QUORUM_RETEST_2026-09-20.md`; Q-008–Q-010 | reopen the offline correction at `57fe5cd`; preserve all live artifacts unchanged |
| 2026-09-20 | design | The lifecycle gap is semantic, not test-only: `make_review_probe_observation` rejects any critic error even when controller quorum legitimately reached the judge. A future harness also needs one verified, exclusive file containing configuration, policies, phase signatures, observation, result pin, ledger path, and lifecycle paths. | observation/acceptance source trace; Python, verification-loop, threat-model, and adversarial-review guides | allow quorum-tolerated critic errors, add full-path fault proof, and add a bounded standalone evidence bundle |
| 2026-09-20 | implementation | Hardened every object node, distinguished omitted `properties` from explicit malformed values, allowed only controller-verified quorum-tolerated critic errors past observation construction, and added a no-dispatch standalone replay bundle that verifies before exclusive private retention. | source, ADR-0007, model/probe/standalone evidence docs | run focused, complete package, container, and adversarial gates |
| 2026-09-20 | verification | The deterministic one-invalid-of-three path retains the failed slot, reaches the judge, signs/authenticates the four-exchange observation, writes a mode-0600 bundle, decodes and replays it from disk, and rejects tamper, duplicate, oversize, overwrite, public-parent, and runtime-directory cases. | focused test and 164-test review suite | complete repository gates |
| 2026-09-20 | verification | Clean `make check` passed Ruff, formatting, Pyright, 2,476 source tests with four skips, 89% coverage, export/build checks, and 1,852 installed-wheel tests. `make container` rebuilt image `sha256:2cf85409…` and passed every offline smoke suite. An earlier unrestricted run had one transient missing runtime-start fixture; its exact test and the complete rerun passed. | complete gate output and exact reproduction | close Q-008–Q-010 offline; preserve the historical live reject |
| 2026-09-20 | pre-live correction | Fresh retest preflight found that `campaign_reviewer` omitted the retained 8,000-byte visible-text limit and reconstructed requests with the 4,000-byte default. No credential, reservation, container, or provider request occurred. The reconstruction now passes the exact launch limit, fixtures declare their actual preview limit, and configuration substitution has a direct regression. | 29 focused campaign/runtime-evidence tests | run the complete gate before creating a new immutable retest revision |
| 2026-09-20 | verification | The post-correction unrestricted `make check` passed Ruff, formatting, Pyright, 2,477 source tests with four skips, 89% coverage, export verification, sdist/wheel builds, and 1,853 installed-wheel tests. The sandbox-only attempt was stopped after localhost fixtures confirmed socket binding was denied. | complete gate output | review and commit the correction, then rebuild the production image from the immutable revision |
| 2026-09-20 | live failure | In the fresh campaign, all three critics successfully counted 18,609–18,623 input tokens, then all three generations were cancelled at the same broker deadline. No judge ran; the controller failed; all containers were removed; three critic reservations are uncertain and the judge allowance remains held. | immutable campaign-7 runtime records, broker outcomes, controller terminal, cleanup receipts, and ledger | preserve the terminal campaign; diagnose and correct only offline |
| 2026-09-20 | diagnosis | `ReviewPolicy` permits a bounded window up to 300 seconds, but the review controller, broker claim, worker exchange, and observation builder collapsed the whole count-plus-generation lifecycle into one 60-second interval. The live transport already enforces a separate 60-second maximum for each provider operation. | controller/broker/duplex/probe/runtime-evidence source trace and exact live timestamps | separate authority presentation, role lifecycle, and provider-operation deadlines without adding retry authority |
| 2026-09-20 | implementation | The bearer claim remains maximum 60 seconds and one use. A separate maximum-300-second exchange clock now begins at broker construction; review roles derive at most two operation windows from policy and remaining controller time. Count and generation each retain their own maximum-60-second live and observation limit, while the async container guardian remains independently bounded at exchange plus five seconds. | source and focused broker/controller/observation/isolation/watchdog regressions | run static checks, broad review tests, then the complete offline gate |
| 2026-09-21 | verification | V-007 passes 146 focused lifecycle tests, 376 broad review tests, Ruff, formatting, Pyright, 2,481 source tests with four skips and 89% coverage, export/build checks, and a clean focused rerun of all 1,855 installed-wheel tests. The first composite smoke stage ended non-cleanly after the source pass; the fully captured focused rerun contains no failures. | unrestricted component-gate output | leave the verified correction uncommitted until explicitly requested |

## Handoff

- Current state: every prior live campaign remains immutable and terminal. The latest
  campaign failed at the conflated broker deadline after successful counts. The
  deadline correction is implemented offline; no credential or provider access is
  authorized by this work.
- Next smallest safe action: review and, only after a later explicit commit request,
  create an immutable revision. Any rebuild or live campaign remains separate work
  and authority.
- Blocker and required authority/input: none for offline work; any paid rerun would
  require wholly fresh authority and is outside this correction.
- Checks already run: prior schema, quorum, output-limit, complete repository, and
  container gates remain recorded above. For V-007, 146 focused lifecycle tests,
  376 broad review tests, Ruff, formatting, Pyright, 2,481 complete source tests with
  four skips and 89% coverage, export/build checks, and 1,855 installed-wheel tests
  pass.

## Close and promote

- Outcome and verification: provider-native strict output is capability gated, every
  object schema fails closed, and deterministic two-of-three quorum survives one
  malformed critic through signed observation and retained offline replay without
  retry; all offline gates pass.
- Durable fact promoted to `PROJECT_MEMORY.md`: the structured-output boundary,
  full-lifecycle quorum behavior, and future standalone retention contract.
- Decision promoted to ADR/documentation: accepted ADR-0007,
  `docs/MODEL_REVIEWER.md`, and `docs/STANDALONE_REVIEW_EVIDENCE.md`.
- Regression test, issue, or improvement-plan link: reviewer/provider/protocol and
  controller regressions plus the verification record.
- Temporary artifacts removed: package smoke environments were automatically removed;
  normal ignored build and coverage artifacts remain.
