# Agentic Verification Loop: repeated cleanup-scope claim reassessment

## Objective and authority

- Requirement: reassess the one cleanup-scope claim repeated and upheld across the fresh three-slot campaign at commit `24704aa6fc4aadba2dcec79b8f83bae44f01a02d`.
- Operational outcome: distinguish a reachable controller defect from a correlated misunderstanding of the schema-2/formal-scope construction invariant before any further live call or code change.
- Invariants and non-goals: standard scope must remain schema 1 with its held allowance preserved; formal scope must remain schema 2 with exact unused-source retirement; inspection must reject false standard cleanup attribution; no campaign evidence is rewritten and no new live, retry, launch, ledger-repair or qualification authority is inferred.
- Risk class: material authorization and financial-accounting investigation.
- Implementation owner and accountable approver: Joshua Myers.
- Commit/revision and starting state: clean `24704aa6fc4aadba2dcec79b8f83bae44f01a02d`; production image `sha256:57f1d71b1ca14d5bf077262fae86b258ea4bbb07a2fba20c52ba3e07a3281200`.
- Selected guides: `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`, and `templates/WORK_NOTE.md`.

## Campaign evidence under review

The sealed campaign's evidence reconstruction accepted all three authenticated slots,
settled 71,309 micro-USD locally, removed all 12 workers, and retained zero unresolved
ledger entries. All three underlying code-review verdicts were `reject`. Each slot had
three critics and one judge repeat the same alleged reachability path: a caller could
construct a schema-2 controller with a non-formal preparation scope and cause unused
judge-allowance retirement.

- Seal: `a1d86217f991f6c5e0cb0292596215ff0340cc1f6610bd944c8517ca3d25a2e4`
- Evidence: `8a41edd6c63931e930dbd35d5829e31e9909353378416ee71558dc4d2f141a25`
- Acceptance: `711d1e865c89f8cc7b1aa10dbfce0017db8bf966e4da2dae3d73ccb6e00feb18`
- Result hashes: `3d20cdc1f86560ec910b44f41ec0d7320be0aaec3f951d7fdb24b84072c5ab3f`, `e91ba8ae9d4669f068a331edc3fc3cee62ffe32f155bbba2643abbb7928df545`, and `0f8074f490bde7daea1805dd74a1ea662c4e2cf4f15ae4d1ed94dc63dc37dc14`.

Campaign acceptance authenticates evidence collection; it does not make the repeated
source interpretation correct or change the retained `reject` verdicts.

## Rubric

| Dimension | Severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Public reachability | blocking | Constructor signature, all source construction sites, runtime composition | No supported path injects schema 2 into a standard-scope controller |
| Contract integrity | blocking | Frozen envelope/authorization contracts and preview validation | Schema 2 is equivalent to exact `formal_campaign` scope at the controller boundary |
| Live-path binding | blocking | Conformance-probe construction and run gate | A formal live preparation cannot execute without a sealed campaign binding |
| Standard/formal behavior | blocking | Focused controller and inspector regressions | Standard holds/schema 1 and formal retirement/schema 2 remain exact |
| Threat-boundary honesty | material | Threat model and privileged-mutation analysis | Trusted in-process mutation is stated rather than misrepresented as an untrusted input path |

## Source trace

1. `PreparedReviewCall` accepts only the literal preparation scopes `standard` and
   `formal_campaign`. `PreparedReviewEnvelope` derives the deferred judge scope from
   the first critic, and immutable `ReviewSpendingEnvelope` validation requires every
   critic and judge scope to match.
2. `BrokeredReviewController.__init__` accepts an envelope, reviewer, policy and time
   limit. It does not accept a `ControllerAuthorization`. It derives schema 2 and the
   exact 600-second grace if and only if the frozen envelope judge scope is
   `formal_campaign`; otherwise it derives schema 1 and zero grace.
3. `ControllerCriticPreview` independently rejects any mismatch between authorization
   schema and envelope scope. `ControllerStart` also requires its schema to match the
   derived authorization.
4. Both production source construction sites—launch preview and conformance probe—use
   that constructor. The conformance probe additionally requires one coherent scope,
   requires formal scope for a sealed campaign, and refuses to run an unbound formal
   preparation.
