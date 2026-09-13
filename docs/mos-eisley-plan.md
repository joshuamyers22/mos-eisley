# `mos-eisley` — Multi-Provider Adversarial Review Harness

**Working name.** A conversational coding agent spanning Claude, GPT, and Gemini, with real machine access — filesystem, shell, local git, GitHub — and integrated adversarial review by competing agents operating without prior context. The primary interface is a persistent terminal conversation following Codex CLI interaction conventions.

This document includes the original design and subsequent amendments. Required
corrections in §23 and accepted changes in §24 supersede conflicting earlier
examples and milestone tables. The user-directed conversational product decision
in §16.0 supersedes earlier treatment of the TUI and session resume as late
convenience features; capability and quality gates still apply. The user-directed
storage and isolation contract in §17 supersedes conflicting storage, aggregation,
and team-export examples throughout this design history. Current implementation
status is tracked in
`docs/ROADMAP.md`; planned modules and commands below are not availability claims.

**Integrated review, 2026-09-08:** §26 incorporates the reviewed adaptive-reasoning
and adversarial-loop proposals and supersedes their conflicting defaults. The
[project review](PROJECT_REVIEW_2026-09-08.md) distinguishes verified implementation
from planned contracts. The revised [routing design](adaptive-reasoning-routing.md)
and [loop project plan](adversarial-review-loop-project-plan.md) supply detailed
acceptance criteria; §26 and the roadmap define their delivery order.

**Session-shape integration, 2026-09-13:** the user-directed adoption of
`codex-session-shape-guide.md` adds the task lifecycle in §6.7 and its G0/G1/G3
acceptance gates. These are planned runtime changes. The guide's numeric heuristics
are evaluation candidates, not provider limits. Active contracts below supersede
historical context examples; detailed storage and skills/provider implementation
history is now linked from §§17.7 and 25. Future updates keep current contracts and
open gates here, implementation status in the roadmap, and execution history in
the linked records.

---

**Delivery workflow, user direction 2026-09-11:** stack related jobs into a bounded
review batch and run focused tests as each job lands. Test affected security,
storage and identity boundaries immediately. Run full quality checks once against
the combined batch before publishing, with required CI, secret scanning, dependency
audit and container gates before merge. Failures block dependent changes; later
code changes require fresh applicable checks and final-revision validation. Keep
test coverage and security gates intact while avoiding a full run per small job.
See [contribution workflow](../CONTRIBUTING.md).

## 1. Goals and non-goals

### Goals

1. **One agent loop, three providers.** Anthropic, OpenAI, and Google reachable through a single canonical message/turn type, with no provider's wire format leaking into the core.
   Each provider must be usable as creator, critic, or judge through roster
   configuration; no role is permanently assigned to a vendor (§7.7).
2. **Real machine control, safely.** Kernel-enforced sandboxing with per-OS backends, an approval policy, and capability tiers per role.
3. **Conversation as the primary workflow, with integrated adversarial review.** The user explores code, plans, requests changes, and discusses results with one persistent assistant. On a review request, N independent critics on different models review a frozen artifact blind and a judge adjudicates; the assistant brings the results back into the conversation. Blindness is enforced structurally, not by prompt.
4. **Local git and GitHub as first-class integrations.** Worktree-per-agent, structured patch application, PR review posting.
5. **Codex-style context budgeting.** A hard session cap well below the model ceiling, explicit output reservation, headroom buffer, per-role compaction policy.
6. **Per-task reasoning effort.** A canonical effort ladder mapped to each provider's parameter, bound to roles, with signal-driven escalation.
7. **Reproducibility.** Retained artifacts support the playback and replay guarantees
   in §23.4; findings remain traceable to their source context within the owner's
   configured storage and retention policy.
8. **User-owned data with configurable storage.** Preserve conversations and run
   evidence in storage selected by the owning user, locally or in the cloud. Never
   pool user data or model-selection statistics across users; new sessions do not
   automatically inherit previous conversational content (§17).
9. **Creator-led delegated coding.** The creator writes the plan and tests and owns
   the final result, obtains critic/judge review of both, approves them, and delegates
   at least one meaningful coding subtask to an implementation subagent. Optimize for clean,
   efficient code and total task cost, including review and rework (§§14.2.1, 15.7).

### Non-goals

- No custom model hosting, fine-tuning, or local inference in v1.
- No web UI. TUI plus machine-readable output only.
- Not a LiteLLM replacement — the provider layer covers only what this harness needs.
- Version 0.1.0 supports Windows hosts through a tested WSL2 deployment using the
  Linux backend; WSL1 and native Windows execution are excluded from 0.1.0.
- Version 0.1.1 delivers full native Windows parity under the platform release
  contract in §27. A successful import or conversation-only subset is not full
  Windows support.

---

## 2. Architecture

```
mos-eisley/
  core/
    types.py           # canonical Turn, Block, ToolCall, ToolResult, Usage
    loop.py            # agent loop, budgets, cancellation
    budget.py          # context budget resolution + accounting
    effort.py          # canonical effort ladder + resolution
    registry.py        # model registry
  providers/
    base.py            # Adapter protocol
    anthropic.py  openai.py  google.py
    conformance.py     # cross-provider test harness
    credentials.py     # typed credential references; never literal headers
    endpoints.py       # trusted endpoint policy + capability probes
  extensions/
    events.py          # typed lifecycle events and bounded observers
    subagents.py       # capability-bounded child-agent controller
    skills.py          # versioned prompt/rubric asset loader
  exec/
    policy.py          # policy-first model: paths, network, approvals
    seatbelt.py        # macOS backend
    bwrap.py           # Linux backend (bubblewrap + seccomp)
    landlock.py        # Linux fallback
    windows.py         # Windows restricted-token/Job Object backend (v0.1.1)
    none.py            # already-contained mode
    classify.py        # shell AST -> auto-approve | ask | deny
  tools/
    registry.py  schema.py  truncate.py
    builtin/           # read, grep, list, apply_patch, run_tests, shell
    mcp.py             # MCP client, tiered
  vcs/
    git.py             # worktrees, patch application, protected paths
    github.py          # gh CLI / REST, scoped tokens
    publisher.py       # isolated credential holder
  review/
    brief.py  critic.py  judge.py  findings.py  pipeline.py
  run/
    log.py  store.py  replay.py
  network/
    broker.py  cache.py # allowlisted fetch/search + provenance cache
  eval/
    mutate.py  metrics.py  sweep.py
  cli/
    main.py  tui.py  config.py
```

**Layer rules.** `core` and `review` never import `providers`. `review` never imports `vcs.github` — the credential holder is reachable only from `publisher`, and only through a schema-validated boundary (§19).

**Stack:** Python 3.12+, asyncio, Pydantic v2, Typer, Textual for the TUI, and
storage adapters with local files/SQLite by default and optional user-configured
cloud database/object storage (§17).

---

## 3. Canonical domain model

Define your own types. Do not adopt OpenAI's message format internally — it cannot losslessly carry Anthropic signed thinking blocks, Gemini thought signatures, or Anthropic cache breakpoints.

```python
class ReasoningBlock(Block):
    kind: Literal["reasoning"] = "reasoning"
    visible: str | None  # summary text, if exposed
    opaque: dict  # provider-tagged blob, replayed verbatim
    provider: str


class ToolCallBlock(Block):
    id: str  # harness-assigned, always present
    name: str
    args: dict
    native_id: str | None  # provider's own id, if any


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    blocks: list[Block]
    usage: Usage | None
    cache_breakpoint: bool = False
```

**Opaque reasoning state is the critical field.** Anthropic keeps previous thinking blocks in context by default on Opus 4.5+ and Sonnet 4.6+ (counting as input tokens); earlier Opus/Sonnet and all Haiku models strip them automatically. Gemini 3 tightened thought-signature validation specifically to improve multi-turn function calling. Dropping any of these degrades tool use silently or errors outright.

**Tool call IDs are harness-assigned.** Gemini matches `functionCall`/`functionResponse` by name, which breaks on parallel calls to the same tool. Mint your own, map bidirectionally in the adapter, never let a provider ID reach `core`.

---

## 4. Provider adapter layer

### 4.1 Mapping table

| Concern | Anthropic | OpenAI | Google |
|---|---|---|---|
| System prompt | separate `system` param | instructions / system message | `systemInstruction` |
| Tool schema key | `input_schema` | `parameters` | `functionDeclarations[].parameters` |
| Tool call | `tool_use` block | `tool_calls` / function call item | `functionCall` part |
| Tool result | `tool_result` on a **user** turn | `role: "tool"` message | `functionResponse` part |
| Reasoning control | `output_config.effort` | `reasoning.effort` | `thinking_level` |
| Reasoning state | signed thinking blocks | reasoning items | thought signatures |
| Sampling | rejected on Claude 5 (400) | mostly rejected on reasoning models | supported |

### 4.2 Tool schema subset

Author once, emit per-provider.

- Allowed: `object`, `string`, `number`, `integer`, `boolean`, `array`, `enum`, `required`, `description`
- Forbidden: `$ref`, `oneOf`, `allOf`, `anyOf`, `format`, `patternProperties`, recursion, tuple-typed arrays

