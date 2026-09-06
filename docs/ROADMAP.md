# Delivery roadmap

1. **Implemented:** production-template scaffold and recorded review walking
   skeleton, request-bound fixtures, quorum/evidence policy, artifacts and replay.
2. **Implemented:** canonical multi-turn/tool protocol, inert fixture tool, model
   registry, deterministic effort resolution, byte budgets and boundary journal.
3. **In progress — live read-only review:** OpenAI Responses adapter and explicit
   one-prompt command implemented with documented capabilities, data-transfer
   acknowledgement, bounded I/O, reviewed-price per-response spending reservations
   and contract tests. Shared local cross-process spending admission is implemented.
   Next: credentialed conformance and isolated broker integration,
   then wire OpenAI into critic/judge review before other providers.
4. **In progress — quality and routing gate:** deterministic, content-addressed
   sweep plans, structurally blinded recorded execution, route-blind grading packets,
   provenance-bound adjudication and exact-coverage scoring are implemented offline.
   Fixed-matrix group-mean bounds and comparison-family correction are implemented;
   group independence remains an operator assertion. Per-finding decisions and
   descriptive two-grader agreement are implemented offline. Recorded evaluation
   now has a no-mount, network-disabled container boundary with negative probes.
   A detached cleanup watchdog handles launcher death and bounded worker lifetimes.
   Request-bound single-use host grants and private worker/broker IPC with mandatory
   shared spending admission are fixture-tested in real containers;
   see `PROVIDER_BROKER.md` for limits. Assignment-bound private audit chains and
   crash-conservative ledger recovery inventory are also implemented. Validated
   responses now produce non-scoreable, assignment-bound conformance
   artifacts containing usage, latency and settled spend. The explicit read-only
   recovery CLI and bounded decoded OpenAI HTTP client are implemented, while
   streaming and automatic retry/release remain prohibited. A blinded strict-schema
   OpenAI conformance request and fail-closed one-assignment CLI lifecycle are
   fixture-tested. Ed25519 authentication now binds exact human adjudication to an
   independently supplied public-key policy. The offline dual-grade gate reverifies
   two distinct graders, preserves both signed sources and requires a trust-disjoint
   resolver to sign exact conflict coverage; it remains non-promotable. The
   dual-lineage compiler now reverifies the full private artifact chain into a
   distinct observation schema. Authenticated scoring
   reverifies that complete lineage and calculates the registered metrics while
   retaining literal promotion denial. A content-addressed routing-study protocol
   now seals label-free feature partitions, role candidate floors and fallbacks,
   the cost-first objective, and freeze-before-holdout discipline; it cannot inspect
   results or authorize activation. Profile-aware calibration scoring now reverifies
   the full authenticated lineage and corrects confidence across every sealed
   profile and route without accepting holdout outcomes. Calibration-only policy
   freezing now applies the sealed role floors, complete-cost requirement, and
   deterministic objective while recording holdout as unevaluated and denying
   activation. One-attempt frozen-policy holdout evaluation now uses a private,
   exclusive local claim, reverifies both source lineages, and reports adequacy,
   under-routing, fallback coverage, and cost regret without promotion authority.
   Policy-level thresholds are now pinned before holdout, and a verification-only
   Ed25519 gate grants promotion readiness only after full evidence recomputation
   and an authority signature independent of graders and resolvers; activation stays
   disabled. Next run explicitly authorized credentialed conformance, then run the repeated
   backend × model × effort sweep on clean and defective samples. Learn and
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
