# Agentic Verification Loop: citation and observation completion

## Objective and authority

- Requirement, issue, or project-brief link: correct the positive `source_unit`
  evidence gap and failed post-result observation construction from the final live
  read-only review retest.
- User journey or operational outcome: a supported diff finding survives retained
  reconstruction, and every completed critic/judge exchange can be collected for an
  unsigned observation proposal without phase confusion.
- Invariants and non-goals: no provider calls, credential access, retries, live
  authorization, sealed-artifact mutation, or relaxation of citation validation.
- Risk class: material
- Implementation owner: Joshua Myers
- Verifier or accountable approver, if required: Joshua Myers
- Commit/revision and starting worktree state: `ce22ac1bd8ef058d2d6336c9e17002bda8aa811f`; clean

## Rubric

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Project-specific outcome | blocking | retained positive citation and two-critic observation regressions | exact `source_unit` retained; critic/critic/judge map to critic/critic/judge authorizations |
| Correctness and failure handling | blocking | cardinality and incomplete-lifecycle tests | malformed construction fails before returning observations |
| Security/privacy/data integrity | blocking | offline tests and existing runtime-evidence verification | no secret/provider access and no weakened evidence binding |
| Maintainability/operability | high | one shared semantic mapping used by campaign and probe paths | no duplicated positional authorization policy |

## Budget and stopping rules

- Maximum iterations: 4
- Elapsed-time or review window: one implementation session
- Compute/cost ceiling, if material: zero provider calls and USD 0
- Pass rule: no blocking findings; focused, broad, full, and production-like gates pass
- Diminishing-return rule: stop after a complete clean gate and adversarial review
  finds no new blocking issue
- Escalation/domain-input trigger: any need for live authority or sealed-run mutation
- Rollback or abort condition: citation acceptance weakens, an exchange receives the
  wrong phase authorization, or credentials/provider transport are touched

## Iterations

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | grouped phase-aware collector and conformance-probe post-result method | retained failure shape plus one-phase-to-many-exchanges contract | V-001 blocking, V-002 high | centralize mapping and add positive/malformed regressions | 36 focused and 371 broad review tests pass |
| 2 | campaign path migrated to the shared collector; durable records updated | distinct adversarial pass over exact diff and trust boundaries | no new blocking finding | retain existing exact single-exchange verification and keep observation separate from attestation | Ruff, format, Pyright, diff check, `make check` and `make container` pass |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| V-001 | flattened exchange/authorization zip with multiple critics | critic two is checked against judge authorization | blocking | corrected with phase-aware grouped construction shared by campaign and probe paths | two-critic mapping and reversed/incomplete-shape regressions pass | Joshua Myers |
| V-002 | broker/conformance positive citation path lacks a finding | positive schema-2 fidelity is not demonstrated at the retained boundary | high | corrected with deterministic positive integration coverage | retained result contains the exact multiline postimage finding and unit | Joshua Myers |

## Exit

- Stop reason: the complete clean gate and adversarial review found no new blocking
  issue, satisfying the stated stopping rule.
- Rubric result and blocking findings: all rubric dimensions pass; V-001 and V-002
  are closed and no blocking finding remains.
- Full quality-gate command and result: unrestricted `make check` passed Ruff,
  formatting and Pyright; 2,467 source-checkout tests passed with four skips and 89%
  coverage; export verification, sdist and wheel builds passed; 1,848 tests passed
  against the installed wheel. `git diff --check` also passed.
- Production-like replay/fault/rollback evidence, if applicable: `make container`
  passed the network-none/read-only CLI and isolation, controller, approval,
  conformance, probe, runtime-evidence, campaign, campaign-runner and launch smokes.
- Remaining uncertainty, owners, and dates: the positive citation proof is
  deterministic offline integration evidence, not a claim that a live model will
  emit a finding. The immutable historical retest still has no signed observation
  and grants no live authority. Joshua Myers owns any separately authorized future
  campaign.
- Human/domain approval, if required: user directed implementation.
- Durable facts promoted to tests, `PROJECT_MEMORY.md`, this record and
  `docs/LIVE_READ_ONLY_REVIEW_QUALIFICATION_VERIFICATION.md`; ADR-0006 remains the
  citation-policy authority.
