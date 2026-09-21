# Work Note: structured review output and quorum resilience

- Status: closed after post-live correction
- Owner: Joshua Myers
- Started (UTC): 2026-09-20
- Last updated (UTC): 2026-09-20
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

## Handoff

- Current state: the live retest is immutable and rejected; Q-008–Q-010 are corrected
  and verified offline for current/future runs. No credential or provider access is
  authorized.
- Next smallest safe action: review and commit this offline correction. Any later live
  work requires wholly fresh planning and authority.
- Blocker and required authority/input: none for offline work; any paid rerun would
  require wholly fresh authority and is outside this correction.
- Checks already run: focused schema and lifecycle tests, 164 broad review tests,
  Ruff, formatting, Pyright, 2,476 complete source tests with four skips and 89%
  coverage, 1,852 installed-wheel tests, and all container smoke tests.

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
