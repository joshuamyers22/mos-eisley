# Adversarial architecture review: G4 isolated reviewer execution

## Review metadata

- Repository: mos-eisley-memory-selection
- Branch and commit: `feat/production-template-guidance` at `331874d0`
- Reviewer: Codex; accountable owner Joshua Myers
- Review date: 2026-09-24
- Product purpose: immutable offline reviewer-test execution and exact count evidence
- Runtime: Python 3.12, unittest and the existing immutable Docker boundary
- First-party source scope: new G4 execution/controller/worker/CLI and focused tests
- Exclusions: Git/E2, correction dispatch, live providers and public activation
- Pre-existing working-tree changes: none
- North star: roadmap G4 and plan §26.2/§26.4
- Blocking threshold: any uncontrolled execution, substitution, count, cleanup or
  authority defect
- Reviewer context: implementation author; this is adversarial self-review, not an
  independent final G4 approval
- Ceiling: four evidence-changing passes in one offline session

## Executive verdict

- Overall grade: pass for the isolated execution/count slice, with explicit residual
  trust and later-gate limits.
- Release recommendation: retain as offline G4 infrastructure; do not authorize a
  candidate, correction or production write workflow yet.
- Highest risk: false passing evidence from the wrong code, wrong test set or wrong
  failure mode.
- Strongest intended property: no-mount immutable-image execution with exact bound
  inputs and canonical receipts.
- Recommended next improvement: connect this evidence to authenticated custody and
  trusted VCS/E2 provenance before designing candidate/correction dispatch.

## Verification evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Formatting/lint/type | `make check` plus focused Ruff/Pyright | pass | 812 files formatted; zero lint/type findings |
| Focused tests | `python -m unittest tests.test_reviewer_test_package tests.test_reviewer_implementation_binding tests.test_reviewer_test_execution` | pass, 25/25 | Includes real clean-child controls and hostile cases |
| Full tests/coverage | `make check`; affected localhost rerun | reconciled pass | 2,456 run; 31 sandbox-only errors; same 48 tests pass unrestricted |
| Build/package | `make verify-export build`; `make smoke` | pass | sdist/wheel built; 1,787 installed-wheel tests pass; four new modules present |
| Architecture contracts | source and CLI review; canonical/tamper/overlap tests | pass | no host fallback or executable adapter; all downstream authority false |

## Architecture map

- Entities/domain policy: immutable request, job, observation, receipt and paired
  control contracts.
- Application use cases: assemble/verify exact material; run isolated tests; verify
  receipt; validate known controls.
- Infrastructure adapter: existing `OfflineContainer` and private artifact writer.
- Delivery mechanism: explicit G4 CLI commands.
- Composition root: main CLI creates the exact immutable-image container.
- External systems: local Docker daemon and prebuilt immutable image only.
- Dependency direction: CLI/container adapter -> execution policy -> immutable G4
  package/binding contracts.

## Findings

- Closed, blocking: installed-package shadowing could select wrong code. A clean
  isolated `python -I` child now places materialized roots ahead of site packages.
- Closed, high: implicit lifecycle storage could write under the reviewed tree. The
  CLI now requires an explicit disjoint lifecycle root and tests pre-execution
  rejection.
- Closed, high: distinct binding records alone did not prove distinct control code.
  Paired controls now require distinct implementation-tree hashes.
- Accepted residual: the exact Docker image, daemon and host kernel are trusted;
  dynamic Python can alter in-process state; declared dependency/build bytes are not
  proof of image correspondence; Git/E2 and human custody are not yet authenticated.
  These limits are documented and remain later G4 gates, not silent acceptance.

## Clean Code and architecture checks

- [x] Domain contracts reject invalid states at construction.
- [x] Worker protocol is versioned, canonical and bounded.
- [x] Filesystem, process, output and time ownership are explicit.
- [x] CLI remains thin and cannot fall back to host execution.
- [x] Direct adapter generation contains no wrapper/result policy.
- [x] Failure evidence distinguishes assertion, import/infrastructure and count drift.
- [x] Tests cover hostile inputs and actual known-control behavior.

## Follow-up review

- Review date: 2026-09-24 after focused, full source and installed-wheel verification.
- Findings closed/remaining: three closed; only the explicitly deferred trust/gate
  limits above remain.
- Next review trigger: any runner, container, adapter, count or receipt schema change.
