# Agentic Verification Loop: structured review output and quorum resilience

## Objective and authority

- Requirement, issue, or project-brief link: G2 live read-only review and the
  2026-09-20 citation-observation retest quorum failure.
- User journey or operational outcome: capable critic and judge models receive an
  enforced response schema, while one invalid critic in a redundant roster cannot
  prevent two valid critics from reaching the judge.
- Invariants and non-goals: no retry, repair prompt, weakened parser, provider call,
  credential access, live authorization, or reinterpretation of retained evidence.
- Risk class: material
- Implementation owner: Joshua Myers
- Verifier or accountable approver, if required: Joshua Myers for offline changes;
  fresh explicit approval is required for any paid rerun.
- Commit/revision and starting worktree state: `6213cce43b0f8538756991a2e581e9332a601de4`; clean

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Project-specific outcome | blocking | structured critic/judge requests and 3-of-2 controller fault test | native strict schema emitted; judge reached with one invalid critic |
| Correctness and failure handling | blocking | schema compatibility and malformed-response tests | schema 1 omits `source_unit`; schema 2 includes it; duplicate keys still reject |
| Security/privacy/data integrity | blocking | threat model, request projections, offline gates | no new authority, retry, tools, secrets, or provider calls |
| Maintainability/operability | high | one shared schema normalizer and documentation | conformance and reviewer paths cannot drift in strictness policy |

## Budget and stopping rules

- Maximum iterations: 4
- Elapsed-time or review window: one implementation session
- Compute/cost ceiling, if material: zero provider calls and USD 0
- Pass rule: no blocking findings; focused, broad, full, and production-like gates pass
- Diminishing-return rule: stop after a clean complete gate and adversarial pass add
  no new blocking evidence
- Escalation/domain-input trigger: any need to weaken local validation or dispatch a
  paid request
- Rollback or abort condition: legacy requests change when the optional format is
  absent, non-capable models receive unsupported fields, or malformed output can pass

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Canonical optional strict-output contract and exact OpenAI projection | Official Responses API contract plus retained malformed critic failure | No new blocking finding; capable and incapable routes require different payloads | Gate `response_format` on the resolved model capability and preserve absent-field canonical bytes | 52 focused protocol/provider/reviewer/conformance tests pass |
| 2 | Shared recursive schema normalization for reviewer and conformance paths | OpenAI strict schemas require every object property in `required`, including nullable fields | High prompt/schema conflict: schema-2 instructions said to omit `source_unit` where the strict schema requires `null` | Require explicit `null` in that case; retain schema-1 removal before normalization | Focused tests pass after correction; Ruff, formatting, and Pyright pass |
| 3 | Three independently prepared critics with threshold two | One deliberately malformed critic plus two valid critics | No blocking finding; one invalid response is tolerated without retry | Keep strict decoding and prove redundancy at the controller boundary | 19 controller tests and 372 broad review tests pass |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| V-001 | `ModelReviewer` schema exists only in instructions | provider can emit structurally invalid JSON that fails quorum | blocking | correct using the already-supported native schema boundary | exact provider-payload test | Joshua Myers |
| V-002 | prior live roster had no spare critic | one invalid answer prevents threshold two | high | use three independently admitted critics with threshold two, without retry | deterministic controller fault test | Joshua Myers |

## Exit

- Stop reason: complete offline implementation and clean package/container gates.
- Rubric result and blocking findings: pass with no open offline blocking finding.
  The live retest remains separately authorized work.
- Full quality-gate command and result: unrestricted `make check` passed Ruff,
  formatting, Pyright, 2,472 source tests with four skips, 89% coverage, export and
  distribution builds, and 1,851 installed-wheel tests. The first sandboxed run
  reached all source tests but reported 31 pre-existing localhost fixture errors
  because socket binding was denied; the unrestricted rerun passed those fixtures.
- Production-like replay/fault/rollback evidence, if applicable: deterministic
  one-invalid-of-three controller replay reaches the judge and returns `accept`
  without retry. `make container` rebuilt image
  `sha256:25bc91214f3317eda824ed21979de76647505af8e97a524206762c80bcbbcbda`
  and passed every offline smoke test.
- Remaining uncertainty, owners, and dates: a later live result is still required;
  offline schema conformance cannot guarantee model quality or provider availability.
- Human/domain approval, if required: user directed this implementation.
- Durable facts promoted to tests, ADRs, docs, or `PROJECT_MEMORY.md`: regression
  tests, accepted ADR-0007, model-reviewer documentation, qualification history,
  and project memory.
