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

---

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
- Windows is not a v1 target. WSL2 works via the Linux backend.

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

Codex enforces a session cap far below the model ceiling: reportedly 400,000 tokens split into 272,000 input and 128,000 reserved output, then a ~5% headroom buffer leaving roughly 258,400 usable input. Auto-compaction fires at a configurable threshold defaulting near 200,000 (`model_auto_compact_token_limit`, configurable downward only). The rationale given: a tight cap makes compaction fire about once per deep investigation and produce a manageable summary, where a million-token window delays it until the history is too large for the summary to be reliable.

> Verify against your installed `codex --version` before hardcoding. The cap has moved across releases and the public figures come from third-party write-ups, not OpenAI docs.

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

Five categories tracked separately — the aggregate is useless for diagnosis: system prompt, tool schemas, project instructions (`AGENTS.md`, 32 KiB cap), conversation turns (including retained reasoning), tool outputs (fastest-growing).

Count with each provider's own endpoint, cached on a hash of the serialized prefix.

**Startup assertion:** if the assembled prefix exceeds 25% of `usable`, fail with a diagnostic naming the offending category.

### 6.4 Compaction policy — by role

Codex uses a single-layer handoff summary replacing history. Inherited costs: compounding loss across repeated compactions, and destruction of the prompt-cache prefix so the next turn pays cold-start. Community guidance treats three successive compactions as a restructure signal and prefers subagents, since a fresh agent with a focused prompt preserves full fidelity.

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

`[stable prefix: system + tools + brief] + [volatile: turns]`, explicit cache breakpoint at the boundary. With N critics on one brief, the prefix is the largest cost lever. Compaction invalidates it — a second reason to keep it off the critic path.

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
    for level in reversed(LADDER[: LADDER.index(requested)]):
        if level in model.efforts:
            return level  # log the substitution
    raise UnsupportedEffort(model.id, requested)
```

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

At most one retry, one empirically selected step up. Triggers are role-specific and
externally observable: failed executable evidence for an author, unresolved critic
disagreement for a judge, or an evaluation-only miss on a labeled defect. Schema
failure gets a bounded format-repair attempt at the same route; it is not evidence
that harder reasoning is required. A model's self-reported confidence never triggers
escalation by itself. Both attempts and the trigger are logged. Keep an escalation
only when held-out evaluation shows positive payoff after added cost and latency.

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

Truncate to a byte cap with head/tail retention and an explicit `[truncated: N bytes omitted, full output at <path>]` marker. Write the full output to disk, hand the agent a greppable path. Unbounded tool output is the most common way a loop dies and the most common source of budget overrun.

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

**Never operate on the user's checked-out working tree.** Every agent gets `git worktree add runs/<id>/worktrees/<agent>/` from a pinned base SHA, disposable at run end. Benefits: parallel agents can't collide, the user's uncommitted work is untouched, and cleanup is `git worktree remove`.

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

The critic's context is built from a directory on disk, never forked from a conversation:

```
runs/<id>/brief/
  spec.md  diff.patch  constraints.md  test_output.txt
  manifest.json         # sha256 of each file -> brief_id
```

`brief_id` is the content hash; the same brief replays to any model, any time. **The author's transcript never enters a critic's context** — the author's reasoning is precisely what critics must be blind to.

### 15.2 Blindness invariants

Asserted in code, tested in CI:

1. Critics run concurrently and never observe each other.
2. No critic is told which model authored the artifact.
3. The judge receives critiques with identity stripped and order randomized.
4. No critic is told another critic flagged anything.
5. Personas differ deliberately — correctness, spec mismatch, operational failure modes — so they don't share one blind spot.

### 15.3 Findings schema

```python
class Finding(BaseModel):
    location: str  # file:line or symbol
    claim: str
    severity: Literal[
        "correctness", "spec_violation", "security", "performance", "preference"
    ]
    evidence: Evidence  # command | failing_test | citation
    suggested_fix: str | None
    confidence: float
