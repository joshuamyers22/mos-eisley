# Adversarial review: positive citations and post-result observation

## Review metadata

- Repository: Mos Eisley Memory Selection
- Remote: `https://github.com/joshuamyers22/mos-eisley.git`
- Branch and starting commit: `feat/production-template-guidance` at
  `ce22ac1bd8ef058d2d6336c9e17002bda8aa811f`
- Reviewer and date: Codex under Joshua Myers's single-operator contract, 2026-09-20
- Product purpose: bounded, evidence-backed memory selection and review
- Runtime and framework: Python 3.12, Pydantic contracts, isolated broker workers
- First-party scope: retained positive citation coverage, runtime evidence grouping,
  conformance-probe post-result collection, campaign observation and focused tests
- Exclusions: provider dispatch, credentials, spending, signatures, historical-artifact
  mutation, and authorization of another qualification campaign
- Pre-existing working-tree changes: none
- North star: G2, Q-006, `docs/PYTHON_ENGINEERING_GUIDE.md`, the verification-loop,
  threat-model and adversarial-review guides
- Blocking threshold: unsupported citation admission, missing/surplus exchange
  truncation, wrong phase authorization, weakened runtime binding, live access, or a
  failed release gate
- Independence: owner-authorized self-review; no independent human review is claimed
- Ceiling: four evidence-changing iterations, zero provider calls and USD 0

## Executive verdict

- Overall grade: A for the scoped offline correction
- Release recommendation: approve the offline correction; no live authority follows
- Highest risk attacked: flattening per-exchange runtime records against per-phase
  authorizations silently assigns the judge authorization to a later critic
- Strongest property: one semantic collector validates the complete review shape,
  assigns authorization by phase, then delegates every exchange to the existing exact
  request/runtime/cleanup verifier
- Recommended first improvement: none in the scoped correction; retain an explicit
  authorization boundary for any future live campaign

## Verification evidence

| Check | Command/evidence | Result | Notes |
|---|---|---|---|
| Formatting | `uv run --frozen ruff format --check .` | Passed | Complete repository |
| Lint | `uv run --frozen ruff check .` | Passed | Complete repository |
| Static typing | `uv run --frozen pyright` | Passed | Zero errors |
| Focused tests | citation, conformance-probe and runtime-evidence modules | 36 passed | Positive retained citation and grouped observation cases |
| Broad review tests | `PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -p 'test_review*.py'` | 371 passed | Includes campaign, launch, tamper and handoff coverage |
| Full tests/coverage/package | unrestricted `make check` | Passed | 2,467 source tests, four skipped, 89% coverage, exports and distributions verified, then 1,848 installed-wheel tests passed |
| Production-like contracts | `make container` | Passed | Build plus isolation, controller, approvals, conformance, probe, runtime, campaign and launch smokes |

## Architecture map

```text
campaign/probe adapters -> grouped runtime collector -> exact exchange verifier
brokered review --------> citation policy ---------> retained judge result
```

- Domain policy: citation catalogs and exact quote validation remain unchanged.
- Application use cases: the conformance probe exposes collection only after a
  finished review; campaign observation uses the same grouped collector.
- Infrastructure adapters: the existing single-exchange collector verifies retained
  request, worker operation, lifecycle and cleanup records.
- Delivery/composition: no public live entry point or transport authority was added.
- External systems: none used by this correction.

## Findings and disposition

### Resolved blocking: phase authorizations were treated as exchange authorizations

- Location: private post-result construction and the former per-call campaign loop
- Principle: explicit domain cardinality / dependency rule / fail-closed errors
- Evidence: two critics plus one judge produce three exchanges but exactly two signed
  phase authorizations; a flattened zip assigned the judge authorization to critic two
- Failure mode: correct retained runtime evidence is rejected, or positional policy
  diverges between orchestration paths
- Correction: validate the whole shape and phase order before filesystem reads, reuse
  the critic-phase authorization for all critics, reserve judge authorization for the
  final exchange, and share that policy between campaign and probe paths
- Acceptance: two-critic mapping, reversed phase and incomplete-shape tests pass
- Status: closed

### Resolved high: positive citations stopped at the pure policy boundary

- Location: conformance-probe integration coverage
- Principle: boundary-focused tests / retained evidence fidelity
- Evidence: pure schema-2 validation covered a finding, but brokered retained
  reconstruction used only empty critiques
- Failure mode: a regression could discard or alter `source_unit` after local citation
  validation while the pure citation suite stayed green
- Correction: run a deterministic multiline postimage finding through critic parsing,
  exact citation validation, judge uphold and retained result reconstruction
- Acceptance: the retained `revise` verdict contains the exact finding and unit ID
- Status: closed

No open critical, high, medium or low finding remains in the scoped diff. The
historical retest still has no signed observation and is not reinterpreted.

## Clean-code and architecture assessment

- The grouped helper owns one cohesive policy: mapping review phases to exchanges.
- The exact single-exchange verifier remains the only filesystem/runtime binding path;
  no validation logic was copied or weakened.
- Shape and phase checks occur before collection, preventing silent `zip` truncation.
- The probe method names post-result availability explicitly and fails before evidence
  construction unless the controller, judge preview, authorizations and lifecycles are
  complete.
- The positive citation test is deterministic and local; it does not rely on model
  behavior to choose whether to emit a finding.
- No retry, fallback, credential read, provider dispatch or signature synthesis was
  introduced.

## Improvement plan

| Priority | Change | Finding addressed | Owner | Verification | Status |
|---:|---|---|---|---|---|
| 1 | Centralize phase-aware runtime observation construction | Wrong authorization mapping | Joshua Myers | Multi-critic and malformed-shape tests | Complete |
| 2 | Prove a positive citation at the retained boundary | Citation evidence gap | Joshua Myers | Broker/judge/retained integration test | Complete |
| 3 | Complete package and container gates | Release evidence | Joshua Myers | `make check`; `make container` | Complete |

## Final challenge result

The hardest rule is exact request/runtime/cleanup identity, and the new helper delegates
it to the existing verifier rather than creating a parallel interpretation. The module
with the new policy has one reason to change: review exchange grouping. Malformed shape
or phase order raises before partial output; no broad exception can convert it into an
observation. External-provider replacement does not affect phase mapping. The original
one-critic test passed for the wrong reason because exchange and authorization counts
were both two; the two-critic regression now exercises the actual cardinality mismatch.
The complete package and container gates passed, and this final challenge found no
new blocking issue. The stop rule is met. The deterministic positive citation test
does not assert that a live critic will emit a finding, and the immutable historical
retest remains unsigned and nonqualifying.
