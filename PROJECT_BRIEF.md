# Project Brief

- Problem and affected users: developers need independent, evidence-backed review
  of code changes across competing model providers without sharing author history.
- Implemented milestones: explicit brief -> recorded critics -> dedupe -> recorded
  judge -> policy verdict, plus a provider-neutral multi-turn agent loop using an
  inert fixture tool. Both paths produce private, content-verified offline replays.
- Conversation preview: a recorded text terminal now supports contextual follow-ups,
  queued input, cancellation, private local snapshots and explicit same-owner,
  same-workspace resume, metadata-only listing, latest-session selection and
  exact-snapshot deletion. Explicit recorded review now returns a retained report
  and contextual summary while keeping critic requests separate from chat history.
  Bounded multiline drafts support explicit send/discard during active work.
  Queued steering preserves task links and unanswered user intent across resume.
  The first full-screen terminal now provides multiline editing, a scrollable
  transcript, review expansion and persistent status using the same controller.
  Bare `mos` opens it in the current workspace with a built-in recorded preview
  and private default storage; `mos resume --last` reopens the latest session.
  User/project memory now has private scoped storage, explicit CLI management,
  startup loading, `/memory` inspection and stale-memory dispatch/resume checks.
  Explicit refresh/off controls now persist the session selection, preserve earlier
  request context and support resume without replaying consumed recording exchanges.
  A persistent directory header and `/directory` inspection show the workspace.
  Per-session snapshot budgets are configurable up to 32 MB with visible usage;
  an opt-in SQLite backend now writes incremental message/artifact records and
  provides bounded metadata pages. Explicit single-session JSON-to-SQLite migration
  now previews sizing, verifies the exact import and preserves the source. A separate
  transcript CLI now reads verified text pages with bounded payload reads and
  unexpanded artifact references. SQLite's terminal now uses those pages for F5
  history browsing, with background reads and draft-preserving navigation.
  F7/F8 and a separate artifact CLI now explicitly open one verified memory or
  review artifact, with an independent read budget. A derived resume checkpoint
  now supports read-only `resume --inspect`, selecting recent messages, unfinished
  work and steering ancestry without loading artifacts. Routine SQLite transitions
  now reuse verified checkpoints and skip unchanged row writes. SQLite controllers
  release historical artifact values after full verification and stream retained
  bytes when saving. Queued reviews hydrate one admitted packet at execution;
  at most the latest review result stays decoded. Initial loads and external commits
  verify historical entries one at a time under a separate input bound and stream
  the exact snapshot hash, avoiding full-history artifact accumulation.
  Chat context has a separately
  saved byte budget and text-only history selection; admission rejects oversized
  requests before consuming attempts and preserves queued work and steering.
  Per-launch active memory/recording limits now reject oversized SQLite header
  inputs before hydration and bound recording-file reads; recovery/refresh/dispatch
  also admit selected inputs. They preserve saved hashes and do not expand storage,
  memory-content or provider bounds. Size/hash checks now stream canonical JSON and
  reuse the checked recording digest within startup and refresh, avoiding complete
  byte buffers without caching model identities. Smaller state transitions, bulk migration and
  longer conversation limits remain planned under plan §17.7.
  Live conversation/review, advanced terminal features and remote
  session storage remain open; see `docs/CONVERSATIONS.md`.
