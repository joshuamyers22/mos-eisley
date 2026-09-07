# Delivery roadmap

**Product direction, 2026-09-06:** the primary experience is a persistent terminal
conversation launched with `mos`, following plan §16.0. Users can ask questions,
plan, request changes, steer ongoing work, and request independent review within
the same session as those capabilities become available. A minimal conversational
TUI and safe session resume are an early product workstream alongside item 3;
advanced visual polish can follow later. This is planned work, not an availability
claim, and preserves the existing provider, spending, quality, and containment gates.

**Data ownership and storage, 2026-09-06:** keep saved conversations, replay,
evaluation evidence, and model-selection records under one user's ownership.
Default to private local files/SQLite, and support user-configured cloud database
and object-storage adapters. No cross-user sharing, pooling, or aggregation,
including anonymized model-selection telemetry. Fresh sessions may automatically
reuse only that user's minimal model-selection aggregates; prior conversational
content requires explicit same-owner resume or inspection. Plan §17 defines the
contract; comprehensive enforcement and remote adapters remain planned work.

**Project guidance and operational evidence:** adopt the production template's
structured-logging and bounded memory/note principles with Mos Eisley's ownership,
fresh-session, and audit guarantees. Add per-project points of view and best-practice
templates with explicit binding, versioned snapshots, independent overrides, and
visible precedence. Preferences and telemetry infrastructure remain project choices.
See plan §§16.6, 17.5–17.6 and `docs/PROJECT_GUIDANCE_DESIGN.md`; these are planned
capabilities, not current automatic template or memory loading.

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
   Define a versioned provider-adapter interface and extensible model catalog so
   new providers/backends and model entries can be added without rewriting the
   agent loop. Keep explicit route identities, capability/pricing provenance, and
   per-backend conformance; catalog discovery proposes entries without enabling
   them. These extension contracts are planned work (plan §§4.6 and 5.1).
   Make Anthropic, OpenAI, and Google interchangeable as creator (author), critic,
   and judge, with independent contexts and all six distinct-provider role
   assignments supported by the common contracts. Keep coding-child model/effort
   selection independent of the creator (plan §7.7); this remains planned work.
   In parallel, build the conversational session controller and minimal terminal
   over recorded providers and explicit inputs: contextual follow-ups, visible
   progress, queued steering, cancellation, private persistence, and safe resume.
   Live conversation requires conformance, transfer policy, and aggregate session
   spending admission. Integrate review results into the main conversation while
   keeping critic briefs isolated; add repository reads, edits, and tests only after
   their execution gates. Keep `exec`/JSON automation on the same controller.
   Add project-guidance attach/show/update/detach with trusted project bindings and
   frozen per-role rubrics. Alongside private persistence, add explicitly selected
   project memory and handoff notes; writing them requires scoped write capabilities.
   Never reuse private history merely because a guidance template was attached.
   Build owner-scoped storage interfaces with the session controller; verify local
   user isolation, explicit resume, and fresh-session context separation. Add
   remote database/object adapters only after server-side isolation, retention,
   migration, and no-aggregation tests pass. Backend selection must not change
   ownership or silently create additional copies.