```

- **At most 5 findings, ranked.** Uncapped critics produce a wall of style nits.
- **Executable evidence preferred:** require the test or command that would fail if the claim holds, then run it. Strongest single lever on false-positive rate.
- **`preference` findings never block.** Unlabeled findings rejected at parse time.

### 15.4 Adjudication

1. **Dedupe** across critics — embedding cluster or an LLM merge at `medium` effort. Preserve which critics contributed to each cluster.
2. **Score** by agreement × evidence executability × severity, **weighting cross-family agreement above within-family** — three Claude instances agreeing is correlated, not independent.
3. **Judge** returns `accept | revise(required_changes) | reject`, and is never the model that authored.
4. **Rotate roles** across runs.

### 15.5 Bias controls

| Bias | Control |
|---|---|
| Self-preference | blinding + judge rotation |
| Verbosity | length cap; judge sees normalized-length summaries |
| Position | randomized order; periodic permuted re-run to measure |
| Herding | strict concurrency, no cross-critic visibility |
| Sycophancy | adversarial persona + executable-evidence requirement |

### 15.6 Rounds

Two maximum: critique, rebuttal, verdict. Returns fall off sharply; cost is multiplicative in (critics × rounds).

### 15.7 Plan review, creator approval, and delegated implementation

For the creator-led coding workflow, use this explicit sequence:

1. **Creator writes the plan and tests.** Freeze a concrete plan with constraints,
   interfaces, proposed coding subtasks and routes, and an aggregate cost/time
   budget, together with creator-authored executable tests for the required behavior
   and relevant failure cases. Record exact digests for both the plan and test suite.
2. **Critic reviews the plan and tests.** Supply both frozen artifacts and permitted
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
- A fresh session starts with fresh conversational context. Only the owning user's
  minimal model-selection statistics may be reused automatically across sessions.
  Resuming a selected conversation or explicitly opening a prior run retrieves only
  that user's requested records; saved content is never ambient memory for new tasks.

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

### 16.1 Commands

```
mos                                    # interactive TUI in cwd
mos "prompt"                           # TUI with initial prompt
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
usable as documentation today; automatic loading and binding remain planned work.

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
  a saved conversation or inspect selected prior records. Independent critics still
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
template's evidence-index pattern. Memory contains stable keyed constraints,
accepted decisions, verified traps, and open work, each with a source reference and
last-verified date. Verify entries against requirements, code, tests, or ADRs before
use; memory is not evidence by itself. Retrieve before editing, update keys in place,
label uncertainty, and remove stale or duplicate entries. Never turn routine
progress, raw logs, transcripts, secrets, or hidden reasoning into durable memory.
Do not auto-rewrite policy based on a successful trajectory.

Keep disposable scratch private and ignored with task-end cleanup. Use a bounded
work note for multi-session work, handoffs, incidents, experiments, or material
investigations: objective, concise observations/attempts, evidence links, remaining
work, owner, and review/delete date. On closure, promote verified facts to memory,
decisions to ADRs, maintained explanations to docs, and work history to issues;
close or remove obsolete notes. Tracking/export into project Git is an explicit
publication of a reviewed, sanitized project document, not default persistence.

Memory and notes default to private artifacts bound to both owner and project under
§17. A fresh session requires explicit selection of the relevant memory/note or
explicit same-owner resume; attaching a best-practice template does not authorize
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

---

## 18. Evaluation harness

All user-derived datasets, grading records, reports, and learned policies obey §17
ownership. Evaluate and compare within one user's data; do not create a shared
benchmark or persona/routing policy from multiple users' runs. Shipped synthetic
fixtures may be shared only when they contain no user-derived data.

### 18.1 Ground truth by mutation

Inject synthetic defects into known-good commits of your own repos — off-by-one, inverted condition, dropped null check, swapped argument order, silently changed default. Each mutation is a labeled defect at a known location, in your domain, for free. Maintain a matched set of **clean** commits.

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

Two expectations worth confirming rather than assuming:

1. **The quality curve flattens early.** Sonnet 5 at xhigh reportedly approaches Opus 4.8 pricing while scoring slightly worse on several benchmarks — the effort dial and model dial trade against each other and must be searched jointly.
2. **False positives likely rise with effort.** A critic thinking harder on clean code has more time to invent objections. If confirmed, optimal critic effort sits *below* optimal author effort — the opposite of role intuition.

Sampling is unavailable (§4.3), so variance requires repeated runs per cell. Three
repetitions are a smoke test only; use sequential stopping or a pre-registered power
target before promoting a routing policy. If no cheaper route meets the quality
constraint with adequate confidence, retain the role fallback.

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
| **M12** | Mutation eval + (backend × model × effort) sweep | FP rate on clean commits measured; routing policy set from data |