Implementation status, 2026-09-09: the canonical subset above remains unchanged.
The MCP adapter on `feat/mcp-schema-compatibility` now expands bounded local
references, enforces supported constraints locally and wraps complex object
arguments in one JSON string when necessary. It reports the encoding and changes;
unsupported keywords/references still fail closed. See
[configuration](MCP_DATA.md#tool-schema-compatibility) and
[verification](MCP_SCHEMA_VERIFICATION.md). Paid-provider conformance remains a
separate gate.

Gemini's OpenAPI-subset dialect is the binding constraint. Validate at tool-registration time in CI, not on first call. **This applies to MCP-sourced schemas too** (§13) — many servers emit schemas Gemini rejects.

### 4.3 Sampling parameters are gone

Non-default `temperature`/`top_p`/`top_k` return 400 on Claude 5; temperature must be 1 or unset whenever thinking is enabled on any Claude model, and is deprecated entirely on 4.7+. OpenAI reasoning models generally reject sampling too.

**Consequence:** "temperature 0 for reproducible critics" is unavailable. Reproducibility comes from content-addressed briefs, pinned model IDs, and fixed effort — not sampling. Eval variance requires N repeated runs.

### 4.4 Conformance suite

Same brief + same tools through all three adapters, asserting: identical canonical `Turn` shape; tool call IDs round-trip a two-hop exchange; reasoning state survives a three-turn loop; every provider error maps to a `HarnessError` with a `retryable` flag; stop reasons normalize to `end_turn | tool_use | max_tokens | filtered | error`. Runs nightly against live APIs.

### 4.5 Endpoints and credentials

Custom and OpenAI-compatible endpoints are an adapter capability, not proof of
provider equivalence. Each endpoint must be named in trusted user/admin policy,
use TLS unless it is an explicitly approved loopback service, pass the conformance
suite, and declare its data-handling policy and supported model capabilities.
Resolve DNS and redirects through the network broker so a configured public URL
cannot pivot into a private or link-local address.

Authentication uses typed `CredentialRef` values (`environment`, OS keychain,
OAuth token store, or provider-native identity), never a free-form header map in a
project file. Repository configuration cannot add endpoints, choose credential
references, or inject headers. Login/logout commands modify only the selected
trusted credential store; tokens and resolved headers never enter manifests,
events, prompts, or replay artifacts.

### 4.6 Provider extensibility

The initial three providers are starting integrations, not a closed list. Define a
versioned provider-adapter interface and explicit registration mechanism so an
additional provider or backend can be added without changing the agent loop,
review pipeline, or selection engine. Keep provider SDK dependencies optional and
provider wire formats inside the adapter. The contract covers canonical requests
and responses, capability reporting, effort mapping, usage/cost accounting, bounded
timeouts and cancellation, and normalized errors; unsupported features must be
reported explicitly rather than silently approximated.

Register adapters through trusted user/admin configuration with stable provider and
backend IDs, compatible interface versions, and pinned implementation digests.
Executable adapter packages follow §24.3 supply-chain controls and execute only in
the provider/broker boundary with scoped credentials and network access. Project
files and model output cannot install or load adapters. An OpenAI-compatible API
still requires its own endpoint identity, capability record, and conformance evidence
under §4.5; compatibility does not confer equivalence or approval.

Ship a reusable adapter contract suite and development guide, including a fixture
adapter that demonstrates adding a provider without edits to core dispatch code.
Live eligibility requires endpoint/data policy, credentialed conformance, and
spending checks; automatic selection additionally requires §7.3 evaluation evidence.
Design these interfaces alongside the core provider work; deliver external adapter
loading later in E1 after the existing quality and containment gates. This is planned
extensibility, not a claim that arbitrary providers are currently supported.

---

## 5. Model registry

Versioned data file, printed by `mos models`.

```toml
[models."claude-opus-5"]
provider = "anthropic"
context = 1_000_000
max_output = 128_000
efforts = ["low","medium","high","xhigh","max"]
default_effort = "high"
thinking_retained = true
sampling_allowed = false
price_in = 5.00 ; price_out = 25.00

[models."claude-sonnet-5"]
provider = "anthropic"
context = 1_000_000 ; max_output = 128_000
efforts = ["low","medium","high","xhigh","max"]
default_effort = "high"
tokenizer_note = "~30% more tokens than Sonnet 4.6 for the same text"
price_in = 2.00 ; price_out = 10.00

[models."gpt-5.5"]
provider = "openai"
context = 1_050_000 ; max_output = 128_000
efforts = ["none","low","medium","high","xhigh"]
default_effort = "medium"

[models."gemini-3-pro"]
provider = "google"
context = 1_048_576 ; max_output = 65_536
efforts = ["low","high"]
```

Three facts everything downstream must respect:

1. **Gemini 3 Pro caps output at 65,536** — half the others. A flat 128k reserve is impossible there.
2. **Effort support is per model ID, not per family** on OpenAI. `xhigh` exists on 5.2+ and codex-max but not gpt-5.1; `minimal` only on the original GPT-5 line.
3. **Sonnet 5's tokenizer is denser** than 4.6's. Any shared cross-model token estimate is wrong; use each provider's counting endpoint.

Pin exact model IDs. Never ship an alias as a default.

### 5.1 Extensible model catalog

Adding a model on an existing backend should normally require a validated registry
entry and conformance evidence, not core-code changes. Key routes by provider,
backend/endpoint, and exact model ID so identical vendor model names on different
services cannot collide. Version the catalog schema and allow trusted user-owned
overlays with explicit precedence; reject duplicate or ambiguous route identities.
Record input modalities, tool/structured-output support, context and output limits,
effort mappings, counting method, reviewed pricing and freshness, lifecycle status,
and conformance provenance. Unknown capabilities are ineligible for requirements
that depend on them.

Provider catalog discovery is an explicit brokered refresh that proposes entries
for validation. It cannot silently enable a model, change defaults, or replace a
pinned model with an alias. `mos models` should expose configured routes, capability
and availability status, and why a route is excluded. Keep account availability
separate from static capabilities. Deprecation, removal, pricing changes, or material
capability drift must invalidate affected eligibility and calibration as appropriate;
retain prior snapshots for historical replay. New behavior beyond the adapter
contract requires a versioned adapter change rather than opaque registry code.

---

## 6. Context budget subsystem

### 6.1 The Codex arithmetic

The design borrows explicit session caps, output reservation and headroom from the
Codex reference workflow. Historical third-party token figures are not a Mos Eisley
contract. Resolve limits from the selected model's versioned registry entry and
trusted role configuration, validate them together, and reconcile estimates with
reported provider usage. Local byte admission and provider token admission are
separate checks; passing either one does not establish that the other fits.

### 6.2 Resolution

```python
def resolve_budget(model: ModelSpec, role: RoleConfig, effort: Effort) -> Budget:
    cap = min(role.session_cap, model.context)
    reserve = min(role.output_reserve_for(effort), model.max_output)
    usable = int((cap - reserve) * (1 - role.headroom_pct))
    return Budget(cap, reserve, usable, compact_at=role.compact_at)
```

Effort and budget resolve together, in one function, once (§7.4).

### 6.3 Accounting

Track system instructions, tool schemas, project guidance/activated skills,
selected memory/checkpoints, conversation turns (including retained reasoning),
and tool outputs separately. Count each serialized segment once and expose
subcategories without double-counting them. The project-instruction byte ceiling
remains separately configured; it is not a target instruction size.

Use the adapter's declared counting method, cache estimates only against exact
serialized inputs and counting-policy versions, and reconcile with reported usage.
Show unknown counts rather than treating bytes or unavailable usage as tokens.

**Admission:** following §23.2, 25% prefix usage is an advisory diagnostic, not a
universal failure threshold. Enforce configured hard maxima and fail when required
evidence, output reserve or headroom cannot fit. Diagnostics name the contributors,
required/available capacity and applicable policy. Warning thresholds cannot enlarge
budgets or silently omit required content.

### 6.4 Compaction policy — by role

Compaction can lose evidence across successive summaries. Measure retained coverage
and actual cache behavior; neither a summary nor a fresh child guarantees full
fidelity. The following role limits are Mos defaults subject to validated trusted
configuration, rather than claims about current Codex defaults.

Your critics **are** the subagent pattern:

| Role | Session cap | Compaction |
|---|---|---|
| `brief_builder` | 60k | n/a |
| `critic` | 120k | **none — fail closed** |
| `judge` | 200k | **none — fail closed** |
| `dedupe` | 120k | none |
| `author` | 400k | Codex-style, max 3, then hard stop |

A compaction inside a critic silently summarizes away the evidence under review. Overrun means a bug in brief construction or an untruncated tool result — raise `BudgetExceeded` with the category breakdown attached.

### 6.5 Cache-aware layout

Assemble `[stable: system + selected tools + applicable guidance + frozen brief]`
before volatile task state and turns. Use an explicit cache breakpoint where the
adapter supports one. Track exact segment identity and actual hits; a compaction
may change some segments while leaving others reusable. High cache-hit rates do
not excuse carrying irrelevant context through repeated requests (§6.7.6).

### 6.6 Context reduction is a lossy evidence transform

Adversarial review on 2026-09-10 of `context-management-plan.md` (input SHA-256 `9a2b957c352331df9304e4d23065022789456418816e5dd2362498860fea5c88`) accepts its direction but not its universal claims. Smaller, better-targeted context is a useful optimization hypothesis; it is not evidence that nothing relevant was lost. The numbers proposed there — five failures, 400 lines, a 5:1 delegation ratio, and compaction at 70% — are configuration candidates to evaluate, not protocol guarantees or release gates.

The adopted boundary is:

| Proposal | Disposition | Mos Eisley constraint |
|---|---|---|
| Bounded tool views | adopt | preserve an inspectable, immutable full-result artifact and disclose every omission |
| Isolated subagents | already present, narrow | a structured report is a claim with provenance, never a substitute for required evidence |
| External work state | adopt | typed, owner-scoped, revisioned, and advisory; retrieved text cannot gain instruction authority |
| Deliberate compaction | adopt for `author` only | derivative state with lineage; never permitted for `critic` or `judge` |
| Retrieval over stuffing | adopt typed/lexical retrieval first | no automatic trajectory retrieval; semantic retrieval remains deferred |
| Cache-friendly prompt order | adopt as optimization | cache behavior must not change semantics, access, retention, or freshness |

#### 6.6.1 Tool-result envelope

Every command or file-read result that may be reduced has two representations:

1. an owner-scoped, content-addressed full artifact, subject to the same redaction, retention, size, and access policy as its model-visible view; and
2. a typed bounded view containing operation identity, repository/workspace and revision, exit status, stdout/stderr identity, byte and line counts, encoding, artifact digest, reduction policy/version, omitted ranges/count, and a `complete` flag.

A filesystem path by itself is not durable evidence: files can mutate, disappear, cross an ownership boundary, or expose host layout. Required evidence binds the digest and metadata above. If the full artifact cannot be retained, the bounded view says so and may not claim completeness.

Reduction is reversible and evidence-aware. It may prioritize failing tests and head/tail excerpts, collapse ANSI/control noise, and de-duplicate only semantically equivalent records. It must not blindly remove repeated events, framework frames, library frames, generated files, lockfiles, or passing-test output: each can carry timing, supply-chain, coverage, or causal evidence. Ordering, stream identity, exit status, and omission metadata survive. A verifier can request bounded pagination or the pinned artifact; if required evidence cannot fit, the operation fails visibly instead of silently truncating it.

Read caching uses at least `(owner, project, workspace/repository identity, tree/revision, path and file identity, content digest, read policy/version)`. Mutations, symlink or metadata changes relevant to the operation, authority changes, and verifier freshness requirements invalidate the entry. “Unchanged bytes” alone is insufficient.

#### 6.6.2 Externalized state and subagent reports

Durable context separates `objective`, `constraint`, `decision`, `open_question`, and `work_item`. Each record carries source and authority, active/superseded status, owner/project, creation and verification revision, content digest, and provenance links. Updates are atomic and concurrency-safe. Privacy, retention, export, and deletion rules apply to these records exactly as they do to prompts and traces.

Model-generated notes, summaries, retrieved documents, tool output, and subagent reports are untrusted advisory data. They cannot promote text to a user constraint, authorize an action, certify evidence, or override a later user request. A decision record names who authorized it and why; superseded instructions remain distinguishable from active ones.

Subagent return schemas additionally carry status, scope attempted, sources and digests, completeness/coverage, uncertainty, unresolved conflicts, and budget usage. The parent or judge can inspect the bound artifacts and independently verify material claims. Delegation is chosen for isolation or parallel value under the aggregate budget, never solely because an estimated input/output ratio crosses a fixed threshold.

#### 6.6.3 Author compaction contract

An `author` compaction is an untrusted derivative, not a new authority source. Its manifest binds:

- input transcript/state digests and prior-compaction lineage;
- active objective and constraints with source/authority and supersession state;
- material decisions with rationale, approvals, irreversible effects, spend, and unresolved questions;
- current work item, referenced artifacts, and repository revision;
- categories and ranges dropped, before/after token counts, and compactor/model/policy version.

Exact sensitive text need not be copied into every prompt: a private, policy-governed artifact plus a digest-bound excerpt is preferable when it preserves reconstructability. The newest active user instruction wins over an earlier objective. Compaction never converts quoted or retrieved prompt-injection text into an instruction.

After compaction, Mos Eisley checks structural validity, artifact availability, authority ordering, revision freshness, and semantic coverage of a fixture set. Failure restores the pre-compaction state or stops with `BudgetExceeded`; it does not continue from a partial summary. Repeated compaction is capped by §6.4, and changing bound inputs invalidates the derivative.

#### 6.6.4 Retrieval and cache safety

The first retrieval implementation uses local typed filters and lexical search over the bounded project memory in §17.6; it does not require Postgres or embeddings. Every query binds owner/project, corpus and index version, revision/time cutoff, policy, and limit. Results include provenance, rank basis, coverage/overflow, omission reasons, and a bounded continuation mechanism so a hard cap cannot masquerade as completeness.

Semantic retrieval is a later, explicit capability. It requires evaluation for cross-owner leakage, stale embeddings, prompt injection, false omission, version drift, privacy/retention, and outcome quality before activation. Raw trajectory retrieval and automatic history injection remain out of scope.

Prompt caching binds exact serialized segment hashes, provider/model and tool-schema versions, and applicable policy. Cache hits are telemetry, not evidence of correctness. Secrets are not retained longer, and stale content is not reused, merely to improve hit rate.

#### 6.6.5 Evaluation and exit criteria

Instrument category-level input/output counts, artifact bytes, truncation/overflow, cache hit/miss, retrieval coverage, compaction count, latency, and cost without recording raw content merely to obtain a metric. Include the cumulative-request and handoff measurements in §6.7.6. Evaluate context policies on representative and held-out tasks using independent outcome quality, completion rate, verifier disagreement, missed-evidence rate, harmful-action rate, latency, and whole-task cost. “Tokens per success” alone rewards cheap false confidence.

Exit criteria:

- bounded views are reproducible from digest-bound full artifacts and disclose loss;
- owner/project isolation and instruction-authority tests pass for notes, reports, compactions, retrieval, and caches;
- required evidence survives or causes an explicit stop, never a silent continuation;
- threshold defaults are configurable and supported by evaluation rather than treated as universal constants;
- compaction and retrieval improve whole-task outcomes on held-out cases without regressing safety gates.

### 6.7 Bounded tasks and milestone context lifecycle

**Planned contract, adopted from the session-shape guide on 2026-09-13.** Implement
this through the existing controller, typed durable state, private artifact store
and admission path. It is not a second memory service or an automatic delegation
policy. The user-facing conversation may persist while its active model context
is reduced under visible, versioned rules.

#### 6.7.1 Shared work-unit contract

Author and child work use the same versioned record: task/work-unit ID and revision,
parent/dependencies, one outcome, scope and interfaces, applicable requirement IDs,
completion evidence, stopping condition, and permitted resource ceiling. Reference
the originating user direction, current policy and any required authorization;
the record itself grants none. Retain status as queued, active, completed, blocked
or cancelled, with a reason and evidence references for terminal transitions.

Size units around one component, reproducible defect, review question or other
coherent outcome. Simple questions retain direct-answer behavior and need no new
user form or review ceremony. A unit completes only when its required verification
has passed; exhausted budgets or unavailable evidence remain unresolved. Record
adjacent cleanup or follow-on features as separate work. Continue into an already
authorized dependent unit when its prerequisites hold, without another confirmation;
never treat a unit boundary as cancellation of the user's larger objective.

Each further inspection or verification pass identifies what it can resolve:
changed inputs, an unresolved failure, missing evidence, or a freshness requirement.
Reuse still-valid findings and evidence references. Repeated verification without
such a reason is a diagnostic; it cannot replace required checks or independent
review with a cached success.

#### 6.7.2 Milestone checkpoint and continuation

At a completed milestone, material objective change, or deliberate handoff, update
one bounded task checkpoint in place from §6.6.2 records. Capture the objective,
repository/workspace and branch, relevant revision and working-tree fingerprint,
main files, active decisions with rationale/source, completed work, verification
commands/results/revisions, untested claims, blockers and next bounded actions.
Keep a short ordered next-action view (normally three); preserve links to the full
outstanding-work set so omitted work cannot disappear. A 300–800-word view is an
initial editorial target, with configurable byte/token admission and explicit
overflow, not a guarantee that every task fits. Do not copy logs or transcripts.

Update only when durable state changes, atomically against the expected checkpoint
revision. Default storage is private and owner/project scoped (§17.6). Export to
`PROJECT_MEMORY.md` or another repository document is a separate explicitly
authorized, sanitized publication. A checkpoint is distinct from both automatically
loaded reusable memory and the SQLite storage-resume metadata in §17.7.

Provide an explicit continuation selection naming the checkpoint revision and next
work unit. A user request to continue that selected work supplies the selection;
do not add a second confirmation. A fresh session receives that bounded view,
applicable approved guidance and necessary evidence, without ambient old history.
Before execution, verify workspace, branch/tree, relevant files, evidence availability
and revision freshness. Mark old test results stale when their bound inputs changed;
do not silently carry them forward as a current pass. Apply later user direction
and resolve any material mismatch before dependent work.

Bind continuation to the original task ledger and lineage. Context/session changes
cannot reset spend, consumed attempts, correction/review counters, cancellation,
outstanding steering, approval expiry or uncertain side effects. Revalidate authority
and never replay an uncertain operation automatically. Commit the handoff and claim
the selected continuation atomically/idempotently before dispatch so retries or
concurrent resumes cannot create duplicate work. If required state or evidence
cannot be recovered, preserve the checkpoint and report the exact blocker.

#### 6.7.3 Context-pressure decisions

Extend `/status` and `/context` with per-category usage, available capacity, growth
since the last boundary, substantial tool-call count, repeated reads and compaction
count. Report byte and token estimates distinctly, including unavailable provider
counts. Advisories are bounded metadata events emitted on threshold crossings or
material changes, not another accumulating transcript.

Trusted configuration may trial the guide's 30–40% context usage and 20–30 substantial
tool-call heuristics. Define and version the denominator and substantial-call rule
in the evaluation policy; exclude UI polling/status inspection from that counter.
These trigger an assessment, not automatic stopping, new user approval or a child.
At a completed milestone, offer checkpoint-based fresh continuation. For the same
ongoing objective, use validated author compaction if permitted and useful. Hard
admission limits remain authoritative. Critics/judges never compact or inherit
author checkpoints, and repeated pressure grants no automatic delegation authority.

#### 6.7.4 Narrow evidence acquisition

Built-in search/read/diff/test interfaces default to scoped queries, bounded pages,
summary-first views and focused verification. Expose range/limit controls and
operation-specific summaries: test identities, exit status, actionable failure
excerpts and immutable evidence references. Preserve complete results under the
§6.6.1 artifact policy when retention permits; disclose missing originals and every
omission, and stop if required evidence is unavailable. A summary's brevity cannot
be treated as proof of completeness.

Batch independent read-only checks with separate operation IDs, output envelopes,
status and cancellation. Do not batch dependent checks, mutations or approvals.
Reuse conclusions/read results only while §6.6.1 identity and freshness checks hold;
required verification remains independent of an optimization cache.

#### 6.7.5 Task-scoped instructions and tools

At work-unit admission, materialize only applicable approved guidance, activated
skills and selected tool schemas. A versioned manifest records included rule IDs,
scope, source/digest, tool identities/schema digests, required/optional status,
selection reasons, omitted candidates and per-category size. Selection narrows the
trusted capability set; it cannot add authority. Required guidance or tools that
cannot fit or become available produce an explicit failure, not a silent omission.

Directory guidance follows explicit scope and §16.6 precedence. Nested files cannot
activate a template, broaden tools or override trusted policy. Keep root instructions
short and stable; put specialized rules near their scope and detailed explanations
in bounded, explicitly selected references. Treat 1–3 KiB for root instructions as
an editorial starting point, not a correctness limit. Advisory validation reports
oversized/duplicate rules and candidate temporary-state content with source locations;
semantic classification is best-effort and never silently deletes or rewrites rules.

Use a minimal default MCP/tool profile and select task-specific integrations only
within existing authority. Unselected schemas do not enter the model request, and
unselected servers do not start merely to build a prompt. Reuse approved catalog
metadata; if required discovery needs startup, perform it through the existing
authorized MCP boundary. Profile changes apply at safe boundaries and are pinned
per request. Release task-scoped server references on closure without stopping a
server still used by another task. Unused/overlapping integrations are diagnostics,
not grounds to remove a tool needed for required evidence.

Expose instruction-size and profile diagnostics through the future offline typed
doctor registry (§25.3) and template validation. No executable skill checks, network
probes, automatic config rewrites or new credential paths are introduced.

#### 6.7.6 Measurement and acceptance

Sum input over every actual model request, including repeated context, compaction,
handoff, child, review, retry and abandoned work. Split reported cached/uncached
input where available; retain unknowns and distinguish local estimates, admitted
requests and confirmed usage. Do not sum unique prompt bytes and call that total
input. Record repeated-read rate (same still-valid operation identity), original and
model-visible tool-output volume, checkpoint size, handoff/revalidation overhead,
and whole-task latency/cost. Metric payloads need no raw content.

G0 freezes schemas, counting definitions and deterministic negative fixtures. G1
demonstrates milestone completion → private checkpoint → explicit fresh-context
continuation → detection of changed repository state → verified completion, while
preserving outstanding obligations, aggregate budgets and critic isolation. Test
missing evidence, stale tests, changed instructions, concurrent/duplicate handoffs,
budget-reset attempts, required-tool omission and memory/checkpoint confusion.

G3 compares the existing selection policy with bounded units/checkpoints, narrow
tool views and task profiles on matched representative and held-out tasks, with
ablation where feasible. Freeze model/routes, rubrics, total budgets and quality
criteria before measuring. Include completion, missed evidence, stale-state errors,
verifier disagreement, harmful actions, latency and total cost. Promote defaults
only after preregistered quality/non-inferiority gates pass and cumulative context
or cost improves; inconclusive results retain the baseline. Fixture enforcement
alone establishes no live quality or savings claim.

---

## 7. Effort subsystem

### 7.1 The three ladders

| | Parameter | Levels | Default |
|---|---|---|---|
| Anthropic | `output_config.effort` | low, medium, high, xhigh, max | Sonnet 5: high |
| OpenAI | `reasoning.effort` | none, minimal, low, medium, high, xhigh, max (model-dependent) | gpt-5.5: medium |
| Google | `thinking_level` | low, medium, high (model-dependent) | — |

Effort is the control; adaptive thinking is the *mode* — `adaptive` is not a valid effort value. Manual budgets (`thinking: {type:"enabled", budget_tokens:N}`) return 400 on Sonnet 5 and Opus 4.7+. Opus 5 exposes the full ladder with `max` on top and converts additional effort into results more reliably than earlier Opus models, so the level chosen carries more weight. Gemini 3 replaced `thinking_budget` with `thinking_level`.

### 7.2 Canonical ladder and fallback

```python
LADDER = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]


def resolve_effort(model: ModelSpec, requested: str) -> str:
    if requested in model.efforts:
        return requested
    raise UnsupportedEffort(model.id, requested)
```

This is the planned strict selection behavior. The current low-level registry
resolver can return a lower effort with `substituted=True`; it is not a calibrated
route resolver or evidence that a role floor was met. Future dispatch must reject
that substitution for exact manual and calibrated requests. A fallback is a
separately configured eligible route with its own evidence, decision and reservation.

**Cross-provider effort is not comparable.** Gemini has three common levels where
Claude has five. A Gemini critic at `high` and a Claude critic at `high` are different
settings. API and subscription-backed clients for the same nominal model are also
distinct routes because their harnesses and entitlement behavior can differ. Never
read cross-route disagreement as a capability signal when settings were substituted;
the run log must surface that at analysis time.

### 7.3 Selection — empirically calibrated difficulty routing

Roles define a hard minimum and a conservative fallback, not a permanent route. The
normal path selects the least expensive eligible `(model, effort)` pair whose
held-out evaluation results satisfy the role's quality constraints for prompts with
the same observable difficulty profile. Manual model and effort selection remains
an explicit override.

Do not ship a hand-written score that equates prompt length with difficulty. Start
with an interpretable, versioned policy trained from the sweep in §18.3. Candidate
features must be known before dispatch and must not contain evaluation labels:

- role and requested output contract;
- input tokens/bytes, changed lines, files and language count;
- tool and structured-output requirements;
- deterministic risk tags such as authentication, concurrency, cryptography,
  migrations and public-API changes;
- whether the feature vector is outside the calibration distribution.

Each routing policy pins its feature-schema version, calibration-set digest,
candidate registry snapshot, provider backend and client version, primary metrics,
confidence method and decision thresholds. The run artifact records the requested
route, every eligible candidate, the resolved route and the reason. Subscription
routes intersect the calibrated candidates with the official client's current
entitlements; an unavailable cell is ineligible, not silently substituted. Missing,
stale or out-of-distribution policy data uses the conservative fallback or fails;
no route may fall below the role minimum.

Selection evidence derived from user runs belongs exclusively to that user (§17).
Aggregate only that user's model performance; never pool observations, derived
policies, or model rankings across users. Historical prompts and code are not
loaded into a new conversation to perform selection.

```toml
[role.critic]
minimum = { model_tier = "economy", effort = "low" }
fallback = { model_tier = "balanced", effort = "high" }
min_detection_lcb = 0.90
max_false_positive_ucb = 0.05

[routing]
policy = "routing-policy-v1.json"
on_uncalibrated = "role_fallback" # or "fail"
allow_model_substitution = false
```

An extra model-based difficulty classifier is not the initial implementation. Add
one only if a held-out comparison shows that its incremental routing benefit exceeds
its latency, cost and new failure modes. Until the first calibrated policy exists,
automatic routing is unavailable rather than intuition-backed.

Implementation boundary: seal the label-free feature manifest, numeric partition
boundaries, exact categorical fields, role allowlists, fallbacks, selection
objective and freeze-before-holdout rule before scoring. Every resulting profile
must have comparable clean and defective cases in both splits; sparse profiles fail
closed instead of being pooled after outcomes are visible. A content digest fixes
the design but does not prove when it was authored, so promotion also requires an
external append-only pre-registration attestation.

Profile calibration scoring must reverify the sealed study and authenticated grading
lineage, accept only the exact calibration observation matrix, and allocate confidence
across `profiles × routes × metrics × splits`. It emits no route selection and grants
neither promotion nor activation authority.

The freezer then applies the sealed role allowlist and cost-first objective to that
reverified calibration evidence. Any missing cost among quality-eligible permitted
routes makes the profile uncalibrated; use the sealed fallback or fail closed. The
frozen candidate policy records that holdout is unevaluated and cannot activate a
runtime route.

The implemented holdout boundary consumes a policy-keyed exclusive claim in an
existing private directory before scoring. It reverifies the frozen calibration
chain and the complete independent holdout chain, preserves every profile/route
score, and reports selected-route adequacy, under-routing, missed adequate
alternatives, fallback/fail-closed coverage, and cost/latency regret. Incomplete cost
coverage suppresses hindsight-cheapest and regret claims. This local claim is
crash-conservative but cannot prevent an analyst from copying data, selecting a new
claim directory, deleting state, or reading holdout outcomes elsewhere; independent
custody is still required. The report grants neither promotion nor activation.

Policy-level holdout acceptance thresholds are a separate pre-registered artifact
whose digest is pinned into the holdout claim and report. The unsigned deterministic
comparison cannot claim promotion readiness. A verification-only gate recomputes
both source chains and every threshold, requires a domain-separated Ed25519 signature
from an authority disjoint from graders and resolvers, and emits the only promotion-
ready receipt. That receipt still cannot authorize runtime activation.
Policy-level rates explicitly weight sealed profiles equally; they do not claim to
estimate the production traffic mix without a separately registered distribution.

The implemented activation-eligibility boundary then consumes only that authenticated
promotion. Three mutually distinct operational authorities, all disjoint from the
evaluation and promotion signers, sign: (1) exact route, cost, freshness, and control
requirements; (2) route-specific catalog, price, conformance, and drift assertions;
and (3) emergency-stop and revocation state. The readiness snapshot binds the signed
policy context, every selected route, and every required fallback without model or
effort substitution. The resulting receipt expires at the earliest input deadline
and grants neither runtime activation nor configuration mutation. These operational
values are signed attestations—Mos Eisley does not query or validate their sources—and
a still-valid older control sequence remains replayable without an external monotonic
latest-state anchor. Runtime preflight, atomic installation, rollback, and traffic
monitoring remain separate future gates.

The implemented runtime preflight adds a private append-only local control anchor.
Its pre-registered policy fixes a unique identity, activation trust-policy digest,
and the identities allowed to sign control state; that policy digest is bound by the
activation signer. Every update has a greater sequence and issuance time, hash-links
the prior entry, and may not remove revocations. Preflight reconstructs every earlier
evaluation and authorization gate and requires the exact latest anchored state within
a signed maximum age. It remains non-dispatching because first-state bootstrap,
whole-database rollback by the owner, and a state change after the check require an
external monotonic witness and atomic one-use dispatch protocol.

### 7.4 Effort ↔ max_tokens coupling

At high/xhigh/max with a tight `max_tokens`, you get a response that is almost entirely thinking followed by a truncated answer and `stop_reason: "max_tokens"`. Anthropic suggests starting around 64k `max_tokens` for Opus 4.7 at xhigh or max.

```toml
[effort_reserve]
low = 16_000 ; medium = 32_000 ; high = 64_000 ; xhigh = 96_000 ; max = 128_000
```

Raising a critic's effort shrinks its usable input. Higher effort also inflates context *growth* across a loop, since retained thinking counts as input tokens. Effort is a budget parameter as much as a quality parameter.

### 7.5 Escalation on signal

At most one capability escalation to an empirically qualified route. Triggers are
role-specific and externally observable: failed executable evidence for an author
or a preregistered experimental failure signal. Judges remain pinned in the initial
cohort and measurement path (§26.3); judge escalation requires a separately versioned
study. Evaluation labels never become live routing features. Schema
failure gets a bounded format-repair attempt at the same route; it is not evidence
that harder reasoning is required. A model's self-reported confidence never triggers
escalation by itself. Both attempts and the trigger are logged. Keep an escalation
only when held-out evaluation shows positive payoff after added cost and latency.
One same-route format repair is a separate allowance; all attempts, children and
correction cycles share the predeclared task budget. Uncertain provider delivery
does not permit resending. Recovery sequences are observational evidence, not
controlled counterfactual comparisons (§26.3).

### 7.6 Extensible selection strategies

Separate route eligibility from selection strategy. A trusted resolver first
filters the catalog by provider/data policy, current account availability,
capabilities and modalities, context/output needs, role minimums, conformance,
spending limits, and required evidence. A versioned selection interface then
receives the eligible route snapshot, permitted task features, role, user
preferences, and budget, and returns a concrete route and effort with a structured
reason or an explicit no-route result. The controller rechecks current eligibility
and reserves spend at dispatch; a selector cannot grant authority or call providers.

Support explicit manual selection, named per-role profiles with fixed routes and
fallbacks, and the empirically calibrated strategy in §7.3. Make the strategy
replaceable without rewriting provider adapters or the agent loop. Future selectors
may optimize cost, latency, or quality among qualified candidates, but each new
automatic strategy must pass preregistered held-out evaluation and activation gates.
Executable selector extensions use the same trusted registration, versioning,
revocation, and supply-chain controls as adapters, with no credentials or network
access. They receive only the owner's permitted features and selection aggregates
under §17, never another user's history.

Expose provider/backend, model, effort, and selection profile in the planned CLI and
conversation controls. Allow per-session defaults and explicit per-task/role
overrides within trusted policy; manual choices cannot bypass eligibility or spend
limits. Model switches occur at safe turn boundaries with an explicit context
handoff: never forward provider-specific opaque reasoning to a different route or
send conversation content to an unapproved provider. Preserve the frozen route for
an in-flight review. Unavailable routes fail visibly or use only an explicitly
configured, eligible fallback; record every substitution.

Record strategy ID/version/digest, registry snapshot, requested and resolved route,
effort, candidate exclusions, and decision reason in owner-scoped run artifacts.
`mos policy check` must explain selection using the same resolver without dispatch.
Verify manual overrides, new model registration, strategy replacement, stale
catalogs/evidence, unsupported modalities, budget exhaustion, route collisions,
fallbacks, and replay of recorded decisions. Define the interface with the routing
work; external selector loading belongs to later E1 and does not enable unvalidated
automatic routing.

### 7.7 Interchangeable creator, critic, and judge roles

**User-directed product requirement:** Anthropic, OpenAI, and Google must each be
eligible to supply the creator, critic, and judge through the same role contracts.
"Creator" is the user-facing planning, authoring, and integration role called
"author" elsewhere in this plan; it is not an additional competing controller.
Support explicit per-task rosters and evaluated selection policies that rotate
providers and models among these roles without changing pipeline code. Implementation
subagents have their own model/effort assignment and need not match the creator.
Interchangeability is a planned capability, subject to route conformance and role
requirements, not an assertion that every model has equal ability.

For the three-provider review profile, support all six assignments of the three
distinct providers to creator, critic, and judge. Keep creator transcripts and
implementation-subagent reasoning out of the independent critic's context. The
judge receives the frozen artifact and structured findings needed to adjudicate,
not the creator's private reasoning or provider/model identities. Switching roles
never merges contexts or grants extra authority. A same-provider creator and coding
subagent does not count as independent cross-provider review evidence.

Example requested profile: **Astra as creator; Luna with max thinking as the coding
subagent**, with eligible models from the other two providers as critic and judge.
These are user-facing example labels, not hard-coded production model IDs or a
claim of current availability. Resolve each label to an exact configured provider,
backend, model, and supported effort before use; expose the resolved roster and
reject an unsupported `max` request rather than silently weaken it. The critic and
judge assess the creator-written plan and tests before the creator approves
execution as specified in §15.7.

---

## 8. Tool layer

### 8.1 Registration and tiers

```python
@tool(tier=Tier.READ_ONLY, timeout=30)
def grep(pattern: str, path: str = ".", max_matches: int = 100) -> str:
    """Search for a regex pattern under path."""
```

| Tier | Tools | Roles |
|---|---|---|
| `READ_ONLY` | read, grep, list, git show/diff/log | critic, judge, dedupe |
| `TEST` | READ_ONLY + run_tests in sandbox | critic (evidence execution) |
| `WRITE` | TEST + apply_patch, write_file | author |
| `EXEC` | WRITE + shell | author, opt-in |
| `NET` | fetch, MCP servers with network | author, explicit allowlist |

**Enforced at dispatch, not by prompt.** A reviewer with write access is not a reviewer. This mirrors what production Codex review setups already do — pinning review profiles to `sandbox_mode = "read-only"` and `approval_policy = "never"` so the invocation cannot modify the filesystem or prompt mid-run regardless of prompt content.

Tier is a property of the *role*, not the request. An agent cannot escalate its own tier mid-run; escalation requires a new agent with a new context.

### 8.2 Output discipline

Use the typed bounded-view/full-artifact contract in §6.6.1 and scoped acquisition
defaults in §6.7.4. Head/tail excerpts alone are insufficient: retain operation and
stream identity, exit status, content digest and explicit omission/completeness
metadata. Full output stays in the private policy-governed artifact store when
retention permits, with bounded retrieval; a mutable path is not evidence identity.

---

## 9. Execution and sandboxing

Policy-first: the policy lives in `exec/policy.py` as data; OS-specific backends enforce it. Same policy, three enforcement mechanisms.

### 9.1 Sandbox modes

| Mode | Filesystem | Network |
|---|---|---|
| `read-only` | read anywhere permitted; no writes | denied |
| `workspace-write` | writes confined to writable roots | denied by default, allowlist opt-in |
| `danger-full-access` | unrestricted | unrestricted |
| `none` | no harness sandbox applied | inherited |

`none` is for when the harness is already inside a container or VM — relevant for your Linux boxes. Codex has the same escape hatch: it applies no platform sandbox but still communicates network-access state to tools and MCP servers, so the model knows what it can attempt.

### 9.2 Path policy

Precedence **Deny > Write > Read, most-specific-wins**. Writable roots scoped to the agent's worktree plus `/tmp`. Protected metadata — `.git`, `.mos-eisley`, `.agents` — forced read-only **even inside a writable root**. Read-deny globs expanded at policy-build time and **failing closed on malformed patterns**.

### 9.3 macOS backend — Seatbelt

Commands run via `sandbox-exec` with an `.sbpl` profile generated per mode.

- **Invoke `/usr/bin/sandbox-exec` by hard-coded absolute path**, never resolved from `PATH`. Path resolution is an injection vector and Claude Code/Codex both hardcode it.
- Profiles are Scheme-like policy files: `allow file-read*`, `deny network-outbound` with loopback and detected proxy ports permitted.
- For restricted read, append a curated platform policy rather than broadly allowing `/System` — broad allows defeat the point, but a naive deny breaks common toolchains.
- Seatbelt is formally deprecated by Apple but remains the only kernel-level option; treat it as a supported-but-fragile dependency and keep the `none` + container path viable.

**Bug not to replicate:** Codex's macOS profile blocks network unconditionally, ignoring `network_access = true` in config, so the only workaround users have is `--sandbox danger-full-access` — which drops *all* protections to get network. Make the network rule conditional at profile-generation time so opting into network doesn't cost you filesystem confinement.

### 9.4 Linux backend — bubblewrap + seccomp

Two-stage launch: `bwrap` establishes the filesystem/namespace view, then `PR_SET_NO_NEW_PRIVS` plus a seccomp-BPF filter locks down syscalls, then `execvp` the target.

- seccomp denies `ptrace`, `process_vm_readv`/`writev`, and `io_uring_*` unconditionally.
- In restricted-network mode it blocks all socket families **except `AF_UNIX`**. The AF_UNIX exemption is mandatory — without it basic shell operations break.
- **Landlock fallback** (kernel 5.13+) where bwrap is unavailable: read everywhere, write only to whitelisted roots plus `/dev/null`. Weaker, and it cannot restrict reads.

Deployment caveats to document in the README, because both will bite on your VMs:

- Ubuntu 24.04+ and other AppArmor-restricted distros may need `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0` for unprivileged user namespaces.
- Inside Docker, bwrap needs `CLONE_NEWUSER`, which many runtimes block. Running the harness in a container requires `SYS_ADMIN` and an unconfined seccomp profile — or use `--sandbox none` and rely on the container as the boundary, which is the cleaner choice.

### 9.5 Sandbox debugging

Ship `mos sandbox exec -- <command>` to run an arbitrary command through the active profile without a model in the loop. This is how you verify a toolchain passes enforcement before a real session, and it will save hours. On macOS, document the denial log predicate:

```
sudo log stream --style compact --info \
  --predicate 'subsystem == "com.apple.sandbox" OR process == "sandboxd"'
```

Denial detection is heuristic on every platform — a command that fails for an unrelated reason can look like a sandbox denial and vice versa. Surface the raw exit code and stderr alongside the harness's guess, never instead of it.

### 9.6 Externally contained profile and devcontainer

Ship a reference devcontainer as a reproducible compatibility and containment-test
target, not as a security attestation by itself. Pin the base image by digest, avoid
host Docker/SSH/editor sockets and ambient credentials, use an explicit mount list,
drop unnecessary Linux capabilities, enable `no-new-privileges`, and apply CPU,
memory, PID, disk, and output limits in the outer runtime.

At startup, the `none` backend must still print and record which boundary properties
Mos Eisley could verify and which are merely declared by the caller. Run the complete
positive and negative sandbox suite inside the reference image. If the runtime cannot
demonstrate a mandatory property, security-sensitive workflows fail closed rather
than treating the presence of `.devcontainer.json` as proof.

---

## 10. Approval policy and command classification

### 10.1 Policies

| Policy | Behavior |
|---|---|
| `untrusted` | prompt for everything not on the trusted allowlist |
| `on-failure` | run sandboxed; on sandbox denial, ask whether to retry unsandboxed |
| `on-request` | model asks when it judges it needs escalation |
| `never` | no prompts; sandbox denials are hard failures |

Sandbox mode and approval policy are orthogonal. The two combinations that matter:

- `workspace-write` + `on-failure` — the interactive default. Productive, and escalation is explicit.
- `read-only` + `never` — the review default. No prompts, no writes, safe unattended in CI.

Support a granular form (`approval_policy = { granular = {...} }`) so specific categories — permission requests, skill scripts — can fail closed while others still prompt.

### 10.2 Command classification

Deciding "is this shell command safe to auto-run" is harder than it looks, and heuristics are the weak point in every existing implementation.

Approach: parse with a real shell grammar (`tree-sitter-bash` or `bashlex`) and auto-approve **only** when all of these hold:

1. The AST is a single simple command (no pipes, `&&`, `;`, subshells).
2. No redirection, no command substitution, no process substitution.
3. The executable is on the trusted allowlist by absolute path.
4. Every path argument resolves inside a readable root after symlink resolution.
5. No argument matches a deny pattern (`--force`, `-rf /`, `sudo`, `curl … | sh`).

**Anything else asks.** Parse failure asks. Unknown executable asks. This trades convenience for a classifier you can actually reason about, and it degrades safely: the worst case is an extra prompt.

Cache approvals per `(command_hash, cwd, session)` so the same command isn't re-prompted, but never persist approvals across sessions — that turns a one-time decision into a standing grant.

---

## 11. Git integration

### 11.1 Worktree isolation

**Never operate on the user's checked-out working tree.** Every coding agent gets
an isolated Git worktree from a pinned base SHA through the trusted VCS broker.
Session worktrees persist across turns and resume; run completion alone does not
authorize deletion. Child worktrees may be disposable after their changes and
evidence are retained and the lifecycle checks pass. The user-facing creation,
repository grouping and cleanup contract is in [§16.0.4](#1604-repository-grouped-sessions-and-isolated-worktrees).
Separate checkouts prevent overlapping file edits; shared Git metadata still
requires broker coordination and the execution sandbox remains mandatory.

### 11.2 `.git` is protected

Read-only in every tier including `WRITE`. This is not tidiness — it closes a code-execution path:

- `.git/hooks/*` — writing a `pre-commit` hook is arbitrary code execution on the user's next commit.
- `.git/config` — `core.fsmonitor`, `core.sshCommand`, and `alias.*` all execute shell.
- History rewriting and ref deletion are unrecoverable in ways an agent shouldn't be able to reach.

Blocked by policy regardless of tier: `push --force`, `reset --hard` on non-agent branches, `filter-branch`, `branch -D`, `git config` writes, submodule init from URLs not already in `.gitmodules` at the base SHA.

### 11.3 Structured patch application

Expose `apply_patch(patch: str)` rather than letting the model shell out to `git apply`. The tool:

- validates patch format before touching disk
- rejects path traversal and any target under a protected path
- returns structured conflicts the model can act on, instead of raw stderr
- records the patch verbatim into the run log

### 11.4 Provenance

Agent-authored commits carry trailers so any line traces back to a run:

```
Mos-Eisley-Run-Id: <run_id>
Mos-Eisley-Role: author
Mos-Eisley-Model: claude-opus-5
Co-Authored-By: mos-eisley <noreply@localhost>
```

`mos blame <file>:<line>` joins these against the authenticated user's run index
to answer "which run, which model, at what effort, produced this line, and what did
the critics say about it." A run ID in shared Git history grants no access to the
owning user's private records.

---

## 12. GitHub integration

### 12.1 Access options

| Option | Best for | Notes |
|---|---|---|
| `gh` CLI subprocess | local dev | inherits the user's existing auth; no token handling in the harness |
| REST/GraphQL + fine-grained PAT | CI | explicit scopes, auditable |
| GitHub MCP server | extensibility | goes through §13 tiering like any other server |

Default to `gh` locally, fine-grained PAT in CI. Both live behind one `vcs/github.py` interface.

### 12.2 Least-privilege scopes

| Purpose | Scopes |
|---|---|
| Fetch PR + diff for review | `contents: read`, `pull_requests: read` |
| Post review comments | `pull_requests: write` **only** |
| Author pushes (CI) | `contents: write`, non-protected branches only |

Never a classic PAT. Never `repo` scope. Never `workflow` scope — that lets an agent modify CI definitions, which is a self-granting privilege escalation.

### 12.3 The publisher is a separate process

This is the central control and §19 explains why. The agent that reads the PR diff has **no network and no credentials**. A separate `publisher` process holds the token, accepts a schema-validated `Verdict` object, and posts it. Nothing free-form crosses that boundary.

### 12.4 Workflows

```
mos review --pr 1234        # fetch PR -> build brief -> pipeline -> verdict
mos review HEAD~1..HEAD     # local diff, no GitHub involvement
mos review --pr 1234 --post # ... and hand the verdict to the publisher
```

Findings already carry `location` as `file:line`, so they map onto GitHub review comments directly. The verdict maps to a check-run conclusion: `accept` → success, `revise` → neutral with annotations, `reject` → failure.

CI shape: call `mos exec --json` and gate the merge on the check run. Store raw run
artifacts only in the owning user's configured private backend (§17), never in a
shared CI artifact collection or log. Publish only the explicitly requested work
product through the publisher. Do not use `pull_request_target` for untrusted
checkout or test execution.

---

## 13. MCP client

MCP servers are another tool source and get the same treatment as builtins:

- Classified into a capability tier at registration, in config, by a human. A server is never auto-trusted because it advertises itself as read-only.
- Their schemas pass through the §4.2 subset validator. Many servers emit schemas Gemini rejects.
- Untrusted or network-capable servers never enter a critic's tool set.
- Network-access state is communicated to servers so they can behave correctly under the sandbox.
- Server responses are **untrusted content** (§19), not privileged instruction.

```toml
[mcp_servers.postgres]
command = "mcp-server-postgres"
tier    = "read_only"
env     = ["PGHOST", "PGDATABASE"]     # explicit allowlist, not inherited
```

### 13.1 Startup, health, and authentication

Apply the task/role tool-profile selection in §6.7.5 before request assembly. Lazy
startup and schema disclosure are separate: an unstarted server's schemas must not
remain in every prompt merely because that server exists in the approved catalog.

Start MCP clients lazily and concurrently so an unused or optional server cannot
block session startup. Report an explicit `starting | ready | degraded | failed`
state. An optional server failure degrades the advertised tool set; failure of a
server required by the selected task is an `infrastructure_error`, never a silent
skip or successful review. Bound startup and tool-call time, cancel descendants,
and circuit-break repeatedly failing servers.

OAuth and other interactive login flows belong to the trusted controller. Store
only credential references in configuration and redact protocol traffic at both
write and display boundaries. Tool annotations from a server are descriptive,
not authorization; local policy remains authoritative.

### 13.2 Outward service boundary — post-gate

An outward MCP server is useful for invoking narrow Mos Eisley capabilities from
other clients, but it is not part of the review MVP. The first surface should expose
read/review status, policy preflight, and replay over versioned schemas—not a general
`run` endpoint. Caller-supplied `tier`, `sandbox`, `roster`, endpoint, or repository
identifiers are requests that trusted policy may narrow or reject; they never grant
authority. Add authenticated sessions, rate limits, cancellation, idempotency, and
audit records before exposing it beyond loopback.

Every read, list, search, replay, and export must enforce §17 ownership using the
authenticated caller, including when multiple users use the same service. Caller
supplied user IDs or knowledge of another user's run ID grant no access.

Do not build an MCP server and a separate app-server protocol in parallel. They
duplicate authentication, cancellation, session, and schema semantics. Add an app
server only when a concrete first-party client cannot be served by the chosen
boundary.

### 13.3 Remote MCP connections — planned M11A and M11B

**User-directed addition, 2026-09-09.** Users must be able to register their own
hosted MCP endpoint, authenticate when required, inspect its tools, and select
the tools and read/write permissions Mos Eisley may use. Deliver the connection
through explicit CLI/configuration first; the conversational interface can use
the same controller operations when available. Owner: Josh Myers.

Status, 2026-09-09: M11A is implemented on the remote HTTP feature branch; see
[configuration](MCP_DATA.md) and [verification](MCP_HTTP_VERIFICATION.md). M11B is implemented for pre-registered public clients on `feat/mcp-oauth`; see
[OAuth verification](MCP_OAUTH_VERIFICATION.md). Other registration methods remain
unsupported. These stages connect to existing hosted servers; deployment of an outward
Mos Eisley server remains separate under §13.2. The original heading is retained
to preserve links to this milestone specification.

#### M11A — Streamable HTTP with token authentication

- Add an explicit transport choice: local stdio command or remote MCP URL. Remote
  configuration identifies the endpoint, credential reference, allowed tools,
  write grants and resource limits. Keep existing stdio configurations compatible.
  A server can be unauthenticated only when explicitly configured that way;
  protected endpoints require an operator-selected access-token reference.
- Use the installed MCP SDK's Streamable HTTP support for discovery and calls,
  including JSON and streaming responses. Pin and test the supported protocol
  revisions and compatibility behavior; unsupported versions must produce a clear
  failure. Bound connection establishment, reads, whole calls and cancellation.
- Require HTTPS for remote endpoints. Any local plaintext test endpoint requires
  an explicit loopback exception. Enforce approved destinations during initial
  connection, DNS resolution and redirects; private-network access is explicitly
  scoped rather than enabled for every URL. Never forward a token to a different
  origin. Do not accept credentials embedded in URLs, arbitrary credential header
  maps, or authority supplied by repository content or server responses.
- Reuse the canonical dispatcher, schema validation, per-tool allowlist and
  explicit write grants. Remote access does not widen tool permissions. Enforce
  bounded streaming/frame decoding before an oversized response can accumulate
  in memory; keep existing catalog, argument and canonical-result limits.
- Report connection/authentication failures and unavailable required tools.
  Cancellation closes active responses. Do not automatically resubmit tool calls
  after transport failure: a write can commit before its response is lost. Report
  that uncertain outcome and require source inspection before a new write attempt.
- Keep tokens in the credential-owning controller and associate them with the
  owning user and approved endpoint. Redact transport errors, headers and logs;
  provide disconnect/removal without persisting credentials in ordinary config.

**Exit criteria:** a remote test server registers, lists approved tools, and
executes a read plus an explicitly permitted write from the installed client.
Tests reject invalid/expired tokens, unapproved tools and writes, disallowed
destinations/redirects, invalid certificates, unsupported versions, malformed
streams and oversized responses. An interrupted-write fixture proves there is
no duplicate submission. Credential capture proves no cross-origin or cross-user
disclosure. Cancellation, required-server failures and existing stdio tests pass.
This gate uses fixtures and does not require a paid model call.

#### M11B — OAuth login and credential lifecycle

Depends on M11A's transport, destination controls and credential boundary.
Implement the supported MCP authorization profile: protected-resource and
authorization-server discovery, client identification/registration, browser login,
PKCE, callback/state and issuer validation, and explicit scope selection. Validate
discovered authentication URLs under the same destination policy as the endpoint;
discovery itself grants no permission to transmit credentials elsewhere.

Store access and refresh credentials securely under the owning user, server,
issuer and client identity. Support expiry, refresh, denied/revoked access,
reauthentication and logout/removal. Serialize concurrent refreshes and prevent
credential crossover between accounts. Request additional scopes only through an
explicit user authorization flow; login does not grant new Mos Eisley tools or
write permissions. Refreshing a credential must not automatically repeat a tool
call with an uncertain execution outcome. Logout removes local credentials and
attempts provider revocation where supported, reporting what was actually revoked.

**Exit criteria:** an OAuth-protected fixture server supports login, discovery,
authorized calls, refresh, reauthentication and logout. Tests reject mismatched
state/issuer/resource, replayed callbacks, denied scopes and malicious discovery
redirects. Two-user/two-server tests prove credential and refresh isolation;
revoked access cannot silently reconnect. Tests cover the documented supported
registration methods and preserve M11A's no-duplicate-write invariant.

#### Dependencies and separate acceptance gates

Schema compatibility (§4.2 and the adversarial finding in §23) now has a bounded
MCP implementation on `feat/mcp-schema-compatibility`: local reference expansion,
locally enforced constraints and explicit JSON argument wrappers. See
[schema verification](MCP_SCHEMA_VERIFICATION.md). Unsupported schemas still fail
closed over either transport; this does not establish paid-provider conformance.

Status, 2026-09-09: `feat/bounded-mcp-analysis` implements the first opt-in OpenAI
analytical loop, separate from evaluation/conformance authorization. It includes
promoted-context bootstrap, read-only MCP grants, definition-revision checks,
run-wide token/byte/turn/tool/deadline limits and an atomic whole-run reservation
in the operator's shared local ledger. Fixture tests cover conversations, denials,
concurrent admission and uncertain billing. It retains content in memory; SQL/result
artifacts, independent numeric verification and paid analytical conformance remain
open. See [operator contract](ANALYSIS.md) and [evidence](ANALYSIS_VERIFICATION.md).

Status, 2026-09-09: `feat/analysis-evidence-artifacts` adds schema-2 analytical
answers rendered from checked returned cells, a SQL/result/timing/usage trail,
explicit private retention, offline integrity/lineage verification and bounded CSV
exports from a selected captured result. These checks do not establish source
truth, appropriate metric selection or source snapshots; unrestricted narrative
verification and chart/UI work remain open. See [contract](ANALYSIS_EVIDENCE.md)
and [evidence](ANALYSIS_EVIDENCE_VERIFICATION.md).

Status, 2026-09-09: `feat/analysis-evaluation` adds an offline grader for saved
analytical bundles, frozen expectations, label-free task exports and per-arm
missing/failure accounting. It checks question/configuration/prompt/catalog identity,
revision, reviewed SQL/source metadata and typed cells. Domain labels and stable
fixtures still need review; ontology-free execution, controlled live comparisons
and statistical conclusions remain open. See [contract](ANALYSIS_EVALUATION.md)
and [verification](ANALYSIS_EVALUATION_VERIFICATION.md).

Status, 2026-09-09: `feat/analysis-raw-baseline` adds explicit raw source-discovery
and SQL analysis through the same bounded controller. Semantic/custom/write tools
are excluded; artifacts record raw mode with no semantic revision. Offline suites
can now compare raw/promoted arms, but controlled execution, domain fixtures and
quality assessment remain open. See [contract](ANALYSIS_RAW_BASELINE.md) and
[verification](ANALYSIS_RAW_VERIFICATION.md).

Status, 2026-09-09: `feat/analysis-comparison-schedule` freezes label-free case/arm
orders with balanced positions and checks pinned artifacts for recorded ordering,
overlap and pre-schedule starts. Missing/failed timing stays unknown and every
assignment remains in the assessment. A synthetic four-run demo exercises both
raw/promoted modes; live execution, source freezing and domain quality assessment
remain open. See [contract](ANALYSIS_COMPARISON_SCHEDULE.md) and
[verification](ANALYSIS_SCHEDULE_VERIFICATION.md).

Paid model selection and use of connected tools belongs to the analytical-agent
workstream (§14 and Ana Lite Stage 3). It requires per-user transfer authorization,
whole-run spending reservations, turn/token/tool/time limits, cancellation and
private result retention. M11A/M11B can finish using direct calls and fixture
agents; neither stage enables paid model or critic access automatically.

Protocol references: [MCP transports, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
and [MCP authorization, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization).
Recheck SDK/protocol compatibility when implementation begins.

---

## 14. Agent loop

```
assemble context -> count tokens -> check budget
  -> call provider (stream)
  -> normalize stop reason
  -> if tool_use: classify -> approve/deny -> dispatch sandboxed -> append results
  -> repeat until end_turn | budget exhausted | limit hit
```

Per-agent limits, all enforced: iterations, input tokens, output tokens, wall clock, dollars, tool calls. Cooperative cancellation with cleanup of in-flight subprocesses. Per-provider semaphores plus exponential backoff with jitter on `retryable` errors.

Every request and response written to `runs/<id>/agents/<name>/turns.jsonl` before the next iteration begins, so a crashed run is still analyzable.

### 14.1 Typed lifecycle events

Expose a versioned lifecycle event bus for observability and policy composition:
`run.started/completed`, `agent.started/completed`, `turn.started/completed`,
`tool.requested/completed`, `finding.emitted`, `policy.denied`, and
`artifact.persisted`. Events carry immutable run/agent IDs, sequence numbers,
policy and brief digests, and bounded typed payloads.

Initial handlers are built-in or explicitly installed, digest-pinned trusted
components. A handler may
observe, reject, or further narrow an operation, but cannot enlarge capabilities,
rewrite trusted identifiers, or execute with the triggering agent's ambient
environment. Define deterministic ordering, timeout, output cap, backpressure,
failure mode, and circuit breaking per handler. Log every veto separately so a
compromised or broken handler cannot silently suppress a finding.

Do **not** run arbitrary shell hooks when `finding.emitted` fires. A finding may
contain a structured `EvidenceRequest`; the controller validates it and dispatches
it through the TEST evidence broker under its own policy and budget. External
command/plugin handlers remain disabled until the same sandbox and supply-chain
requirements as tools are met.

### 14.2 General subagents

Implement critics, judges, dedupe, and future delegated work on one general child
agent primitive. A child receives a fresh context built from an allowlisted,
content-addressed brief—not the parent's transcript—and returns a versioned,
schema-validated result. Persist its parent ID, task, brief digest, route, policy
digest, budget, and cancellation outcome.

Effective child authority is the intersection of parent authority, trusted policy,
role policy, and the child's request. This is a capability lattice, not `min(tier)`:
filesystem roots, network destinations, tools, credentials, providers, and resource
limits are independent dimensions. Enforce maximum depth, child count,
concurrency, cumulative tokens/dollars, wall time, and propagated cancellation.

Repeated compaction is a diagnostic signal, not permission to spawn automatically.
Replacing a fourth compaction with a child changes task semantics and can multiply
cost; promote that behavior only if evaluation demonstrates higher task success
within the same aggregate budget.

### 14.2.1 Creator-led coding delegation

Once coding execution and bounded children are available, coding workflows must
assign at least one meaningful implementation subtask to a subagent. A critique,
status check, or cosmetic no-op does not satisfy this requirement. The creator
retains responsibility for architecture, task decomposition, authoring the tests,
integration, test execution, and the final answer, and may implement other portions
itself. If no eligible child or adequate aggregate budget is available, report the
unmet delegation requirement
and resolve it before claiming the delegated workflow can proceed.

Give each coding child the creator-approved plan and test-suite revisions, scoped
file ownership, interfaces, acceptance criteria, permitted tools, and a
token/cost/time allowance. The creator writes concrete tests for the requested
behavior and relevant failure cases before implementation delegation; a prose test
plan alone does not satisfy this requirement. The critic and judge assess test
adequacy together with the plan. Tests may initially fail or await the planned
interfaces, but their expected behavior must be explicit. Coding children implement
against these tests and cannot delete, weaken, or redefine them to make a patch
pass. Test corrections require creator ownership and renewed critic/judge review
of the affected plan/test revision. Test-file creation and execution remain subject
to the execution/VCS gates; this ordering does not grant early machine access.
Use isolated worktrees and the trusted VCS broker when writes become available.
Parallelize only independent coding tasks; serialize shared-file edits and record
dependencies. Return a patch, relevant verification evidence, and unresolved issues
for creator integration. Children cannot approve their own final integration or
expand the accepted plan; material scope changes return to plan review (§15.7).

The explicit objective is **clean, efficient output at a cost-effective total task
cost**. Evaluate correctness, maintainability, unnecessary code/dependencies, and
task-relevant runtime/resource efficiency alongside completion, latency, and spend.
Prefer the least expensive child route shown to meet those requirements, using
appropriate reasoning effort. Include creator planning, critic/judge calls, child
execution, context handoffs, integration, testing, and retries in cost comparisons;
a lower per-token price alone does not establish savings. Reserve aggregate spend
before dispatch and keep correction/escalation within the approved task budget.

Define and evaluate this workflow alongside the author workstream. Activate delegated
coding only after both execution/VCS containment and the E2 bounded-subagent gates
pass; it does not authorize earlier model-driven writes. Validate against a
creator-only baseline on matched tasks before promoting a default delegation policy.

### 14.3 Versioned skills and personas

A skill is a progressively disclosed prompt/rubric bundle with a manifest,
compatibility constraints, source provenance, and content digest. Trusted user/admin
policy owns the allowlist. Repository-local files are untrusted hints and may select
only an already-approved skill version; they cannot register executable code,
request credentials, or enlarge a capability. Skill scripts are inert assets unless
separately registered and authorized as normal tools.

Move critic personas into skills only after the current inline persona is covered by
golden and held-out evaluations. Pin every run to skill digests and measure each
version's detection, false-positive, cost, and calibration effects. “Closest wins”
discovery is forbidden for authority-bearing fields; configuration still intersects
with trusted policy as required by §23.1B.

The initial implementation is intentionally narrower: standards-compatible
`SKILL.md`, optional `mos.yaml` containing only `version` and `kind`, prompt-only
persona/procedure packages, explicit discovery roots, and exact
`source:name@sha256:digest` activation. It rejects scripts, executable files,
toolbundles, `allowed-tools`, name-only precedence, and implicit project activation.
Discovery snapshots the complete bounded package once; model-context disclosure is
progressive from that immutable snapshot. Recorded reviews may bind persona skills
only when the activated, outer-trimmed body is byte-for-byte equal to the existing
request-bound cassette,
and schema-2 runs record the exact source, version, package digest, and instruction
digest. See `docs/SKILLS.md` and the disposition in §25.

---

## 15. Adversarial review pipeline

### 15.1 Brief materialization

The critic's context is built from a directory on disk, never forked from a conversation.
The proposed materialized layout is:

```
runs/<id>/brief/
  spec.md  diff.patch  constraints.md  test_output.txt
  manifest.json         # sha256 of each file -> brief_id
```

`brief_id` is the content hash; the same brief replays to any model, any time. **The author's transcript never enters a critic's context** — the author's reasoning is precisely what critics must be blind to.

Current recorded `Brief` has only `spec`, `diff` and `constraints`; the directory
layout and executable test receipts require new versioned contracts. Independent
test derivation receives plan/interfaces only; implementation and author telemetry
are withheld until the explicit binding/evidence phases in §26.2.

### 15.2 Blindness invariants

Asserted in code, tested in CI:

1. Critics run concurrently and never observe each other.
2. No critic is told which model authored the artifact.
3. The judge receives critiques with identity stripped. Current recorded replay
   uses canonical hash order; future randomized evaluation persists its permutation.
4. No critic is told another critic flagged anything.
5. Personas differ deliberately — correctness, spec mismatch, operational failure modes — so they don't share one blind spot.

### 15.3 Findings schema

```python
class Finding(BaseModel):
    location: str  # file:line or symbol
    claim: str
    category: Literal[
        "correctness", "spec_violation", "security", "performance", "preference"
    ]
    impact: Literal["blocker", "high", "medium", "low"]
    evidence: Evidence  # currently a source-bound citation
    suggested_fix: str | None = None
```

- Display a short ranked summary while retaining original findings. Current inputs
  are bounded at 50 findings per critic; future protocols must report overflow or
  truncation explicitly, and incomplete required coverage must not silently accept.
- Executable evidence requires the isolated evidence broker and a new receipt
  contract; a model-supplied command or failing test is not proof or authority to run.
  Pin expected/observed behavior, artifact, test, binding and environment identities.
- **`preference` findings never block.** Unlabeled findings rejected at parse time.

### 15.4 Adjudication

1. **Dedupe** exact content deterministically and preserve every original. Semantic
   clustering remains an evaluated extension and cannot erase distinct evidence.
2. **Validate evidence** against the frozen artifact and governing requirement.
   Citation presence and model agreement alone do not establish correctness.
3. **Judge** adjudicates identified findings; the controller derives the code
   verdict from category/impact policy. Missing quorum, invalid IDs, unavailable
   judgment or incomplete required evidence fails closed as `infrastructure_error`.
4. **Rotate roles** across runs under eligible rosters; preserve each in-flight
   roster. Freeze measurement components within a study/cohort. Provider diversity
   is not a measured guarantee of independent errors.

The current judge returns upheld IDs and one rationale; per-objection unresolved
dispositions and executable-evidence judgments need versioned contracts. Until
sampled judging passes §26's quality gate, all blocking corrections retain judging.

### 15.5 Bias controls

| Bias | Control |
|---|---|
| Self-preference | blinding + judge rotation |
| Verbosity | bounded structured findings and original evidence references; no lossy evidence normalization |
| Position | randomized order; periodic permuted re-run to measure |
| Herding | strict concurrency, no cross-critic visibility |
| Sycophancy | adversarial persona + executable-evidence requirement |

### 15.6 Rounds

Planned default: two critique/rebuttal rounds per frozen artifact and at most two
correction cycles per task, bounded further by one shared cost/deadline budget.
Persist counters across resume. New artifact revisions invalidate dependent
acceptance but do not reset task counters. Stop with unresolved findings on budget,
cancellation or non-convergence; repeated failures do not prove plan ambiguity.
Current recorded review performs one critic/judge pass and has no correction loop.

### 15.7 Plan review, creator approval, and delegated implementation

For the creator-led coding workflow, use this explicit sequence:

1. **Creator writes the plan and tests.** Freeze a concrete plan with constraints,
   interfaces, proposed coding subtasks and routes, and an aggregate cost/time
   budget, together with creator-authored executable tests for the required behavior
   and relevant failure cases. Record exact digests for both the plan and test suite.
2. **Independent readings, then critic review.** In the Stage-0 experimental profile
   (§26.2), two fresh readers first seal readings of the plan/interfaces without
   creator tests, private reasoning or each other's output. Then supply the critic
   both frozen plan/tests, reading findings, and permitted
   repository evidence in a fresh context; assess correctness, maintainability,
   efficiency, missing requirements, test adequacy, and the proposed delegation and
   cost assumptions.
3. **Judge adjudicates.** Resolve the structured findings into an accept, revise,
   or reject disposition tied to the exact plan and test-suite digests, with blocking
   findings explicit. Apply the existing bounded review rounds rather than an unlimited loop.
4. **Creator approves.** The creator considers the verdict and records acceptance
   of that exact plan and test suite before releasing coding work. A revise/reject
   disposition or unresolved blocker requires revised artifacts and renewed review. This is an agent
   workflow decision, not a new user-confirmation step or permission to bypass policy.
5. **Subagents implement; creator integrates.** Dispatch at least one coding child
   against the approved plan and tests. The creator checks patches, runs permitted tests,
   resolves integration issues, and retains ownership of the result. A materially
   changed plan or any changed approved test invalidates the affected approval and
   dependent child authorization until renewed review and creator approval.
6. **Review the result.** Submit the frozen implementation and verification evidence
   to independent critic/judge review, then have the creator accept the final result
   or coordinate bounded corrections. Plan acceptance alone does not prove the code
   meets its requirements. All rounds share the task's aggregate budget.

Persist the plan and test-suite revisions, critic findings, judge disposition,
creator approval, child assignments/patches, final verification, and per-role usage
as owner-scoped artifacts. No coding child may start before matching plan/test approval. Questions and
non-coding conversation retain §16.0's direct-answer behavior.

Use the active project's requirement-linked rubric (§16.6) and declare resource
ceilings and stopping rules before extended verification. Each further pass must
add a focused test, replay, fault case, measurement, or meaningfully different
review evidence. Stop on the pass threshold, diminishing returns, or the budget
ceiling and report unresolved findings. Tokens, iterations, and finding counts are
diagnostics, not quality targets; novelty without ground truth requires domain
evidence. This adapts the production template's bounded-verification guidance and
does not waive creator-authored tests, delegated coding, or required independent
review. Project-specific rubric weights and methods remain configurable.

---

## 16. CLI interface

### 16.0 Conversational product contract

**Implementation status, 2026-09-09:** the first recorded conversation terminal
supports contextual follow-ups, queued messages, cancellation, private local saving
and explicit same-user/workspace resume. Metadata-only session listing, latest
selection and locked exact-snapshot deletion now provide navigation and manual
retention. See [usage and limits](CONVERSATIONS.md).
An [explicit recorded review round-trip](CONVERSATION_REVIEW.md) now preserves
separate critic requests and returns a retained report and contextual summary.
[Multiline drafting](CONVERSATIONS.md#multiline-composition) now queues bounded
messages with explicit send/discard and keeps unsent content out of saved state.
[Queued steering](CONVERSATIONS.md#steering-during-work) now links refinements
to active chat tasks and preserves unanswered intent at explicit continuation.
The [interactive terminal](CONVERSATION_TUI.md) now provides a scrollable
transcript, editable multiline composer, review expansion and persistent status.
Bare `mos` now opens that interface in the current workspace, displays the workspace
and session ID, and uses a built-in recording with private default storage.
`mos -C PATH` selects another workspace; `mos resume --last` reopens the latest
session in that workspace without requiring cassette/storage flags. Initial
literal prompts now use `mos chat "PROMPT"`, `mos -- "PROMPT"`, or session launch
options followed by a prompt. [User-defined session names and a resume picker](CONVERSATION_NAMES.md)
now support optional labels, rename/clear controls, filtering and explicit selection
for duplicate names. Live authentication/setup remains planned. The default preview
needs no credentials or network connection.
The full product contract below remains the target; live conversation/review,
mid-request interruption and advanced terminal controls are not yet available.

**User direction, 2026-09-06:** Mos Eisley should be conversational like Codex.
Opening `mos` starts an ongoing conversation in the selected workspace. Plain
language is sufficient to explore, plan, implement, debug, and request independent
review as the corresponding capabilities become available. Slash commands are
optional shortcuts; `mos exec` and explicit subcommands serve automation.

The interaction reference is the [official Codex CLI documentation](https://learn.chatgpt.com/docs/codex/cli),
checked 2026-09-06: a terminal conversation with follow-ups, active-turn steering,
visible commands/diffs, and saved chats. The requirements below are Mos Eisley
product decisions, not a claim of complete Codex parity or current availability.

**Session behavior:**

- Keep one user-facing assistant and conversation across requests. Follow-ups such
  as "why?", "fix the first one", and "now review the change" resolve against
  the active task, prior answers, and identified artifacts. Ordinary questions
  receive direct answers without invoking the full adversarial pipeline.
- Interpret requests in context: explaining or reviewing does not authorize edits;
  a request to fix or build authorizes the relevant work within resolved policy.
  Continue authorized work through verification. Ask a concise question when a
  missing decision changes the outcome, and request approval only at a real policy
  boundary. Show unavailable capabilities plainly.
- Show assistant progress, tool activity, relevant diffs, and results in a readable
  transcript. Stream text when the adapter supports it; otherwise display bounded
  progress while waiting. Keep the composer usable during work, visibly queue
  steering messages, and apply them at the next safe execution boundary. A stop
  action cancels active work and its children while preserving the conversation
  and recording any effects already completed or still uncertain.
- Treat a new message as a refinement of the active task unless it explicitly
  replaces or cancels it. A status question gets a brief answer and work continues.
  Clarifications and policy approvals appear inline with the reason they are needed.
- "Review this change" and `/review` enter the same review workflow. Freeze the
  target revision and materialize a scoped brief; critics receive neither the
  conversational history nor each other's findings. Return the adjudicated
  findings to the main conversation, where the user can discuss or request fixes.
  Never silently run a panel for every conversational turn.
- Persist messages, task state, artifact references, and usage in the owning user's
  configured storage (§17), which may be local or remote.
  `mos resume` selects a saved conversation and `mos resume --last` continues the
  latest one for the workspace. Resume revalidates current policy and capabilities,
  never restores expired approvals or repeats uncertain side effects automatically.
  Conversation compaction preserves user intent, decisions, and remaining work;
  frozen critic contexts retain their separate compaction rules.
- A fresh session starts with fresh conversational context. The owning user's
  minimal model-selection statistics and enabled, explicitly curated user/project
  memory (§16.0.2) may be reused across sessions.
  Resuming a selected conversation or explicitly opening a prior run retrieves only
  that user's requested records; full saved conversations are never ambient memory
  for new tasks. Saving a specific fact to memory is a separate, scoped action.
- Close bounded work units and update private task checkpoints under §6.7. Keep
  the ongoing conversation usable; a fresh-context handoff is visible and explicitly
  selected, while an already-authorized next work unit can proceed without renewed
  permission. Preserve task obligations and ledgers across both compaction and
  session changes. Context-pressure advisories explain the next useful action and
  never interrupt work solely because a heuristic threshold was crossed.

**Terminal layout:** a scrollable conversation, compact expandable tool/review
details, a multiline composer, and the persistent status line specified in §16.4.
The main transcript distinguishes user input, assistant progress, final answers,
and approval requests. Model and effort changes apply to subsequent eligible
calls, retain the conversation, and remain subject to provider policy and budget.

Illustrative interaction once review and write capabilities are available:

```text
$ mos
you > Explain how authentication works here.
mos > [Inspects permitted files and explains the flow with references.]
you > Review the changes I made to token refresh.
mos > [Runs independent review and returns the adjudicated findings.]
you > Fix the first issue and run the relevant tests.
mos > [Applies the authorized fix, verifies it, and reports the result.]
you > Why did you choose that approach?
mos > [Explains the decision using the same conversation context.]
```

**Delivery and acceptance:** make a minimal conversational terminal and session
controller an early product workstream alongside live read-only review. Begin with
recorded providers and explicit input artifacts, then enable live conversation
after provider conformance, transfer policy, and aggregate session spending gates.
Repository discovery, edits, tests, and publishing each retain their existing
containment and authority prerequisites. Advanced visual polish can follow later.
Acceptance requires contextual follow-ups, visible queued steering, cancellation
without losing the session, safe save/resume, and a review round-trip that preserves
critic blindness. Interactive and non-interactive paths share orchestration and
policy; the renderer owns no separate execution authority.

### 16.0.1 Directory selection and visibility

**User direction, 2026-09-09:** users must be able to select and see the directory
used by the session, following the terminal startup interaction in Codex.

- Bare `mos` starts in the shell's current directory. `mos -C PATH` selects a
  directory explicitly. Show its canonical path in the startup header; keep the
  active directory visible in a compact header/status area during work, with the
  full path available when abbreviated. Display the project root separately when
  it differs from the working directory.
- Add a directory selector and `/directory` inspection/switch flow. Selecting a
  new project opens a fresh session with that project's memory and capabilities.
  Resolve active work and unsent input before switching; never silently retarget
  an in-flight operation or carry the previous project's context into another.
- Validate the selected directory before creating a session. Resolve aliases and
  symlinks consistently, show the resolved target, and retain the same binding for
  resume. A directory selection supplies context, not broader filesystem access.
- The startup implementation provides `-C`, a persistent directory header,
  `/directory` inspection, and the opt-in
  [startup selector](CONVERSATION_DIRECTORY.md) via `--choose-directory` for chat
  and resume. Enter previews the canonical target; Ctrl-S selects it. Cancellation
  precedes session/memory access, and edits invalidate the preview. Directory
  identity is rechecked during selection and startup. New chats load the chosen
  project's memory; resume retains its workspace checks and paused queued work.
  Paths are bounded to 4,096 printable UTF-8 bytes; Tab scans at most 1,024 immediate
  entries and offers at most 100 directories, with no partial list on overflow.
  Pipes, plain/JSON mode and inspection use `-C PATH`. In-session F9 and
  `/directory switch [PATH]` now support an explicit handoff: active work and
  unsent/pending input block switching; the picker keeps the old session locked
  and cancellation returns to the same controller. Selection closes that session
  and opens a fresh recorded conversation with the target project's memory.
  Old queued work remains saved, while history, name, recording, review packet,
  initial prompt and resume/refresh selectors are cleared from the new launch.
  Invocation storage/backend, memory location, no-memory choice and budgets remain.
  The terminal input parser is fresh for each screen and buffered keystrokes are
  cleared at handoff. Git-marker discovery now displays the nearest candidate root
  separately in the header, selector preview and `/directory`; startup JSON also
  includes the root, discovery status and effective memory workspace. The scan
  checks at most 64 ancestors without opening marker/configuration files or running
  Git. File markers keep worktrees separate; symlinks, special markers, read errors
  and bounds produce an unknown root. Discovery is cached for each launch and
  refreshed on resume/switch. It supplies display metadata only. These checks preserve
  canonical-path persistence and do not add a durable inode identity or filesystem sandbox.

### 16.0.2 User and project memory

**User direction, 2026-09-09:** provide two durable memory scopes in addition to
saved conversations. The [first implementation](CONVERSATION_MEMORY.md) now supports
private user/project documents, explicit CLI show/set/append/clear/enable/disable,
startup loading, active revision display and `/memory` inspection. Memory revisions
are retained with sessions and bound into recorded chat requests; changed memory
pauses before another dispatch and prevents stale resume. `--no-memory` bypasses
loading. `/memory refresh` and `/memory off` now explicitly replace the active
selection between requests and leave queued work paused until `/continue`.
`resume --refresh-memory` provides the same transition for saved sessions, with
`--no-memory` to disable loading. Earlier messages retain their historical context;
consumed recording exchanges remain unchanged. Custom recordings require an explicit
replacement via `--refresh-cassette`, retained privately for subsequent resumes.
Project scope defaults to the canonical workspace. New sessions can explicitly
select an ancestor via [`--memory-project-root PATH`](CONVERSATION_MEMORY_PROJECT.md).
The identity is retained across resume, refresh, historical artifact reads and
JSON/SQLite transfers; legacy sessions retain their original bindings and bytes.
The startup selector previews the effective identity, and switching directories
clears it for the fresh session. Git-marker roots are displayed separately and
never select memory. Explicit mappings and terminal scoped edits are implemented
as described below. Explicit scoped remember phrases are implemented; broader
natural-language interpretation and automatic extraction remain planned.
The requirements below remain the complete target.

**Terminal memory controls:** `/memory show|append|set|clear|enable|disable user|project`
now manages the session-bound saved scope in full-screen and plain/JSON modes.
Append/set require explicit single-line text; other actions reject extra text.
Active requests block management, and attempted edits/inspection pause queued work.
Receipts identify the saved document while session selection and historical requests
remain unchanged until explicit refresh. Pasted/composed chat and model output
cannot invoke this path. Existing locks, ownership and document limits apply;
write failures warn that publication may have occurred. Reviewed selective forgetting
and individual-entry replacement are implemented below, along with reviewed
acceptance of selected structured assistant proposals.
See [terminal memory controls](CONVERSATION_MEMORY.md#edit-from-a-terminal-session).

**Scoped remember shortcuts:** directly entered `remember this for this project: TEXT`
and `remember this everywhere: TEXT` now append the explicitly supplied text to the
retained project or user scope. Ambiguous scope, missing content and oversized or
multiline control requests ask for correction without persistence. Pasted/composed
text, initial prompts, quoted/embedded phrases and model/tool output do not invoke
the shortcut. No model request is created; the receipt shows actual saved text,
queued work stays paused and session memory still requires explicit refresh.
Active work blocks saves and rejected full-screen submissions retain their draft.
General natural-language interpretation and contextual references remain planned.
See [remember a preference](CONVERSATION_MEMORY.md#remember-a-preference).

**Reviewed selective forgetting:** `/memory forget user|project EXACT_TEXT` and the
explicit scoped `forget this ...: TEXT` forms preview removal of one unique exact
span. Receipts show the complete resulting text; `/memory apply-forget HASH` checks
the reviewed current-document hash under the existing exclusive lock before saving.
Missing or overlapping/duplicate matches reject, and all other characters remain
unchanged. One ephemeral per-session review is replaced by a new scoped preview command, invalidated
by ordinary memory writes and consumed before a matching apply. Resume/directory
handoff require a fresh preview. Active work blocks controls; pasted/composed input
cannot apply them. Current selection/history remain unchanged until refresh and
historical copies are not erased. Tests cover stale edits, unsafe current files,
partial publication, real process death, both storage backends and session review
loss. See [reviewed selective forgetting](CONVERSATION_MEMORY_FORGET.md).

**Reviewed exact replacement:** `/memory replace user|project {"old":"TEXT","new":"TEXT"}`
previews replacing one unique exact span with explicitly supplied new text. JSON
supports escaped newlines and quotes; duplicate keys, invalid types, empty/unchanged
text and oversized results reject before a review is created. The complete result,
old/new text, target, before revision and fresh review identifier bind the confirmation
hash. `/memory apply-replace HASH` uses the shared locked compare-and-swap and
consume-before-write safeguards; `/memory discard-replace` cancels. Forget and
replacement share one ephemeral review per terminal session. All other characters
and the document's enabled state are preserved; session selection changes only on
explicit refresh. Tests cover overlapping matches, UTF-8 limits, stale/unsafe targets,
partial publication and process death, literal pasted/composed input, disabled
selection, combined-context rejection and CLI apply/refresh/resume on both storage
backends. General interpretation remains planned; structured assistant proposal
review is implemented below.
See [reviewed replacement](CONVERSATION_MEMORY_REPLACE.md).

**Assistant proposal acceptance:** `/memory review-proposal user|project INDEX`
selects a completed assistant chat reply containing exactly one strict JSON proposal
(append/text, replace/old/new or forget/old). Indices match displayed zero-based
message labels; the user chooses the scope. Receiving model output does not create
memory storage, and user prompts, files, review/judge output and free-form prose
cannot enter this path. Full source, before state and complete result bind the
fresh review hash. `/memory apply-proposal HASH` rechecks the source and uses a
locked compare-and-swap, including expected absence; `/memory discard-proposal`
cancels. All three memory review kinds share one ephemeral slot. Explicit apply
preserves other text and enabled state; refresh alone adopts the saved change.
Tests cover malformed/untrusted proposals, source and target changes, concurrent
creation, partial publication and process death, idle/literal-input boundaries,
and actual recorded-reply acceptance/resume on snapshot and SQLite backends.
No live provider dispatch, automatic extraction or transcript interpretation is
introduced. See [assistant proposal review](CONVERSATION_MEMORY_PROPOSALS.md).

**Selected assistant text:** `/memory review-text user|project INDEX "EXACT_TEXT"`
now previews appending a user-selected span from an ordinary completed assistant
reply. A JSON string supports exact multiline/quoted content. Missing, repeated or
overlapping matches reject, with no normalization or inferred selection. The complete
source reply, selected text, target and complete result are visible before applying
through `/memory apply-proposal HASH`. The confirmation binds a distinct selection
operation, complete source and character offsets. It shares the existing ephemeral
review slot, locked stale-write checks, private storage and consume-before-write
handling. Tests cover literal controls, source changes outside the selected span,
concurrent creation, bounds, active work and CLI apply/refresh/resume on both backends.
This is explicit curation; automatic extraction and broad interpretation remain
planned. See [selected reply text](CONVERSATION_MEMORY_SELECTION.md).

**Adoption batch:** explicit selection and a read-only `memory-project-preview`
now support inspection before adopting a root. The preview reads both project
documents under one shared lock and reports source-only, target-only, empty,
same-identity or collision states, including disabled/empty documents. Starting a
root-selected chat uses the root document; it leaves workspace documents untouched.

**Guarded copy batch:** `memory-project-migrate` previews the complete proposed
document and copies an existing workspace document only to an absent ancestor-root
document. Apply requires its fresh hash, binds storage/lock and directory identities
plus source/target snapshots and proposed bytes, and rechecks under an exclusive lock
immediately before atomic no-overwrite publication. Disabled and empty documents
count as collisions. Source/user documents, saved session identities, historical
memory and request hashes are preserved. The earlier `memory-project-preview` hash
remains informational and is not accepted for apply. Focused stale-input, identity,
locking, collision and interrupted-publication tests run before the combined gate.

**Guarded recovery batch:** `memory-project-recover` previews one explicitly named
interrupted-publication alias against the originally approved target document hash.
Apply requires the recovery hash, rechecks storage/lock/directory and record identities
under an exclusive lock, and removes only the verified extra link. Ordinary readers
retain their single-link rule; target/source/user bytes and session history remain
unchanged. Stale inputs, wrong scope/owner, symlinks, extra links and noncanonical
records fail closed. Fault tests include recovery after actual process death.

**Reviewed collision batch:** `memory-project-resolve` requires an explicit
keep-target, use-source, append-source or use-text strategy and a fresh preview hash.
Apply preserves source/user files, target enabled state and session history. Changed
text increments the target revision and receives an apply-time UTC timestamp; all
other proposed fields are fixed by the preview. No-ops preserve bytes and metadata.
Before atomic replacement, a verified private canonical prior-target backup is
flushed durably. Source/target records and file identities, storage/lock and directory
identities are rechecked under the exclusive lock immediately before publication.
Literal append does not deduplicate or infer a conflict resolution. Fault tests cover
backup/replacement interruption, stale inputs and existing changed-memory guards.

**Explicit worktree mapping batch:** new sessions accept `--memory-project-map PATH`
to select another existing directory's owner-scoped memory without an ancestor
relationship. The choice is mutually exclusive with ancestor-root selection, is
canonicalized and saved as `memory_project_mapping`, and survives refresh, resume,
cold SQLite reads, historical artifacts and JSON/SQLite transfers. The directory
picker previews it; `--no-memory` retains it without memory reads. Directory switching
clears it. Default Git discovery never selects it, and source workspace/tool authority
remain unchanged. Resume accepts no identity override.

**Reviewed relocation batch:** `memory-project-relocate` copies from an exact
canonical saved project identity to an absent document at any existing destination,
including unrelated worktrees. The source directory can be gone; its nearest
existing ancestor identity and absence are bound to the review alongside target,
storage/lock, source record identity and complete snapshots. Reappearance, changed
inputs, unsafe records and collisions reject apply. Fresh operation-specific hashes
and exclusive locking guard atomic no-overwrite publication. Source/user documents
and all saved session identities/history remain intact. Explicit recovery supports
one interrupted publication's verified staging alias even with a vanished source.
Ordinary memory access and resume still require their saved directories to exist.

**Cross-mapping collision batch:** `memory-project-relocate --strategy` now
requires a separate resolution review for two existing documents across unrelated
worktrees or from a vanished source identity. Keep-target, use-source, append-source
and use-text use the existing durable backup and replacement protocol. Resolution
binds source presence/ancestor, both record identities, target directory, storage,
lock, strategy and reviewed content to an operation-specific hash. Target enabled
state is preserved; no-ops preserve bytes and metadata. Changed text gets the next
target revision and an apply-time UTC timestamp. Source/user documents and session
history remain intact. Copy, resolution and recovery reviews are not interchangeable,
and recovery flags cannot mix with a resolution strategy. Fault tests cover late
source reappearance and actual process death before/after replacement.

**Reviewed staging cleanup batch:** `memory-project-cleanup` explicitly discards
one complete single-link project staging record or repairs one interrupted backup
publication by removing only its verified extra staging link. Exact filenames,
record hashes and canonical owner/project snapshots are required. Preview binds
current project memory, candidate records/identities, storage/lock and the selected
workspace's presence/ancestor, including vanished directories. Apply rechecks under
an exclusive existing lock, unlinks only the selected name and flushes the directory.
Backup bytes, live memory and saved sessions remain intact. Discard can remove the
selected staging copy even when no live project document exists; the full receipt
makes that absence explicit. Fault tests cover actual process death during copy,
resolution, backup publication and cleanup. Invalid records use the separate raw
staging review below. See [memory cleanup](CONVERSATION_MEMORY_CLEANUP.md).

**Reviewed retention and batch cleanup:** `memory-project-cleanup-batch` accepts
1–32 explicit records in a bounded, strict JSON manifest. Staging discard, backup
link repair and retained-backup pruning share the existing private owner/project
validation. Pruning requires an explicit modification-time cutoff and distinct,
readable current project memory; backups matching current memory are protected.
It does not infer backup age from document timestamps or promise a newest-count
policy without an inventory. Full records, observed identities, policy and current
memory are bound to one preview. Every selection is checked under one exclusive lock
before deletion, then each is rechecked before unlink. Duplicate/overlapping names
are rejected. Sequential apply reports unlinked and directory-flushed names
separately on in-process failure; process death requires inspection and fresh review
of the remaining exact selection. No rollback or automatic continuation is claimed.
Live memory, user preferences and saved sessions remain intact.

**Reviewed invalid staging disposal:** `memory-staging-discard` reviews one exact
migration/resolution staging filename and its raw SHA-256, with complete base64
bytes bounded to 256 KiB. Its storage-wide receipt explicitly leaves project
attribution unverified; it does not infer identity from invalid JSON or the current
directory. Private current-user ownership, one link, regular-file type, exact names
and existing storage/lock are required. Valid snapshots are always refused,
including noncanonical serializations and foreign-owner/project or user-scope
snapshots. The raw review binds file bytes/identity/metadata and storage/lock before
exclusive-lock unlink and directory flush. Current memory documents are not read
or bound, and remain untouched. In-process failure receipts distinguish unlink from
successful directory flush; process death requires inspection and fresh review.
Tests cover actual interrupted publication with empty/partial writes and death
after unlink. Shared storage locking is separated from project-document selection.
This command is not part of project-scoped cleanup batches. See
[raw staging review](CONVERSATION_MEMORY_STAGING.md).

**Persistent mapping configuration:** `memory-project-mapping show/set/remove`
reviews an owner-private registry in the configured memory storage. Exact canonical
workspace/target paths carry directory device/inode pins; changed directories
require fresh review. Bounded canonical JSON (128 mappings, 1 MiB), whole-registry
before/after receipts, revisions, shared locks and atomic durable replacement guard
updates. Read-only missing-registry inspection does not create storage. Removal
accepts a vanished workspace's exact saved identity. New launches and both recording
generators use saved mappings, explicit root/map flags override them, and
`--memory-project-local` bypasses the registry. `--no-memory` retains its existing
no-memory-storage-access guarantee and skips automatic registry lookup.
Picker/startup and directory handoff share a captured registry snapshot with directory rechecks. Resume retains the saved
session mapping independently of registry changes or corruption. Memory editing
continues to address explicit `-C` identities. Tests cover both session backends,
unsafe storage, stale reviews, directory replacement, publication failures,
picker/handoff selection, overrides and resume. See
[saved mapping configuration](CONVERSATION_MEMORY_MAPPINGS.md).

**Inventory-based backup retention:** `memory-project-retention` now proposes
reviewed pruning with explicit `--keep-newest` and `--before-ns` policies. Its
complete inventory is bounded to 1,024 directory entries, 128 backups and 8 MiB
(256 KiB per record), failing closed on unsupported backups even for other
projects. Exact canonical private single-link backups, storage/lock/workspace
identities, full selected-project records, current memory and deterministic file
mtime/name ordering are bound to review. Newest-count, age and current-memory
protections combine. At most 32 oldest eligible backups are selected; excess
requires fresh review. Under one exclusive lock, apply rescans the reviewed
inventory minus its own deletions before every unlink and reports removed/flushed
progress separately. Tests include real limits, retained-file changes, partial
failures and process death. No background retention is enabled. See
[backup retention](CONVERSATION_MEMORY_RETENTION.md).

**Expanded staging review:** the raw invalid-file command now accepts an explicit
`--review-max-bytes` limit through 4 MiB, retaining its 256 KiB default and refusing
all valid snapshots. Separate `memory-project-staging-discard` verifies owner,
project identity and snapshot integrity for canonical/noncanonical staging records;
it rejects duplicate JSON keys. Full raw bytes, validated record, current project
memory, historical workspace anchor, file/storage/lock identities and review limit
are bound to one preview. Stale raw, logical, metadata or policy bindings fail
before deletion. Both paths share private single-link reads and interrupted
unlink/flush receipts. Actual process death, real maximum-size inputs and preserved
live memory/session state are covered. Snapshot/context limits are unchanged. See
[exact-byte staging review](CONVERSATION_MEMORY_STAGING_REVIEW.md).

**Unsupported backup disposal:** `memory-backup-discard` reviews exact invalid
backup bytes with explicitly unverified project attribution and current-memory
protection. `memory-project-backup-discard` validates owner/project identity and
snapshot integrity for noncanonical, misnamed or oversized backup encodings. It
refuses duplicate keys, supported canonical backups, and missing, unreadable or
matching current project memory. Complete raw bytes, actual/canonical backup names,
unsupported reasons, historical workspace anchor, current memory, file/storage/lock
identities and review limit (256 KiB by default, configurable through 4 MiB) bind
preview to exclusive-lock apply. Staging and backups share bounded single-link reads and interrupted
unlink/flush receipts. No inventory, age/count promise, normalization, publication
or automatic recovery is added. Real size boundaries, unsafe files, stale bindings,
current-memory protection, partial failure and process death are tested. See
[unsupported backup review](CONVERSATION_MEMORY_BACKUP_DISCARD.md).

**Mapping registry history and recovery:** updates now retain and flush the exact
previous registry before publication. Explicit history lists at most 128 backup or
staging files, 8 MiB total, within a 1,024-entry scan; each file is bounded to 1 MiB.
Reviewed restore accepts canonical same-owner records, verifies content-addressed
backup names and every directory pin, preserves the source, backs up current bytes
including bounded corruption, and publishes revision `max(current, source) + 1`.
If the current record is absent or invalid, only the source revision is available.
Reviewed discard binds exact raw bytes, current registry, file/storage/lock identities
and refuses valid recovery-file deletion while current mappings are absent or invalid.
Partial receipts distinguish backup durability, publication, deletion and final flush.
Real process-death, partial backup, file replacement, size limits and both session
backend resume tests cover these boundaries. No automatic recovery or cleanup runs.
See [mapping history and recovery](CONVERSATION_MEMORY_MAPPING_RECOVERY.md).

**Reviewed mapping import:** a private same-owner versioned path manifest now
imports up to 128 mappings/1 MiB. Merge previews identify additions, unchanged
entries and conflicts; apply blocks conflicts unless keep/replace is explicitly
selected. Whole-registry replacement lists removals and permits a reviewed empty
registry. Duplicate JSON keys, unsupported fields/types, foreign owners, unsafe
files, duplicate canonical workspaces and stale file/parent/directory identities
are rejected. Preview hashes bind complete input/current bytes, resolved mappings,
policies and destination identities. Publication retains the exact prior registry
and reports backup/publication/flush progress. Existing snapshot/SQLite resumes
and memory documents retain their identities/content. No startup import, automatic
rebind or history retrieval is added. See
[reviewed bulk mapping import](CONVERSATION_MEMORY_MAPPING_IMPORT.md).

**Mapping-history retention:** explicit `memory-project-mapping retain` reviews
up to 128 canonical owner-scoped backups/8 MiB within a 1,024-entry scan, with a
1-MiB per-file limit. Newest-count, explicit filesystem-mtime cutoff and exact
current-registry protections combine; an absent current registry protects every
backup, while corrupt current data or any invalid/unsafe backup blocks retention.
At most 32 oldest eligible backups are selected. Apply rechecks the complete
inventory minus its own removals before every unlink and reports removed/flushed
names separately. Real limits, retained-file changes, process death, partial CLI
errors and both backend resumes are tested. No automatic cleanup or session/memory
changes are introduced. See [mapping-history retention](CONVERSATION_MEMORY_MAPPING_RETENTION.md).

**Remaining migration limits:** mapping files larger than 1 MiB and unsupported artifact basenames remain
outside registry recovery/cleanup. Files above 4 MiB, ambiguous duplicate-key snapshots,
unsupported backup filename syntax and foreign-owner/project or user snapshots
remain outside the supported backup disposal workflows.
Unselected resolution backups are retained; no automatic deletion, startup recovery
or session identity rewriting is enabled. Common Git metadata or remote URLs never
merge memory.

| Scope | Contents and reach | Initial storage design |
| --- | --- | --- |
| User | Personal preferences and facts the user chooses to reuse across projects. | Private user memory under the configured Mos home. |
| Project | Curated reusable project decisions, conventions, setup details and verified traps the user chooses to retain. | Private memory keyed by owner and canonical project root under the configured Mos home. |

Temporary execution state belongs in the task checkpoint (§6.7.2): active branch,
current test results, blockers, pending work and next actions are not ordinary
startup memory. A deliberate request to retain a temporary fact may record its
revision/expiry and revalidation requirement; it must not become an evergreen
claim. Do not silently migrate or delete existing user-authored memory. The new
classification is a planned proposal/edit contract, not a claim that the current
Markdown memory implementation enforces semantic categories.

Use readable Markdown content with versioned metadata (scope, project identity,
source, revision and update time). The UI exposes the exact storage location.
Project memory is private to its owner by default; storing it beside source or
sharing it through Git is an explicit export choice. A shared remote URL does not
merge project identities or users' memories. Project moves and worktree sharing
require an explicit mapping, with the effective project identity shown to the user.

- **Loading and precedence:** load enabled user memory and the selected project's
  memory at session start. Specific project preferences override general user
  defaults; the user's current instructions override both. Memory never overrides
  application policy or grants approvals, credentials, tools or spending authority.
  Show which scopes and revisions are active and make conflicts inspectable.
- **User controls:** `/memory` shows active user/project entries and their sources.
  Support scoped add, edit, delete, clear and enable/disable controls, plus a
  session-level option to start without memory. A request such as "remember this
  for this project" directly authorizes that scoped save; "remember this everywhere"
  selects user memory. Resolve an ambiguous scope before persisting it. Report the
  actual saved change and scope. Model-suggested memories remain proposals until
  accepted; never silently promote tool output, repository text or whole transcripts.
- **Session consistency:** retain the effective memory revisions with session
  state and request evidence. Changes apply at an explicit next-turn refresh, never
  to a dispatched request. Resume shows stale/deleted revisions and offers current
  memory or no memory; it must not silently restore a forgotten item as active memory.
  Clearing memory stops future inclusion and explains any copies retained in saved
  sessions/backups, with deletion controls for those records under §17.
- **Scope and context limits:** initially cap combined memory at 32 KiB and account
  for it separately from conversation and project-instruction budgets. Make omitted,
  oversized, unreadable or invalid content visible; never silently truncate a rule.
  Apply bounded file reads and private, atomic writes. User memory is available
  across projects only because it was explicitly saved to that scope; project facts
  never migrate into user memory automatically. Keep secrets out of generated
  memory, and apply provider transfer policy to memory included in live requests.
- **Review isolation:** independent critics/judges receive only memory-derived
  requirements deliberately materialized in their scoped brief. They do not load
  ambient personal memory or conversational history. Memory remains distinct from
  repository `AGENTS.md` instructions and minimal model-selection aggregates.

The scope/precedence reference is [Codex's global and project guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
checked 2026-09-09. The memory storage, controls and retention rules above are Mos
product decisions; they do not assert that Codex implements this memory design.

**Acceptance:** demonstrate visible directory selection, isolated projects and
users, user preferences surviving a new project session, project overrides and
current-message precedence, scoped remember/forget, disabled memory, bounded
loading, concurrent-edit conflict detection, safe resume after edits/deletion,
and unchanged critic isolation. Deliver inspectable, explicit memory first;
automatic memory extraction remains a later, separately configurable feature.
### 16.0.3 Session names and easy resume

**User direction, 2026-09-10 — implemented for the recorded terminal:** users can give sessions memorable names
so they can find and resume the right conversation without remembering its ID.
Naming and the resume picker are delivered together. See the
[usage, integrity and capacity contract](CONVERSATION_NAMES.md).

- Allow an optional name when creating a session, for example
  `mos chat --name "Parser cleanup"`. Support renaming or clearing an existing name
  from the terminal (`/rename`) and an explicit session-management command.
  Unnamed sessions remain supported, and the immutable session ID remains the
  authoritative identity through every rename.
- Show the name alongside the ID in the session header, `mos sessions`, and the
  resume picker. Support filtering the picker by name and explicit lookup such as
  `mos resume --name "Parser cleanup"`, scoped to the selected owner, workspace,
  storage location and backend. Exact-ID and `--last` resume remain available.
- Allow duplicate names, but never silently select one matching session over
  another. Show matching IDs, saved times and workspace information for explicit
  selection; noninteractive ambiguous lookup must fail with guidance to use an ID.
  Specify consistent Unicode normalization, whitespace and case matching rules.
- Treat names as bounded, private user-authored metadata. Render them safely and
  keep them out of model instructions, curated memory and automatic fresh-session
  history retrieval. Naming or renaming must not dispatch work, alter conversation
  content, or make another user's or project's sessions discoverable.
- Persist names across restart, resume, migration and export/import for both JSON
  and SQLite storage. Define versioned metadata and integrity coverage so existing
  unnamed sessions and saved state hashes remain verifiable. Use the existing
  ownership, locking and stale-selection guards for rename and resume; a changed
  or deleted selection requires an explicit new choice.

**Acceptance:** create, rename, clear, list, filter and resume named sessions on
both backends; preserve names through restart and transfers; retain compatibility
with unnamed sessions; test duplicate and Unicode names, invalid/oversized input,
safe terminal rendering, workspace/user isolation, concurrent rename and stale
selection. Selecting a name must not automatically continue queued work.

**Delivered scope:** `mos chat --name NAME`, `/rename NAME`, `/rename --clear`,
`mos session-rename`, `mos resume --name NAME`, and interactive bare `mos resume`.
Names use 1–120 printable NFC characters, trim outer spaces, preserve interior
spaces, and match with Unicode case folding. Duplicate names require explicit
selection; noninteractive ambiguous lookup fails with ID guidance. Rename uses
the existing lock/save path and changes revision, state hash and saved time while
preserving conversation content and recording progress. Optional metadata is
omitted for unnamed state so older canonical bytes and hashes remain verifiable.
Name persistence is covered across SQLite working saves, migration, export and
transfer. Names stay outside model requests and memory.

The picker retains bounded summaries and renders 20 rows per page, with filtering,
refresh, cancel, active-session status, full selected name/ID and stale-selection
checks before controller recovery. SQLite reads metadata pages of 100 up to 1,000
sessions; JSON keeps its existing 256-session, default 8 MB snapshot scan. Larger
catalogs require existing paginated listing and explicit-ID resume. These are
navigation bounds, not an increase to conversation capacity. Live setup and
cross-workspace browsing remain separate work.

### 16.0.4 Repository-grouped sessions and isolated worktrees

**User direction, 2026-09-12 — planned:** let users organize sessions by repository
and start independent tasks in isolated Git worktrees, following the interaction
pattern of Codex. The official [worktree documentation](https://learn.chatgpt.com/docs/environments/git-worktrees)
describes parallel chats in separate checkouts and choosing a starting branch.
The requirements below define Mos Eisley's scope; they are not availability claims.

**Repository and session navigation:**

- Provide a repository list in the terminal and an equivalent CLI listing. Under
  each repository, group its registered local-checkout and linked-worktree sessions.
  Show session name/ID, branch or detached commit, worktree path, last activity,
  active/idle status and whether the worktree is missing. Support bounded paging,
  filtering, keyboard selection, new session and explicit resume. Keep the active
  repository and worktree visible alongside the conversation and diff panel.
- Use an owner-scoped repository identity verified against Git's common directory
  and registered worktrees. A directory name or matching remote URL is insufficient:
  unrelated clones and nested repositories remain separate. Aliases of the same
  verified checkout should not duplicate groups. Relocation requires an explicit
  verified rebind; missing or replaced paths must not silently select another tree.
  Non-Git directories retain ordinary workspace sessions with worktree creation
  shown as unavailable.
- Grouping is navigation metadata. It does not merge transcripts, broaden file
  permissions, select project memory across worktrees, or feed sibling sessions to
  a model. Preserve existing explicit memory mappings and same-owner storage rules.
  Cross-worktree selection resolves the saved session's exact workspace and policy;
  existing workspace-scoped `--last` behavior remains unchanged. Opening a session
  stays passive until the user submits work.

**Create and use an isolated worktree:**

- From a selected repository, offer a new session in an isolated worktree. Let the
  user choose a local starting branch or commit and optionally name the session and
  new branch. Resolve and retain the exact base SHA before creation; use a unique
  private managed path and either a unique branch or detached HEAD. Respect Git's
  branch checkout restrictions and never reset an existing branch to make room.
  Register an existing owner-approved worktree as an alternative to creating one.
- Preserve the source checkout, staged/unstaged changes and untracked files. Start
  from the selected commit by default; including local edits is a separate explicit
  snapshot operation with conflict handling. Do not copy secrets, ignored files or
  run repository setup hooks automatically. Environment setup uses the existing
  trusted execution policy.
- Bind the session, tools, terminal, tests and diff view to its selected worktree.
  Multiple sessions may progress in separate worktrees while keeping independent
  drafts, task state, approvals and evidence. Switching the visible session neither
  redirects an active operation nor cancels another session. Serialize conflicting
  writers to one checkout and shared Git metadata operations through the broker.
  Git worktrees share repository metadata and are not a security sandbox.
- Persist repository/worktree IDs, canonical path, starting SHA and observed
  branch/HEAD with the session using versioned JSON/SQLite metadata. Resume rechecks
  ownership, Git registration and tree identity before enabling tools; external
  moves, branch changes and missing worktrees require reconciliation. Preserve
  legacy session hashes and workspace identities during migration.

**Lifecycle and acceptance:** retain worktrees across restart and conversation
archival. Archiving/deleting a session and removing a worktree are separate actions.
Removal must check active sessions/processes, Git locks, dirty/untracked files and
unmerged or unreferenced commits, with no automatic force removal or branch deletion.
Require a verified preservation path or an explicit decision to discard changes.
Retain session history and review evidence independently of checkout cleanup; a
removed worktree remains visible as unavailable for execution. Interrupted creation
or removal must have inspectable, bounded recovery without touching unrelated paths.

Acceptance tests must demonstrate two simultaneous sessions on one repository in
different worktrees, isolated edits and correct tool/diff targets, grouped discovery
and exact resume after restart on both storage backends, and unchanged source edits.
Cover duplicate names, unrelated clones with identical remotes, nested repositories,
path substitution, foreign owners, stale selections, branch collisions, concurrent
Git operations, active/dirty worktree cleanup and interrupted creation/removal.
Verify that grouping never imports sibling history or changes memory selection.

**Delivery:** repository identity and metadata-only grouped navigation can follow
the G1 session foundations. Managed worktree creation, coding and integration belong
to G4 / Author-VCS (original M6), after trusted Git and applicable containment gates;
coordinate the session selector with the v1 diff panel (§16.4.1). This feature adds
no new dependency to the G2 live read-only review exit gate. WSL2 and native Windows
qualification follow §27.

### 16.1 Commands

Initial prompts now use `mos chat "PROMPT"` or `mos -- "PROMPT"`; a launch beginning
with session options also accepts one prompt. The explicit separator preserves
unknown-command errors. Startup submits literal text through the shared controller
before reading piped follow-ups or awaiting TUI input, with existing input, memory,
context, storage and recorded-request checks. Blank, oversized or invalid UTF-8
prompts fail before storage creation. Resume without submitted input stays passive
and never repeats the initial prompt. See the [terminal guide](CONVERSATION_TUI.md).
The command examples below also include later planned capabilities.

```
mos                                    # interactive TUI in cwd
mos -C /path/to/project                 # select and display the working directory
mos -- "prompt"                        # TUI with literal initial prompt
mos chat "prompt"                      # explicit new-session form
mos exec "prompt"                      # non-interactive
mos exec --json "prompt"               # NDJSON events, one per state change
mos exec resume --last
mos review <ref> | --pr <n> [--post]   # the adversarial pipeline
mos resume [<id> | --last | --all]
mos replay <run-id> [--agent <name>]
mos sandbox exec -- <cmd>              # test the active profile
mos policy check --tool <name> [-- <argv...>] # resolve, explain; never execute
mos blame <file>:<line>                # run provenance
mos eval <suite> [--sweep]
mos models
mos features                            # maturity + effective-policy status
mos auth login|logout <provider>
mos mcp login|logout <server>
mos update check                        # planned: check published application releases
mos update                              # planned: guided application upgrade
mos completion <shell>
```

### 16.2 Flags

| Flag | Meaning |
|---|---|
| `-m, --model` | override model |
| `-p, --profile` | layer a named profile |
| `-s, --sandbox` | `read-only \| workspace-write \| danger-full-access \| none` |
| `-a, --ask-for-approval` | `untrusted \| on-failure \| on-request \| never` |
| `-e, --effort` | canonical effort level |
| `-c key=value` | inline config override, repeatable |
| `--cd` / `--add-dir` | working dir / extra writable root |
| `--network` | opt into network in workspace-write |
| `--json` | NDJSON events to stdout |
| `--output-schema <file>` | validate the final result against a bounded schema |
| `--roster` | named model roster for review roles |

`mos policy check` must use the same resolver and semantic command validators as
dispatch, print the decision and policy provenance, and perform no model, tool, or
network action. `--output-schema` constrains only the final typed result; it cannot
select tools or capabilities, and schema failure exits non-zero after one bounded
format-repair attempt. Feature flags report `experimental | preview | stable |
disabled-by-policy` and are maturity gates, never a way for project config to bypass
trusted policy.

### 16.3 Config layering

Project guidance templates use the explicit project binding and precedence contract
in §16.6. The historical "closest wins" sketch below cannot grant authority or
silently replace an approved template, requirement, or project-memory selection.

```
~/.mos-eisley/config.toml                # base
~/.mos-eisley/<profile>.config.toml      # profile overlay
<project>/.mos-eisley/config.toml        # project (closest wins)
AGENTS.md                         # project instructions, 32 KiB cap
CLI flags and -c overrides        # highest priority
```

```toml
# ~/.mos-eisley/config.toml
model           = "claude-opus-5"
effort          = "high"
approval_policy = "on-failure"
sandbox_mode    = "workspace-write"

[sandbox_workspace_write]
network_access  = false
writable_roots  = ["/tmp"]

[budget.default]
session_cap = 400_000 ; headroom_pct = 0.05 ; compact_at = 200_000

[roster.default]
author  = { model = "claude-opus-5", effort = "high" }
critics = [
  { model = "claude-opus-5", effort = "high", persona = "correctness" },
  { model = "gpt-5.5",       effort = "high", persona = "spec"        },
  { model = "gemini-3-pro",  effort = "high", persona = "operational" },
]
judge   = { model = "gpt-5.5", effort = "xhigh" }
```

```toml
# ~/.mos-eisley/review.config.toml — ship this in the repo
sandbox_mode    = "read-only"
approval_policy = "never"
compaction      = "disabled"
network_access  = false
[budget.default]
session_cap = 120_000
```

Read-only plus never-approve means a review invocation cannot modify the filesystem or pause for input regardless of what the brief or the model says.

### 16.4 TUI slash commands

```
/status /context /compact /clear /new /model /effort
/approvals /sandbox /diff /review /init
```

`Alt+,` / `Alt+.` steps effort down/up mid-session. Persistent status line: model, effort, sandbox mode, live token count against budget.

Extend context/status inspection and fresh continuation with §6.7's selection,
pressure and checkpoint contracts. Command names listed here remain planned where
the conversation documentation does not report an implementation.

### 16.4.1 V1 — live full-screen diff panel

**User direction, 2026-09-12:** include a live `/diff` panel in product v1's
conversation/TUI workstream. Its acceptance criteria are required for v1 release;
the feature remains planned. Deliver it after the trusted read-only Git and
workspace/path boundaries are available, alongside Git-backed coding integration.
No package version is assigned by this entry. The interaction reference is the
Claude Code newsletter from Lydia, received 2026-09-12, titled "This week in
Claude Code: /resume on desktop, start sessions from your phone, and more",
specifically its live diff panel and selected-lines-to-prompt behavior.

- In full-screen mode, `/diff` toggles a panel beside the conversation. Show the
  changed-file list, per-file added/removed line counts, and a navigable diff.
  Preserve the composer draft, conversation scroll position and active task when
  opening, closing or moving focus between panes. Support keyboard navigation
  and mouse selection where the terminal supports it.
- Refresh as agent or external edits change the selected workspace. Coalesce
  updates and perform bounded Git reads outside the UI event loop; preserve file,
  hunk and scroll selection where possible. Show refresh failures and stale data
  explicitly. Cancel old refreshes on directory switches and reject results bound
  to the previous workspace or an obsolete refresh generation.
- Label the comparison basis. Initially show tracked staged and unstaged changes
  relative to HEAD, with their status distinguished; list untracked files separately
  and preview them only within existing read policy. Handle an unborn HEAD,
  renames, deletions, binary files, no changes and non-Git directories explicitly.
  Bound files, bytes and rendered hunks, disclose omissions and offer explicit
  bounded expansion. Never imply a partial view is the complete patch.
- Let users select diff lines and attach them to the next prompt. The composer
  shows a removable attachment preview with workspace, path, old/new line ranges,
  comparison basis and snapshot digest. Freeze the selected bytes; later refreshes
  cannot silently change the attachment. Indicate when its source has changed.
  Count attachments against request/context limits, preserve them on rejected
  submission, and retain admitted provenance with the request. Selection alone
  neither sends a request nor authorizes an edit or review. Treat excerpts as
  untrusted source content, never as instructions or an automatic critic brief.
- Target a side-by-side layout at 110 or more terminal columns, following the
  reference. At narrower widths use a focused diff view or an explicit resize
  notice; preserve drafts and selections through resize. Keep plain/JSON modes
  functional without terminal layout or escape sequences.

Dependencies: full-screen conversation controls, the trusted read-only Git broker
and workspace/path policy, plus bounded prompt attachments. Diff reads must disable
external diff/textconv helpers and use the existing trusted Git configuration.
Panel operations do not stage, revert, commit or expand tool authority.

Acceptance: exercise real PTY open/close/focus/resize behavior; concurrent edits
and rapid refresh; staged/unstaged/untracked, renamed, deleted, binary and oversized
inputs; stale selections and attachments; request rejection and retry; directory
switch isolation; hostile paths/terminal text and Git configuration; and continued
conversation, cancellation and draft preservation while the panel is open.

**Preliminary engineering estimate:** 60–100 hours, with 80 hours for planning:
12–20 for layout/navigation, 16–26 for bounded Git refresh, 16–28 for selected-line
attachments, and 16–26 for integration, review, tests and documentation. This assumes
the trusted Git and conversation foundations have shipped; their implementation,
Windows qualification and desktop pop-out windows are outside this estimate.

### 16.5 Event stream

```
{"type":"session.started","run_id":"...","sandbox":"read-only","roster":"default"}
{"type":"agent.started","agent":"critic.spec","model":"gpt-5.5","effort":"high"}
{"type":"token_count","agent":"critic.spec","system":1200,"tools":3400,
 "instructions":800,"turns":15200,"tool_output":40100,"budget":110000}
{"type":"command.classified","cmd":"pytest -q","decision":"auto","reason":"allowlist"}
{"type":"command.denied","cmd":"curl …","reason":"network_blocked"}
{"type":"approval.requested","cmd":"npm install","policy":"on-failure"}
{"type":"finding","agent":"critic.spec","severity":"correctness","location":"src/x.py:44"}
{"type":"effort.escalated","agent":"judge","from":"xhigh","to":"max"}
{"type":"verdict","decision":"revise","required_changes":3}
{"type":"session.completed","cost_usd":4.12,"duration_s":186}
```

---

### 16.6 Project-specific points of view and best-practice templates

Support attaching one or more declarative guidance templates independently to each
project, including existing repositories not generated by the production template.
Provide a guided initialize/attach/show/update/detach flow in the planned CLI and
conversation controls. Start with local Markdown plus a versioned descriptor;
remote distribution can follow the trusted package/extension gates. The editable
starter is `templates/PROJECT_POINT_OF_VIEW.md`. Copying it into a repository is
usable as documentation today; automatic role-context loading remains planned work.

**Local inspection slice implemented:** `mos guidance-inspect --descriptor FILE
--markdown FILE -C WORKSPACE` now verifies a bounded, versioned advisory descriptor
and its exact Markdown content digest. Stable rule IDs map to unique exact text
spans; inspection reports applicability, rationale, checks, full source bytes and
locations. A revalidatable snapshot binds the inspector's owner, canonical target,
raw descriptor bytes and content while remaining explicitly unbound. Unknown or
executable/authority-bearing fields, duplicate keys/IDs, missing/ambiguous spans,
unsafe final files and oversized inputs reject. Only the two user-selected files
are read. Inspection does not attach templates or activate conversation, history,
tool or provider paths. See [local guidance inspection](PROJECT_GUIDANCE_INSPECTION.md).

**Private binding slice implemented:** `mos guidance attach|show|update|detach`
binds explicitly reviewed snapshots to the owner's exact canonical workspace and
directory identity. Mutations preview complete before/after data and a diff, then
apply the reviewed hash under the private storage lock. Immutable snapshots survive
updates/detach and can be inspected by digest; empty records retain a revision counter
for stale-review rejection. Sources and stored identities are revalidated before
publication. Eight templates per project and 512 KiB per stored file bound this
slice. Binding neither loads history nor changes session contexts. Automatic semantic
analysis, accepted requirements and role materialization
remain subsequent work. See [private project guidance binding](PROJECT_GUIDANCE_BINDING.md).

**Independent override slice implemented:** `mos guidance-overrides set|clear|show|effective`
reviews and pins a complete project profile of up to 64 advisory rule replacements
or omissions with explicit reasons. Qualified rule IDs must exist in attached
templates. Effective inspection shows defaults, approved adjustments, omitted rules
and exact provenance; it does not materialize model context. The profile is bound
to the entire binding revision, so any binding change requires explicit re-review
before effective use. Previews include previous/proposed rule text and source bytes;
guarded publication retains immutable versions. Unknown authority fields and unsafe
or oversized inputs reject. User direction, accepted requirements and trusted policy
remain separate higher-authority layers; automatic semantic analysis and role contexts
remain later work. See [project guidance overrides](PROJECT_GUIDANCE_OVERRIDES.md).

**Explicit conflict assessment slice implemented:** `mos guidance-conflicts set|clear|show|effective`
records reviewed conflicts among active qualified advisory rules. Preferred-rule
choices require rationale, respect advisory precedence, and cannot exclude another
chosen winner through overlapping resolutions. The complete assessment is pinned
to binding/override revisions; changed guidance makes it stale. Both effective
inspection paths expose unresolved/stale/unassessed status and retained exclusion
provenance. Empty assessments require explicit review rationale and claim only that
no conflicts were reported. Guarded publication retains immutable source/basis
snapshots; historical views cannot claim current resolution completion. Automatic
semantic detection, trusted-policy integration and role
materialization remain later work. See [project guidance conflict review](PROJECT_GUIDANCE_CONFLICTS.md).

**Requirement acceptance slice implemented:** `mos requirements set|show|clear`
reviews a complete accepted set from up to eight explicitly selected brief/ADR
files. Stable requirement/source IDs, exact unique source passages, content hashes,
applicability, rationale and checks are retained in private project revisions.
Guarded apply binds the complete proposal, prior state and owner/directory identity;
clear preserves history and a revision tombstone. Source labels and advisory templates
cannot self-accept requirements. [Requirement acceptance](PROJECT_REQUIREMENTS.md)
documents limits and examples. The combined review below pins these accepted
revisions; trusted-policy integration and role-context materialization remain subsequent work.

**Combined precedence slice implemented:** `mos guidance-assess set|clear|show|effective`
reviews accepted requirements and active advisory rules in one independently reviewed
assessment. Accepted requirements outrank approved overrides and advisory defaults;
contradictory accepted requirements remain unresolved until the accepted set changes.
The complete requirement/binding/override basis is pinned, stale choices stop applying,
and historical reports cannot claim current completion. Existing advisory-only
assessments do not establish combined completion. [Combined guidance review](PROJECT_GUIDANCE_PRECEDENCE.md)
documents explicit conflict references, guarded publication and scope. Automatic
semantic detection, trusted-policy evaluation and role-context loading remain subsequent work.

**Owner-policy selection check slice implemented:** `mos guidance-policy-check`
checks the current combined view against explicitly selected owner-private policy
outside the project, bound to a reviewed raw hash and exact owner/project identity.
Qualified prohibitions can block selected requirements or advisory rules; they cannot
grant runtime authority or be waived by a guidance assessment. Allowed output requires
current complete combined review and satisfied prohibitions; blocked/incomplete results
return nonzero. [Owner policy checks](PROJECT_GUIDANCE_POLICY.md) document scope,
consistency, limits and a private-file example. This read-only slice does not evaluate
arbitrary policy prose or replace runtime controls. Broader user/admin policy
intersection, runtime admission and frozen role contexts remain subsequent work.

**Frozen role-context slice implemented:** `mos guidance-context freeze|show`
projects explicitly selected rules into bounded creator/coder/critic/judge packets.
Every omitted accepted requirement needs a scope reason; unresolved/stale guidance,
policy prohibitions and unavailable rules reject. Guarded apply pins selection,
policy and the combined assessment into immutable private snapshots. Historical reads
reconstruct exact projections from retained sources and cannot claim current authority.
[Role guidance packets](PROJECT_GUIDANCE_ROLE_CONTEXT.md) exclude unselected source
text, private policy prose and automatic history loading. Safe-boundary run/provider
admission, broader policy intersection and retention/recovery remain subsequent work.

**Current role-context admission slice implemented:** `mos guidance-context check`
requires exact role/scope and snapshot/context hashes, current complete assessment
and an explicitly selected unchanged private policy. The guarded local loader
reconstructs the packet and holds the guidance lock through short local use, with
source/identity rechecks. Its diagnostic output is not reusable authority.
[Current role admission](PROJECT_GUIDANCE_ROLE_ADMISSION.md) documents stale rejection,
consumer constraints and remaining run-manifest/provider integration.

**Recorded review guidance slice implemented:** `mos guidance-review prepare|run`
projects matching current critic/judge packets into an explicit review brief before
request hashing and byte-budget checks. Run admission checks both current packets
and the selected policy before and after offline execution. Hashed guidance artifacts
pin source/derived briefs and role provenance; historical replay verifies projection
without reopening current sources. [Guided recorded reviews](PROJECT_GUIDANCE_REVIEW.md)
document bounded inputs, exact rubric pairing, schema compatibility and remaining
live terminal/provider integration. Recorded fixtures do not establish live quality.

**Terminal guided review slice implemented:** `mos guidance-review packet` exports
bounded guidance-bearing review packets for terminal `/review`. Plain/TUI execution
checks explicit launch policy and current exact project guidance before queueing and
execution, and rechecks after recorded execution. Resume never reuses historical
admission; directory handoff clears project-specific selections. Snapshot/SQLite
artifacts retain exact provenance without importing chat memory or creator history.
[Terminal guided reviews](CONVERSATION_GUIDANCE_REVIEW.md) document the unchanged
terminal budgets, schema compatibility and remaining live provider authorization.

A template describes its ID/version, scope, source revision and content digest,
engineering preferences, applicability, rationale, verification rubric, logging
and note conventions, and justified departures. Separate advisory preferences from
accepted project requirements by stable rule ID. A template's own label cannot
make a recommendation mandatory: the user accepts requirements through the project
brief or an ADR. Language/framework choices, statistical methods, deployment and
observability stacks, and review cadence remain project choices, not global rules.

The trusted owner configuration binds the template snapshot and approved project
overrides to an exact workspace/project identity. Repository-local declarations
request guidance only; opening a repository, nested folder, or same-named project
cannot activate or change it. Shared default templates remain immutable snapshots;
overrides affect only the selected project. Show a concrete diff before adoption or
updates, preserve existing files, and never silently track a template's latest
version. Explicit user requests to attach/update constitute authorization for that
scope; do not add a second confirmation when it is already authorized. Detach stops
future inclusion without deleting project work or rewriting historical manifests.

Resolve effective guidance visibly: current user direction within trusted policy,
accepted project requirements/ADRs, approved project overrides, then selected
advisory defaults. Mandatory-policy conflicts cannot be resolved by a template;
report unresolved same-priority contradictions. A justified departure from an
advisory preference can be recorded and executed within existing authority without
another approval step. No template can add tools, execute commands, select secrets
or storage destinations, increase budgets, or relax containment. References are
explicit, bounded, project-scoped inputs, not automatic recursive file/network reads.

Materialize only the relevant approved guidance into each role's brief. Creator
plans and tests cite applicable requirement/rubric IDs; coding children receive the
same requirements for their scope. Critics/judges receive the frozen requirements,
rubric, and approved departures without creator transcripts or private work notes.
Record exact template/override digests and included rule IDs in run provenance.
Changes during a run apply at a safe boundary; changes affecting approved plans or
tests require §15.7 re-review. Policy inspection explains effective guidance and
its provenance without executing template-suggested commands.

Static adopted guidance is declarative project configuration, not imported session
history. It cannot embed, reference for automatic loading, or launder saved memory,
notes, telemetry results, or conversation summaries into fresh sessions. Those
remain explicitly selected evidence under §§17.2 and 17.6. Template selection never
authorizes publishing private run data into a shared repository.

Apply §6.7.5's instruction-size diagnostics and task-scoped materialization to
templates and approved directory guidance. Root instructions hold stable broad
rules and canonical verification commands; specialized rules and detailed reference
material enter only the scopes that need them. Diagnostics are advisory and cannot
discard accepted requirements or select new authority-bearing inputs.

Acceptance: two projects using the same base retain independent overrides and
detach behavior; two users cannot see each other's private bindings or artifacts.
Test missing/changed versions, conflicts, nested projects, symlink/path escape,
oversize/cyclic references, instruction injection, history disguised as guidance,
mid-run updates, and replay against the pinned snapshots. This contract lands with
trusted project configuration and the conversation workstream; broader executable
extensions remain separate E1/E2 work.

---

## 17. Run artifacts and telemetry

**User direction, 2026-09-06:** retain transcripts, saved conversations, replay
artifacts, evaluation records, and model-selection evidence, with strict ownership
by one user. The user may point storage at local files/databases, a cloud database,
or object storage. The boundary is user identity, not physical storage location.
There is no cross-user pooling or aggregation, including anonymized statistics.

### 17.1 Retained artifacts and backend selection

The following is a logical artifact layout. A filesystem adapter maps it to private
directories; an object-storage adapter maps it to authorized private objects:

```
runs/<run_id>/
  manifest.json     # config snapshot, roster, git sha, brief_id, sandbox policy
  brief/
  agents/<name>/
    turns.jsonl  findings.json  budget.json
  commands.jsonl    # every classified command + decision + exit code
  critiques/        # per-critic, blinded
  verdict.json
  events.jsonl
  worktrees/        # disposable
```

**Configurable storage:** separate artifact storage from the metadata/index store.
Ship private local files plus SQLite first. Add adapters for a user-selected remote
SQL database (initially PostgreSQL) and object storage (initially S3-compatible).
Users may combine local and remote adapters. All adapters expose equivalent scoped
save/load/list/delete behavior, integrity checks, and retention controls; replay and
resume do not depend on local path layout. Remote support is planned, not currently
implemented.

Only trusted user configuration may select storage drivers, endpoints, databases,
buckets, regions, and credential references. Project files, prompts, plugins, and
model output cannot redirect persistence or choose another owner. Keep credentials
in the trusted controller, use encrypted transport to remote services, and enforce
encryption at rest. Show the effective storage destinations before the first write
under a changed configuration; never silently replicate or fall back to a different
destination when a backend fails. A storage change affects future writes; moving
existing records is a separate explicit, owner-preserving migration.

The index contains `runs`, `agents`, `findings`, `verdicts`, `usage`, and `commands`,
all scoped to the owning user. Local and remote indexes are equally private. No
team-wide Postgres sink, central analytics warehouse, or shared run catalog is part
of the design.

### 17.2 Ownership and isolation

- Resolve the owner from the trusted local identity or authenticated service
  identity, never a request's arbitrary `user_id`. Bind artifacts, indexes, caches,
  backups, evaluation lineage, skill evidence, spending records, and derived
  model-selection policies to that owner. Different devices/instances may access
  the same owner's chosen backend only with that owner's authenticated access.
- Enforce ownership on every read, write, list, search, resume, replay, export, and
  delete, including referenced artifacts and migrations. Use private directories
  and file permissions locally. Remote backends must use dedicated credentials/
  databases or enforce server-side row/object access controls. A table predicate,
  bucket prefix, opaque run ID, or unguessable content hash alone is insufficient.
- Shared infrastructure is allowed only when it preserves user isolation. Prohibit
  cross-user deduplication, shared content caches, global model rankings, pooled
  evaluation datasets, derived training data, and aggregate telemetry built from
  user records. Removing names or hashing identifiers does not create an exception.
- Fresh sessions cannot automatically retrieve earlier prompts, code, transcripts,
  summaries, embeddings, findings, or artifacts. The owner can explicitly resume
  a saved conversation or inspect selected prior records. Enabled user/project
  memory (§16.0.2) is a separate exception for explicitly curated facts and
  preferences, not permission to search historical content. Apply these ownership,
  retention and deletion rules to memory and its revisions too. Independent critics still
  receive only their materialized brief, even within the same user's session.
- Ownership covers replicas, object versions, temporary spools, database journals,
  and backups. Retention and deletion are user-controlled and cover derived records;
  report any backend backup/version expiry delay rather than claiming immediate
  physical erasure. Do not publish user artifacts through diagnostics or CI logs.

### 17.3 Model-selection exception across instances

Only minimal, structured performance aggregates for the same user may automatically
carry across sessions to select individual models and reasoning effort. Use an
allowlisted schema keyed by provider/backend, model/version, effort, and bounded
role/task categories, with counts and measured quality, completion, latency, token,
and cost statistics. Missing quality measurements remain unknown.

This selection store contains no prompts, code, conversation summaries, embeddings,
tool output, free-text feedback, file paths, repository identifiers, or per-run
content hashes. It is not a second transcript store. Keep it separate from the
retained raw evidence, restrict its consumer to that user's selection logic, and
provide an owner-scoped reset. No transfer to other users, fleet-wide optimization,
shared defaults learned from users, or centralized model-performance collection is
permitted. Model-selection evidence never grants permission to read prior content
into a new agent conversation.

### 17.4 Egress and acceptance criteria

Configuring remote persistence authorizes storage only at the selected destination,
not analytics, sharing, or model training. Approved inference can send the active
task's permitted context to its selected provider; it does not authorize uploading
the historical store. Verify provider/account data-handling requirements separately
before live use; Mos Eisley's storage isolation is not a claim about third-party
retention. Publishing a requested patch or review result is a separate scoped work
product action, never permission to export the underlying transcript or user stats.

Release gates: exercise two distinct users against every supported backend and
prove no cross-user read/write/list/search/replay/delete, reference substitution, cache
reuse, or contribution to model selection. Also test fresh-session context
isolation, explicit same-owner resume, concurrent same-owner access, forged owner
IDs, credential rotation, failed migrations, and owner-scoped deletion/reset.
Outbound capture must show no analytics or unintended storage copies. Backends
that cannot enforce these properties are unsupported; existing local privacy and
hash checks alone do not establish these guarantees.

Emit `token_count` with the full breakdown on **every** turn. Lack of compaction visibility is the standing complaint about long CLI sessions.

Redaction is an egress invariant, not merely a logging helper. Apply the same
versioned redaction policy before writing logs, indexing, replay display, export,
notifications, and outward service responses. Persist the redaction-policy digest
and record that a field changed without retaining the secret. If policy requires a
byte-exact raw artifact for deterministic cassette replay, keep it separately
encrypted with tighter access and retention; ordinary replay and display always use
the redacted form. Data minimization and capability isolation remain primary—the
redactor is defense in depth.

### 17.5 Operational logging and evidence-driven improvement

**Published-template re-review:** production-project-template commit
`d59f3e661a1fa3456505cf36f91b51f4a1c873ac` includes a Python event/sanitizer/sink core
and local JSONL spool plus a C++ encoder. Prefer evaluating the pinned Python
implementation behind a Mos-owned adapter before duplicating it. Version any
package or reviewed source extraction and retain provenance; generated archetype
placeholders and mutable branches are not runtime dependencies. This is a planned
integration candidate, not telemetry code installed by this plan amendment. See
`docs/PROJECT_GUIDANCE_DESIGN.md` for the published-source review and test scope.

Routing/loop records additionally use the decision-time eligibility, probability,
actual-action, verification, failure and follow-up contracts in §26.3 and the
revised routing design. They remain bounded and owner-scoped; they do not authorize
raw trajectory retrieval or automatic policy training. Missing historical fields
remain unknown rather than being reconstructed as experimental evidence.

Adopt the production template's structured event principles for Mos Eisley's own
runtime. Maintain a versioned mapping from canonical lifecycle events to its
language-neutral telemetry envelope: UTC time, severity, stable event/error code,
service/environment, release/revision, operation, outcome, safe correlation IDs,
and duration. Review and pin the source schema; an existing dot-named lifecycle
event is not automatically valid under a snake-case telemetry schema. Add bounded,
allowlisted fields for roles, route/effort, usage, pricing version, cost, gate and
stop reasons only when they support a named operational decision.

Measure completed tasks, provider/tool failures, timeouts/cancellation, budget
denials, review outcomes, and whole-task delegation cost. Keep accepted findings,
escaped defects, regressions, and measured quality alongside token/latency/cost
diagnostics; fewer tokens or log lines alone do not establish improvement. Missing
quality data stays unknown. Log handled errors once at their responsible boundary
and preserve safe causal references without copying exceptions or payloads into logs.

Operational events exclude prompts, completions, reasoning, source/diffs, tool
arguments/results, reviewer prose, secrets, and private/client data. The separately
retained conversation/replay artifacts in §17.1 retain their own explicit access
and retention contract. Do not export the content-bearing §16.5 event stream
directly. Bound serialization, queues, disk use, sampling and retention; surface
dropped-event counts, sampling coverage, and incomplete query windows.

If using the upstream spool, distinguish queue acceptance from fsync-confirmed
durability and pending records. Expose health independently of that same log sink,
including drop reasons, writer errors, accepted/durable gap, quarantine, pressure,
and drain failure. Consumers accept only closed files with verified checksum
sidecars, never bare JSONL or active/quarantine files. Validate quota/drop-new,
rotation, fork, crash recovery, and bounded shutdown on the actual service-account
filesystem. Keep spools owner-scoped; run IDs are not access controls. Apply the
Mos-specific schema and content allowlist before invoking upstream code: permissive
`safe_message`, arbitrary nested attributes, or sanitized traceback support do not
automatically satisfy the no-content telemetry contract.

Optional diagnostic sink failure may degrade observability with counted loss, but
must never weaken mandatory audit, authorization, before-send markers, or spend
ledger durability. Mandatory records retain their fail-closed transaction contract.
Telemetry cost estimates, including query-time repricing, cannot replace pinned
reservation/settlement prices or release uncertain spend. A `retryable` diagnostic
flag does not override request-specific retry prohibitions.

Keep telemetry owner-scoped and local by default. Optional `telem`/OTLP or other
export adapters require explicit trusted destinations, per-owner access/retention,
schema/redaction checks, and bounded failure behavior. No central multi-user data
pool, shared learned defaults, automatic export, or dependency on the template's
HDD/Parquet/DuckDB/Grafana deployment is introduced. Distinguish the project being
built's own telemetry design from Mos Eisley's private operational data.

Support explicitly requested reviews of scoped aggregates: name the user outcome,
baseline/query/window and limitations, distinguish observation from inferred cause,
create an owned improvement proposal with regression evidence and guardrails, then
assess on a later window. Cadence is project-configured; scheduling or observing a
signal does not authorize code, prompt, policy, or deployment changes. Tests cover
schema mapping, redaction, cardinality/resource bounds, sink failure versus required
audit failure, isolation, incomplete windows, and unchanged spending enforcement.

### 17.6 Bounded project memory and work notes

Provide optional project-scoped memory and note templates using the production
template's evidence-index pattern. Reusable memory contains stable keyed constraints,
accepted durable decisions and verified traps, each with a source reference and
last-verified date. Open work and volatile execution facts belong in task checkpoints
or bounded work notes (§6.7.2), not automatically loaded reusable memory. Verify
entries against requirements, code, tests, or ADRs before
use; memory is not evidence by itself. Retrieve before editing, update keys in place,
label uncertainty, and remove stale or duplicate entries. Never turn routine
progress, raw logs, transcripts, secrets, or hidden reasoning into durable memory.
Do not auto-rewrite policy based on a successful trajectory.

Keep disposable scratch private and ignored with task-end cleanup. Use a bounded
work note for multi-session work, handoffs, incidents, experiments, or material
investigations: objective, concise observations/attempts, evidence links, remaining
work, owner, and review/delete date. On closure, propose reusable verified facts for
scoped memory acceptance under §16.0.2, decisions for ADRs, maintained explanations
for docs, and work history for issues. Apply already-authorized publications within
their scope; closure alone grants no export or automatic memory-promotion authority.
Close obsolete notes and remove them only under the selected retention/deletion
policy. Tracking/export into project Git is an explicit
publication of a reviewed, sanitized project document, not default persistence.

Memory and notes default to private artifacts bound to both owner and project under
§17. Enabled, explicitly curated reusable user/project memory may load at startup
under §16.0.2. Task checkpoints and work notes require explicit selection or
same-owner resume; attaching a best-practice template does not authorize
automatic historical retrieval. The template's general "read project memory at
startup" guidance is narrowed accordingly. Independent critics receive only relevant
verified evidence deliberately frozen into their briefs, never creator work notes
or previous critiques. Record the selected artifact versions and limit retrieval
size; updates affect subsequent snapshots rather than changing an in-flight brief.

Add these workflows with private session storage and scoped repository writes, not
an automatic global memory service. Evaluate repeated-action rate, stale-memory
errors, retrieval misses, context cost, and correct task completion on representative
development and disjoint assessment tasks before expanding retrieval. Embeddings,
vector databases, automatic cross-session recall, autonomous memory/schema mutation,
and training on user records are not introduced by this amendment. Verify project
and owner isolation, explicit loading, stale evidence correction, safe cleanup,
concurrent edits, export boundaries, and deletion of derived copies.

### 17.7 Long-session storage and independent budgets

**Current baseline:** the recorded preview has independent storage, selected-context,
complete-request, active-input and pending-text admission limits. SQLite provides
incremental record/artifact persistence, bounded navigation and explicit migration,
export and retention operations. `/context` previews selection and full-request
admission; saved request admissions retain source selection, omissions and budgets.
These are byte-based local checks, not provider-native token measurements.

Cold verification still reads history, accepted saves still hash logical history,
and active text bookkeeping remains bounded by the preview's small message cap.
Visible author compaction, task-checkpoint continuation (§6.7), bounded history
transitions and the long-session acceptance gate remain open. The SQLite resume
checkpoint is storage metadata; it is not the task checkpoint defined in §6.7.

Detailed changes and original limitations are retained in the
[session storage implementation history](SESSION_STORAGE_IMPLEMENTATION_HISTORY.md).
Operator contracts remain in [CONVERSATION_STORAGE.md](CONVERSATION_STORAGE.md)
and [CONVERSATION_SQLITE.md](CONVERSATION_SQLITE.md). Add future implementation
history to the linked record; keep this section focused on current behavior,
outstanding work and acceptance.

The recorded preview still caps messages/attempts at 16. Raising the snapshot budget
does not lift
model context, memory, message, tool, or spending bounds. Complete the following
work before claiming support for long coding sessions:

| Stage | Required behavior and acceptance |
| --- | --- |
| Incremental persistence | Versioned local SQLite metadata and incremental records, with private owner-scoped immutable artifact/memory references. Commit each transition and its references before dispatch without rewriting all earlier content. Retain revision checks, consumed attempts and steering ancestry. |
| Bounded navigation | Stable cursors and bounded pages for listings and transcript reads. Resume loads a bounded working set; listing does not parse every transcript. Concurrent writes, stale cursors and missing references produce defined recoverable outcomes. |
| Independent budgets | Separate disk/retention quotas, page/record read limits, pending-input capacity, active model context, memory and provider spending. Report usage before capacity rejection. A storage increase grants no inference or tool authority. |
| Context management | Visible, versioned author compaction and §6.7 checkpoint continuation preserve current user instructions, decisions, unresolved work, task ledgers and required evidence links. Retain originals under policy and record selection/omissions. Detect stale repository/test state before dependent execution. Fresh sessions and independent critics cannot retrieve ambient history. |
| Migration and retention | Explicit owner-preserving migration with dry-run sizing, interruption recovery and count/digest verification. Retention previews and crash-safe cleanup include unreferenced objects and journals/backups under their documented expiry. Listing never silently migrates data. |
| Capacity and recovery gate | Demonstrate at least 1,000 messages and retained content above 32 MB with bounded page reads. Test crash boundaries, disk-full/truncated writes, concurrent writers, corrupt objects, stale cursors, interrupted migration, retention races, ownership and critic isolation using fixtures. |

The [implementation sequence](CONVERSATION_STORAGE.md#planned-incremental-storage)
defines this local work before remote SQL/object adapters, which must enforce
equivalent server-side ownership and retention guarantees. Do not substitute a
larger monolithic snapshot constant for these acceptance criteria.

---

## 18. Evaluation harness

All user-derived datasets, grading records, reports, and learned policies obey §17
ownership. Evaluate and compare within one user's data; do not create a shared
benchmark or persona/routing policy from multiple users' runs. Shipped synthetic
fixtures may be shared only when they contain no user-derived data.

### 18.1 Ground truth by mutation

Inject synthetic defects into reviewed commits of the owner's repositories:
off-by-one, inverted condition, dropped null check, swapped argument order, silently
changed default. These provide candidate seeded positives; filter equivalent or
trivial mutants and independently adjudicate the labels. Audit matched clean cases
and include real historical bugs. Generation is cheap; reliable ground truth is not
free. Keep exposed development regression fixtures separate from protected holdout.

### 18.2 Metrics

| Metric | Why |
|---|---|
| Detection rate on mutants | does it find real bugs |
| **False-positive rate on clean commits** | **the binding constraint** |
| Cost per true finding | is it worth running |
| Cross-family agreement rate | how independent are the critics really |
| Escalation payoff | did the retry change a verdict |
| Under-routing rate | did the selected route fail a task-quality criterion that an eligible stronger route passed |
| Routing regret | extra cost/latency versus the cheapest adequate route in hindsight |
| Calibration/OOD coverage | how often can the learned policy route rather than use its fallback |
| Localization accuracy | file:line correct, not just "something's wrong" |
| Correct-work damage | unnecessary changes requested or regressions introduced on independently established acceptable tasks |
| Whole-task completion and cost | include every stage, failed/abandoned task, repair, child, binding, test and judge call |
| Incremental stage value | paired ablation of caught/escaped defects and damage; overlap alone cannot justify removing review |

### 18.3 The (backend × model × effort) sweep

`mos eval --sweep` runs the backend × model × effort grid into the evaluation store.
Repeated, blinded results define the cheapest adequate route for each task under
pre-registered detection, false-positive, latency and cost constraints. API and
subscription-backed routes are separate cells even when their nominal model matches.
Fit an interpretable prompt-difficulty policy on the calibration split, freeze it as
a content-addressed artifact, then measure routing quality once on a final holdout.
Never tune thresholds on that holdout. Report confidence intervals and under-routing
separately for each role, backend, provider, repository domain and risk tag.

Current implementation evaluates each sealed prompt profile, preserves all candidate
scores, and reports route adequacy, fallback/fail-closed coverage and cost/latency
regret. Its exclusive local claim prevents an accidental second CLI attempt for the
same frozen policy in one trusted directory; it is not a substitute for independently
controlled holdout access.

Treat quality saturation, effort-related false positives, shared difficulty across
families, and historical lookup value as testable hypotheses, not routing rules.
Use reviewed current route/pricing snapshots when evaluating them. Pin grading and
judge settings while varying the registered execution candidates.

Repeated calls measure within-case variability, not additional independent tasks.
Three repetitions are a smoke test only. The implemented statistical protocol uses
a fixed complete matrix; calculate attainable sample size and cost before buying a
sweep. Sequential stopping, adaptive sampling and off-policy estimators require a
new reviewed protocol and cannot reuse its confidence claims. If no cheaper route
qualifies, retain the eligible fallback. Output-budget routing also requires a new
candidate/schema version; current route identity does not include that action.

---

## 19. Trust boundaries and security

Once the harness holds a GitHub token and can write to disk, prompt injection stops being a quality problem and becomes a security one.

### 19.1 Untrusted content sources

Every one of these is attacker-influenced in a normal workflow: PR diffs and titles, issue and comment text, file contents in the repo, dependency manifests, test output, fetched web pages, MCP server responses. **All of it arrives as data, none of it as instruction.**

### 19.2 Capability separation is the primary control

| Role | Reads untrusted input | Credentials | Filesystem write | Network |
|---|---|---|---|---|
| critic / judge | **yes** | none | no | **no** |
| author | via brief only | none | own worktree | allowlist only |
| publisher | structured `Verdict` only | GitHub token | none | GitHub API only |

The agent that reads the untrusted PR is not the agent that holds the token. A successful injection against a critic controls a process with no credentials, no write access, and no network — the blast radius is a bad finding, which the judge and the executable-evidence requirement are already designed to catch.

### 19.3 The schema airlock

Only typed `Finding` and `Verdict` objects cross from the untrusted side to the credentialed side. Free-form model output can never become an API call argument.

Residual risk: `claim` and `suggested_fix` are model-authored strings that get posted publicly. So the publisher must sanitize markdown and HTML before posting, must never let a finding field determine the endpoint, repo, or PR number, and must reject any finding whose `location` falls outside the diff under review.

### 19.4 Additional controls

- **Env allowlist.** Subprocesses get an explicit env list, never the parent's full environment. Inheriting `GITHUB_TOKEN` into a shell whose output goes back to the model is how tokens leak.
- **Outbound secret scanning.** Scan briefs and tool outputs for key patterns before they reach a provider. Fail closed on a hit.
- **Model allowlist.** Assert the resolved model ID against the roster before every call. Repository content never reaches a provider not named in the active roster.
- **Key storage.** OS keychain or env; never config files; redacted in all logs and event streams.
- **`danger-full-access` requires an explicit CLI flag**, prints a warning, and is never reachable from a profile alone.
- **Structured-output parsing as defense in depth.** A critic emitting prose instead of findings fails the run rather than passing free text downstream.

### 19.5 Brokered web evidence and cache

Critics and judges retain no NET capability. When a review needs current external
evidence, the trusted brief builder issues a bounded search/fetch request through the
network broker, freezes the result into the brief, and records query/URL, provider,
retrieval time, final resolved URL, response/content hash, media type, license or
usage metadata when known, and cache policy. Redirects, DNS resolution, private and
link-local addresses, scheme/port, request size, and response size are enforced by
the broker.

Cache keys must cover normalized request inputs, search/fetch provider and version,
policy, owning user, and freshness window—not just a query hash. No cache is reused
across users, and cached content is not automatically loaded into new sessions
under the model-selection exception (§17). Cache entries remain untrusted
content and can be stale or poisoned; they never become instructions, credentials,
or an authority source. A finding must cite the frozen artifact it used. This path
ships only after the no-NET critic invariant and injection corpus pass end to end.

### 19.6 Multimodal and document inputs

Support images later as content-addressed brief artifacts for screenshots, rendered
UI, diagrams, and visual diffs. Validate media type independently of extension,
decode with resource limits, strip active metadata where possible, and record the
exact bytes and transformations supplied to each provider. A model without the
required modality is ineligible for that route.

In the same later E3 phase, support reading PDFs, Word files (`.docx` and legacy
`.doc`), and scanned documents supplied explicitly in a conversation or review
brief. Extract text and tables from digital documents; use OCR for scanned pages
and image-only PDFs, with page rendering for visual interpretation when needed.
Preserve source references: PDF/scan page numbers and Word headings, paragraphs,
or table identifiers, plus rendered page numbers when available. Answers and review
findings must cite the source location, flag uncertain OCR or layout extraction,
and report unreadable, unsupported, or truncated content rather than silently omit it.

Also support reading Excel workbooks (`.xlsx`) and CSV files in E3. For XLSX,
enumerate sheets and extract bounded cell ranges and tables, preserving sheet names,
cell addresses, headers, value types, and formula text alongside available cached
values. Identify hidden sheets/rows and merged cells; report missing or potentially
stale formula results without recalculating formulas or refreshing external links.
For CSV, handle encodings, delimiters, quoted fields, and embedded newlines with
explicit parsing settings or reported detection assumptions. Preserve raw field
values, including leading zeros, and report ambiguous types or malformed records.
Support questions, summaries, and bounded tabular analysis with citations to XLSX
sheet/cell ranges or CSV logical record and column references. Disclose sampling,
truncation, and conversion assumptions so partial data is never presented as complete.

Keep originals and derived text, tables, OCR, and page images as content-addressed,
owner-scoped artifacts under §17 storage and retention rules. Record parser/OCR
versions, transformations, and the exact artifacts sent to each provider. Run
parsing, conversion, and OCR in an isolated, resource-bounded worker with no network
access; never execute macros, embedded scripts, or external document references.
Enforce file, page, sheet, row, column, cell-size, decompression, runtime, and
model-context limits. Document
content remains untrusted evidence, not instructions or authority; provider/data
policy and modality eligibility apply to every derived artifact. This is planned
reading support, with delivery gated by §24.4.

Audio/voice/realtime interaction is
not required by the review workflow and remains out of scope until a measured use
case justifies its privacy, storage, and provider-conformance surface.

---

## 20. Testing

| Layer | Approach |
|---|---|
| Adapters | recorded cassettes + nightly live conformance (§4.4) |
| Budget | property tests: usable input never negative, never exceeds model context |
| Effort | table-driven fallback tests against the registry |
| Tools | schema-subset validation at import |
| **Sandbox** | **negative tests: write outside root, network from read-only, `.git/hooks` write, symlink escape, `sudo` — all must fail on both backends** |
| Classifier | corpus of shell commands with expected auto/ask/deny labels; parse failures must ask |
| Blindness | assert a critic's serialized context contains no author transcript, no sibling critique, no model identity |
| Injection | corpus of adversarial diffs containing instruction-shaped text; assert no credential use, no network, no write |
| Pipeline | golden-run replay: fixed brief + cassettes → deterministic verdict |
| Policy preflight | `policy check` and real dispatch resolve identically; preflight performs no execution |
| Lifecycle events | ordering, timeout, backpressure, veto audit, and capability non-escalation |
| Subagents | capability-lattice intersection, depth/concurrency/budget caps, cancellation, cross-agent isolation |
| Skills | digest pinning, progressive-disclosure budget, untrusted-project non-escalation, inert scripts |
| Network broker | DNS rebinding, redirects, private IPs, cache poisoning/staleness, response/output limits |
| Redaction | seeded secrets absent from write, replay, export, notification, and service responses |
| Service boundary | authentication, caller-request narrowing, rate limits, replay rejection, cancellation |

The sandbox negative tests and the blindness assertions are the two most important suites in the repo.

---

## 21. Delivery milestones

**Historical table, not the active execution queue.** Use `docs/ROADMAP.md` and
§26.4 for current dependencies and acceptance gates. In particular, this table's
provider order, finding cap, agreement scoring and late-TUI sequence are superseded.

| # | Milestone | Exit criteria |
|---|---|---|
| **M0** | Canonical types, agent loop, Anthropic adapter, JSONL run log | One agent completes a tool-using task end to end; full transcript on disk |
| **M1** | Tool registry, schema subset, capability tiers, truncation | Read-only tier provably cannot write; import-time schema validation in CI |
| **M2** | **Execution layer: policy model, Seatbelt + bwrap/seccomp backends, `mos sandbox exec`** | Negative test suite passes on macOS and Linux; `none` mode works in a container |
| **M3** | **Approval policy + command classifier** | Labeled command corpus passes; parse failure asks; approvals cached per session only |
| **M4** | OpenAI + Google adapters, conformance suite | Same brief through all three, identical canonical shape, reasoning state survives 3-turn loop |
| **M5** | Registry, budget subsystem, effort subsystem, coupling | `mos models` prints registry; budget assertion fires on oversized prefix; effort fallback logged |
| **M6** | **Git integration: worktrees, protected `.git`, `apply_patch`, provenance trailers** | Author agent lands a patch in an isolated worktree; hook-write test fails closed |
| **M7** | Brief materialization + single blind critic + findings schema | Content-addressed brief; blindness assertions pass; ≤5 ranked findings parsed |
| **M8** | Fan-out to N critics, dedupe, judge, verdict | Full `mos review <ref>` produces a verdict with cross-family agreement scoring |
| **M9** | **GitHub integration + isolated publisher** | `mos review --pr N --post` posts inline comments; injection corpus shows no credential reach |
| **M10** | CLI surface: profiles, TUI, `--json` events, resume/replay | `mos exec --json` usable from CI; `review` profile ships read-only |
| **M11** | MCP client, tiered | An MCP server registers, is tiered, and its schemas pass the subset validator |
| **M11A** | Remote MCP: Streamable HTTP and token authentication (implemented; feature branch) | Remote discovery/read/write, destination and credential isolation, bounded streams, cancellation and uncertain-write tests pass; stdio remains compatible (§13.3) |
| **M11B** | Remote MCP: OAuth public-client login and credential lifecycle (implemented; feature branch) | Login, refresh, scope changes, reauthentication and logout pass issuer/callback, user/server isolation and no-duplicate-write tests (§13.3) |
| **M12** | Mutation eval + (backend × model × effort) sweep | FP rate on clean commits measured; routing policy set from data |

M2 and M3 moved ahead of the provider work deliberately. Once the harness can touch the machine, everything after it inherits whatever boundary you built — retrofitting a sandbox around an agent loop that already assumes free filesystem access is a rewrite.

### 21.1 OpenAI live-conformance prerequisite for M12

**Pinned 2026-09-07:** OpenAI broker output cannot enter the M12 empirical sweep
until six exact profiles—Luna/low, Terra/medium, Sol/medium, Sol/high, Astra/high,
and Astra/max—each have three consecutive, precommitted, distinct authenticated
successes. This is 18 successes total. Every attempted sample and terminal outcome
must be retained. After a failed attempt, the affected profile needs three newly
precommitted consecutive successes following a reviewed root-cause disposition and
regression test; failures cannot be silently replaced.

The prerequisite also requires five retained failure-boundary results: rejection of
an expired or mismatched authorization before credential access; a separately
consented live authentication rejection; a controlled ambiguous post-reservation
timeout/disconnect with retained exposure; a controlled invalid or identity-mismatched
structured response; and real-container launcher-death cleanup with read-only recovery.
Controlled ambiguous faults use dedicated ledgers that are never released or reused
for success. The complete operational contract and non-authority limits are defined
in `OPENAI_LIVE_CONFORMANCE_GATE.md`.

---

## 22. Open risks

1. **Sandbox is the highest-consequence subsystem.** Seatbelt is deprecated; bwrap needs privileges many container runtimes withhold; Landlock can't restrict reads. Every backend has a documented gap. Keep `--sandbox none` + container as a supported deployment rather than a fallback, and treat the negative test suite as release-blocking.
2. **Prompt injection with credentials attached.** Capability separation (§19.2) is the control, but it only holds if no one adds a network tool to the critic tier for convenience. Enforce it with a test, not a convention.
3. **Provider drift.** Effort ladders, context caps, and reasoning-state formats have all changed within two release cycles across all three vendors. The registry must be data; the conformance suite must run nightly.
4. **Cost.** N critics × 2 rounds × high effort is multiplicative. Cache-prefix discipline (§6.5) is the mitigation; per-run dollar caps are the backstop.
5. **Correlated critics.** If the three models share training data, "independent" agreement may be far less independent than the scoring assumes. The cross-family agreement metric exists to measure exactly this.
6. **False positives dominating.** Above roughly one spurious finding per clean commit, the tool gets ignored regardless of detection rate. Executable evidence is the main lever; be ready to make it mandatory.
7. **The judge as single point of failure.** One model adjudicating means one model's biases decide. Rotation plus periodic two-judge runs with disagreement tracking is the check.
8. **Classifier over-trust.** Denial detection is heuristic everywhere; an allowlist that grows from convenience rather than evidence is how a safe default becomes an unsafe one. Grow it from the `commands.jsonl` data, and re-review it quarterly.

---

## 23. Adversarial review

**Review date:** 2026-09-05
**Disposition:** **Revise before implementation.** The capability-separation direction is strong, but several stated invariants are mutually incompatible or weaker than they appear. The items below should be treated as changes to the plan, not merely implementation notes.

### 23.1 Release-blocking contradictions

#### A. `read-only` currently means “can exfiltrate any readable local file”

The sandbox table permits reads “anywhere permitted.” On a developer machine that can include SSH configuration, cloud credentials, browser state, source trees unrelated to the review, and other private files. Denying network does not solve this: a model can use the read tool and send the content to its model provider in the next inference request. Outbound secret-pattern scanning is bypassable and cannot be the primary boundary.

**Required change:** make filesystem reads allowlist-based. A critic should see only its materialized brief, a minimal runtime/toolchain image, and explicitly mounted evidence paths. Home directories, credential stores, other repositories, host `/proc`, and ambient Unix sockets must be absent rather than covered by deny globs. Record every file supplied to a provider in the run manifest.

#### B. Trusted user policy and untrusted project configuration are merged

`<project>/.mos-eisley/config.toml` and `AGENTS.md` are attacker-controlled when reviewing a PR, yet the layering rules let project configuration select providers, models, MCP servers, writable roots, sandbox behavior, and possibly network access. That lets repository content enlarge its own capabilities or route proprietary code to a new provider.

**Required change:** split configuration into:

- a **trusted policy** from user/admin configuration and explicit CLI grants;
- **untrusted project hints** that may choose prompts and test commands only within that policy.

Merge permissions by intersection, not “closest wins.” Project files may only reduce capabilities. They must never enable network, add a writable/readable root, register an executable or MCP server, select an unapproved provider, change the publisher target, or weaken approval policy. Print the resolved policy and its provenance before a run.

#### C. The TEST tier executes hostile code without a sufficient containment story

Running tests from an untrusted PR is arbitrary code execution. Read-only source and no Internet are insufficient: tests need scratch writes, can read mounted secrets, consume CPU/RAM/PIDs/disk, inspect processes, talk to Docker/SSH agents over `AF_UNIX`, and encode data into output that is then sent to a provider.

**Required change:** treat TEST as a distinct containment tier, not READ_ONLY plus a command. Use a disposable filesystem/VM or container with read-only source, a private per-agent scratch directory, an empty secret-free environment, no inherited file descriptors, no host sockets, and explicit CPU, memory, PID, disk, output, and wall-clock limits. Do not expose Docker or container-runtime sockets. Test execution should be disabled on a backend that cannot enforce those properties.

#### D. Git commits conflict with the promise that `.git` is always read-only

An author cannot stage or commit without writing the worktree index, object database, refs, and metadata under the repository’s common `.git` directory. A linked worktree also contains a `.git` pointer and mutates the user repository when it is created or removed. M6’s exit criterion is therefore impossible under §11.2 as written.

**Required change:** keep Git metadata outside the agent boundary. The agent edits ordinary files only; a small trusted VCS broker validates the resulting diff and performs allowlisted stage/commit operations. Alternatively, use a disposable clone whose entire Git database can be discarded. Worktree creation, commit, and cleanup belong to the controller, never the model-facing shell. Add locking and crash recovery for concurrent runs.

#### E. A separate publisher process is not automatically a security boundary

If the publisher runs as the same OS user, accepts requests on a discoverable local socket, or shares inherited descriptors/environment, compromised test code may be able to invoke or inspect it. Unrestricted `AF_UNIX` makes this worse. A typed payload prevents endpoint injection only if the endpoint identity is supplied by trusted controller state and the caller is authenticated.

**Required change:** use one-way, authenticated IPC; bind each request to immutable `(run_id, repository_id, PR_number, base_sha, head_sha)` values chosen before untrusted content is read; reject replays; and give the publisher no general-purpose filesystem access. Prefer a separate OS identity/container or a short-lived CI job with a GitHub App installation token. The local `gh` path must run only inside this publisher boundary, since it inherits user credentials.

#### F. “Network allowlist” is not defined at an enforceable layer

Seatbelt/seccomp can permit or deny sockets, but a hostname allowlist requires control of DNS, redirects, proxies, IP changes, and connection targets. Permitting general outbound sockets and asking tools to honor an allowlist is not enforcement.

**Required change:** deny raw outbound networking and route allowed HTTP traffic through a broker/proxy that enforces scheme, host, port, DNS resolution, redirect policy, request size, and response size. Mount only the broker socket into the sandbox. Define whether loopback and Unix sockets are denied by default; they should not be globally exempted.

#### G. The command classifier gives unsafe commands an undeserved “safe” label

A single simple command can still execute arbitrary code (`python -c`, `find -exec`, `git -c`, `make`, package-manager lifecycle hooks), mutate files (`sed -i`), or interpret attacker-controlled configuration. Conversely, reliably identifying every path argument from a generic shell AST is impossible. String deny patterns such as `--force` are not a security model, and parsing Bash does not help if execution uses another shell.

**Required change:** make structured, argv-based tools the default and avoid a shell parser on the auto-approved path. Give each allowed executable a semantic validator for its subcommands, flags, config loading, environment, and path operands. Treat general shell execution as an explicit capability that always remains sandboxed. An approval should authorize a precise capability delta, not declare a command safe. Include the executable hash, argv, cwd, environment-policy digest, sandbox-policy digest, and resolved paths in any approval cache key.

#### H. Backend degradation can silently invalidate the security claims

Landlock cannot provide the proposed read-confidentiality boundary, `none` provides no harness boundary, and enabling user namespaces or `SYS_ADMIN` may materially weaken the host/container posture. A global AppArmor sysctl change is too large a prerequisite for a CLI review tool.

**Required change:** publish a capability matrix and attest the active backend at run start. Security-sensitive workflows must fail closed when their required properties are unavailable. Label `none` as “externally contained/unverified,” require the caller to declare the external boundary, and never report it as equivalent to an enforced Mos Eisley sandbox. Remove the global sysctl recommendation from the default setup path.

### 23.2 Core model and provider-layer issues

1. **Do not replace provider-native tool IDs.** Keep a harness ID for correlation, but replay the provider’s native ID/signature exactly wherever its protocol requires it. The adapter should maintain a per-response mapping and reject ambiguous or missing mappings. “Never let a provider ID reach core” is too strict if lossless replay is a goal.
2. **The canonical `Turn` is underspecified.** It needs ordered content blocks, tool-result blocks, refusal/filter metadata, attachments or binary references, provider request IDs, and a versioned extension mechanism. Decide whether system/developer instructions are turns or immutable request metadata. Test interleaved reasoning, text, and multiple tool calls—not just shape equality.
3. **`opaque: dict` is not safely replayable by definition.** Provider state may contain ordered byte strings, signatures, SDK-only types, or fields that must not be persisted. Store a versioned provider envelope as bytes/JSON plus media type, SDK/API version, retention policy, and encryption status. If provider policy forbids persistence, downgrade the claim from replayable to auditable.
4. **The schema intersection is likely too restrictive for MCP.** Rejecting every `$ref`, union, and format will make many useful servers unregisterable. Add a deterministic schema-lowering layer with a loss report, or expose provider-specific wrappers. Never silently weaken validation. Validate tool *outputs* as well as inputs.
5. **Token counts are estimates until the provider reports usage.** Counting endpoints may differ from the final serialized request or omit future output/reasoning growth. Use conservative preflight estimates, reconcile with post-call usage, include retry and cache billing, and validate `reserve < cap`, `compact_at <= usable`, and all role/model combinations at configuration load.
6. **Caching is provider-specific.** A canonical cache breakpoint does not imply equivalent OpenAI, Anthropic, and Google behavior or pricing. Put cache strategy in adapters, log cache hits/writes from returned usage, and make the harness correct when caching is unavailable.
7. **Registry values are operational data, not source-code truth.** Every entry needs an effective date, API version, price units/currency, feature flags, data-residency eligibility, and provenance. Validate configured models with a low-cost capability probe and pin the resulting registry snapshot into each run. Do not promise that a vendor alias is immutable merely because it looks versioned.
8. **Escalation triggers are role-confused.** “No state-changing tool call” is expected for critics and judges, and schema failure usually calls for constrained repair rather than more reasoning. Define role-specific triggers and separate a format-repair retry from an effort-escalation retry. Self-reported judge confidence should not be the sole escalation signal.
9. **Startup failure at 25% prefix usage is arbitrary.** A large but intentional brief may be valid. Make this a warning plus an operator-configured hard maximum; fail on inability to reserve the required output or evidence budget, not on a universal percentage.

### 23.3 Review methodology issues

1. **`severity` mixes impact with category.** `correctness`, `security`, and `performance` are categories; `preference` is a disposition. Add separate fields such as `category`, `impact = blocker|high|medium|low`, and `blocking: bool` derived by policy. Otherwise agreement and verdict scoring are not coherent.
2. **Evidence needs provenance, not just a label.** Include observed result, expected result, artifact/command hash, exit status, relevant output range, executor identity, and whether the evidence was independently reproduced. Critic-authored commands must be validated and run by the evidence broker; a critic must not receive authority simply by placing a command in JSON.
3. **A five-finding cap can suppress critical defects.** Cap displayed findings, not collection. Never drop a blocker/security finding because five lower-impact issues ranked above it. Preserve overflow findings in the run artifact and measure how often truncation changes the verdict.
4. **Agreement is not evidence.** Cross-family agreement can amplify a shared misconception. Make reproduced evidence and spec conflict primary; use agreement only as a calibrated secondary feature. Learn weights on held-out evaluations rather than hard-coding them.
5. **Dedupe can destroy distinctions.** An embedding or LLM merge may combine defects with different causes or fixes. Preserve every original finding, have dedupe propose clusters, and let the judge split them. Give each finding and cluster a stable fingerprint.
6. **Blindness is only partial.** Model identity can be inferred from prose, and deliberately different personas confound model-family comparisons. Maintain two modes: heterogeneous coverage for production and same-persona replicated trials for evaluation. Report persona and model effects separately.
7. **Normalized-length summaries may remove decisive evidence.** The judge should receive bounded structured fields plus referenced evidence artifacts, not lossy prose normalization. Any summarization must retain links to originals.
8. **Rebuttal flow is unspecified.** Define exactly what the author sees, whether critics can respond, and whether new evidence is allowed. Do not reveal critic/model identities. A rebuttal should be structured per finding and cannot modify the artifact under judgment without creating a new `brief_id`.
9. **Quorum and outage semantics are missing.** Specify the minimum number and family diversity of successful critics, what happens on provider timeout/filtering, and how CI distinguishes `reject` from `infrastructure_error`. Never silently accept because critics failed. Do not launch a costly judge when quorum is impossible.
10. **Automated posting needs a human-safety mode.** Default `--post` to a draft/check annotation until false-positive targets are met. Rate-limit comments, make posting idempotent, collapse obsolete findings, and prevent mentions, bidi-control characters, oversized Markdown, or secret-like strings in public text.

### 23.4 Reproducibility, storage, and privacy

- **Replace “every run replayable” with three explicit guarantees:** (1) transcript playback, (2) deterministic pipeline replay using recorded provider/tool responses, and (3) best-effort live re-execution. Live model calls are not reproducible even with fixed effort and model IDs.
- A `brief_id` alone is insufficient. Pin the base/head blobs, submodules, untracked inputs, tool versions, dependency lockfiles, OS/architecture, environment policy, sandbox image digest, adapter/SDK/API versions, registry snapshot, prompts, schemas, and raw serialized requests. Verify hashes before a replay.
- Write logs atomically and make the manifest append-only or hash-chained. A crash between tool execution and logging must be detectable. Record controller decisions separately from model-controlled text.
- Raw transcripts, repository contents, reasoning envelopes, and command output are sensitive. Store under a private directory with restrictive permissions, configurable retention/deletion, encryption where appropriate, and redaction before indexing. Postgres should not receive raw or high-cardinality sensitive fields.
- Use SQLite for the default local index. Under the later §17 user direction,
  remote databases and object storage are configurable per user; the earlier
  team/CI aggregation proposal is superseded. Every backend must isolate users.
- Multi-provider review sends proprietary code to three vendors. Add an explicit provider/data policy: repository allowlist, consent, retention/zero-data-retention eligibility, region, maximum classification, and per-provider exclusions. Secret scanning is defense in depth, not authorization to upload.

### 23.5 Sandbox test gaps

The negative suite should additionally cover symlink races and replacement after validation, hard links, bind mounts, `/proc` and `/sys`, device files, inherited file descriptors, environment-variable loaders, dynamic linker variables, Git filters/hooks/config includes, Unix sockets (SSH agent, Docker, editor services), loopback listeners, DNS and redirects, process signaling, fork bombs, disk exhaustion, output floods, orphaned grandchildren, cancellation, and concurrent-agent cross-read/write. Run the suite on every supported OS/kernel combination; a mocked backend is not release evidence.

The plan also needs positive compatibility tests for compilers, package managers, language caches, and test runners. A sandbox that is secure but breaks normal builds will drive users toward `danger-full-access`.

### 23.6 GitHub-specific changes

- Prefer a GitHub App with short-lived installation tokens in CI over a long-lived PAT when feasible. Pin repository and permission scope in trusted controller state.
- `file:line` is not enough for review comments. Store base/head side, diff hunk/position, rename status, and blob SHA; gracefully fall back to a summary for deleted, binary, generated, or out-of-diff lines.
- Confirm the merge-gating semantics of verdict conclusions. A neutral conclusion may satisfy a required check and therefore fail to enforce `revise`. Map policy outcomes deliberately and keep `infrastructure_error` distinct from a code verdict.
- Prohibit `pull_request_target` in shipped examples for untrusted checkout/test execution; a warning leaves a predictable unsafe copy-paste path.
- Add idempotency keys, retry/rate-limit handling, stale-head rejection, and a dry-run payload preview before publishing.

### 23.7 Resource and lifecycle controls

Per-agent “limits” need enforcement below the Python loop. Put subprocesses in their own process group/container/cgroup, close inherited descriptors, apply rlimits/cgroup quotas, stream through a bounded spool, and kill descendants on timeout or cancellation. Reserve disk space for logs and fail cleanly when it is exhausted. Use private per-agent temp directories rather than shared `/tmp`, and ensure one agent cannot read another agent’s full-output spill files.

Cost caps are necessarily predictive before a provider response. Estimate the maximum next-call cost—including retained reasoning, retry, and cache writes—before dispatch; do not begin a call that can exceed the remaining cap. Define rate-limit fairness so one fan-out does not starve unrelated runs.

### 23.8 Recommended scope and milestone changes

**Product-priority amendment:** §16.0 supersedes the conversational TUI and resume
deferral below. The historical sequence remains here for design provenance; a
minimal conversation can ship over recorded/explicit inputs while machine access
and live review continue to meet their gates. See `docs/ROADMAP.md` for current order.

The current plan attempts a multi-provider agent framework, two OS sandboxes, a policy engine, Git/GitHub automation, MCP, a TUI, provenance, and an evaluation platform before demonstrating that adversarial review beats a simpler baseline. Reduce the first usable release:

1. **Security/design gate:** threat model, trusted/untrusted config split, capability lattice, provider data policy, run-state machine, and backend capability matrix.
2. **Offline core:** canonical types and pipeline against recorded fixtures/fake providers; no shell and no live machine writes.
3. **Local review MVP:** local diff/brief, read-scoped critics, structured findings, deterministic dedupe, judge, SQLite, JSON output. No author agent, test execution, MCP, network, TUI, commits, or posting.
4. **Evaluation gate:** compare one critic, N critics, and N critics plus judge on blinded clean/defective sets. Set explicit detection, false-positive, latency, and cost thresholds before expanding authority.
5. **Containment spike:** prove TEST isolation and resource controls on each supported backend. If a property cannot be enforced, remove it from that backend’s advertised capabilities.
6. **Write path:** add an author worktree plus trusted VCS broker only after containment tests pass.
7. **Publish path:** add authenticated isolated publisher, dry run, then GitHub posting.
8. **Convenience features:** resume/live replay, TUI, MCP, blame/provenance, and Postgres export after the security and quality gates.

M0 must not execute model-selected machine commands before the sandbox exists. Its “tool-using task” should use inert fixture tools or run inside an already verified external container. Move the threat model and config-policy tests ahead of every live provider milestone.

### 23.9 Evaluation corrections

- Mutation testing provides seeded positives, not complete ground truth. Equivalent/trivial mutants must be filtered, and “clean” commits can contain real defects. Use human adjudication, held-out repositories, real historical bugs, and periodically audited clean samples.
- Three repetitions are enough for a smoke test, not for choosing defaults across a
  large backend × model × effort grid. Pre-register primary metrics, report confidence
  intervals, control for multiple comparisons, and use sequential stopping/power
  analysis to manage cost.
- Prevent benchmark leakage: critics must not see mutation labels, mutation-generator templates, expected locations, or prior verdicts. Separate calibration and final holdout sets.
- Measure end-to-end utility: accepted true findings, developer override rate, time-to-resolution, review latency, and cost. Detection rate without developer trust is not a sufficient success criterion.
- A cassette-backed golden test can assert deterministic orchestration, but it says nothing about current live-model quality. Keep conformance, safety, and quality suites separate.

### 23.10 Decisions required before coding

| Decision | Recommended default |
|---|---|
| Is private source allowed to reach all three providers? | Deny unless repository policy explicitly allows each provider |
| What may project config change? | Prompts and commands within a trusted allowlist; capabilities only narrow |
| Is host test execution supported? | No; disposable contained executor only |
| Who writes Git metadata? | Trusted VCS broker, never the agent sandbox |
| What is the storage backend? | Local files/SQLite by default; user-selected cloud database/object storage with enforced user isolation (§17) |
| What happens without critic quorum? | `infrastructure_error`, never `accept` |
| Can a review post automatically in v1? | Dry-run/draft only until quality gates pass |
| What does “replay” mean? | Explicit playback, cassette replay, or best-effort live re-execution |
| Which sandbox properties are mandatory? | Read-scope, write-scope, no raw network/host sockets, resource limits, process cleanup |

**Go/no-go criterion:** do not grant WRITE, TEST, NET, Git credentials, or publishing authority until its boundary has a concrete threat model, a backend capability assertion, and adversarial tests that fail closed on every supported deployment target.

---

## 24. Adversarial review of the Arbiter Codex-parity delta

**Review date:** 2026-09-05

**Source:** `arbiter-codex-parity.md` from the local Downloads directory

**Disposition:** **Adopt selectively, with security and evidence gates.** The source
contains useful product-surface ideas, but “Codex has it” is not a sufficient reason
to add it. Parity can import mature interaction patterns; it must not import ambient
authority, duplicate service protocols, or claims that are unsupported or already
stale.

### 24.1 Source qualification

Current official documentation confirms that Codex has configurable subagents whose
model and reasoning effort can inherit or be overridden, and a skill system based on
progressive disclosure. It also documents Codex as an MCP client with stdio/HTTP
transports and OAuth. Those facts support the general concepts, not the exact Arbiter
interfaces or security defaults:

- [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Codex skills](https://learn.chatgpt.com/docs/build-skills)
- [Codex MCP client](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

The official [Codex documentation index](https://learn.chatgpt.com/docs/llms.txt)
currently labels the older “Use Codex with Agents SDK” MCP-server path deprecated
and points users toward App Server or the Claude Code plugin. Therefore, an outward
Mos Eisley MCP server can be justified by interoperability, but not by an
unqualified claim that it is required for current Codex parity. Product-comparison
claims must carry a verification date and official source; unsupported claims are
treated as design hypotheses.

### 24.2 Decision matrix

| Proposed parity item | Decision | Adversarial disposition |
|---|---|---|
| Lifecycle hooks | **Adopt, narrowed** | Implement typed events and trusted bounded handlers (§14.1). No arbitrary shell hook, ambient environment, or authority increase. A finding requests evidence; it never causes direct execution. |
| General subagent spawning | **Adopt** | Use the common primitive in §14.2 with a fresh materialized brief, capability-lattice intersection, lineage, aggregate budgets, depth/concurrency caps, and cancellation. |
| Automatic child after repeated compaction | **Reject pending evaluation** | It changes semantics and can multiply spend. Compaction count is telemetry until a held-out comparison proves a better result under the same total budget. |
| Skills/personas | **Adopt, staged** | Version and hash prompt/rubric assets (§14.3). Repository skills are untrusted selectors, scripts are inert, and persona migration requires regression and held-out evaluation. |
| MCP server plus app server | **Split and defer** | Keep the client. Add one narrow outward protocol only after quality/security gates (§13.2); do not maintain two auth/session stacks without distinct users. |
| Image and audio inputs | **Images later; audio deferred** | Images have a concrete review use case and receive artifact/media controls (§19.6). Audio, voice, and realtime interaction do not yet improve the core review outcome. |
| PDF, Word, and scanned-document inputs | **Adopt later in E3** | Extract text and tables from PDFs and Word files; OCR scanned documents with source citations, extraction-quality reporting, isolated processing, and owner-scoped artifacts (§19.6). |
| XLSX and CSV inputs | **Adopt later in E3** | Read workbook sheets and delimited tables for bounded analysis with sheet/cell or record/column citations, explicit parsing assumptions, inert formulas, and the same artifact/isolation controls (§19.6). |
| Cached web search | **Adopt after containment** | Only the trusted brief builder gets brokered network access. Critics consume frozen, cited, untrusted artifacts; the cache includes provenance and freshness (§19.5). |
| Endpoint and auth modes | **Adopt, hardened** | Use trusted endpoint records and typed credential references (§4.5), not arbitrary URL/header dictionaries. Require TLS/loopback exception, SSRF controls, conformance, and provider/data policy. |
| Provider, model catalog, and selection extensibility | **Adopt, staged** | Define versioned adapter/catalog/selector contracts with the core provider and routing work; deliver trusted external adapter and selector loading in E1. Additional routes and strategies must satisfy existing conformance, eligibility, spending, and evaluation gates (§§4.6, 5.1, 7.6). |
| Local open-weight models | **Keep out of v1** | Different branding does not prove independent training lineage. “Free per call” ignores hardware, energy, operations, and latency. Add a local endpoint only if blinded evaluation shows incremental coverage or acceptable cost/quality. |
| Model-keyed capability defaults | **Reject** | Model labels such as “frontier,” “small,” or “cyber” are mutable and do not determine the OS authority a task needs. Policy is task/role/data based; a provider or model restriction may narrow authority, never raise it. |
| Per-project guidance, memory, and observability | **Adopt, scoped** | Add declarative project template binding (§16.6), owner-scoped operational telemetry (§17.5), and explicitly selected memory/notes (§17.6). Engineering preferences remain project-specific; no automatic history import or estate-wide telemetry dependency. |
| Policy preflight | **Adopt** | `mos policy check` shares the dispatch resolver, explains provenance, and executes nothing (§16.1–16.2). |
| Feature flags | **Adopt** | Use maturity gates with explicit policy status. Flags cannot bypass trusted-policy intersection. |
| Structured final output | **Adopt** | `--output-schema` validates a bounded final object and has no capability-selection effect. |
| Write/replay redaction | **Adopt and strengthen** | Use one egress invariant across persistence, display, replay, export, notification, and services (§17); isolate any policy-approved encrypted raw cassette. |
| Nonblocking MCP startup | **Adopt with required-tool semantics** | Lazy/concurrent startup is useful, but a required-server failure is an infrastructure error rather than an invisible skip (§13.1). |
| MCP login/logout, shell completion, notifications | **Adopt incrementally** | Credential lifecycle belongs to the trusted controller. Completion is low risk. Notifications must use redacted typed events and an allowlisted destination; none belongs on the critical path. |
| Branching, undo, per-turn checkpoints | **Defer** | Hidden Git refs and metadata writes conflict with the VCS-broker boundary. First implement content-addressed patch snapshots in the disposable run store; add branching only after replay semantics, retention, locking, and recovery are specified. |
| Devcontainer profile | **Adopt as evidence, not proof** | Pin the image by digest and run positive/negative backend tests inside it. An externally contained profile must attest its properties; a container file alone does not prove namespace, socket, resource, or host isolation. |
| Hook/subagent milestone reordering | **Do not retroactively reorder** | The implementation already has pipeline/evaluation work. Add the extension substrate after the §23.8 evaluation gate; do not let parity work bypass containment or quality evidence. |

### 24.3 Additional requirements introduced by this review

1. **Extension supply chain.** Every executable extension needs an immutable digest,
   provenance, compatibility range, capability declaration, signature/allowlist
   decision, and revocation path. Prompt-only assets still need a digest because a
   rubric change can alter false-positive rate.
2. **No authority from configuration vocabulary.** A field named `sandbox`,
   `tier`, `headers`, `endpoint`, `model`, or `skill` in an untrusted project,
   MCP call, or service request is only a request. The trusted resolver supplies and
   intersects actual authority.
3. **Event safety.** Lifecycle payloads are bounded and redacted, handler order is
   deterministic, blocking decisions identify a trusted policy owner, and vetoes are
   auditable. Observability handlers default to fail-open for availability; security
   policy handlers use an explicit fail-closed mode.
4. **Child isolation.** A child sees no parent transcript, sibling state, credentials,
   or spill files unless a content-addressed reference is explicitly mounted.
   Aggregate limits are reserved before spawn so parallel children cannot each spend
   the full remaining budget.
5. **Search-cache integrity.** Cached pages and search snippets are never privileged
   because they were fetched earlier. Validate redirects on every refresh, retain the
   resolved-source chain, expire negative and error entries, and make stale use
   visible in findings.
6. **Interoperability before breadth.** The outward service begins with narrow,
   idempotent, schema-versioned operations. A general remote agent runner, caller
   chosen sandbox, or caller chosen credential context is explicitly excluded.

### 24.4 Evidence gates

These additions are not promoted to stable because they exist. Promotion requires:

- lifecycle and skill non-escalation tests plus a malicious-extension corpus;
- project-guidance isolation, precedence, pinned snapshots and bounded references;
  memory/note explicit loading and safe export; operational telemetry redaction,
  failure behavior, and unchanged mandatory audit/spend guarantees (§§16.6, 17.5–17.6);
- subagent comparisons against the existing specialized review path, reporting
  quality, cost, latency, isolation failures, and aggregate-budget violations;
- all six three-provider creator/critic/judge assignments through common contracts,
  with role isolation and capability rejection; creator-led coding fixtures proving
  creator-written plan/tests, critic/judge review, and exact creator approval precede child execution, at
  least one child performs meaningful coding, test weakening and stale approvals
  fail, and final code
  receives review; matched delegation studies report clean/efficient output and
  whole-task cost including integration and rework (§§7.7, 14.2.1, 15.7);
- network-broker SSRF/DNS-rebinding/redirect/cache-poisoning tests and proof that
  critics remain unable to open sockets;
- endpoint conformance and data-policy approval for every new backend;
- provider and selector extension contract suites demonstrating registration without
  core-loop changes, version/identity validation, revocation, and no authority
  escalation; catalog refresh cannot enable routes, and selection preflight/dispatch
  must agree subject to explicit rejection when eligibility changes (§§4.6, 5.1, 7.6);
- egress tests seeding credentials in prompts, tool output, events, MCP traffic, raw
  artifacts, and replay paths;
- service-boundary authentication, rate-limit, cancellation, replay, and
  caller-request-narrowing tests;
- image decompression-bomb, malformed-media, metadata, and cross-provider
  conformance tests before multimodal routing becomes eligible;
- PDF, Word (`.docx`/`.doc`), and scanned-document fixtures covering text/table
  extraction, OCR quality, source citations, and explicit partial/unreadable results;
  malformed files, decompression bombs, active content, external references, and
  prompt injection must not escape worker isolation or resource limits, and derived
  artifacts must pass owner-isolation, retention, and provider-conformance checks;
- XLSX/CSV fixtures covering multiple and hidden sheets, merged cells, value types,
  formulas and missing cached values, encodings, delimiters, quoting, embedded
  newlines, leading zeros, and malformed records; verify source references,
  bounded analysis, explicit sampling/truncation, inert formulas/external links,
  resource limits, and the same artifact/isolation controls as document inputs.

**Result:** parity work is post-gate extensibility. It may make Mos Eisley easier to
integrate and specialize, but it cannot advance ahead of the local review quality
gate, containment proof, or the trusted/untrusted configuration split in §23.8.
The user-directed declarative project guidance, private memory/notes, and local
operational-event contracts in §§16.6 and 17.5–17.6 can be built with the conversation
and storage workstreams. Their write, export, and executable-extension capabilities
still require the corresponding gates; attaching guidance cannot advance authority.

### 24.5 Post-gate delivery order

| Phase | Scope | Exit criteria |
|---|---|---|
| **E1 — control substrate** | policy preflight, egress redaction, typed lifecycle events, feature maturity registry, typed credentials/endpoints, trusted provider/selector extension loading and model catalog overlays | preflight/dispatch equivalence; seeded-secret egress suite passes; handlers and extensions cannot escalate authority; adapter/catalog/selector contract suites pass; every endpoint passes conformance and data-policy checks; automatic strategies remain evaluation-gated |
| **E2 — delegation assets** | general subagent primitive, creator-approved plan review and delegated coding, versioned skills, persona migration experiment | aggregate-budget and isolation tests pass; interchangeable role contracts and plan-approval ordering pass; coding also requires execution/VCS containment; delegation meets preregistered quality/efficiency and whole-task cost targets; specialized versus general pipeline comparison meets pre-registered non-inferiority thresholds; skill version does not regress false-positive target |
| **E3 — external evidence** | brokered fetch/search, provenance cache, image brief artifacts, PDF/Word reading, scanned-document OCR, and XLSX/CSV reading and bounded analysis for conversations and reviews | critics remain socketless; broker and cache adversarial suites pass; images, documents, and tabular inputs pass isolation/resource and cross-provider conformance; extraction/OCR and tabular parsing quality, source citations, and owner-scoped artifact handling meet §24.4 |
| **E4 — interoperability** | narrow outward MCP server, credential lifecycle, completion and redacted notifications | authenticated schema-versioned operations pass narrowing, rate-limit, cancellation, idempotency, and replay tests; no general remote runner |

An app server, audio/realtime mode, automatic compaction delegation, local model
route, and Git-backed turn branching remain unplanned candidates. Each requires a
separate measured use case and threat-model amendment before receiving a milestone.

---

## 25. Adversarial review of Skills, SecretRef, and Doctor

**Review date:** 2026-09-05

**Source:** `mos-eisley-skills-secrets-doctor.md` from the local Downloads directory

**Disposition:** **Adopt the prompt-only skills foundation now; split and defer the
authority-bearing subsystems.** The proposal correctly identifies provenance,
shadowing, validation/use races, secret exposure, and diagnostic drift. It combines
three independently risky systems, however, and assumes a configuration substrate
that this implementation intentionally does not yet have. Shipping them together
would turn a prompt-asset feature into new host-code and credential paths.

### 25.1 Decision matrix

| Proposal | Decision | Required narrowing |
|---|---|---|
| Portable `SKILL.md` | **Adopt now** | Follow the Agent Skills frontmatter shape; keep Mos-only structure in an optional sidecar. |
| `mos.yaml` | **Adopt narrowly** | Only `version` and `kind = persona | procedure`; extra fields fail. It grants no capability. |
| Progressive loading | **Adopt now** | Snapshot the whole bounded package once, disclose metadata/body/resources progressively from that immutable snapshot. |
| Source precedence | **Reject project-wins** | Preserve source-qualified identities, report collisions, and require exact references. A project package never shadows a user package. |
| Skill trust/tiering | **Defer persistence** | Project activation requires an explicit invocation-local opt-in. Structural validity is never trust. Add durable approvals only after trusted config provenance exists. |
| Scripts/toolbundles/check code | **Reject in this phase** | Reject `scripts/`, executable bits, `toolbundle`, and `allowed-tools`; do not import package code. |
| Persona migration | **Observe now; promote later** | Bind only bodies exactly matching request-bound recorded personas. Change personas only after paired golden/held-out evaluation. |
| Per-skill provenance | **Adopt now** | Record source, name, version, whole-package digest, instruction digest, byte count, and critic binding in a hashed run artifact. |
| SecretRef | **Defer as a separate security program** | First implement config provenance, child-environment isolation, read denial, audited transport substitution, and seeded-secret egress tests. |
| Opaque secret handles | **Useful defense, not a boundary** | The transport necessarily sees plaintext. Never claim handles solve SDK/proxy/log leakage. |
| Secret migration | **Defer** | Requires crash-safe journaling and scoped residual-secret verification without plaintext backups. |
| Doctor diagnostics | **Defer executable/fix surface** | A future read-only typed check registry can land separately. No skill code imports; online and billable probes are explicit. |
| `doctor --fix` | **Defer** | Automatic mutation needs per-remedy idempotence, re-verification, collision handling, and a permanently non-secret/non-sudo boundary. |

### 25.2 Implemented foundation and invariants

The first slice is implemented in `run/skills.py`, `core/skills.py`, the `mos skills`
CLI, and schema-2 recorded-run artifacts. It enforces:

1. only explicitly supplied roots are read; there is no ambient home, repository,
   config, or `AGENTS.md` discovery;
2. activation uses `source:name@sha256:whole-package-digest`, never a mutable name or
   version alone;
3. project packages require explicit activation and never win a collision;
4. all package bytes are bounded and snapshotted before use; later filesystem edits
   cannot change the activated body or lazy resource;
5. YAML aliases, anchors, tags, and duplicate keys plus symlinks, special files,
   executable bits, scripts, and capability vocabulary fail closed;
6. validation and discovery explicitly grant no authority;
7. recorded skill bindings exactly cover critics and their activated instructions
   must reproduce each cassette persona byte for byte; replay verifies their hashed
   provenance artifact.

### 25.3 Evidence and remaining gates

The implementation has malicious-package and integration tests, but it does not
establish that any persona improves review quality. Before a persona revision replaces
an inline default, pre-register a paired comparison on identical clean and defective
samples and report detection, clean false-positive risk, calibration, completion,
latency, tokens, and cost. Freeze the package digest before holdout and apply the same
family-wise correction and independent-group rules as the routing study.

Before SecretRef, land read-denial and child-environment isolation across every
supported containment backend. Seed secrets through config, provider errors, HTTP
diagnostics, tool output, events, run/replay/export, and crash paths. Before doctor,
define a versioned result contract and prove offline mode opens no network path;
mandatory security checks cannot succeed by skipping.

The first offline doctor/template diagnostics should also expose §6.7.5's instruction
sizes, duplicate/scoped-rule advisories and selected MCP/tool schema costs. Required
missing capabilities fail explicitly; editorial size heuristics remain warnings.
These checks parse bounded data and reuse approved metadata. They do not import
skill code, start servers, resolve secrets or make provider calls merely to report
context overhead. Keep them separate from deferred executable remedies and fixes.

The package snapshot prevents ordinary post-validation drift but not a malicious
same-UID process racing trusted ancestor directories. Package signatures and archives
are absent, so historical reconstruction depends on retaining the exact digest-named
package. These limits are explicit in `docs/SKILLS.md` and milestone review 22.

**Historical evidence index:** the implementation sequence below is retained in
[skills and provider implementation history](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md).
The original headings remain as stable reference targets. Current delivery work is
in §26.4 and the roadmap; append future detailed execution records to the history
instead of expanding the active plan.

### 25.4 Implemented paired evidence gate

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#254-implemented-paired-evidence-gate).

### 25.5 Implemented independent promotion-readiness gate

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#255-implemented-independent-promotion-readiness-gate).

### 25.6 Implemented deterministic package retention

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#256-implemented-deterministic-package-retention).

### 25.7 Implemented current archive-to-promotion binding

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#257-implemented-current-archive-to-promotion-binding).

### 25.8 Implemented authenticated revocation and rollback nomination

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#258-implemented-authenticated-revocation-and-rollback-nomination).

### 25.9 Implemented transactional quarantine staging

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#259-implemented-transactional-quarantine-staging).

### 25.10 Implemented independent one-use installation authorization

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2510-implemented-independent-one-use-installation-authorization).

### 25.11 Implemented atomic inert installation and recovery evidence

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2511-implemented-atomic-inert-installation-and-recovery-evidence).

### 25.12 Implemented independent atomic default selection

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2512-implemented-independent-atomic-default-selection).

### 25.13 Implemented signed post-selection health and drift eligibility

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2513-implemented-signed-post-selection-health-and-drift-eligibility).

### 25.14 Implemented one-use skill runtime preparation and spend admission

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2514-implemented-one-use-skill-runtime-preparation-and-spend-admission).

### 25.15 Implemented full routing revalidation and guarded broker admission

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2515-implemented-full-routing-revalidation-and-guarded-broker-admission).

### 25.16 Implemented independent dispatch-authority consumption

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2516-implemented-independent-dispatch-authority-consumption).

### 25.17 Implemented ephemeral request-bound broker capability

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2517-implemented-ephemeral-request-bound-broker-capability).

### 25.18 Implemented provider-owning pre-reserved transaction

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2518-implemented-provider-owning-pre-reserved-transaction).

### 25.19 Implemented content-verified runtime response publication

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2519-implemented-content-verified-runtime-response-publication).

### 25.20 Implemented authenticated runtime conformance attestation

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2520-implemented-authenticated-runtime-conformance-attestation).

### 25.21 Implemented portable publication-history witness

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2521-implemented-portable-publication-history-witness).

### 25.22 Implemented authenticated aggregate billing evidence

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2522-implemented-authenticated-aggregate-billing-evidence).

### 25.23 Implemented credential-isolated Admin API billing collection

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2523-implemented-credential-isolated-admin-api-billing-collection).

