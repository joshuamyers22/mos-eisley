# Delivery roadmap

1. **Implemented:** production-template scaffold and recorded review walking
   skeleton, request-bound fixtures, quorum/evidence policy, artifacts and replay.
2. **Implemented:** canonical multi-turn/tool protocol, inert fixture tool, model
   registry, deterministic effort resolution, byte budgets and boundary journal.
3. **In progress — live read-only review:** OpenAI Responses adapter and explicit
   one-prompt command implemented with documented capabilities, data-transfer
   acknowledgement, bounded I/O and contract tests. Next: credentialed conformance,
   cost limits, then wire OpenAI into critic/judge review before other providers.
4. **In progress — quality and routing gate:** deterministic, content-addressed
   sweep plans, structurally blinded recorded execution, route-blind grading packets,
   provenance-bound adjudication and exact-coverage scoring are implemented offline.
   Fixed-matrix group-mean bounds and comparison-family correction are implemented;
   group independence remains an operator assertion. Per-finding decisions and
   descriptive two-grader agreement are implemented offline. Next add an isolated
   live executor and authenticated grading/resolution controls, then run the
   repeated backend × model × effort sweep on clean and defective samples. Learn and
   freeze an interpretable difficulty-routing policy only after held-out detection,
   false-positive, latency and cost thresholds pass. Uncalibrated prompts use a
   conservative role fallback or fail closed.
5. **Execution:** threat model and capability matrix; macOS/Linux negative tests,
   isolated test runner, scoped filesystem and network policy, cancellation.
6. **Author/VCS:** disposable worktrees and trusted Git broker after containment.
7. **Publisher:** authenticated isolated credential process, dry run, idempotency.
8. **Extensions after the quality/security gates:** policy preflight, redaction,
   typed lifecycle events and trusted endpoint/credential contracts; then bounded
   subagents and versioned skills; then brokered web/image evidence; finally one
   narrow outward MCP interface. See plan §24.5 for acceptance criteria.
9. **Convenience:** TUI, resume, provenance and optional Postgres export.

The saved `docs/mos-eisley-plan.md` is design history including its adversarial review.
Current implemented behavior is defined by the project brief, ADR and tests.
