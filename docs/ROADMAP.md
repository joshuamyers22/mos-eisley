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
reuse that user's minimal model-selection aggregates and enabled
user/project memory explicitly curated under §16.0.2. Full prior conversational
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
   A fixed-model, metadata-only OpenAI readiness command now records exact
   `gpt-5.6-luna` visibility or a coarse safe failure while explicitly denying
   billing, Responses, quality, scoring, and routing claims. Its first credentialed
   operator attempt exposed a compressed-response decode failure; the bounded client
   now forces identity encoding and schema-2 receipts retain only a safe local
   transport subcategory. On 2026-09-07, a fresh private schema-2 operator receipt
   confirmed exact `gpt-5.6-luna` metadata visibility through that fixed path while
   retaining literal denials of billing, Responses, scoring, and routing authority.
   An independently authorized minimal synthetic Responses canary is implemented
   with fixed repository-owned input, exact two-request binding, a 32-token output
   cap, shared-ledger admission, zero retries, content-addressed private evidence,
   and literal downstream denials. On 2026-09-07, the first operator-signed live
   canary completed and offline verification confirmed 40 input tokens, 5 output
   tokens, 14 micro-USD retained, a settled unblocked ledger, and exact Responses
   access while billing and routing authority remained false. Those exact-profile
   conformance prerequisites subsequently passed as described in item 4. The
   separate reviewed offline boundary has now converted only the 18 qualifying
   records into a non-gradeable partial seed. A second offline boundary commits the
   exact 342-request remainder and its aggregate cost ceiling without authorizing
   execution. Next, build its one-use assignment execution decision, then wire
   OpenAI into critic/judge review before other providers.
   A first [recorded conversation terminal](CONVERSATIONS.md) now implements
   contextual follow-ups, visible progress, queued follow-up messages, cancellation,
   private local snapshots and explicit same-user/workspace resume. A consumed
   interrupted request is never replayed automatically. Workspace-scoped metadata
   listing, latest-session selection with a locked hash recheck, and exact-snapshot
   deletion with temporary-file cleanup now provide navigation and manual retention.
   An [explicit recorded review round-trip](CONVERSATION_REVIEW.md) now freezes a
   selected packet, keeps critic requests separate from chat history, and returns
   retained evidence plus a bounded summary for contextual follow-ups.
   [Multiline drafting](CONVERSATIONS.md#multiline-composition) now supports
   bounded code blocks, explicit send/discard and input backpressure during work.
   [Queued steering](CONVERSATIONS.md#steering-during-work) now binds active chat
   refinements to their task and preserves unanswered intent through explicit
   resume. The [interactive terminal](CONVERSATION_TUI.md) now opens by default
   for terminal chat/resume, with an editable composer, scrollable transcript,
   review expansion and status bar. Bare `mos` now launches in the current workspace
   with built-in recorded responses and private default storage; `-C` selects a
   workspace and `mos resume --last` returns without repeating paths. Initial
   positional prompts, a resume picker and live setup remain planned.
   Directory selection/visibility and separate user/project memory are now explicit
   requirements in plan §16.0.1–16.0.2. Deliver scoped memory inspection, editing,
   remember/forget and disable controls with precedence, project isolation and
   retention tests. The first [memory implementation](CONVERSATION_MEMORY.md) now
   provides private owner/project storage, explicit CLI management, startup loading,
   in-session inspection and changed-memory guards before dispatch/resume. Directory
   status stays visible. Explicit `/memory refresh`, `/memory off` and resume refresh
   now persist the selected context while preserving consumed recording exchanges
   and historical memory. Natural-language memory changes, project-root discovery
   and the directory picker remain planned.
   [Snapshot budgets](CONVERSATION_STORAGE.md) are now configurable per session,
   with visible usage and a separate bounded catalog scan override. The 2 MB default
   remains an interim preview limit. Plan §17.5 now sequences incremental records,
   paginated listing/transcript reads, independent context/retention budgets,
   explicit migration and recovery tests before lifting the message cap.
   The first [SQLite adapter](CONVERSATION_SQLITE.md) now implements opt-in
   incremental message/artifact writes, atomic saves/deletes and bounded metadata
   pages with generation-bound cursors. Explicit same-root JSON-to-SQLite migration
   now preserves exact state and source files, with dry-run sizing and verified
   retries after transaction interruption. The transcript CLI now reads bounded
   text pages using saved entry hashes and stale-cursor guards, with explicit
   preparation for legacy indexes. SQLite's terminal now browses those pages with
   F5, Page Up/Down and F6 reload, retaining one page and preserving the draft.
   F7/F8 and `session-artifact` now expand one explicitly selected memory/review
   artifact with snapshot binding, integrity checks and a separate byte budget.
   A separately verified resume checkpoint now supports `resume --inspect` with
   the last four messages, all queued/running work and required steering ancestors,
   under a fixed record-read budget. It leaves artifacts unexpanded and performs
   no recovery. Routine saves reuse a verified checkpoint and skip unchanged writes.
   SQLite controllers now retain historical artifact references and stream stored
   bytes when saving, preserving canonical hashes without rebuilding old artifact
   values. Queued reviews hydrate one admitted packet at execution; at most the
   latest result stays decoded for the renderer. Initial loads and external commits
   now verify historical entries one at a time under a separate input bound, then
   stream the exact snapshot hash and logical size. Active memory/recording values
   remain decoded. Chat context uses a text-only selection
   interface and a separately saved byte budget, checked before an attempt is
   consumed. It preserves completed history and steering, and pauses oversized
   queued work with required/available byte counts. Per-launch memory/recording limits
   now admit SQLite header sizes before either artifact is fetched, including legacy
   loads, and bound recording-file reads. Controller recovery, refresh and dispatch
   check canonical selected inputs; limits leave saved hashes unchanged. Size/hash
   checks now stream canonical JSON and reuse the recording fingerprint within an
   operation; nested mutations are checked anew at the next boundary. Working saves
   now encode each packed record once and reuse its bytes/digest for admission and
   persistence; cold resume skips redundant preparation of verified entries. Runtime
   revalidation now checks a fresh native data tree without a whole-state JSON
   buffer, including full schema validation of the excluded review cache. Working
   saves now preflight exact logical size from record structure and artifact lengths;
   a current checkpoint permits capacity rejection before artifact reads or writes.
   Admitted saves still stream all logical history and verify the preflight size.
   Repeated small archived artifacts can now reuse verified chunks within a 64 KiB
   cache for that save, reducing repeated disk reads without carrying payloads
   between operations. Queued message text now has a per-launch UTF-8 byte budget
   checked before saving new chat, steering or review-prompt submissions. Rejection
   preserves queued work, attempts and message drafts; tighter resume limits allow
   existing work to run or be cancelled. Typed `/steer` and `/review` submissions
   now retain editor text until durable admission, including rejection for missing
   prerequisites, while stop/quit still cancel pending handoffs. `/context` now
   previews selected turn sources, steering ancestry, omissions and canonical
   context usage through the same projection as dispatch, without saving or
   starting work. This metadata preview is versioned and ephemeral; durable
   request-selection records and visible compaction remain planned. Smaller
   text/record transitions, bulk migration and the long-session acceptance gate
   remain open.
   Mid-request interruption and live review
   remain open.
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
   conformance attestation are now implemented. Broker audit schema 4 preserves
   terminal failures, elapsed latency, and allowlisted failure stage/category without
   retaining raw provider diagnostics; a distinct inert assembler requires exact
   blinded-batch coverage without issuing gradeable or scoreable live results. A
   pre-registered, freshness-bounded Ed25519 observer receipt can now authenticate one
   successful credentialed probe while reverifying the exact authorization, audit,
   ledger, and blinded route. It still denies provider authorship, billing, failure
   send proof, complete-batch conformance, conversion, and scoring. A no-send ceremony
   now derives that exact policy and makes the paid-capable command recheck request,
   spend, ledger entry, audit path, installed SDK, and validity before API-key access.
   An independent short-lived Ed25519 authorization now binds explicit blinded
   transfer and maximum spend to that exact policy, must be disjoint from observers,
   and is verified in addition to local consent before API-key access. The
   conformance builder now explicitly binds storage, truncation, service tier,
   streaming, and background controls, and the spending boundary rejects rather than
   rewrites conflicts. One independently authorized and observed live
   `gpt-5.6-luna` low-effort assignment has now passed that exact path with a settled,
   unblocked ledger and authenticated one-assignment receipt. Provider authorship,
   billing, complete-batch conformance, quality, conversion, scoring, promotion, and
   activation remain denied. Metadata-only readiness can now check each exact
   registry model independently without generation or spend authority, but those
   receipts and one successful probe cannot substitute for repeated conformance.
   The remaining three model identities are now visible, and a public hash commits
   the private deterministic selection, exact rate assumptions, token ceilings, and
   one fresh shared $0.15 ledger for five remaining profile probes before paid
   outcomes exist. This commitment grants no execution authority. The frozen live
   gate required three consecutive, precommitted, distinct authenticated successes
   in each of six exact profiles (18 total), complete failed-attempt retention, and
   the five named operational/provider failure boundaries in
   `OPENAI_LIVE_CONFORMANCE_GATE.md`. All 23 execution positions and the offline
   lineage-wide aggregate report passed on 2026-09-09. The report reauthenticated 20
   successful exchanges, counted only the 18 qualifying records, and retained
   literal false conversion, quality, scoring, promotion, activation, and
   additional-request authority. A separately reviewed offline converter now pins
   that exact aggregate digest and projects only its 18 qualifying receipts and
   matching artifacts into a private 18-of-360 partial calibration seed. The seed is
   deliberately incompatible with `RawResultSet` and fixes complete-batch coverage,
   quality, grading, scoring, promotion, activation, and another request to false.
   A credential-refusing offline campaign planner now binds the exact 342-request
   remainder in frozen batch order, six current cache-write-aware standard-rate
   token envelopes, and a $15.377973 aggregate maximum without embedding briefs,
   reserving spend, or granting execution. The shared spending controller now has
   backward-compatible schema-2 cache-write-aware worst-case reservation and exact
   settlement, including fail-closed usage validation; this is fixture-validated
   infrastructure, not campaign authority. A credential-refusing offline boundary
   now fully reverifies those sources and derives/authenticates an independently
   signed, short-lived decision for one exact sequence, provider request, schema-2
   spend envelope, ledger, and fresh audit identity. A separate credential-refusing
   command now fully reverifies that lineage, requires explicit transfer and spend
   consent, and atomically consumes the exact ledger entry into a worst-case held
   reservation without issuing a broker grant or send. The next credential boundary
   must reverify the held preparation and require fresh same-invocation consent before
   key access. Then run the remaining repeated
   backend × model × effort matrix on clean and defective samples only through fresh
   request, transfer, and spend authority.
   Learn and freeze an interpretable difficulty-routing policy only after held-out detection,
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
   reasoning-free result with complete settled lineage. The independently reviewed
   conformance request boundary now includes explicit generation-mode controls and
   rejects post-authorization semantic rewrites. One separately authorized live
   blinded assignment has passed the evaluation broker boundary and received a fresh
   observer signature, but it is not a skill-runtime publication and grants no
   runtime authority. Next, run separately authorized credentialed conformance
   against the exact skill-runtime transaction/publication boundary. A signed,
   freshness-bounded observer attestation can bind that run to its verified
   publication without claiming authorship, billing, or quality. A signed rolling
   publication-history checkpoint can now detect rollback against a separately
   retained prefix, while external retention and newest-checkpoint delivery remain
   operator responsibilities. Independently signed aggregate billing evidence can now
   require exact usage/cost agreement for a complete, exclusive OpenAI Admin API scope
   while reverifying the full conformance and publication lineage. Documented cost
   exports remain daily and do not carry response IDs, so exact request attribution,
   invoice finality, and ledger release remain denied. A separate explicit-consent,
   credential-owning collector now strictly retains bounded complete Admin API pages
   and feeds the signable metadata path while recording that one-minute request count
   does not prove all-day API-key exclusivity. Next, run separately authorized real
   conformance and collection; fixture validation is not provider conformance.
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

## Remote MCP connections

User-directed addition, 2026-09-09: extend the implemented explicit local stdio
client so users can register their own hosted MCP URLs and select tool permissions.
Owner: Josh Myers. Deliver CLI/configuration support first, then reuse it in the
conversational interface. [Plan §13.3](mos-eisley-plan.md#133-remote-mcp-connections--planned-m11a-and-m11b)
defines implementation scope and blocking acceptance tests:

1. **M11A, implemented on the feature branch:** Streamable HTTP with securely referenced tokens, approved network
   destinations, bounded streaming, existing tool/schema policy, cancellation and
   explicit uncertain-write outcomes. Verify with a remote fixture and the installed
   client; retain stdio compatibility.
2. **M11B, implemented for pre-registered public clients:** OAuth discovery/login, secure user/server credential
   storage, scope authorization, refresh, reauthentication and logout. Verify
   malicious discovery/callbacks, denied access and concurrent credential isolation.

See [M11A verification](MCP_HTTP_VERIFICATION.md) and
[M11B verification](MCP_OAUTH_VERIFICATION.md). Other OAuth registration methods
remain unsupported.
The [schema compatibility slice](MCP_SCHEMA_VERIFICATION.md) now provides bounded
local references, local constraint checks and explicit JSON argument wrappers.
Unsupported schemas still fail closed. Paid models using connected
tools require the analytical-agent workstream's transfer, spend, retention and
whole-run limits. Neither stage enables paid tool calls or critic access, or
deploys an outward MCP service.

The saved `docs/mos-eisley-plan.md` is design history including its adversarial review.
Current implemented behavior is defined by the project brief, ADR and tests.
