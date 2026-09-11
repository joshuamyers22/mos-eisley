# Mos Eisley project and imported-plan review

Review date: 2026-09-08. Baseline: commit `4f4149f` on
`feat/skill-release-evidence` in `/Users/josh/Projects/mos-eisley`.
Disposition: retain the offline foundation, revise both imported designs, and
integrate them through [plan §26](mos-eisley-plan.md#26-integrated-project-review-and-delivery-contract).
This was a single-assistant source/design review with local checks, not independent
multi-model review, live-model quality validation, or a complete security audit.

## Inputs and outputs

| Input | Original SHA-256 | Revised repository version |
|---|---|---|
| `/Users/josh/Downloads/adaptive-reasoning-routing.md` | `443224be4cc094b4d57094c9c8efbbdd751bff2ee4fd6aef8f9fc5d0f2150491` | [Adaptive reasoning routing](adaptive-reasoning-routing.md) |
| `/Users/josh/Downloads/adversarial-review-loop-project-plan.md` | `8f1186eae66fc0d514316140e0850b8f7b209ca23a75f8de774a2220f20506b1` | [Adversarial review loop](adversarial-review-loop-project-plan.md) |

Original Downloads files are preserved for provenance; use the revised repository
versions for delivery. The imported loop project's referenced *Design Plan* was not
found alongside these files. Its undefined A/B/C labels and adjudication buckets
are explicitly defined as Mos design decisions in the revision. Other Mos worktrees
were identified but neither merged nor credited as implemented in this checkout.

Reviewed implementation boundaries include `core/models.py`, `core/registry.py`,
`review/pipeline.py`, evaluation models/protocol and routing preflight, together
with the roadmap, README, project brief, statistical design, routing ADR and tests.
The current code preserves exact recorded requests, quorum and provenance; the
preflight schema explicitly denies dispatch. These are useful foundations.

## Mos Eisley findings

Priorities: P1 must be resolved before the affected feature ships; P2 must be
resolved before making the corresponding quality or optimization claim. A planned
fix below closes a specification gap; it does not imply runtime enforcement.

| ID | Priority | Evidence and hole | Incorporated change |
|---|---|---|---|
| M01 | P1 | Main-plan §§15/21 still advertised five findings, LLM dedupe, agreement scoring and a historical delivery order; `core/models.py` and `review/pipeline.py` implement 50-bounded findings, exact dedupe and policy verdicts | Correct §§15/18 directly, label §21 historical, make §26 and roadmap the active dependency contract |
| M02 | P1 | `ModelRegistry.resolve` lowers unsupported effort and sets `substituted=True`; an exact future route/floor cannot be enforced by that helper alone | Strict planned effort resolution and separate evidenced fallback; G6 includes a no-substitution dispatcher test. Existing helper behavior is accurately documented, not silently changed |
| M03 | P1 | Recorded `Brief` has no executable-evidence receipt; judge returns upheld IDs plus one rationale. The proposed multi-stage loop assumes richer state | L0/L2/L3 require versioned clause, test, binding, per-objection and workflow contracts with migration/replay checks |
| M04 | P1 | README/roadmap acknowledge no live critic fan-out, conversation controller, machine executor or runtime router despite deep evidence infrastructure | G1/G2 prioritize usable conversation and live read-only review, with G3 utility evidence before further automatic authority |
| M05 | P1 | Preflight denies dispatch; local anchors cannot prove whole-file freshness; operational readiness is attested. Signer roles do not supply people/key custody | G6 explicitly owns witness/bootstrap, signer operations, atomic one-use dispatch, crash/duplicate/revocation races and stop/fallback exercises |
| M06 | P1 | Original plan's generic sequential stopping conflicts with `StatisticalDesign.stopping_rule=fixed_matrix`; sparse profile families can exceed feasible data/assignment caps | Correct §18.3 and require a pre-spend feasibility calculation in §26.3/G3; adaptive inference remains a separately reviewed protocol |
| M07 | P2 | Route candidate v2 binds backend/model/effort/client/registry/prompt, but no independently routed output-budget action | Hold budgets fixed initially; budget routing requires new identity/schema, evaluation and replay bindings |
| M08 | P1 | Full §17 owner isolation and selection-store minimization remain planned; raw-trajectory learning would bypass them | Preserve private evidence separation, minimal same-owner selection aggregates, explicit reset/invalidation and backend isolation tests |

The feasibility gap is concrete: the current Hoeffding/Bonferroni method with four
profiles and six routes needs at least 1,732 independent clean groups per
profile/split even with zero observed risk to clear 0.05. At three repetitions,
249,408 clean-case assignments exceed the 50,000 cap; at least 13,856 clean cases
also exceed the 5,000-case dataset cap. Defective cases would add work. This is a
planning calculation under the current method, not a sample-size recommendation.

## Adaptive reasoning routing findings

| ID | Priority | Imported proposal and failure mode | Incorporated change |
|---|---|---|---|
| R01 | P1 | "Labels are free" conflates passing reviewer tests/judge outputs with correctness, creating circular training targets | Separate proxy, independent verification, unknown/disputed and delayed follow-up outcomes; retain failed/abandoned tasks and conservative cost |
| R02 | P1 | Nearest-neighbor retrieval over prior conversations/trajectories violates fresh-session minimization | No raw-history/embedding retrieval for automatic selection; only permitted owner aggregates; explicitly scoped offline evidence access |
| R03 | P1 | Cheap-first production and exploration below recommendation bypass existing calibration/role floors | Fixed baseline first, offline cascade/lookup comparisons, qualified actions only, exploration disabled by default |
| R04 | P2 | Cheap failure then expensive success is called a counterfactual bracket although feedback/state/order can change | Evaluate the whole recovery policy or use paired independent frozen starts and randomized order |
| R05 | P2 | Recording one propensity is presented as sufficient for off-policy estimates | Pin eligible distribution and actual dispatch; handle deterministic/zero support, changed eligibility, effective sample size, missingness and sequential-policy limitations |
| R06 | P2 | Universal difficulty surviving releases is assumed; Stage-0 divergence can leak into the call that produced it | Treat transfer as an ablation hypothesis; stage-specific pre-decision cutoffs and re-evaluation on route/version change |
| R07 | P1 | `success - lambda*cost` can exchange correctness for savings | Hard damage/detection/completion constraints precede cost optimization; whole-task denominators and zero-success handling |
| R08 | P1 | Adaptive routing of measurement components conflicts with Mos's general role selector | Freeze judge/grader/rubric/prompt/effort/budget per experiment/cohort; registered execution candidates may vary independently |
| R09 | P2 | Age slices, escalation rate and failure concentration are treated as diagnoses | Use them as signals, retain freshness deadlines, diagnose alternative causes, quarantine/re-evaluate instead of automatic retraining |
| R10 | P1 | Independent output-budget knob and unbounded learning feedback omit context, identity and activation effects | Route-specific context/billing constraints, fixed initial budgets, versioned future actions, mandatory existing promotion/dispatch chain |

The revised design adopts baseline comparisons, distinct effort/output controls,
decision logging, end-to-end economics and a frozen measurement path. It does not
adopt claims that instrumentation is costless, cascades identify causal effort,
or continuous online learning is an authorized implementation step.

## Adversarial review loop findings

| ID | Priority | Imported proposal and failure mode | Incorporated change |
|---|---|---|---|
| L01 | P1 | Bare clause IDs can point at changed meaning; undefined classes/buckets make metrics ambiguous | Revision/text-bound clause references, tombstones, explicit cause/divergence/disposition definitions |
| L02 | P1 | Author/reviewer simultaneous readings imply independence despite creator context; missing commitment semantics | Two fresh readers over identical plan/interface inputs, no creator tests/history, controller-sealed commits before reveal, incomplete on missing reader |
| L03 | P1 | Assertion diffs miss changed fixtures/oracles/skips or a binding that never calls real code | Freeze the entire test package, review separate bindings, count execution, run known-good/bad controls under containment |
| L04 | P1 | Cited failing tests go straight to author, with aptness unchecked until samples | Full initial judging, independent reproduction and requirement/test-oracle validation before blocking correction |
| L05 | P1 | Dropping uncitable tests hides requirements/security gaps | Retain gap/invariant objections with evidence and resolve authority/intent; no invented automatic requirements |
| L06 | P1 | Passing/unrun tests hidden and two-cycle failure relabeled ambiguity can conceal incomplete coverage | Controller retains all results; final full suites and independent review; persistent budgets/counters; unresolved remains unresolved |
| L07 | P2 | High Stage-0/reviewer overlap suggests removing review; consistency/rejection stand in for accuracy | Paired stage ablation and independently graded damage/escaped-defect outcomes; diagnostic rates cannot justify removal |
| L08 | P1 | Gold labels deferred until downgrade although automatic corrections can already damage correct code | Small independent dataset before any bypass/quality claim; GUI deferred, existing dual-grade provenance reused |
| L09 | P2 | Harvested disputes/escaped bugs plus age-out bias labels; never-raised escaped defects are omitted | Ordinary random audit plus hard-case sampling, inclusion/nonresponse records, both dismissed and never-raised escaped bugs |
| L10 | P1 | Gold cases "never enter context" conflicts with executable regression exposure; SQL alone cannot enforce isolation | Separate exposed development fixtures from fresh holdout; packet/cache/note access control and independent custody |
| L11 | P2 | "50–100 per bucket," generic bootstrap and self-agreement ceiling overstate reliability | Preregister estimand, groups, feasible bounds, non-inferiority and absolute damage thresholds; inconclusive cannot qualify |
| L12 | P1 | Mandatory Postgres/site/email assumes unrelated infrastructure and conflicts with Mos product/storage scope | Private local CLI/artifacts first; optional owner-scoped remote adapter/label UI; no external notification dependency |

The revised loop retains addressable requirements, independent readings, blind test
derivation, frozen obligations, structured objections, cost instrumentation and
evidence-gated simplification. It integrates them with creator-owned tests/approval,
delegation and final review rather than substituting a different author workflow.

## Validation and remaining work

- `make check`: lint/format, strict typing, all 345 tests, 90% branch-inclusive
  coverage, locked runtime export and sdist/wheel build passed. Its wheel smoke
  step initially hit sandbox DNS restrictions; `make smoke` subsequently passed
  with network access and installed pinned dependencies.
- The sample/assignment calculation was recomputed from the documented bound.
- Documentation changes only: no new runtime routing, testing, exploration or
  authority was enabled. All 71 local links/anchors across nine changed documents
  resolve, and `git diff --check` passes.
- No credentialed provider sweep, live-model quality experiment, fresh container
  containment run or network dependency vulnerability audit was performed here.
  G2/G3/G4/G6 retain those applicable release requirements.

Residual risks remain operational and empirical: representative independent groups,
sound human labels, sustainable authority/witness custody, provider drift, usable
containment and enough traffic to measure rare damage. The updated plan makes each
an owned exit condition; documents and green fixture tests alone cannot close them.