- Provider preview: OpenAI Responses API adapter and opt-in single-prompt command;
  the private owning-library Luna/low critic/judge profile has completed its exact
  three-slot G2 qualification, while public launch and automatic activation remain
  separately gated.
  The private owning-library review path has one successful bounded standalone
  Luna/low campaign at `b3357aa`: two valid critics preserved threshold-two quorum
  when one critic produced `invalid_evidence`, the judge returned `accept`, and the
  signed observation replayed from complete retained evidence. A later exact
  `0010970a` production image completed an earlier formal three-slot campaign;
  all slots qualified operationally and reconstructed with complete local settlement
  and cleanup. Its `reject`/`revise`/`reject` content verdicts identified an overbroad
  preparation window and ambiguous revision wording. Both are corrected offline by
  retaining 10 minutes for ordinary calls and requiring a sealed `formal_campaign`
  scope for 30 minutes. The old exact-commit campaign does not authorize launch of
  the corrected artifact. The later corrected commit `3b32f14` and production image
  `sha256:3f67fa22ae6ede838269a292ad507e6441d6a5d084fbf5a2c6077ea125be8653`
  completed a wholly fresh sealed campaign with three qualifying `accept` verdicts,
  32,226 micro-USD settled, zero unresolved entries, complete worker cleanup and
  accepted independent reconstruction. This closes G2 qualification but creates no
  launch decision; no public live-review CLI is enabled.
- Routing target: choose model and reasoning effort from prompt difficulty using a
  versioned policy learned from blinded backend × model × effort evaluations. Role
  defaults provide hard minimums and conservative fallbacks; uncalibrated or
  out-of-distribution prompts never silently receive a weaker route. Automatic
  routing remains disabled until data supports it. The offline foundation now
  creates content-addressed sweep plans and exact-coverage calibration/holdout
  reports. Recorded execution now separates backend-visible briefs from labels and
  grader-visible content from route identity, then binds adjudicator provenance. It
  does not call a live provider or learn a policy. Statistical gates now use declared
  independent groups and simultaneous bounds across the planned comparison family;
  repeated runs cannot inflate the independent sample count. Reports explicitly
  deny promotion readiness.
- OpenAI conformance prerequisite: calibration conversion remains disabled until
  three consecutive, precommitted, distinct authenticated successes exist for each
  of six exact model/effort profiles (18 total), every failed attempt is retained,
  and the five named live/controlled failure boundaries pass. The current evidence
  contains one qualifying Luna/low success and a five-profile one-probe commitment.
- Grading: decisions bind each emitted finding by index/hash, identify matched
  defects or false positives, and retain unresolved findings. Two-grader comparison
  reports disagreements without automatically resolving them or asserting independence.
- Success criteria: documented CLI works from the built wheel; missing quorum,
  malformed evidence and malformed tool histories fail closed; identical recordings
  reproduce identical results; strict typing, tests, >=85% branch-inclusive coverage,
  packaging and CI are green.
- Data connection: explicit stdio and Streamable HTTP MCP discovery/calls plus an agent
  dispatcher support the external data-mcp server. Operator config selects tools
  and write capability; Ana Lite can use a separate analysis server profile.
  Schema compatibility adds bounded local references, local constraints and JSON
  wrappers while preserving validation and explicit write grants.
  OAuth supports explicit public-client PKCE login, native-keychain storage, refresh
  and logout. The opt-in analytical command exposes read-only MCP tools to OpenAI
  under whole-run spending limits, with checked cells and optional private evidence.
  Offline analytical evaluation compares reviewed expectations without provider calls.
  Explicit raw mode supports the comparison arm through source discovery and SQL
  with no promoted semantic catalog and the same spending/evidence controls.
  Frozen comparison schedules balance arm positions and check recorded execution
  order offline; failed/missing assignments retain unknown timing.
  The original one-prompt and critic workflows expose no MCP tools. See
  docs/MCP_DATA.md and docs/ANALYSIS_EVALUATION.md.
- Non-goals for this phase: public or automatically activated live adversarial
  review, general machine tools, sandboxing, test execution, repository config,
  GitHub writes, author agents, advanced TUI features and model pricing.
- Runtime: Python 3.12+, uv, macOS/Linux; non-root container for operational use.
- Inputs: user-selected JSON files, bounded before parsing. At most eight critics,
  fifty findings per critic; request budgets and 10-second call deadlines enforced.
- Data: recorded workflows stay local. `openai-run` sends only named prompt and
  instruction files after acknowledgement and never stores its environment key.
  Run files mode 0600 and new run directories mode 0700. Manual retention.
