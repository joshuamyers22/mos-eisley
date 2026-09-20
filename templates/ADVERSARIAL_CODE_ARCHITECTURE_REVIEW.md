# Adversarial Clean Code and Clean Architecture Review

> Use this document for evidence-based reviews inspired by Robert C. Martin's
> *Clean Code* and *Clean Architecture*. Treat the principles as heuristics, not
> a certification standard. Apply architecture proportionally to the system.

## Review metadata

- Repository:
- Remote:
- Branch and commit:
- Reviewer:
- Review date:
- Product purpose:
- Runtime and framework:
- First-party source scope:
- Excluded generated, vendored, experimental, or data paths:
- Pre-existing working-tree changes:
- Requirement/spec and project-specific north star:
- Rubric version and blocking threshold:
- Reviewer context/independence and known shared assumptions:
- Iteration/time/compute ceiling:
- Diminishing-return and escalation rule:

## Executive verdict

- Overall grade:
- Release recommendation: approve / approve with follow-up / block
- Highest risk:
- Strongest property:
- Recommended first improvement:

## Verification evidence

Record exact commands and outcomes. Never describe a check as passing when it
was skipped, deselected, unavailable, or blocked by the environment.
For repeated reviews, identify the new evidence, changed implementation, adversarial
case, or meaningfully different authorized perspective. Re-running the same review
against unchanged evidence is not a new verification pass.

| Check | Command | Result | Notes |
|---|---|---|---|
| Formatting | | | |
| Lint | | | |
| Static typing | | | |
| Unit tests | | | |
| Integration tests | | | |
| Coverage | | | |
| Build/package | | | |
| Architecture contracts | | | |
| Dependency/security audit | | | |
| Latency/capacity benchmark, if applicable | | | |
| Sanitizers/race detection, if applicable | | | |

## Architecture map

Describe the actual dependency flow, not the intended directory names.

- Entities/domain policy:
- Application use cases:
- Ports/interfaces:
- Infrastructure adapters:
- Delivery mechanisms (CLI, HTTP, jobs, UI):
- Composition root:
- External systems:
- Dependency-rule exceptions:

Expected direction:

```text
delivery/infrastructure -> application -> domain
```

## Findings

Order findings by severity, then remediation value. Every finding needs a
specific location, observable evidence, consequence, and bounded correction.

### [SEVERITY] Short finding title

- Location: `path/to/file.ext:line`
- Principle: SRP / OCP / LSP / ISP / DIP / dependency rule / naming / functions /
  error handling / tests / boundaries
- Evidence:
- Failure mode or maintenance cost:
- Why current tests do or do not protect it:
- Recommended change:
- Acceptance criteria:
- Estimated scope: small / medium / large

Severity definitions:

- **Critical:** credible corruption, security, safety, or unrecoverable-loss path.
- **High:** architectural coupling or correctness risk likely to impede change.
- **Medium:** material testability, readability, or operational weakness.
- **Low:** localized design debt with limited consequence.

## Clean Code review

- [ ] Names communicate domain intent and avoid misleading abstractions.
- [ ] Functions operate at one level of abstraction.
- [ ] Long parameter lists are replaced where a cohesive concept exists.
- [ ] Side effects and state transitions are explicit.
- [ ] Errors preserve context and are caught only where recovery is possible.
- [ ] Broad exception handling cannot hide programmer defects.
- [ ] Comments explain decisions and constraints rather than restating code.
- [ ] Duplication represents intentionally shared policy or has been removed.
- [ ] Tests are deterministic, independent, readable, and behavior-focused.
- [ ] Generated artifacts and environment-specific state are not tracked.

## Clean Architecture review

- [ ] Domain policy is independent of databases, APIs, frameworks, and UI.
- [ ] Use cases depend on ports rather than concrete infrastructure.
- [ ] Entry points are thin and delegate to application services.
- [ ] A clear composition root constructs concrete dependencies.
- [ ] Data-transfer schemas do not leak uncontrolled framework objects inward.
- [ ] Transactions and retries are owned at deliberate boundaries.
- [ ] Time, randomness, filesystem, network, and process execution are injectable.
- [ ] Architecture rules are enforced automatically where practical.
- [ ] Package boundaries follow reasons to change, not merely technical categories.

## Metrics and smell inventory

- First-party files / lines:
- Largest modules:
- Functions above the agreed size or complexity threshold:
- Broad exception handlers:
- Import cycles:
- Coverage by critical module:
- Suppressed lint/type findings:
- Known flaky or environment-dependent tests:

## Latency-sensitive review, if applicable

- [ ] The start/end measurement boundary and production clock are explicit.
- [ ] Expected, peak, and overload workloads have percentile distributions.
- [ ] Every queue, batch, retry, and in-flight set is bounded with an age limit.
- [ ] Hot-path allocation, blocking, locks, syscalls, faults, and logging are
      measured rather than assumed.
- [ ] Ownership, update order, snapshot visibility, and memory ordering are clear.
- [ ] Benchmark hardware, OS, compiler, flags, topology, and data are recorded.
- [ ] Deterministic replay covers gaps, duplicates, reordering, stale state, and
      dependency failure.
- [ ] Performance changes cannot bypass validation, risk, audit, or recovery.
- [ ] Custom allocators, containers, SIMD, affinity, and lock-free code have a
      simpler baseline, correctness tests, and before/after evidence.
- [ ] The completed `LATENCY_BUDGET.md` links raw results and regression policy.

Metrics locate review targets; they are not findings by themselves.

## Improvement plan

| Priority | Change | Finding addressed | Owner | Verification | Status |
|---:|---|---|---|---|---|
| 1 | | | | | Not started |

Prefer vertical, behavior-preserving slices:

1. Add characterization tests around the behavior being moved.
2. Introduce the desired seam or port.
3. Move one responsibility at a time.
4. Keep entry points and adapters thin.
5. Run the full quality gate after every slice.
6. Delete obsolete paths and update architecture documentation.

## Change log

| Date | Commit/PR | Improvement | Verification result |
|---|---|---|---|
| | | | |

## Follow-up review

- Review date:
- Findings closed:
- Findings remaining:
- Regressions introduced:
- Metrics before and after:
- Next review trigger:

## Final challenge questions

1. Which business rule is hardest to test without infrastructure, and why?
2. Which module has the most unrelated reasons to change?
3. Where can a broad exception turn a defect into apparently valid output?
4. Which concrete dependency points inward toward policy?
5. What would become difficult if the database, API, CLI, or framework changed?
6. Which test passes for the wrong reason or depends on the developer machine?
7. What is the smallest safe refactor that measurably improves a boundary?
8. Which deadline fails first under overload, and is the response safe?
9. What evidence or perspective changed since the prior verification pass?
10. Has the loop met its pass, diminishing-return, budget, or escalation stop rule?