### 25.24 Implemented failure-preserving brokered evaluation assembly

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2524-implemented-failure-preserving-brokered-evaluation-assembly).

### 25.25 Implemented authenticated brokered evaluation conformance receipt

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2525-implemented-authenticated-brokered-evaluation-conformance-receipt).

### 25.26 Implemented no-send evaluation conformance ceremony preflight

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2526-implemented-no-send-evaluation-conformance-ceremony-preflight).

### 25.27 Implemented signed evaluation conformance authorization

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2527-implemented-signed-evaluation-conformance-authorization).

### 25.28 Recorded first authenticated Terra/medium live conformance success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2528-recorded-first-authenticated-terramedium-live-conformance-success).

### 25.29 Recorded first authenticated Sol/medium live conformance success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2529-recorded-first-authenticated-solmedium-live-conformance-success).

### 25.30 Recorded first authenticated Sol/high live conformance success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2530-recorded-first-authenticated-solhigh-live-conformance-success).

### 25.31 Recorded first authenticated Astra/high live conformance success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2531-recorded-first-authenticated-astrahigh-live-conformance-success).

### 25.32 Recorded first authenticated Astra/max live conformance success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2532-recorded-first-authenticated-astramax-live-conformance-success).

### 25.33 Sealed the second OpenAI live-conformance campaign

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2533-sealed-the-second-openai-live-conformance-campaign).

