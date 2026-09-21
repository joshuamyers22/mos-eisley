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
- Reopened revision and state: `57fe5cd`; clean after committing the immutable live
  retest record

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Project-specific outcome | blocking | structured critic/judge requests and 3-of-2 controller fault test | native strict schema emitted; judge reached with one invalid critic |
| Correctness and failure handling | blocking | schema compatibility and malformed-response tests | schema 1 omits `source_unit`; schema 2 includes it; duplicate keys still reject |
| Security/privacy/data integrity | blocking | threat model, request projections, offline gates | no new authority, retry, tools, secrets, or provider calls |
| Maintainability/operability | high | one shared schema normalizer and documentation | conformance and reviewer paths cannot drift in strictness policy |
| Historical replay retention | blocking | standalone evidence bundle decoded and authenticated from disk | one verified exclusive file retains every serialized authentication input before key loss |

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
- Reopened correction ceiling: three implementation passes, zero provider calls, and
  no mutation or reinterpretation of the completed live retest

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Canonical optional strict-output contract and exact OpenAI projection | Official Responses API contract plus retained malformed critic failure | No new blocking finding; capable and incapable routes require different payloads | Gate `response_format` on the resolved model capability and preserve absent-field canonical bytes | 52 focused protocol/provider/reviewer/conformance tests pass |
| 2 | Shared recursive schema normalization for reviewer and conformance paths | OpenAI strict schemas require every object property in `required`, including nullable fields | High prompt/schema conflict: schema-2 instructions said to omit `source_unit` where the strict schema requires `null` | Require explicit `null` in that case; retain schema-1 removal before normalization | Focused tests pass after correction; Ruff, formatting, and Pyright pass |
| 3 | Three independently prepared critics with threshold two | One deliberately malformed critic plus two valid critics | No blocking finding; one invalid response is tolerated without retry | Keep strict decoding and prove redundancy at the controller boundary | 19 controller tests and 372 broad review tests pass |
| 4 | Reopened after exact live review | Three valid live critics reached a signed observation, while adversarial review exposed Q-008/Q-009 and audit exposed Q-010 | No new blocking finding after correction; one unrelated fixture race reproduced cleanly | Harden all object shapes, permit only quorum-tolerated critic errors in observation, and retain a complete verified standalone replay bundle | focused schema/lifecycle, 164 review tests, clean `make check`, and rebuilt container gate pass |
| 5 | Reopened by fresh retest preflight | The launch preview sealed an 8,000-byte visible-text limit, but campaign/standalone reconstruction silently used the reviewer's 4,000-byte default | Blocking exact-replay mismatch caught before credential access, reservation, container creation, or provider dispatch | Pass the configured limit into every campaign reviewer reconstruction and make fixtures bind their real preview limit | 29 focused tests and the complete repository gate pass: 2,477 source tests, four skips, 89% coverage, and 1,853 installed-wheel tests |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| V-001 | `ModelReviewer` schema exists only in instructions | provider can emit structurally invalid JSON that fails quorum | blocking | correct using the already-supported native schema boundary | exact provider-payload test | Joshua Myers |
| V-002 | prior live roster had no spare critic | one invalid answer prevents threshold two | high | use three independently admitted critics with threshold two, without retry | deterministic controller fault test | Joshua Myers |
| V-003 | `strict_json_schema` conditionally hardens objects | unsupported object shapes can escape normalization | blocking | normalize absent properties and reject malformed properties recursively | direct nested schema regressions | Joshua Myers |
| V-004 | observation construction rejects any critic error | a quorum-tolerated failure cannot complete the promised lifecycle | blocking | rely on verified controller quorum/result; reject infrastructure verdicts, not tolerated critic errors | one-invalid-of-three signed/authenticated observation test | Joshua Myers |
| V-005 | standalone harness retained observation inputs piecemeal | ephemeral-key loss leaves historical authentication unreplayable | high | add one bounded, verified, exclusive evidence bundle containing all serialized replay inputs | decode, replay, tamper, permission, and placement tests | Joshua Myers |
| V-006 | campaign reconstruction omitted `max_text_output_bytes` | a valid live result could fail post-result retention because replay projected a different request | blocking | reconstruct critic and judge requests with the exact launch limit and reject configuration substitution | changed-limit regression plus campaign/runtime-evidence suites | Joshua Myers |

## Exit

- Stop reason: complete offline implementation and clean repository/package gate;
  commit and rebuild the production image from that immutable revision before live
  preparation.
- Rubric result and blocking findings: pass with no open offline blocking finding.
  The live retest remains separately authorized work.
- Full quality-gate command and result: after the output-limit correction,
  unrestricted `make check` passed Ruff, formatting, Pyright, 2,477 source tests
  with four skips, 89% coverage, export verification, sdist/wheel builds, and 1,853
  installed-wheel tests. The preceding sandboxed run was stopped after localhost
  fixtures demonstrated that socket binding was denied; the unrestricted rerun
  passed those fixtures and the complete gate.
- Production-like replay/fault/rollback evidence, if applicable: deterministic
  one-invalid-of-three replay reaches the judge, signed/authenticated observation,
  exclusive disk retention, and fresh offline verification without retry. Tamper,
  duplicate, oversize, unsafe-permission, overwrite, and placement cases fail closed.
  Before iteration 5, `make container` rebuilt image
  `sha256:2cf85409f8ee96d148a3209e2d1bb238d11137f06e2002856f784518a9401b51`
  and passed every offline smoke test. That image predates V-006 and is not eligible
  for the next live attempt; rebuild after committing the correction.
- Remaining uncertainty, owners, and dates: a later live result is still required;
  offline schema conformance cannot guarantee model quality or provider availability.
- Human/domain approval, if required: user directed this implementation.
- Durable facts promoted to tests, ADRs, docs, or `PROJECT_MEMORY.md`: recursive
  schema and full-lifecycle regressions, accepted ADR-0007, standalone-evidence
  documentation, exact output-limit reconstruction regression, qualification
  history, and project memory.
