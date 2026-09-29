# Agentic Verification Loop: content-bound review citations

## Objective and authority

- Requirement, issue, or project-brief link: offline correction of the final
  live-review citation-fidelity failure.
- User journey or operational outcome: an exact multiline postimage quote from one
  unified-diff hunk reaches adjudication without weakening fabricated-citation checks.
- Invariants and non-goals: preserve schema-1 bytes and sealed artifacts; no provider
  calls, credential access, retries, or new live qualification authority.
- Risk class: material
- Implementation owner: Joshua Myers
- Verifier or accountable approver, if required: Joshua Myers
- Commit/revision and starting worktree state: `768519f599c5162aa9270f62959b741a2e2a182c`; clean

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Project-specific outcome | blocking | retained-shape multiline postimage regression | exact quote validates in schema 2 |
| Correctness and failure handling | blocking | stale, invented, normalized and cross-hunk tests | every adversarial case fails closed |
| Security/privacy/data integrity | blocking | schema-1 canonical-byte and offline checks | no artifact drift or external access |
| Maintainability/operability | high | bounded parser, docs and full gates | deterministic catalog with documented limits |

## Budget and stopping rules

- Maximum iterations: 4
- Elapsed-time or review window: one implementation session
- Compute/cost ceiling, if material: zero provider calls and USD 0
- Pass rule: no blocking findings; focused, broad, full and container gates pass
- Diminishing-return rule: stop after two consecutive passes with no new finding
- Escalation/domain-input trigger: any need to reinterpret or mutate sealed evidence
- Rollback or abort condition: schema-1 byte drift, normalization-based acceptance,
  cross-hunk acceptance, or any credential/provider access

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | Added schema-2 content-bound raw/before/after hunk units and exact single-unit validation | Retained failure shape plus invented, stale, whitespace, cross-hunk, malformed-diff and size-bound cases | One high compatibility finding: the schema-1 response prompt advertised the optional schema-2 field | Remove `source_unit` from schema-1 prompt schemas while keeping the shared typed response model | Focused citation tests and broad review suite passed before the prompt correction |
| 2 | Isolated the schema-2 response field in prompt projection and added an explicit schema-1 absence assertion | Prompt-schema regression and complete offline/package/container evidence | No blocking findings remain | Accept the versioned contract and stop after the complete gate pass | 12 focused tests, 366 review tests, 2,462 source tests, 1,843 installed-wheel tests, and container suite passed |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| V-001 | Raw substring validation cannot represent an exact multiline postimage quote. | Supported findings fail before quorum. | blocking | Correct with explicit content-bound units. | retained-shape regression | Joshua Myers |
| V-002 | The first schema-2 implementation reused the expanded evidence schema in schema-1 model prompts. | A legacy critic could emit a field that its request contract does not permit, weakening byte/prompt compatibility. | high | Corrected before closure by deleting `source_unit` from schema-1 response prompt schemas. | schema-1 prompt absence and schema-2 prompt presence assertions | Joshua Myers |

## Exit

- Stop reason: all blocking rubric rows pass, the compatibility finding is corrected,
  and the second verification iteration found no new issue.
- Rubric result and blocking findings: pass; no blocking findings remain. Schema 1 is
  byte/prompt compatible and raw-only, while schema 2 is explicitly content-bound.
- Full quality-gate command and result: the equivalent component gates passed:
  `uv run --frozen ruff format --check .`, `uv run --frozen ruff check .`, and
  `uv run --frozen pyright`; `make test` ran 2,462 tests with four skips and 89%
  coverage; `make verify-export build smoke` passed with 1,843 installed-wheel tests.
  A single uninterrupted `make check` was not claimed because its components were
  completed separately after a sandbox loopback restriction.
- Production-like replay/fault/rollback evidence, if applicable: `make container`
  passed build, help, isolation, controller, approval, conformance, probe, runtime
  evidence, campaign, campaign-runner and launch checks. The retained live shape was
  inspected read-only; no provider or credential access occurred.
- Remaining uncertainty, owners, and dates: model citation quality remains advisory;
  deterministic validation only proves source fidelity. Any future live qualification
  requires new owner authority and a new reviewed campaign.
- Human/domain approval, if required: user directed implementation
- Durable facts promoted to tests, ADR-0006, model-reviewer documentation, the
  qualification history, and `PROJECT_MEMORY.md`.