### 25.34 Recorded second authenticated Luna/low live conformance success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2534-recorded-second-authenticated-lunalow-live-conformance-success).

### 25.35 Completed the Luna/low live-conformance profile

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2535-completed-the-lunalow-live-conformance-profile).

### 25.36 Recorded second authenticated Terra/medium live conformance success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2536-recorded-second-authenticated-terramedium-live-conformance-success).

### 25.37 Completed the Terra/medium live-conformance profile

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2537-completed-the-terramedium-live-conformance-profile).

### 25.38 Recorded second authenticated Sol/medium live conformance success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2538-recorded-second-authenticated-solmedium-live-conformance-success).

### 25.39 Completed the Sol/medium live-conformance profile

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2539-completed-the-solmedium-live-conformance-profile).

### 25.40 Recorded second authenticated Sol/high live conformance success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2540-recorded-second-authenticated-solhigh-live-conformance-success).

### 25.41 Completed the Sol/high live-conformance profile

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2541-completed-the-solhigh-live-conformance-profile).

### 25.42 Recorded second authenticated Astra/high live conformance success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2542-recorded-second-authenticated-astrahigh-live-conformance-success).

### 25.43 Recovered the Astra/high output-limit failure

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2543-recovered-the-astrahigh-output-limit-failure).

### 25.44 Sealed the replacement Astra campaign

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2544-sealed-the-replacement-astra-campaign).