- Planned data contract: retain conversations and evidence in user-selected local
  or cloud storage with enforced per-user ownership. No cross-user aggregation,
  including anonymized model-selection statistics. Fresh sessions automatically
  reuse the same user's minimal selection aggregates; explicit user/project memory
  adds explicitly curated preferences and facts with scoped inspection, editing,
  deletion and disable controls (plan §16.0.2). Full saved conversations require
  explicit resume/inspection. Advanced memory controls, remote adapters and
  comprehensive enforcement remain
  unimplemented; see plan §17 and the roadmap.
- Recovery: run artifacts are authoritative. Missing/invalid manifests reject
  replay; an unavailable SQLite index does not discard completed evidence.
- Failure scenarios: fabricated evidence, unknown judge IDs, missing critics,
  oversized files, symlinks/FIFOs, corrupted runs, malformed tool pairing, reused
  call IDs, adapter/tool timeouts, iteration/tool exhaustion and cancellation.
- Owner: Josh Myers. Production rollout and quality calibration remain future work.
- Reviewed extension direction, 2026-09-08: immutable plan clauses and sealed fresh
  readings, independent test derivation with full-package/binding controls, bounded
  correction and independently measured whole-task damage/cost. Fixed routes and
  full judging remain the baseline; lookup/cascade experiments precede any learned
  policy. Proxy outcomes never replace verified labels or owner-scoped data rules.
  See `docs/PROJECT_REVIEW_2026-09-08.md` and plan §26 for findings, dependencies,
  sample-size feasibility, and remaining runtime gates. The G0 offline record,
  cumulative-measurement, profile-diagnostic and private-replay contracts are now
  implemented with deterministic negative fixtures. G1 now connects scoped profiles,
  context classification and selected tool views to conversation request admission
  without granting ambient authority. Continued work units own exact private profile
  material that is reconstructed and rechecked from the checkpoint archive, and
  durable task boundaries close
  through a private revision-checked checkpoint store with a text-free conversation
  receipt. Explicit fresh-context continuation now claims one exact next action for
  one fresh session and rechecks workspace/test freshness before dispatch while
  preserving lineage and cumulative ledgers. Visible author compaction now binds
  untrusted summaries and source-backed material to retained originals, preserves
  exact user instructions/steering, and records every compacted position in
  schema-4 admission. Advisory context pressure now freezes exact category bytes,
  capacity, boundary growth and executed-tool diagnostics in schema-5/6 admission,
  with explicitly unavailable provider-token counts and no automatic action. Later
  gates remain planned; see
  `docs/G0_MILESTONE_REVIEW.md`,
  `docs/G1_SCOPED_ADMISSION.md`, `docs/G1_CHECKPOINT_CLOSURE.md` and
  `docs/G1_FRESH_CONTEXT_CONTINUATION.md`, `docs/G1_AUTHOR_COMPACTION.md` and
  `docs/G1_CONTEXT_PRESSURE.md` and
  `docs/G1_WORK_UNIT_PROFILE_ACQUISITION.md`.
- G4 offline boundary, 2026-09-24: a canonical blind reviewer-test package now binds
  exact plan/interface/rubric/creator reference identities, complete declared test
  bytes and collection expectations while denying execution, implementation binding,
  repository/VCS mutation, credentials, network, provider use, correction and
  acceptance. Unsafe filesystem inputs, unselected tests, vacuous counts and direct
  undeclared skip/xfail markers fail closed. This does not authenticate independence
  or approval and does not satisfy the later binding, containment, execution,
  correction or final-review gates. See `docs/G4_REVIEWER_TEST_PACKAGE.md`.
- Architecture choices: see `docs/adr/0001-offline-foundation.md`,
  `docs/adr/0002-canonical-agent-protocol.md`,
  `docs/adr/0003-openai-first-provider.md` and the proposed
  `docs/adr/0004-empirical-difficulty-routing.md`.
