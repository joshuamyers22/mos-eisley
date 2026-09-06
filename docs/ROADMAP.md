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
   In parallel, build the conversational session controller and minimal terminal
   over recorded providers and explicit inputs: contextual follow-ups, visible
   progress, queued steering, cancellation, private persistence, and safe resume.
   Live conversation requires conformance, transfer policy, and aggregate session
   spending admission. Integrate review results into the main conversation while
   keeping critic briefs isolated; add repository reads, edits, and tests only after
   their execution gates. Keep `exec`/JSON automation on the same controller.
   Build owner-scoped storage interfaces with the session controller; verify local
   user isolation, explicit resume, and fresh-session context separation. Add
   remote database/object adapters only after server-side isolation, retention,
   migration, and no-aggregation tests pass. Backend selection must not change
   ownership or silently create additional copies.
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
   and an authority signature independent of graders and resolvers. A short-lived
   activation-eligibility gate now consumes that receipt plus three distinct signed
   inputs for exact route/cost/freshness policy, operational readiness, and revocation
   control. It denies substitutions and retains literal runtime/configuration denial;
   operational fields are attestations rather than live provider checks. A pinned,
   append-only local control anchor and read-only preflight now reject older-message
   replay, preserve revocations, and reverify the full source chain without dispatch
   authority. Whole-database rollback still needs an external monotonic witness.
   The one-use admission, dispatch, ephemeral grant, provider transaction, and
   content-verified response publication path and verification-only signed
   conformance attestation are now implemented. Next run explicitly authorized
   credentialed conformance through that exact path and the repeated
   backend × model × effort sweep on clean and defective samples. Learn and
   freeze an interpretable difficulty-routing policy only after held-out detection,
   false-positive, latency and cost thresholds pass. Uncalibrated prompts use a
   conservative role fallback or fail closed.
5. **In progress — prompt skill evidence:** exact instructions now participate in
   evaluation candidate and request identity. A sealed two-arm protocol enforces a
   prompt-only persona-skill treatment, paired independent-group statistics, full
   dual-grade lineage, and a local one-use holdout claim. Reports cannot promote or
   activate the skill. An independent Ed25519 authority can now issue a short-lived
   promotion-readiness receipt only after both split lineages are recomputed, while
   configuration and activation remain denied. Deterministic retained package
   archives now preserve and semantically reverify every validated byte without
   extraction or authority. Current release evidence now recomputes both split
   lineages and binds those exact bytes to a still-valid promotion receipt.
   Independent, expiring release control now authenticates exact allow/revoke state,
   can nominate exact retained rollback bytes, and uses a release-scoped append-only
   local anchor to reject older-message replay. It grants no install authority and
   whole-anchor rollback still needs an external witness. Exact controlled candidate
   or rollback bytes can now be transactionally materialized into a private
   content-addressed quarantine store with a latest-anchor commit guard, full
   post-write verification, and conservative crash inventory. Quarantine grants no
   installation or configuration authority. Independent Ed25519 installation
   authority now binds an exact staged manifest, target, latest control entry, and
   one private at-most-once claim store. Guarded claim consumption burns permission
   before a side effect and holds release control through the future installer's
   commit window. Exact bytes can now be atomically installed into a separately
   locked, private content-addressed store with completion-marker-last durability,
   full reconstruction, and read-only crash correlation. An independently signed,
   state-bound decision can now atomically consume one use and change a private default
   pointer with exact sequence/prior-pointer compare-and-swap. Signed post-selection
   evidence now binds that exact pointer and recomputes objective health and drift
   thresholds against the authenticated promotion holdout under two independent
   authorities. A separately signed one-use runtime preparation now reconstructs the
   exact installed prompt, binds one selected OpenAI route and request, holds current
   control/default locks through a worst-case shared-ledger reservation, and uses that
   single insert as the authorization burn. It issues no broker grant and sends
   nothing. Runtime preparation and a subsequent pinned, one-use broker-admission
   commit now reverify the complete routing lineage. Admission holds both control
   anchors, the default pointer, and the exact existing spend entry, records readiness
   without reserving twice, and still issues no grant or request. An independent,
   maximum-60-second Ed25519 decision can now be consumed once under fresh guards into
   durable eligibility for one future request-bound grant. A pinned issuance store can
   now consume that claim exactly once into a memory-only, maximum-30-second bearer;
   it persists only the capability hash and supports one in-process redemption. A
   separately pinned provider-owning transaction now burns that bearer into an fsynced
   before-send marker, invokes one exact bounded zero-retry OpenAI request, and settles
   the existing reservation. Missing or ambiguous outcomes retain full exposure and
   never permit retry or automatic release. A pinned private response store now
   atomically retains exact provider bytes and publishes a freshly reverified,
   reasoning-free result with complete settled lineage. Next: run separately
   authorized credentialed conformance against this exact boundary. A signed,
   freshness-bounded observer attestation can now bind that run to its verified
   publication without claiming authorship, billing, or quality. A signed rolling
   publication-history checkpoint can now detect rollback against a separately
   retained prefix, while external retention and newest-checkpoint delivery remain
   operator responsibilities. Independently signed aggregate billing evidence can now
   require exact usage/cost agreement for a complete, exclusive OpenAI Admin API scope
   while reverifying the full conformance and publication lineage. Documented cost
   exports remain daily and do not carry response IDs, so exact request attribution,
   invoice finality, and ledger release remain denied. Next, run separately authorized
   credentialed conformance, then collect and strictly parse real Admin API evidence in
   an isolated credential-owning process before stronger operational claims.
6. **Execution:** threat model and capability matrix; macOS/Linux negative tests,
   isolated test runner, scoped filesystem and network policy, cancellation.
7. **Author/VCS:** disposable worktrees and trusted Git broker after containment.
8. **Publisher:** authenticated isolated credential process, dry run, idempotency.
9. **Extensions after the quality/security gates:** a non-authorizing, prompt-only
   skills foundation is implemented with exact recorded-run provenance. Persona
   promotion remains gated on paired quality evaluation. Policy preflight,
   redaction, typed lifecycle events and trusted endpoint/credential contracts;
   then bounded subagents; then brokered web/image evidence; finally one narrow
   outward MCP interface. See plan §§24.5 and 25 for acceptance criteria.
10. **Convenience:** advanced TUI polish and provenance navigation. The core
    conversation, resume, and configurable storage belong to the product workstream
    above; shared analytics or team-wide database exports are excluded.

The saved `docs/mos-eisley-plan.md` is design history including its adversarial review.
Current implemented behavior is defined by the project brief, ADR and tests.