### 25.45 Preserved the v3 pre-dispatch image failure

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2545-preserved-the-v3-pre-dispatch-image-failure).

### 25.46 Authenticated the first replacement Astra/high success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2546-authenticated-the-first-replacement-astrahigh-success).

### 25.47 Authenticated the second replacement Astra/high success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2547-authenticated-the-second-replacement-astrahigh-success).

### 25.48 Completed the replacement Astra/high streak

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2548-completed-the-replacement-astrahigh-streak).

### 25.49 Authenticated the second Astra/max success

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2549-authenticated-the-second-astramax-success).

### 25.50 Completed the OpenAI live success matrix

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2550-completed-the-openai-live-success-matrix).

### 25.51 Made F1 precredential rejection retainable

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2551-made-f1-precredential-rejection-retainable).

### 25.52 Passed the installed-wheel F1 boundary

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2552-passed-the-installed-wheel-f1-boundary).

### 25.53 Made F2 authentication rejection retainable

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2553-made-f2-authentication-rejection-retainable).

### 25.54 Passed the installed-wheel F2 boundary

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2554-passed-the-installed-wheel-f2-boundary).

### 25.55 Passed the installed-wheel F3 boundary

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2555-passed-the-installed-wheel-f3-boundary).

### 25.56 Passed the installed-wheel F4 boundary

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2556-passed-the-installed-wheel-f4-boundary).

