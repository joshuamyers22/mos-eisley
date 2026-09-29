# Adversarial Architecture and Code Review Playbook

The reviewer tries to falsify claims, not validate appearances. Review the
actual dependency graph, runtime behavior, failure handling, and delivery
artifact. Directory names and passing happy-path tests are weak evidence.

## Review sequence

1. Freeze scope: repository, commit, exclusions, runtime, and product purpose.
2. Reproduce the documented clean install, checks, build, and smoke test.
3. Trace one critical request and one state-changing workflow end to end.
4. Map trust boundaries, data ownership, dependencies, and failure propagation.
5. Attack assumptions using the lenses below.
6. Record only evidence-backed findings with location, consequence, correction,
   acceptance criteria, and severity.
7. Rank work by risk reduction per unit effort; verify fixes independently.

## Attack lenses

| Lens | Questions that should make the design uncomfortable |
|---|---|
| Correctness | Which invariant can concurrent, duplicated, stale, or partial input violate? |
| Boundaries | Which business rule imports a framework/vendor type or requires live infrastructure to test? |
| Changeability | What plausible product change crosses the most modules and why? |
| Data | Can migration, replay, deletion, or restore silently lose or reinterpret state? |
| Failure | Where are deadlines, cancellation, retry budgets, idempotency, and backpressure missing? |
| Security | Can identity be confused, authorization bypassed, input amplified, or a secret disclosed? |
| Supply chain | Can an unreviewed dependency or mutable artifact reach production? |
| Operations | Would an on-call engineer detect, localize, mitigate, and recover this failure? |
| Tests | Which test passes for the wrong reason, mocks the behavior under test, or depends on machine state? |
| Performance | Are tail latency, jitter, workload, hardware, queues, clocks, and overload measured end to end? |
| Delivery | Can mixed versions coexist, rollback safely, and preserve schema compatibility? |

## Finding quality

Severity reflects credible impact and likelihood, not reviewer preference.
Separate facts from inference. Avoid style findings unless they create a specific
correctness, comprehension, testability, or change-cost consequence. Metrics are
leads, not findings. A recommended abstraction must name the change it makes
safer and the complexity it introduces.

Use the supplied review template for the report. Block release for credible
uncontrolled corruption, security compromise, unsafe migration, unrecoverable
operation, or inability to build and verify the released artifact. Everything
else receives an owner, priority, verification method, and due date.

## Improvement rules

- Stabilize observed behavior before moving it.
- Fix the highest-risk boundary with the smallest vertical slice.
- Preserve rollback points and avoid long-lived half-migrations.
- Add an automated guard for every defect class when feasible.
- Compare before/after evidence: tests, dependency graph, latency, errors,
  complexity hot spots, or recovery time as relevant.
- Delete obsolete code and exceptions; otherwise the architecture never converges.