M2 and M3 moved ahead of the provider work deliberately. Once the harness can touch the machine, everything after it inherits whatever boundary you built — retrofitting a sandbox around an agent loop that already assumes free filesystem access is a rewrite.

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

The package snapshot prevents ordinary post-validation drift but not a malicious
same-UID process racing trusted ancestor directories. Package signatures and archives
are absent, so historical reconstruction depends on retaining the exact digest-named
package. These limits are explicit in `docs/SKILLS.md` and milestone review 22.

### 25.4 Implemented paired evidence gate

Evaluation routes now bind an exact inline or persona-skill prompt asset. A separate
two-arm protocol seals the dataset, full plan, prompt identities, non-inferiority
margins, paired equal-group estimand, fixed stopping rule, and six-comparison family
before results are inspected. The arms must be identical except for their prompt,
and the candidate must be a digest-identified persona skill.

Scoring reverifies the complete dual-authenticated human-grading lineage, averages
repetitions within cases, pairs candidate-minus-baseline case outcomes, then weights
declared independence groups equally. Holdout CLI use consumes an atomic private
claim before validation so failed or repeated attempts cannot be selectively rerun
without explicit local-control tampering. Cost and latency deltas are reported.

This closes the recommended evidence-foundation slice, not persona promotion. Every
artifact denies activation and each report denies promotion. A later milestone must
define independent signed promotion, retained package archives, rollback, expiry,
and drift monitoring before a skill can replace a default.

### 25.5 Implemented independent promotion-readiness gate

An authority policy now enrolls sorted unique Ed25519 release keys and bounds both
its own validity and the maximum lifetime of a decision. The only signable decision
is deterministically derived from the exact sealed comparison plus matching
calibration and holdout reports; both registered gates must pass. The signature
domain binds the authority policy, exact skill and prompt identities, both reports,
and UTC decision window.

Authentication recomputes both reports from their complete dual-human-grade source
chains, rejects authority overlap with any grader or resolver, checks expiry, derives
the decision again, and verifies the signature. A signed failed experiment remains
a denial. The resulting receipt can claim promotion readiness but literally denies
configuration mutation and activation.

This is an evidence-authorization boundary, not installation. The next retained-byte
archive slice is documented below; author signatures, rollback, revocation,
transactional default changes, and drift monitoring remain mandatory future work.

### 25.6 Implemented deterministic package retention

A retained skill archive now serializes every path and exact byte from the loader's
immutable validated snapshot. Canonical base64, per-file byte counts and digests,
canonical path ordering, collision checks, and the existing domain-separated package
digest make the archive deterministic and content addressed. Retention never
reopens the package, so a post-discovery filesystem mutation cannot change the
archive selected by its exact qualified reference.

Archive verification is deliberately semantic as well as structural: it reparses
the retained `SKILL.md` and optional `mos.yaml`, re-applies the prompt-only rules,
and rebuilds the complete descriptor and normalized instruction-body digest from
the retained bytes. It performs no extraction or materialization. Project-source
retention requires invocation-local approval, and the archive schema fixes
installation, activation, and configuration mutation authority to false.

This closes byte retention alone, not deployment. The next subsection adds a current
promotion-evidence binding; authorship, revocation, rollback, transactional
installation/default changes, and post-install drift monitoring remain separate
mandatory gates.

### 25.7 Implemented current archive-to-promotion binding

A `SkillReleaseEvidence` artifact now joins one semantically reverified retained
archive to one authenticated promotion receipt. Creation recomputes both complete
dual-human-grade lineages, the signed promotion decision, and the archive's parsed
descriptor before requiring exact `SkillIdentity` equality. The CLI supplies the
host UTC clock and rejects a receipt at its expiration boundary.

The artifact embeds both sources and commits their canonical digests, exact candidate
identity, check time, and receipt-bounded expiration. It can only represent a passing,
retained evidence state; literal schema fields continue to deny installation,
activation, and configuration mutation. Reverification rebuilds the artifact and can
also require that it remains current at a separately supplied time.

This closes package substitution between evaluated identity and retained bytes. It
does not authenticate the package author, establish an external timestamp, consult a
revocation witness, select a rollback target, materialize files, change defaults, or
monitor post-install drift. Those remain independent prerequisites for deployment.