5. `_terminal` checks the derived schema-2 discriminator only after the controller has
   reserved and taken ownership of that exact envelope. At this internal boundary,
   schema 2 is already a validated representation of formal scope; it is not an
   independently caller-selected input.
6. Offline inspection separately rejects a cleanup marker unless the retained start
   authorization is schema 2 and the exact envelope judge scope is `formal_campaign`.

The campaign's proposed counterexample conflated the ability to instantiate a standalone
`ControllerAuthorization` record with the ability to inject it into a controller. The
latter path does not exist in the supported API. A hostile same-process caller can write
private Python attributes or call ledger primitives directly, but the design explicitly
treats the composition root and process-local host as trusted. Adding the same redundant
scope comparison in `_terminal` would not create a security boundary against arbitrary
trusted-process mutation and would not prove that a campaign was sealed.

## Verification passes

| # | Evidence added | Result | Decision |
|---:|---|---|---|
| 1 | Exact campaign claim/citation normalization | Nine upheld findings collapse to one reachability claim and one cited terminal branch | Correlation is not independent confirmation |
| 2 | Constructor and dependency trace across all source call sites | Controller authorization is derived, not injected; envelopes are scope-coherent and immutable | Alleged schema-2/non-formal public state is unreachable |
| 3 | Executable public-API probe | Standard produced schema 1/`standard`; formal produced schema 2/`formal_campaign`; assigning the public authorization property raised `AttributeError` | Counterexample failed through supported APIs |
| 4 | Five focused controller/inspection regressions | All five passed in 0.600 seconds | Existing tests enforce substitution rejection and exact standard/formal cleanup behavior |

Focused command:

```sh
uv run --frozen python -m unittest -v \
  test_review_controller.ControllerTests.test_formal_grace_rejects_substitution_and_standard_scope \
  test_review_controller.ControllerTests.test_formal_idle_cancel_retires_unused_judge_allowance \
  test_review_controller.ControllerTests.test_standard_idle_cancel_preserves_allowance_and_schema_one \
  test_review_controller_inspection.ControllerInspectionTests.test_formal_cleanup_marker_completes_exact_allowance_inventory \
  test_review_controller_inspection.ControllerInspectionTests.test_standard_start_rejects_formal_cleanup_marker
```

## Finding disposition

| ID | Location and evidence | Consequence if true | Severity | Disposition and rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| CS-001 | `BrokeredReviewController._terminal`; nine repeated live findings | Non-formal cleanup could understate a held allowance | blocking if reachable | **Rejected.** Schema 2 is derived from the immutable formal envelope; no supported constructor, setter, deserializer or production composition path injects it into a standard controller. | Construction trace, public-API probe and five focused regressions | Joshua Myers |
| CS-002 | Lower-level formal controller can exist in offline/tests without a campaign seal | A library caller could use the process-local formal controller outside live conformance | material residual | **Accepted as an existing trust-boundary fact, not the claimed defect.** Production live conformance refuses unbound formal execution; changing the controller to own campaign admission would be a separate architecture decision. | `BrokeredReviewConformanceProbe.run` unbound-formal rejection | Joshua Myers |
| CS-003 | A privileged same-process caller can mutate private state | Trusted code can bypass local invariants | high under host compromise | **Out of scope by design.** Such a caller can already invoke ledger/provider primitives directly; a duplicate terminal comparison is not containment. | Threat-model boundary and existing late credential/conformance gates | Joshua Myers |

## Exit

- Stop reason: pass rule met after the public reachability trace, executable probe and focused regressions all falsified CS-001 without new contradictory evidence.
- Rubric result: the repeated cleanup-scope claim is a correlated-model misunderstanding, not a confirmed source defect. No runtime or test change is warranted from this claim alone.
- Full quality gate: not rerun because runtime code and tests were unchanged; the exact commit had already passed its repository and production-image gates. The five affected regressions passed, and documentation changes require `git diff --check` before handoff.
- Accountable disposition: Joshua Myers formally accepted this source-level reassessment on 2026-09-23 and directed a wholly fresh live campaign without a reviewer-legibility code change. The retained three live verdicts remain `reject`; acceptance does not rewrite them, grant subject qualification, or authorize provider dispatch by itself.
- No live calls, credential access, spending, ledger mutation or historical artifact changes occurred during reassessment.