### 25.57 Passed the installed-wheel F5 boundary

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2557-passed-the-installed-wheel-f5-boundary).

### 25.58 Passed the aggregate OpenAI live-conformance gate

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2558-passed-the-aggregate-openai-live-conformance-gate).

### 25.59 Implemented partial OpenAI conformance calibration conversion

[Recorded evidence and limitations](SKILLS_PROVIDER_IMPLEMENTATION_HISTORY.md#2559-implemented-partial-openai-conformance-calibration-conversion).

---

## 26. Integrated project review and delivery contract

**Review date:** 2026-09-08. **Decision:** adopt the revised designs as gated
extensions to Mos Eisley. This amendment changes the plan, not runtime authority.
The [project review](PROJECT_REVIEW_2026-09-08.md) records findings for the current
project and both imported plans. The detailed contracts are the revised
[adaptive routing design](adaptive-reasoning-routing.md) and
[adversarial-loop project plan](adversarial-review-loop-project-plan.md).

### 26.1 Current baseline and scope decisions

The reviewed checkout has a working recorded critic/judge pipeline, inert agent
loop, provider preview, spending admission and extensive offline evidence gates.
It does not yet deliver live critic/judge fan-out, a conversational controller,
machine-capable tests/writes or automatic routing. Fixture quality and signed
readiness are not proof of live utility, correctness or operational authority.
The three priorities are a usable recorded conversation/review slice, completion
of live read-only provider integration, and an affordable independent quality study.
No new learning algorithm or evidence artifact should obscure those deliverables.

**Implementation update, 2026-09-12:** the recorded terminal conversation/review
slice and frozen guidance admission are implemented. The
[canonical model review bridge](MODEL_REVIEWER.md) now connects the existing
`Reviewer` and `ModelClient` contracts with one isolated, tool-free request per
critic or judge. It supplies exact finding IDs for adjudication, includes prompt
and response envelopes in byte checks, validates complete JSON answers, and
preserves the pipeline's quorum/evidence/verdict rules and cancellation behavior.
This is an offline-tested library boundary. G2 still requires brokered live
dispatch, explicit transfer/spending admission and credentialed conformance;
the terminal continues to use recorded reviews.

**Async broker lifecycle implemented:** the existing isolated request broker now
has an awaitable entry point. Setup operations retain ownership through cancellation;
provider/pipe teardown completes before exact container removal and guardian finish.
Repeated cancellation cannot interrupt spending cleanup. Shared confinement flags,
one-use claims and uncertain reservations are preserved, with real Docker fixture
coverage. See [async broker lifecycle](ASYNC_BROKER.md). Live review-specific
authorization, aggregate spending and credentialed conformance remain G2 work.

**Broker-bound model client implemented:** one frozen canonical model request can
now consume an existing exact-payload broker through the async worker boundary.
Full request equality preserves local limits omitted from provider payloads; a
single attempt is consumed before asynchronous work. Response validation and failed
cleanup cannot release incurred spending or trigger a retry. The
[brokered model client](BROKERED_MODEL_CLIENT.md) is tested with synthetic review
and real Docker fixtures. It issues no review authority: transfer/audit bindings,
aggregate reservations, dynamic judge admission and credentialed evidence remain next.

**Single-call review admission implemented:** trusted host code can now preview
and explicitly approve one critic or judge request using the reviewer's shared pure
projection. The confirmation binds exact content, role, model, spending policy,
ledger and expiry. Issuance reserves the full conservative per-call allowance before
creating a broker grant; its unique ledger entry prevents repeated issuance. Private
review-mode audit records retain the input/request and spending bindings, and reject
cross-mode or incomplete verification. Crashes and ambiguous sends retain their
holds. See [review broker admission](REVIEW_BROKER_ADMISSION.md). Aggregate critic/judge
reservation, dynamic judge admission with retained finding lineage, guidance gates,
response/evidence retention and authorized credentialed conformance remain G2 work;
this library does not enable a live terminal mode.

**Combined spending allowance implemented:** one explicit envelope approval now
atomically reserves all selected critic calls and a full conservative allowance for
the deferred judge. Failed group admission leaves no new partial reservations.
Critics issue through fixed private paths and consume their existing holds; pricing
violations block subsequent pre-reserved provider operations. The judge allowance
still grants no transfer or request authority. See
[review spending envelope](REVIEW_SPENDING_ENVELOPE.md). Exact dynamic judge-request
binding, retained critic/finding evidence, guidance admission and credentialed
conformance remain required before live review activation.

**Deferred judge allowance transfer implemented:** a separate exact-request
approval can now move the reserved judge allowance to its request-specific hold in
one transaction, with unchanged aggregate exposure. It preserves the original
brief/model/spending policy, requires terminal critic accounting states, retains a
parent-to-child audit record and issues one bounded judge broker. It does not infer
finding validity or quorum from spending records. See
[deferred judge reservation](DEFERRED_JUDGE_RESERVATION.md). Retained critic/response
and finding verification, guidance admission and authorized conformance remain G2
requirements before live terminal activation.

**Retained critic evidence and judge admission implemented:** review broker clients
now save private raw/canonical responses and explicit completion receipts after
worker cleanup. Read-only reconstruction checks every selected critic against the
approved request, broker audit and terminal accounting, then reuses strict decoding,
citation, deduplication and quorum rules. Missing or inconsistent artifacts block
admission; fully recorded invalid/failed critics cannot vote but may coexist with
a valid quorum. Separate judge approval binds the exact evidence and derived request
and rechecks both before issuance. The existing default provider diversity remains
unchanged. See [response evidence](REVIEW_RESPONSE_EVIDENCE.md). Guidance admission,
retained final-verdict verification and authorized credentialed conformance remain
required before live terminal activation.

**Current broker guidance admission implemented:** explicitly selected prepared
guidance now binds critic and judge approvals to the same frozen rubric. The broker
path rechecks the current workspace, assessment and owner policy before reservation,
issuance, provider operations and model completion, with no guidance locks held
over network awaits. Detected changes stop new generation or invalidate an answer
while preserving uncertain or already settled spending. Historical audit checks
reconstruct pinned guidance without reopening current policy or granting new
authority. See [broker guidance admission](REVIEW_GUIDANCE_ADMISSION.md). These
moment-of-use checks do not establish uninterrupted policy validity or atomic
revocation at remote send; live workflow and credentialed conformance remain gated.

**Retained final verdict verification implemented:** read-only reconstruction now
checks the complete approved critic/judge chain and terminal accounting, reuses the
live judge decoder, rejects duplicate/unknown finding IDs and applies the same
deterministic verdict rules as the pipeline. Fully recorded invalid or failed judge
answers yield infrastructure errors with spending preserved; missing or inconsistent
records block reconstruction. A private exclusive result artifact binds approval,
completion and outcome hashes; historical verification requires its independently
pinned hash and recomputes the entire result. See
[final verdict evidence](REVIEW_VERDICT_EVIDENCE.md). Current guidance admission and
authorized credentialed conformance remain required before live activation.

**Brokered review controller implemented:** a process-local controller now binds
the reviewed envelope and policy to an exact approval, runs critics concurrently,
reconstructs their evidence and pauses for separately approved judge transfer. One
deadline includes the approval pause; cancellation waits for every child to finish
broker cleanup. The controller retains the fully reconstructed final result and
bounded private phase records without retries or automatic budget release. It
preserves current guidance checks and the configured quorum. See
[brokered review controller](BROKERED_REVIEW_CONTROLLER.md). Durable records do not
authorize crash resume; live launch/approval UX and credentialed conformance remain
separate requirements before terminal activation.

**Read-only controller inspection implemented:** independently pinned start records
now anchor a metadata-only inventory of saved controller stages, critic/judge
audits and model completions, result presence and conservative spending. Missing
transfer records after an atomic judge allowance transfer leave explicit incomplete
attribution; no inspection grants replay, frees spending or claims a verified
verdict. See [controller inspection](REVIEW_CONTROLLER_INSPECTION.md).

**Host approval interaction implemented:** a one-use flow now presents exact critic
requests and the complete spending envelope before reservation, then separately
presents the evidence-bound judge request. The asynchronous terminal adapter
requires explicit hashes, safely displays exact content, and retains conservative
spending on decline, prompt expiry or cancellation. Real Docker fixtures exercise
the UI/controller boundary. See [approval flow](REVIEW_APPROVAL_FLOW.md). This adds
no credential loading or live launch/configuration authority; conformance remains
a separate gate.

**Explicit launch configuration preview implemented:** a no-dispatch CLI now
projects the selected model registry, critic/judge spending policies, budgets and
current prepared guidance into the exact controller preview. It rejects mismatched
models, implicit effort substitutions, stale guidance and insufficient aggregate
capacity without creating a run or reserving spending. Evaluation conformance
receipts and registry labels cannot establish review-controller conformance;
live launch remains unavailable. See [launch preview](REVIEW_LAUNCH_PREVIEW.md).

**Independent review probe authorization implemented:** exact guided critic and
evidence-derived judge previews now have separate, short-lived Ed25519 authorization
scopes, bound to spending, current authority policy, runtime and controller identity.
An approval adapter checks each signature before and after explicit local consent;
judge scope transfers only the existing allowance. This adds no credentialed executor
or conformance proof. Actual dispatch-time enforcement and authenticated observations
remain G2 work. See [signed authorization](REVIEW_CONFORMANCE_AUTHORIZATION.md).

**Owned review probe dispatch implemented:** a paid-capable library now composes
both signed/local approvals with the controller and bounded OpenAI SDK transport.
It rechecks exact payloads, current policy/guidance, installed SDK, selected images
and expiry before credentials and provider operations, and after provider awaits.
Each count/generation attempt is consumed once; shared spending and cancellation
cleanup remain controller-owned. Real Docker and mocked HTTP/SDK fixtures cover the
boundary. No live provider probe or authenticated conformance observation is claimed;
review-specific observation/acceptance and live launch remain G2 work. See
[owned probe](REVIEW_CONFORMANCE_PROBE.md).

**Authenticated review observation implemented:** one successful probe can now have
an independently signed observer record binding exact phase approvals, observed
exchange intervals, external evidence pins and the retained verdict. Historical
authentication reconstructs the complete local controller/evidence/spending chain
and rejects failed critics, infrastructure errors, stale observations and substituted
policies or artifacts. It authenticates observer identity without proving provider
authorship, billing or repeated conformance. Independent evidence collection,
review-specific repeated-probe acceptance and authorized live runs remain required;
live launch remains unavailable. See [observer records](REVIEW_CONFORMANCE_OBSERVATION.md).

**Review runtime evidence collection implemented:** the owned probe now writes
private count/generation start and end records with exact approval/request/result
hashes, UTC intervals, monotonic durations and active worker lease bindings. It
captures lifecycle paths for independent retention. A read-only collector verifies
these records and matching removal receipts, derives observer evidence pins and
checks pinned exchanges against later changes. Recording failures preserve
conservative spending and cancellation cleanup. Host measurements do not replace
independent runtime assessment or grant live authority. Repeated-probe acceptance
and authorized live runs remain next. See [runtime evidence](REVIEW_RUNTIME_EVIDENCE.md).

**Repeated review probe acceptance implemented:** one read-only evaluator now
requires three distinct, ordered attempts committed before their outcomes, each
matching exact role, SDK/image and quorum profiles. It freshly authenticates observer
records, reconstructs review artifacts, verifies runtime/cleanup pins and requires
complete dedicated-ledger accounting. Missing slots stay incomplete; corrupted
records, repeated responses or unexplained spending cannot pass. The result grants
no retries, provider dispatch or live launch. Independent commitment custody,
authorized live attempts and reviewed launch admission remain outstanding. See
[acceptance](REVIEW_CONFORMANCE_ACCEPTANCE.md).

**Offline review campaign ceremony implemented:** explicit commands now preview a
fixed three-attempt bundle, confirm its canonical hash and privately seal it before
attempts, then freshly review a separately pinned evidence submission. Sealing
requires unused run directories and empty dedicated ledgers funding all allowances.
Review reconstructs the committed configuration and complete evidence chain, keeps
missing slots incomplete and rejects changed artifacts. Local seals are not
independent timestamps or proof of prior custody, and cannot resume prepared
controllers. Actual independent retention, separately authorized live attempts and
reviewed launch admission remain required. See the
[operator ceremony](REVIEW_CAMPAIGN_CEREMONY.md).

**Sealed campaign probe binding implemented:** an owning host can now bind each
prepared probe to a fixed slot and independently retained seal hash. Admission
freshly checks the exact bundle, critic preview, current authority/runtime, ledger
path and judge profile at approval and credential/provider use. Campaign deadlines
also bound SDK operations. Changes block further dispatch while preserving held
spending and cancellation cleanup. The binding grants no signatures, retries or live
activation and does not reconstruct or automatically sequence attempts. Actual
independent custody, authorized live attempts and reviewed launch admission remain
required. See [campaign dispatch binding](REVIEW_CAMPAIGN_DISPATCH.md).

Keep the conversational product contract, creator-authored plan/tests, creator
approval and delegated implementation requirements. Add Stage-0 independent readings
as a measured profile, not a mandatory tax on ordinary questions. Reuse existing
contracts and private storage; no mandatory Postgres, research web UI, notification
system or second router. Proxy telemetry cannot replace the human-grade lineage.
Raw historical trajectory retrieval conflicts with §17 and is not adopted.

Live automatic routing remains off. Exact fallback eligibility, independently
controlled holdout, external monotonic control and atomic brokered dispatch remain
required. Before an activation milestone, document actual authority enrollment,
key custody/separation, revocation/recovery and witness operations. Multiple keys
held by one operator do not demonstrate independent judgment. If the prescribed
operating model cannot be supplied, keep the feature offline/manual; any simplified
trust model needs an explicit new design and threat review rather than cosmetic keys.

### 26.2 Review-loop contract

Use the L0–L5 phases in the revised loop plan. Clause references bind immutable
plan revision and clause text; changed plans/tests invalidate dependent approval.
Two fresh readers seal interpretations before either result is revealed and before
seeing creator tests or reasoning. The later critic reviews creator plan/tests and
reading findings; judge disposition and creator acceptance bind the exact revisions.
Creator-context statements are not independent readings.

Independent reviewer tests supplement creator tests. Derive them from approved
plan/interfaces before revealing implementation. Freeze inputs, fixtures, expected
values, assertions, oracles and collection configuration; bind through a separately
reviewed adapter. Assertion-only diffs cannot detect fake bindings or changed test
meaning. Enforce known-good/known-bad controls, exact collection/execution counts,
and isolated execution receipts before treating failures as evidence.

Initially all blocking corrections retain full judge coverage. Confirm citation
aptness, reproduced failure and an implementation violation; keep test defects,
plan gaps, flakiness and infrastructure failures distinct. Uncitable concerns remain
visible as gaps or impact-supported invariant findings. Every final accepted tree
must pass required creator/reviewer checks and independent implementation review.
Model agreement, a plan-only approval or an author's acceptance cannot replace it.

Defaults are two critique/rebuttal rounds per artifact and two correction cycles
per task, under one aggregate cost/deadline budget. Persist counters and stale-work
invalidation across resume, cancellation and user steering. Exhaustion returns
unresolved evidence, never fabricated acceptance or automatic ambiguity relabeling.

### 26.3 Routing and measurement contract

Start with fixed routes and compare lookup/cascade policies offline. Keep judges,
graders, rubrics and gold evaluation settings fixed within a versioned experiment.
Candidate execution routes vary only as preregistered. The existing selector may
not change its own measuring instrument while claiming comparable results.

Record a durable pre-dispatch decision with policy/features, exact eligible action
distribution, selected probability, requested/resolved effort and budget, and actual
dispatch/reservation identity. A fallback after changed eligibility is a new
decision. Deterministic probability one supports only its observed action; unknown
historical propensity cannot be recovered by assertion. Scope automatic history use
to §17.3's minimal same-owner aggregates. Stage-0 divergence is available only after
Stage 0; never use current/future outcomes as pre-call features.

Treat passing tests, author rejection and judge verdicts as proxies. Preserve
independent verification, unresolved/disputed outcomes, non-completion, follow-up
windows, truncation, tool/provider failure and uncertain spend. Include every stage,
child, repair and abandoned task in whole-task cost. A cascade's later success is
recovery evidence, not proof effort caused the difference; causal comparisons need
separate attempts from the same frozen state or randomized whole-task policies.

Qualify cost savings only after absolute quality limits and non-inferiority margins
pass. Correct-work damage covers independently judged unnecessary requested changes
and introduced regressions on initially acceptable tasks. Also measure missed and
dismissed escaped defects, completion and latency. Report missing follow-up and weak
power; a cheaper policy cannot buy permission to increase damage through a scalar
cost/reward tradeoff. Stage overlap and judge consistency remain diagnostics.

Before any paid study, calculate whether the desired bounds fit case, group, grid,
assignment and spending ceilings. For example, with four profiles, six routes,
three quality metrics and two splits, the existing family contains 144 intervals.
Even zero observed clean risk needs at least 1,732 independent clean groups per
profile/split to get the implemented Hoeffding upper bound at or below 0.05. With
three repetitions, those clean cases alone require 249,408 assignments, exceeding
the current 50,000-assignment cap; 13,856 clean cases also exceed the 5,000-case
dataset cap. Reduce preregistered scope, collect more suitable
evidence or separately review a more efficient statistical design before execution;
do not weaken thresholds, pool sparse profiles or treat repetitions as independent
after seeing outcomes. See [statistical design](STATISTICAL_DESIGN.md).

Group related tasks/revisions, protect holdout before packet construction, retain
a random ordinary-task audit alongside selected hard cases, and track selection
and missing-label probabilities. Keep exposed regression examples out of fresh
holdout. The existing fixed-matrix scorer cannot validate adaptively selected
trajectories. Sequential inference, IPS/doubly robust estimators, output-budget
action schemas and cross-family difficulty transfer are separate research gates.

Exploration is disabled initially. Offline/shadow trials need explicit study spend
and data permissions and grant no machine authority. Later online randomization
can select only already qualified actions above the role floor. Monitoring can
quarantine/stop traffic; it cannot silently retrain/reactivate. Freshness deadlines,
recent-window checks and new model/prompt/tool/template versions trigger renewed
evaluation or eligible fallback/stop, even with no observed failures.

### 26.4 Delivery order and accountable gates

Josh Myers is the project decision owner. Each implementation milestone must name
its implementing owner, independent evidence reviewer where required, frozen
acceptance protocol and expected resource ceiling before work begins. These are
delivery roles, not a new user-confirmation step for ordinary authorized work.

| Gate | Work and dependencies | Concrete exit evidence |
|---|---|---|
| G0 — reconcile and instrument | Current offline core; L0/R0 schemas and telemetry; §§6.6–6.7 artifact/view, work-unit/checkpoint schemas, cumulative input metrics and offline instruction/tool-profile diagnostics | Versioned clause/decision/outcome and task-state fixtures, truthful unknowns, old replay compatibility, owner boundaries, bounded views with disclosed loss; required-tool omission, stale state and budget-reset negative cases |
| G1 — usable product slice | G0; recorded conversation controller; L1 reading experiment; author compaction, explicit checkpoint continuation, pressure indicators and reusable-memory/task-state separation | Conversation → frozen review → visible result → cancel/resume; milestone → checkpoint → fresh continuation detects changed tree/tests and completes with obligations/ledgers intact; duplicate handoff, blindness, stale approval, compaction reconstruction and overflow-stop tests pass |
| G2 — live read-only review | Provider conformance, shared spend and isolated broker integration; independent of later writing | Authorized credentialed conformance; one frozen brief through live critics/judge with preserved quorum, bounded spend, cancellation and evidence artifacts |
| G3 — feasible utility study | G0; L4 labels and existing authenticated matrix chain; G1 for session-policy comparisons; live claims require G2 | Sealed baseline/ablation design and feasible sample/spend calculation; independent clean/defective grading; matched and held-out context-policy completion, missed-evidence/stale-state, latency, cumulative-input and total-cost report; quality gates pass before claiming savings |
| G4 — executable correction loop | Execution containment and trusted VCS/E2 gates; L2/L3; applicable G3 quality gate | Immutable test-package/binding probes, stale-tree rejection, isolated known-bad controls, creator approval before child dispatch, final whole-suite and critic/judge result |
| G5 — qualified simplification | G3 plus representative whole-loop G4 evidence for write workflows; L5/R1/R2 | Paired evidence for any review removal, sampled judging or cheaper selector; damage/recall/completion constraints pass, complete costs, inconclusive means retain baseline |
| G6 — activated routing | G5 plus current promotion/preflight and R3 operational contract | Actual signer/witness custody, no-substitution resolver, one-use dispatch with revocation races/crash recovery tested, session budget, bounded cohort, stop/fallback drill |
| G7 — optional research | G5/G6 as applicable; R4 | Independent benefit from transfer, budget routing or bandit methods; explicit estimator and fresh evaluation, no automatic online learning |

G0/G1 can proceed while G2's live boundary is finished. Planning and labeling do not
require machine-write authority; live evaluation does not wait for coding autonomy.
G4 can be developed in inert fixtures before its production gates pass. Skills and
provider extensions retain their separate release gates and do not substitute for
this sequence. The revised designs are approved planning inputs, not evidence that
G0–G7 have shipped.

Within G0, freeze the shared records and counting definitions before implementing
offline diagnostics. Within G1, connect scoped acquisition/profile selection and
memory classification to the existing admission path, then ship checkpoint closure,
fresh continuation and pressure indicators under §6.7. Do not introduce a parallel
roadmap or wait for deferred executable doctor/SecretRef subsystems. A G3 study may
evaluate available policies incrementally; label unavailable arms and keep live
quality/savings claims behind their applicable provider and measurement gates.

### 26.5 Required adversarial acceptance matrix

| Boundary | Required negative cases |
|---|---|
| Reading/approval | Early reveal, creator tests/history leak, missing second commitment, stale clause/test revision, steering after approval |
| Binding/execution | Unchanged assertions with altered fixtures/oracles, fake adapter, empty/skip/xfail collection, wrong tree, flaky test, hostile subprocess/resource exhaustion |
| Correction | Valid quote with irrelevant requirement, wrong test oracle, absent invariant, partial quorum, author acquiescence, repeated unresolved failure, resumed budget reset |
| Measurement | Future features, same-task split leakage, holdout in cache/notes, selective labels/age-out, never-raised escaped bugs, zero successes, unattainable sample size |
| Routing | Missing/zero-support propensity, changed eligibility after selection, unqualified exploration, effort/budget substitution, stale catalog/freshness, partial feedback/cost |
| Dispatch/storage | Revocation between preflight/send, copied or rolled-back anchor, duplicate/uncertain dispatch, cross-owner aggregate access, reset with stale dependent policy |
| Context reduction | Mutable/missing full artifact, digest mismatch, hidden omitted range, stdout/stderr reorder, meaningful duplicate collapse, stale file-read cache, superseded instruction revival, retrieved prompt injection, cross-owner memory/cache hit, compaction lineage break, hard-cap false completeness |
| Task lifecycle | Changed branch/dirty tree after checkpoint, stale test success, lost pending work/steering, missing checkpoint evidence, concurrent or duplicate continuation, uncertain-effect replay, reset spend/review counters, expired approval revived by a new session |
| Context selection | Temporary checkpoint loaded as ambient memory, unaccepted fact promoted on closure, nested guidance broadens authority, required rule/tool omitted to fit, unrelated schemas enter request, optional profile teardown interrupts another task, byte counts mislabeled as provider tokens |

Pass/fail fixtures prove controller enforcement; representative independent live
evidence proves a quality or savings claim. Keep those statements separate in each
milestone review and in the CLI's availability/status output.

---

## 27. Windows platform release contract

**User direction, 2026-09-11:** make WSL2 a supported Windows-host deployment for
version 0.1.0 and deliver full native Windows support in version 0.1.1. Platform
support does not weaken the ownership, containment, durability, replay, spending,
or capability-separation requirements elsewhere in this plan.

### 27.1 Version 0.1.0 — supported WSL2 deployment

WSL2 runs the Linux build and Linux backend inside a real WSL2 distribution. It is
a supported Windows-host deployment, not a claim that Mos Eisley runs as a native
Windows process. WSL1, native PowerShell/cmd execution, Windows host credentials,
and direct Windows sandbox enforcement remain outside version 0.1.0.

- Publish a Windows Terminal/PowerShell-to-WSL installation and launch path, plus
  upgrade, diagnostics, and uninstall instructions. Record the Windows version,
  WSL version, distribution, kernel, architecture, mount type, and active Mos Eisley
  backend in status and retained provenance.
- Keep repositories, worktrees, configuration, credentials, and private Mos Eisley
  storage in the distribution's Linux filesystem by default. DrvFS paths such as
  `/mnt/c`, Windows network shares, and Windows-host Docker/editor sockets are not
  trusted storage or containment boundaries until their permission, link, locking,
  replacement, durability, and performance behavior passes a separate gate.
- Run installation, packaged-wheel, conversation, save/resume, memory, SQLite,
  OAuth, cancellation, Git, and applicable Linux positive/negative tests on an
  actual Windows-hosted WSL2 runner. A Linux CI job labeled "WSL" is insufficient.
- Preflight must distinguish WSL2 from WSL1 and report unsupported filesystem or
  external-boundary properties. Security-sensitive workflows fail closed when a
  mandatory Linux-backend property cannot be demonstrated under WSL2.
- WSL2 inherits each feature's existing delivery and authority gates. Supporting
  the host environment does not imply that planned TEST, WRITE, GitHub, provider,
  or routing capabilities have shipped.

Version 0.1.0 may claim WSL2 support only after those checks pass from the installed
artifact documented for release. Until then, WSL2 remains a planned support target.

### 27.2 Version 0.1.1 — full native Windows support

Version 0.1.1 runs directly from Windows Terminal, PowerShell, or cmd and provides
parity for every Mos Eisley capability advertised for macOS/Linux in that release.
Conversation-only operation, a WSL subprocess, or a Linux container launcher does
not satisfy this commitment. Implement the following platform boundaries before
claiming native support:

1. **Platform services:** move principal identity, secure file opening, file identity,
   private-directory creation, interprocess locking, atomic replacement, durable
   flush, terminal input, signal/cancellation, process supervision, secret storage,
   executable resolution, and sandbox selection behind explicit platform contracts.
   POSIX and Windows implementations must pass the same invariant suite.
2. **Identity and artifact migration:** replace persisted `owner_uid` assumptions
   with a versioned principal identity that represents POSIX UIDs and Windows SIDs
   without conflating them. Add new conversation, memory, SQLite metadata/cursor,
   transcript, MCP credential-reference, and other affected artifact schemas. Keep
   legacy hashes verifiable; cross-platform use requires an explicit authenticated
   owner-rebinding migration and never silently rewrites retained evidence.
3. **Windows storage boundary:** create and validate explicit DACLs for the current
   principal, use handle-based opens that reject reparse points and special objects,
   identify files by volume and file ID, detect hard-link/path replacement, and use
   Windows locking and replacement/flush primitives. A mechanical `flock`-to-
   `msvcrt` substitution is not equivalent. Initially qualify local NTFS storage;
   network shares, removable filesystems, ReFS, FAT, and exFAT require their own
   durability and isolation evidence before being advertised.
4. **Path and Git semantics:** handle drive-relative and absolute paths, UNC paths,
   case-insensitive collisions, reserved device names, trailing dots/spaces,
   alternate data streams, junctions, long paths, backslash normalization, symlink
   privilege differences, executable suffixes, and Git line-ending/executable-bit
   behavior. Canonical archive paths may remain POSIX-formatted, but conversion to a
   host path must validate the Windows namespace before access.
5. **Terminal and credentials:** provide equivalent TUI/plain/NDJSON behavior using
   Windows console facilities without `termios`, POSIX PTYs, event-loop FD readers,
   or Unix-only signal handlers. Store OAuth material in Windows Credential Manager
   or an equivalently scoped DPAPI-backed service; preserve cross-process refresh and
   logout serialization without plaintext fallback.
6. **Process lifecycle:** use non-inheritable Windows handles and Job Objects so
   timeout, cancellation, launcher death, and shutdown account for and terminate the
   complete descendant tree. Replace POSIX sessions, signals, `pass_fds`, and
   pipe-selector assumptions while preserving uncertain-side-effect reporting.
7. **Native containment:** enforce the common sandbox policy with restricted tokens,
   Job Objects, AppContainer or another reviewed Windows isolation boundary, scoped
   filesystem access, brokered network access, resource limits, handle isolation,
   and descendant cleanup. Publish the precise capability attestation and fail closed
   rather than silently mapping an unenforceable policy to unrestricted execution.
8. **Packaging and release:** use platform-marked dependencies where necessary and
   test installation, upgrades, entry points, all CLI renderers, local stores,
   migrations, credentials, Git integration, process cleanup, and sandboxing on
   supported Windows versions from the built wheel. Add Windows-native quality and
   release jobs; Linux-only CI cannot authorize the version 0.1.1 support claim.

The native adversarial suite must include DACL inheritance and foreign-principal
access, junction/reparse substitution, alternate data streams, case collisions,
reserved/long/UNC paths, concurrent locks, replacement while handles are open,
crash recovery, stale file IDs, handle inheritance, process-tree escape, loopback and
raw-network attempts, resource exhaustion, Git hooks/configuration, and migration of
unaltered version 0.1.0 artifacts. Tests run on native Windows and local NTFS; mocks
may supplement but cannot replace that evidence.

### 27.3 Version 0.1.1 delivery sequence and exit gate

Deliver the native port in this dependency order: invariant-based platform contracts;
identity/schema migration; secure storage and SQLite; terminal and credentials;
process/Git behavior; native containment; then cross-platform replay and release
qualification. Platform work may proceed alongside unrelated provider/evaluation
work, but native TEST or WRITE cannot bypass the G4 execution and VCS prerequisites.

Version 0.1.1 exits only when an installed Windows wheel passes the common quality
suite, Windows storage/migration suite, terminal/credential suite, Git/process-tree
suite, and complete positive and negative sandbox suite on every advertised Windows
version. Its capability/status output must show native Windows, the filesystem and
sandbox backend, and any independently unsupported external environment. There is no
"full Windows" release while an advertised macOS/Linux capability is silently
disabled or delegated to WSL2.

## 28. Application update notifications and guided upgrades

**User-directed addition, 2026-09-12 — planned, required for the finished product.**
When maintainers publish an update, installed Mos Eisley clients should alert users
and offer an easy update flow in the terminal, following the Codex-style experience.
This is application distribution work, separate from the evaluated prompt-skill
installation machinery in §25. The [official Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
documents startup update checks; the behavior below is Mos Eisley's product contract.

### 28.1 Release publication and discovery

- A pushed version tag triggers the release pipeline. Publish immutable versioned
  packages and release notes only after required quality and platform checks pass;
  advance the public release feed only when the advertised packages are available.
  Ordinary branch pushes do not notify stable users. Stable is the default channel;
  preview releases require explicit user selection.
- Check the trusted release feed asynchronously at interactive startup and at a
  bounded interval during long-running sessions. Cache results, cap network time
  and response size, and back off on failures. Users see new releases on the next
  successful check; discovery does not require a persistent push connection.
- Compare installed and available versions, release channel, OS/architecture,
  installation method and runtime compatibility. Do not advertise an incompatible,
  withdrawn or already-installed release as an available upgrade.
- Provide `mos update check` and `/update` inspection with installed/latest version,
  channel, release notes, compatibility and check status. Network failure means
  “unable to check,” with cached results labeled, rather than “up to date.”

### 28.2 User experience and installation

- Show a nonblocking update notice with current/new versions, a short change summary,
  release notes and **Update now**, **Remind me later**, and **Skip this version**
  actions. Preserve the composer, focus and running work; deduplicate notices for
  the same release. Manual inspection remains available after dismissal.
- `mos update` and the terminal action use the same guided flow. Show the exact
  target version and installation method, then obtain user confirmation. Default
  behavior is automatic discovery with user-initiated installation. Allow trusted
  user/admin policy to disable checks or delegate updates to central management;
  repository configuration and model output cannot change update policy.
- Detect and respect the supported installation method. Use its approved package
  manager or the verified standalone updater; for unsupported, editable or centrally
  managed installations, show precise manual instructions instead of modifying an
  unrelated environment. Never infer installation commands from release-note text.
- Before replacement or restart, finish or explicitly cancel active work and await
  worker cleanup, then durably save the session, draft and queued intent. If saving
  fails, defer the update. After successful installation, report the installed
  version and offer restart/resume of the exact session. Do not replay consumed
  provider requests or release uncertain spending during restart or recovery.
- Noninteractive commands never prompt, update or restart implicitly, and update
  notices never contaminate their machine-readable output. Provide a structured
  check result and require explicit installation selection for automation.

### 28.3 Integrity, persistence and recovery

Fetch metadata and packages only through trusted distribution endpoints with TLS,
authenticated publisher provenance and artifact-integrity verification. Release
metadata is bounded inert data. Reject tampered artifacts, unexpected redirects,
channel substitution and unintended downgrades before installation. Update checks
send only necessary release/platform information, without workspace paths,
conversations, memory, provider credentials or cross-user telemetry.

Serialize updates across running clients and retain the current runnable version
until a staged replacement verifies successfully, using the package manager's
supported transaction/recovery mechanism where applicable. Preserve configuration,
credentials, memory, sessions, repository/worktree bindings and audit/spending
records. Version storage migrations, back up affected state before mutation, and
verify supported upgrade paths. An incompatible rollback must not open newer
storage with an older binary: recover a compatible version or an explicitly selected
backup without discarding newer evidence. Failed downloads, installation, migration
or restart must report an actionable recovery path and never claim success.

### 28.4 Delivery and acceptance

Deliver release publication/feed and read-only notification first, then guided
installation and safe restart, then migration/recovery qualification. This is a
finished-product release requirement alongside packaging and the conversation UI;
it does not advance or block the G2 live-review capability gate. Qualify macOS,
Linux and Windows-hosted WSL2 under the 0.1.0 platform contract, and full native
Windows under 0.1.1 (§27), for every advertised installation method.

Acceptance evidence must cover a published release reaching an older installed
client; notice, notes, defer/skip and manual recheck; successful update and exact
session resume; offline/timeout behavior; disabled and centrally managed checks;
stable/preview and platform selection; invalid provenance and damaged packages;
concurrent clients and active work; interrupted download/install/restart; storage
migration failure and compatible recovery; and clean noninteractive output. Run
the upgrade and recovery scenarios against packaged installations on each supported
platform before claiming this feature is available.

## 29. Codex-style installation and first launch

**User-directed addition, 2026-09-12 — planned, required for the finished product.**
Users must be able to install Mos Eisley with a short terminal command and then run
`mos` from a project directory, without cloning the repository, building source or
manually setting up Python. The [official Codex CLI installation guide](https://learn.chatgpt.com/docs/codex/cli)
provides the reference experience: standalone installation, Windows, npm and
Homebrew options, followed by launch and authentication. This section defines Mos
Eisley's distribution requirements; package names and installer endpoints must be
secured and verified before runnable public instructions are published.

### 29.1 Supported installation routes

| Route | Required Mos Eisley experience |
|---|---|
| Standalone macOS/Linux | One copyable shell command downloads the official installer, selects a compatible release and installs the `mos` launcher in a user-owned executable directory. Also offer download/inspect/run instructions. |
| Windows-hosted WSL2, 0.1.0 | A Windows-facing guide checks WSL2 prerequisites, then uses the Linux installer inside the selected distribution. Identify the installed environment and explain how to launch from Windows Terminal. |
| Native Windows, 0.1.1 | One copyable PowerShell command installs a verified native package in a per-user location and makes `mos` available in a new terminal, after §27 native qualification. |
| npm | An official scoped package supports a single global-install command and exposes `mos`, selecting the same verified platform release. Clearly state the supported Node/npm prerequisites. |
| Homebrew | A maintained official tap/package provides a single install command on qualified macOS/Linux targets, with normal upgrade and uninstall behavior. |
| Direct download | Versioned OS/architecture archives with integrity/provenance information support manual, pinned and offline installation using a previously acquired complete package. |

Package the Python application with its required interpreter and runtime
dependencies for standalone distribution, or deliver an equivalently self-contained
runtime. npm and Homebrew routes use the same versioned application artifacts;
users do not manage a separate Python environment. Retain wheels/source installs
for developers and existing automation, with their prerequisites clearly documented.
All routes expose the same `mos` CLI and record installation origin, version,
channel and architecture for §28's update resolver. Native Windows remains gated
on 0.1.1 even if a package manager can install a launcher earlier.

### 29.2 Setup, coexistence and removal

- Install for the current user without administrator access by default. Support an
  explicit destination and version selection. Check OS/architecture and prerequisites
  before mutation; explain unsupported targets and required external tools.
- Make PATH setup explicit, bounded and idempotent. Detect existing `mos` commands,
  alternate installations and package-manager ownership before replacement; explain
  conflicts and require deliberate selection rather than overwriting another tool.
  Re-running the installer must repair or report the selected installation safely.
- After installation, show the installed version and the next step: enter a project
  directory and run `mos`. First launch guides provider selection and supported
  authentication, explains missing prerequisites and verifies local readiness.
  Installation itself does not require provider credentials or make paid requests.
- Use §28's release feed, artifact verification, channel controls and transactional
  recovery for first installation as well as upgrades. Bound downloads/extraction,
  reject archive path escapes and unsafe links, and leave no partial active launcher
  after failure. Support proxy/managed environments with explicit diagnostics.
- Document install, version verification, update and uninstall together for every
  route. Uninstall removes only that installation's owned files and launcher;
  preserve credentials, configuration, memory, sessions and evidence by default.
  Any data deletion is a separately selected, previewed operation. Switching install
  methods must preserve user state and leave one clearly selected active launcher.

### 29.3 Delivery and acceptance

Deliver the verified standalone artifacts and shell installer first, then npm and
Homebrew distribution, first-launch guidance and uninstall instructions. Qualify
the Windows paths according to §27. Publish the supported installation commands
prominently in the README and release documentation only after endpoint/package
ownership and installed-artifact checks pass. Connect every advertised method to
§28's notifications and method-specific upgrade flow before finished-product release.
This packaging work does not change the G2 capability gate.

Test each advertised route on clean supported OS/architecture environments,
including machines without Python and standalone targets without Node. Verify
`mos --version`, help, first launch, credential-free setup, session save/resume,
upgrade through §28, repeat install, custom paths and paths with spaces, PATH
conflicts, denied permissions, failed/interrupted downloads, tampered archives,
unsupported platforms, pinned/offline installation and state-preserving uninstall.
Exercise npm/Homebrew ownership and switching explicitly; mocks or a source-tree
launch cannot substitute for a successful installed-package journey.
