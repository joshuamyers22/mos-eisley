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
  now previews sizing, verifies the exact import and preserves the source. Paginated
  transcript loading, bulk migration and longer conversation limits remain planned
  under plan §17.5.
  Live conversation/review, advanced terminal features and remote
  session storage remain open; see `docs/CONVERSATIONS.md`.
- Provider preview: OpenAI Responses API adapter and opt-in single-prompt command;
  one independently authorized Luna/low assignment has passed credentialed
  conformance, while complete profile and failure-boundary conformance remains open.
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
- Non-goals for this phase: live adversarial review, general machine tools,
  sandboxing, test execution, repository config, GitHub writes, author agents,
  advanced TUI features and model pricing.
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
  explicit resume/inspection. Advanced memory controls, remote adapters and comprehensive enforcement remain
  unimplemented; see plan §17 and the roadmap.
- Recovery: run artifacts are authoritative. Missing/invalid manifests reject
  replay; an unavailable SQLite index does not discard completed evidence.
- Failure scenarios: fabricated evidence, unknown judge IDs, missing critics,
  oversized files, symlinks/FIFOs, corrupted runs, malformed tool pairing, reused
  call IDs, adapter/tool timeouts, iteration/tool exhaustion and cancellation.
- Owner: Josh Myers. Production rollout and quality calibration remain future work.
- Architecture choices: see `docs/adr/0001-offline-foundation.md`,
  `docs/adr/0002-canonical-agent-protocol.md`,
  `docs/adr/0003-openai-first-provider.md` and the proposed
  `docs/adr/0004-empirical-difficulty-routing.md`.