4. **In progress — quality and routing gate:**
   Add the §17.5 versioned operational-event mapping alongside live provider work,
   preserving required audit/spend durability and owner isolation. Evaluate outcomes
   and guardrails on later windows; telemetry review does not authorize changes.
   Published template `d59f3e6` supplies a Python core/local-spool reuse candidate;
   evaluate a pinned Mos adapter with independent health, explicit queue/durability
   semantics, and Mos-specific sanitization before enabling it. No telemetry code
   is added by the adoption review itself.
   Existing evaluation progress: deterministic, content-addressed
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
   and an authority signature independent of graders and resolvers. A short-lived
   activation-eligibility gate now consumes that receipt plus three distinct signed
   inputs for exact route/cost/freshness policy, operational readiness, and revocation
   control. It denies substitutions and retains literal runtime/configuration denial;
   operational fields are attestations rather than live provider checks. A pinned,
   append-only local control anchor and read-only preflight now reject older-message
   replay, preserve revocations, and reverify the full source chain without dispatch
   authority. Whole-database rollback still needs an external monotonic witness.
   Next design a one-use brokered dispatch transaction, then run explicitly authorized
   credentialed conformance and the repeated
   backend × model × effort sweep on clean and defective samples. Learn and
   freeze an interpretable difficulty-routing policy only after held-out detection,
   false-positive, latency and cost thresholds pass. Uncalibrated prompts use a
   conservative role fallback or fail closed.
   Define a replaceable selection interface over controller-filtered eligible
   routes: manual choices, per-role profiles, and calibrated automatic strategies.
   Expose session/task overrides and explainable decisions; new strategies retain
   quality, spending, privacy, and activation gates. See plan §7.6 for planned
   interface, model-switching, fallback, and acceptance requirements.
5. **In progress — prompt skill evidence:** exact instructions now participate in
   evaluation candidate and request identity. A sealed two-arm protocol enforces a
   prompt-only persona-skill treatment, paired independent-group statistics, full
   dual-grade lineage, and a local one-use holdout claim. Reports cannot promote or
   activate the skill. An independent Ed25519 authority can now issue a short-lived
   promotion-readiness receipt only after both split lineages are recomputed, while
   configuration and activation remain denied. Deterministic retained package
   archives now preserve and semantically reverify every validated byte without
   extraction or authority. Current release evidence now recomputes both split
   lineages and binds those exact bytes to a still-valid promotion receipt. Next:
   authenticated revocation and rollback, then transactional installation and
   post-promotion drift evidence.
6. **Execution:** threat model and capability matrix; macOS/Linux negative tests,
   isolated test runner, scoped filesystem and network policy, cancellation.
7. **Author/VCS:** disposable worktrees and trusted Git broker after containment.
   Add creator-led coding: creator writes the plan and executable tests, critic
   reviews both, judge adjudicates, creator approves the exact plan/test revisions,
   then delegates at least one meaningful coding subtask
   and owns integration, tests, and final critic/judge review. Example: Astra creator
   with a Luna max-thinking coding child, resolved to eligible exact model routes.
   Target clean, efficient code and cost-effective whole-task execution, counting
   planning, review, handoffs, integration, and rework. Delegated writes also require
   E2 bounded-subagent gates (plan §§7.7, 14.2.1, 15.7).
8. **Publisher:** authenticated isolated credential process, dry run, idempotency.
9. **Extensions after the quality/security gates:** a non-authorizing, prompt-only
   skills foundation is implemented with exact recorded-run provenance. Persona
   promotion remains gated on paired quality evaluation. Policy preflight,
   redaction, typed lifecycle events and trusted endpoint/credential contracts,
   plus E1 trusted provider/selector extension loading and model catalog overlays;
   then E2 bounded subagents and creator-approved delegated coding after execution
   containment; then E3 brokered web/image evidence plus PDF and Word
   (`.docx`/`.doc`) reading, scanned-document OCR, and XLSX/CSV reading and bounded
   tabular analysis for conversations and reviews, with text/table extraction,
   page/sheet/cell/record citations, parsing and extraction-quality reporting, and
   isolated processing of owner-scoped artifacts; finally one narrow outward MCP
   interface. Document and spreadsheet support is later planned work, not currently
   available.
   See plan §§19.6, 24.4–24.5, and 25 for scope and acceptance criteria.
10. **Convenience:** advanced TUI polish and provenance navigation. The core
    conversation, resume, and configurable storage belong to the product workstream
    above; shared analytics or team-wide database exports are excluded.

The saved `docs/mos-eisley-plan.md` is design history including its adversarial review.
Current implemented behavior is defined by the project brief, ADR and tests.
