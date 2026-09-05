# Delivery roadmap

1. **Implemented:** production-template scaffold and recorded review walking
   skeleton, request-bound fixtures, quorum/evidence policy, artifacts and replay.
2. **Implemented:** canonical multi-turn/tool protocol, inert fixture tool, model
   registry, deterministic effort resolution, byte budgets and boundary journal.
3. **In progress — live read-only review:** OpenAI Responses adapter and explicit
   one-prompt command implemented with documented capabilities, data-transfer
   acknowledgement, bounded I/O and contract tests. Next: credentialed conformance,
   cost limits, then wire OpenAI into critic/judge review before other providers.
4. **Quality gate:** single-critic baseline versus fan-out/judge, held-out clean and
   defective samples, human labels, latency/cost/false-positive thresholds.
5. **Execution:** threat model and capability matrix; macOS/Linux negative tests,
   isolated test runner, scoped filesystem and network policy, cancellation.
6. **Author/VCS:** disposable worktrees and trusted Git broker after containment.
7. **Publisher:** authenticated isolated credential process, dry run, idempotency.
8. **Convenience:** TUI, MCP, resume, provenance and optional Postgres export.

The saved `docs/mos-eisley-plan.md` is design history including its adversarial review.
Current implemented behavior is defined by the project brief, ADR and tests.
