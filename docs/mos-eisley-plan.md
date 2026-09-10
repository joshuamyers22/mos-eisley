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
positional prompts, an interactive resume picker and live authentication/setup
remain planned. The default preview needs no credentials or network connection.
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
- The current startup implementation provides `-C`, a persistent directory header
  and `/directory` inspection. The selector and in-session switching are planned.

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
Project scope currently uses the selected canonical workspace; Git-root
discovery, mapping, natural-language saves and automatic extraction remain planned.
The requirements below remain the complete target.

| Scope | Contents and reach | Initial storage design |
| --- | --- | --- |
| User | Personal preferences and facts the user chooses to reuse across projects. | Private user memory under the configured Mos home. |
| Project | Project decisions, conventions, setup details and ongoing context the user chooses to retain for that project. | Private memory keyed by owner and canonical project root under the configured Mos home. |

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

### 16.1 Commands

```
mos                                    # interactive TUI in cwd
mos -C /path/to/project                 # select and display the working directory
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

### 17.5 Long-session storage and independent budgets

**Direction following the 2 MB capacity discussion:** the snapshot limit is an
interim preview constraint, not a long-session product target. The first
[storage-budget implementation](CONVERSATION_STORAGE.md) now lets the user save a
64 KB–32 MB snapshot budget with `--session-max-bytes` on launch or resume. The
default remains 2 MB; legacy canonical hashes remain unchanged. `mos sessions`
reports actual bytes and the saved limit. Listing/latest selection has a separate
8 MB scan budget, explicitly adjustable up to 128 MB with `--catalog-max-bytes`.
Budget changes preserve history and consumed attempts and do not dispatch work.

The default JSON backend still reads and rewrites whole snapshots. An
[opt-in SQLite adapter](CONVERSATION_SQLITE.md) now commits changed message records
and session-scoped artifact references transactionally, with exact-state deletion
and bounded metadata pages. Cursors bind the owner, database, workspace and catalog
generation; a changed catalog requires restarting pagination. SQLite currently
reconstructs the complete bounded state on initial resume, then uses reference-based
working state for current records; its physical file has an
initial 256 MB ceiling. `mos session-migrate SESSION_ID` now previews a same-root
JSON-to-SQLite copy; applying requires its exact source hash. Import preserves
owner, revision, history and consumed attempts, verifies the reconstructed state
inside the transaction and retains the JSON source. Verified retries cover rollback
and an already committed import. Bulk/cross-root migration, incomplete database
initializer repair remain open. `mos session-transcript SESSION_ID` now reads
bounded, verified text pages without loading the header or artifact contents.
Pages use saved per-entry digests and owner/session/catalog-bound cursors; older
indexes require an explicit exact-hash preparation step. The SQLite terminal now
uses this reader for F5 history browsing, Page Up/Down navigation and F6 reload.
It retains one page plus visited cursors, serializes background reads, discards
obsolete results and preserves the draft. Session changes clear the selected page;
browsing never dispatches or saves work. Its live display shows four recent messages.
F7 selects a memory/review reference on the current page; F8 opens or closes one
artifact. `mos session-artifact SELECTION` provides the same explicit read through
the CLI. Selections bind the store, owner, workspace, session, snapshot, catalog
generation, message position, field, hash and byte size. Reads verify the selected
message reference, enforce a 512,000-byte default before fetching the artifact,
then verify its hash and typed schema. The CLI accepts an explicit limit up to
32 MB; this budget covers stored payload bytes, not rendered output or RAM.
The terminal retains at most one expanded artifact and clears it on selection,
page, session or view changes; obsolete background results are discarded.
Expansion grants no model or critic access.

SQLite saves now include a derived resume checkpoint: the exact stored header hash
and byte size, plus bounded message status, review kind, steering links and record
sizes. Full loads verify it against the complete state. `mos resume --last
--storage-backend sqlite --inspect` reads this checkpoint in a read-only transaction,
verifies the header, and selects the last four messages, queued/running work and
their complete steering ancestry. It verifies only selected message payloads and
reference availability; artifacts stay unexpanded. Header plus selected records
must fit 512,000 bytes, with admission before fetching message payloads. Inspection
reports omitted-message count, pending positions and which running position would
be interrupted on normal resume. It does not recover, save or dispatch work.
Older indexes require the existing exact-hash `session-transcript --prepare` step,
which now prepares both page and resume metadata while preserving state and raw
records. The checkpoint still has a 16-message bound and needs a scalable layout
before the message cap can be lifted.

Routine SQLite saves now reuse a verified checkpoint while the same connection
observes no external commits or uncoordinated local writes. The write transaction
checks the stored index and expected revision/hash, skips unchanged message and
artifact writes, inserts new artifacts and removes only unreferenced ones. It does
not reread old payloads into Python for the full-state compatibility API; the
reference-based controller path streams retained bytes as described below.
External commits anywhere in the
database trigger full session validation before another save. Failed operations,
preparation, deletion and connection reopen clear the local checkpoint; publication
happens only after a successful commit. No artifact payload is cached in this
checkpoint, only bounded metadata, canonical verification status and artifact digests. Import and explicit
load/delete retain full validation.

Chat dispatch now builds context through a text-only message interface and admits
the canonical UTF-8 JSON for system instructions and selected turns before saving
`running` or consuming an attempt. Both backends retain an independent
`--context-max-bytes` budget (256,000 default; 4,000–1,000,000 range). Selection
preserves all earlier completed exchanges and unanswered steering ancestry;
active memory contributes through the system instructions, while historical
memory/review artifacts stay outside selection. An oversized request reports its
required size and saved limit, remains queued and pauses continuation. No automatic
compaction or omission occurs. This budget is neither provider tokens nor a bound
on complete wire requests or peak RAM; review execution retains its isolated packet
limits. The selected config is frozen before the running transition and reused for
dispatch. Context resizing preserves attempts and saves its own transition.
The complete model request also passes the agent loop's shared byte-budget check
before the running transition; a larger context budget cannot bypass the recorded
provider's 79,800-byte usable input limit. Provider-budget rejection likewise leaves
work queued, reports required/available bytes and consumes no attempt.

SQLite controllers now release historical memory/review values after full initial
verification and retain their admitted references. Current saves validate working
inputs and source-record hashes, stream archived bytes in 32 KiB chunks, and preserve
the canonical snapshot hash and logical byte budget without rebuilding historical
artifact objects. Changed records, artifact insertion/collection and generation
updates remain atomic; checkpoint and working-state publication follow commit.
Archived content cannot change through a reference; queued cancellation and
running-to-interrupted recovery are the admitted status-only changes. Queued review
packets hydrate at execution under a 512,000-byte aggregate record/artifact input
limit. At most the latest result stays decoded for the live renderer. JSON snapshots
reject runtime references. Older indexes and noncanonical artifact JSON retain the
full-state compatibility path until an ordinary save and reopen.

Bounded cold resume remains open: initial verification and external-commit recovery
still reconstruct full state, active memory/recording values remain decoded, and
each save still hashes all logical history bytes. The current working state keeps
text for all 16 messages. Next bound cold loading, reduce text/record bookkeeping
into bounded transitions, and budget active memory/recording hydration. Preserve
attempt accounting, interrupted-work recovery and
steering ancestry. The inspection selection is not a provider context policy;
context selection/compaction must explicitly preserve or account for earlier intent.
Neither backend has passed the long-session gate below.

The recorded preview still caps messages/attempts at 16. Raising the snapshot budget
does not lift
model context, memory, message, tool, or spending bounds. Complete the following
work before claiming support for long coding sessions:

| Stage | Required behavior and acceptance |
| --- | --- |
| Incremental persistence | Versioned local SQLite metadata and incremental records, with private owner-scoped immutable artifact/memory references. Commit each transition and its references before dispatch without rewriting all earlier content. Retain revision checks, consumed attempts and steering ancestry. |
| Bounded navigation | Stable cursors and bounded pages for listings and transcript reads. Resume loads a bounded working set; listing does not parse every transcript. Concurrent writes, stale cursors and missing references produce defined recoverable outcomes. |
| Independent budgets | Separate disk/retention quotas, page/record read limits, pending-input capacity, active model context, memory and provider spending. Report usage before capacity rejection. A storage increase grants no inference or tool authority. |
| Context management | Visible, versioned compaction preserves current user instructions, decisions, unresolved work and required task links. Retain original evidence and record request selection/omissions. Fresh sessions and independent critics cannot retrieve ambient history. |
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

### 19.6 Multimodal inputs

Support images later as content-addressed brief artifacts for screenshots, rendered
UI, diagrams, and visual diffs. Validate media type independently of extension,
decode with resource limits, strip active metadata where possible, and record the
exact bytes and transformations supplied to each provider. A model without the
required modality is ineligible for that route. Audio/voice/realtime interaction is
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
| Cached web search | **Adopt after containment** | Only the trusted brief builder gets brokered network access. Critics consume frozen, cited, untrusted artifacts; the cache includes provenance and freshness (§19.5). |
| Endpoint and auth modes | **Adopt, hardened** | Use trusted endpoint records and typed credential references (§4.5), not arbitrary URL/header dictionaries. Require TLS/loopback exception, SSRF controls, conformance, and provider/data policy. |
| Local open-weight models | **Keep out of v1** | Different branding does not prove independent training lineage. “Free per call” ignores hardware, energy, operations, and latency. Add a local endpoint only if blinded evaluation shows incremental coverage or acceptable cost/quality. |
| Model-keyed capability defaults | **Reject** | Model labels such as “frontier,” “small,” or “cyber” are mutable and do not determine the OS authority a task needs. Policy is task/role/data based; a provider or model restriction may narrow authority, never raise it. |
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
- subagent comparisons against the existing specialized review path, reporting
  quality, cost, latency, isolation failures, and aggregate-budget violations;
- network-broker SSRF/DNS-rebinding/redirect/cache-poisoning tests and proof that
  critics remain unable to open sockets;
- endpoint conformance and data-policy approval for every new backend;
- egress tests seeding credentials in prompts, tool output, events, MCP traffic, raw
  artifacts, and replay paths;
- service-boundary authentication, rate-limit, cancellation, replay, and
  caller-request-narrowing tests;
- image decompression-bomb, malformed-media, metadata, and cross-provider
  conformance tests before multimodal routing becomes eligible.

**Result:** parity work is post-gate extensibility. It may make Mos Eisley easier to
integrate and specialize, but it cannot advance ahead of the local review quality
gate, containment proof, or the trusted/untrusted configuration split in §23.8.

### 24.5 Post-gate delivery order

| Phase | Scope | Exit criteria |
|---|---|---|
| **E1 — control substrate** | policy preflight, egress redaction, typed lifecycle events, feature maturity registry, typed credentials/endpoints | preflight/dispatch equivalence; seeded-secret egress suite passes; handlers cannot escalate authority; every endpoint passes conformance and data-policy checks |
| **E2 — delegation assets** | general subagent primitive, versioned skills, persona migration experiment | aggregate-budget and isolation tests pass; specialized versus general pipeline comparison meets pre-registered non-inferiority thresholds; skill version does not regress false-positive target |
| **E3 — external evidence** | brokered fetch/search, provenance cache, image brief artifacts | critics remain socketless; broker and cache adversarial suites pass; images pass media/resource and cross-provider conformance |
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

### 25.8 Implemented authenticated revocation and rollback nomination

A separate release-control policy enrolls sorted unique Ed25519 authorities and
bounds decision lifetime. Every enrolled control identity and public key must be
disjoint from the promotion authorities and all graders and resolvers across both
splits. The only signable control decision is deterministically derived after
reverifying the exact release evidence and its complete upstream lineage.

The signature commits the trust-policy digest, release-evidence digest, current
archive, candidate identity, monotonic sequence, allow/revoke disposition, optional
rollback nomination, and UTC window. A rollback nomination is permitted only for a
revoked release, embeds exact semantically reverified retained bytes in the resulting
receipt, and must identify a different package for the same source-qualified persona
name. It remains a nomination rather than an extraction or install instruction.

A private SQLite anchor is scoped to one release-evidence digest and pins the exact
authority policy, allowed control signers, and a minimum bootstrap sequence. Canonical
entries are hash-linked and fully reverified on every read. Sequence and issue time
must advance, a revocation cannot be removed, and consumers can require the exact
latest signed state. This prevents ordinary older-message replay but not owner-driven
whole-database rollback or cloning; an external monotonic witness is still required.

Every new contract and CLI event continues to fix installation, activation, and
configuration mutation to false. Transactional staging, exact post-write checks,
atomic default switching, crash recovery, and drift-triggered rollback remain the
next independent deployment gate.

### 25.9 Implemented transactional quarantine staging

An exclusive private store can now materialize the exact candidate archive from an
allowed control or the exact embedded rollback archive from a revoked control. The
staging entry point first rebuilds the authenticated control at its recorded time,
then reauthenticates the release, promotion, both comparison splits, and retained
archive at the current host time.

The store policy pins the exact release-control anchor policy and caps both completed
packages and incomplete transactions. Each transaction binds the current control
receipt and exact anchor entry, writes payload files exclusively with private modes,
reconstructs the archive and semantic skill descriptor from the written bytes, writes
the completion manifest last, and fsyncs files and all directory levels. Only then is
the verified directory atomically renamed to its archive-digest path and both sides
of that rename fsynced. Exact existing packages are verified before idempotent reuse;
there is no overwrite or repair path.

Latest-control validation and package commit share one SQLite read transaction. A
concurrent anchor advance cannot commit a newer revocation between verification and
the atomic staging rename. This closes the local check-to-use race, not same-UID
replacement of the entire anchor/store or rollback of their external trust roots.

Interrupted transactions remain bounded and visible under a separate transaction
directory. Status inventories intent/completion-marker presence but never resumes,
deletes, or promotes partial state automatically. Every contract and event continues
to deny installation, activation, and configuration mutation, and no runtime code
reads the quarantine store. Independent signed install authority, atomic default
switching and recovery, and post-install drift evidence remain future gates.

### 25.10 Implemented independent one-use installation authorization

A separate installation-authority policy enrolls sorted unique Ed25519 identities
and keys that must be disjoint from the release controllers, promotion authorities,
graders, and resolvers in both evidence splits. It pins the exact quarantine-store
policy, release-control anchor policy, one private claim-store identity, one inert
installation-target identity, its own validity window, and a maximum decision life.

The derived signable decision reverifies the entire release lineage and every staged
byte. It binds the exact staging manifest, archive, source-qualified persona, candidate
or rollback action, signed control, latest anchor entry, release evidence, claim store,
target, and UTC window. Authentication recomputes that decision, checks the independent
signature, reauthenticates all sources at the host clock, and again requires the same
latest anchor entry. The receipt grants installation permission for only that exact
target while fixing activation and configuration mutation to false; it records that
installation has not occurred.

A private SQLite claim ledger is pinned back to the exact authority policy. Guarded
consumption reverifies the authenticated receipt, burns the signed decision digest
durably before any caller side effect, retains the exact receipt used, and keeps the
release-control read transaction open across the
caller's commit window. Exceptions never refund the claim, so ambiguous or failed
attempts require a newly signed authorization. The raw claim operation is private and
there is deliberately no standalone consume CLI that could waste permission without
an installer transaction.

This is an authority and at-most-once substrate, not deployment. No installed-package
store, default pointer, runtime lookup, completed-install receipt, automatic recovery,
or drift monitor exists. Local claim and control databases can still be rolled back or
cloned by their owner without an external monotonic witness. The next slice must define
the atomic installation/default transaction, complete-or-incomplete recovery evidence,
and post-commit verification before any authorized prompt reaches a model request.

### 25.11 Implemented atomic inert installation and recovery evidence

An installed-store policy now pins one exact installation-authority policy, quarantine
store, at-most-once claim store, and opaque installation-target identity. Its private
layout contains an immutable policy, owner-private cross-process lock, content-addressed
completed packages, and bounded transaction directory. It has no default pointer or
runtime reader.

The installer preflights existing content and capacity before consuming authority,
then reauthenticates the complete evaluation/promotion/release/staging chain under the
latest-control guard. The claim is durably burned before writes. While that revocation
guard remains held, the installed-store lock serializes a second inventory check,
transaction creation, provenance files, exact payload writes, post-write semantic
archive reconstruction, completion-manifest write, directory fsyncs, and atomic rename
to the archive digest. Concurrent installs cannot exceed configured limits or overwrite
an existing exact package. An already installed digest is rejected before consuming a
new authorization when visible at preflight; a later race fails conservatively.

Every completed package retains its exact authenticated authorization, consumed claim,
quarantine manifest, intent, descriptor, and payload. Store loads reverify the external
installation signature and rebuild the full archive from disk. The result alone records
`installation_performed: true`; every store, intent, manifest, result, and event fixes
default mutation, configuration mutation, activation, and runtime lookup to false.

Read-only recovery inspection correlates durable claim-ledger entries with completed
manifests and incomplete intents. It distinguishes `completed`, `incomplete`, and
`claim_only`, and separately inventories transaction directories without an intent.
It never retries, finalizes, deletes, refunds, or changes a default. Local owner rollback
and cloning, same-UID path replacement, external monotonic state, default selection,
runtime consumption, and drift monitoring remain open. The next slice requires a
separate signed default-change authority and an atomic recoverable pointer transaction.

### 25.12 Implemented independent atomic default selection

A default-authority policy now pins independent Ed25519 identities, the exact installed
store and historical installation-authority policy, latest release-control anchor, one
private default-store identity, and a bounded decision lifetime. Default authority IDs
and keys must be disjoint from every evaluator, resolver, promoter, release controller,
and installer in the reverified source lineage.

Each decision binds the exact installed manifest, historical installation authorization
and signed installation decision, archive and persona identity, current release-control
entry, candidate or rollback action, next sequence, expected previous pointer digest,
and validity window. Authentication rebuilds the complete evaluation through installed
package provenance and rejects any release-control or default-state advance.

The private default store uses rollback-journal SQLite with `synchronous=EXTRA`. Under
the latest release-control read guard, one `BEGIN IMMEDIATE` transaction reverifies the
entire canonical revision chain and installed packages, performs the signed
sequence/prior-pointer compare-and-swap, inserts the unique decision and immutable
selection record, and updates the singleton current pointer. Consumption and mutation
therefore either commit together or both roll back. An ambiguous commit response is
resolved through read-only status; automatic recovery is unnecessary and absent.

This is a narrow control-plane configuration change. Results record
`default_changed: true`, while every authority, pointer, result, status, and event denies
all other configuration mutation, activation, and runtime lookup. No shipped runtime
reads the pointer. Local database/control rollback or cloning, external monotonic state,
post-selection health evidence, runtime consumption, drift monitoring, and automatic
rollback remain open. The next slice adds post-promotion drift and health evidence
before any selected prompt can reach a model request.

### 25.13 Implemented signed post-selection health and drift eligibility

A health-authority policy now pins the exact default/control/promotion trust roots and
requires at least two independent Ed25519 identities. The identities and keys must be
disjoint from each other by role and from every evaluator, resolver, promoter, release
controller, installer, and default selector in the fully reverified source lineage.

One signer fixes the exact current pointer, installed bytes, latest release-control
entry, authenticated promotion holdout reference, measurement-protocol digest,
freshness/lifetime limits, independent-group floor, and direction-aware numeric
thresholds. A distinct observer signs the exact post-selection measurement window,
evidence-bundle digest, group counts, confidence-bound rates in integer parts per
million, complete-cost coverage and delta, and p95 latency delta.

Issuance rebuilds promotion and release control, holds the latest local control guard,
verifies the complete default revision chain and installed package, and accepts only
the archive currently permitted by control. It rejects observations that predate
selection, are future-dated or stale, have insufficient groups, fail the original
registered health gate, or drift beyond the separately signed tolerances from the
holdout report. The result expires at the earliest source or policy boundary.

This remains evidence, not execution. The CLI accepts no private keys; the evidence
bundle and measurement protocol are authenticated by digest but not fetched or
recomputed. Local database rollback/cloning, clock integrity, continuous monitoring,
alert delivery, provider dispatch, and automatic rollback remain
open. Every artifact denies dispatch, activation, configuration mutation, and
automatic rollback. The non-sending preparation substrate below addresses one-use
request, prompt, health, route, and spending admission; brokered provider dispatch
remains a separate gate.

### 25.14 Implemented one-use skill runtime preparation and spend admission

A new runtime-authority policy pins the exact health authority, default store, model
registry, and shared spend ledger while requiring its signers to be identity- and
key-disjoint from every upstream health, default, installation, release, promotion,
grading, and resolution authority. The signable decision fixes one request, current
pointer and health receipt, exact reconstructed persona prompt, provider/model/effort
route, routing-preflight digest, normalized provider/broker request hashes, reviewed
spend policy, deterministic ledger entry, worst-case reservation, and short validity
window.

Preparation reverifies the full skill-health chain, selected installed bytes, current
control/default state, registry and exact route with no effort substitution. The
request explicitly acknowledges external data transfer but no transfer occurs. To
avoid a non-atomic claim-ledger/spend-ledger composition, the shared spend-ledger insert
itself is the one-use authorization burn. Verified release-control and default-pointer
read locks remain held across that insertion. All provider-independent checks occur
first. The reservation pessimistically charges the policy's maximum input tokens plus
the requested output cap without contacting a provider.

The prepared private artifact contains the exact prompt and user input but issues no
bearer grant and records that no request was sent. A read-only status path distinguishes
absent, held, settled, uncertain, and violation states while denying retry and automatic
budget release. Failed inserts consume nothing; a crash after commit leaves authority
burned and budget held.

This is not dispatch. The routing preflight is exact-route matched and bound by the
independent runtime signature. Runtime policy schema version 2 and the preparation path
now also pin and recompute its complete empirical source chain. The existing provider
transport cannot consume a pre-reserved entry and must not be composed because it would
reserve twice. External monotonic state, dispatch authority, credentials, network send,
response audit, settlement, and automatic rollback remain open.

### 25.15 Implemented full routing revalidation and guarded broker admission

A pre-created admission-store policy pins one private store identity, both control
anchors, the default store, and the spend ledger. The signed runtime-authority policy
pins that complete policy, plus the routing activation-authority and control-anchor
policies. Runtime signers must be independent of authorities and evaluators in both the
skill and routing lineages.

Preparation and broker admission now reconstruct the routing preflight from its full
calibration, holdout, promotion, operational-signature, eligibility, and anchored
control sources. The admission commit holds read locks on the exact latest routing
control, exact latest skill release control, current default pointer, and exact held
spend entry. A deterministic insert uniquely claims the prepared request, runtime
decision, and existing ledger entry in the pinned admission store. It does not create
a second reservation, and injected failures roll back only the admission while leaving
the earlier conservative reservation held.

Admission remains non-executing. It contains no request body, credential, or bearer
capability, and every policy, artifact, status, and event denies provider dispatch,
send, retry, and automatic release. Store copying/rollback, clock integrity, and
organizational collusion remain external. The following slice adds independent
dispatch authority and durable consumption while deliberately deferring the first
request-bound bearer, provider transfer, and ambiguous-send settlement.

### 25.16 Implemented independent dispatch-authority consumption

A separate Ed25519 dispatch policy now pins the runtime-preparation authority and a
pre-created claim-store policy. That store policy pins the admission store, both
control anchors, default store, and spend ledger. Dispatch signers must be identity-
and key-disjoint from runtime-preparation signers. Decisions last at most 60 seconds
and bind the exact admission, prepared and signed runtime artifacts, route, normalized
provider and broker request hashes, both controls, default pointer, ledger entry, and
reservation.

Consumption reconstructs the complete routing and skill lineages and exact stored
admission. Read guards hold both latest controls, current default, existing held spend,
and exact admission through an at-most-once claim commit. Replay, stale state, policy
substitution, settled spend, expiry, and invalid signatures fail closed. Injected
database failure leaves the admission and conservative spend reservation unchanged.

The resulting claim authorizes only a future exchange for one request-bound grant. It
is not a bearer and no current transport accepts it. Every contract and event records
that no grant was issued, direct provider dispatch is unauthorized, no request was
sent, and retry and automatic budget release are denied. Ephemeral bearer issuance,
the durable before-send boundary, pre-reserved transport, outcome settlement, external
monotonic state, and credentialed conformance remain open.

### 25.17 Implemented ephemeral request-bound broker capability

Dispatch-authority policy schema version 2 now pins a pre-created broker-grant-store
policy, which in turn pins the dispatch-claim and admission stores, both control
anchors, default store, and spend ledger. Grant issuance reconstructs the entire
routing and skill evidence graph, exact signed preparation and admission, and exact
signed and consumed dispatch authority. It holds both control anchors, current
default, existing held spend, admission, and dispatch claim through one durable unique
issuance commit.

The issuance store persists only exact provenance and a domain-separated hash of a
fresh random 256-bit capability. The bearer remains in process memory, is capped at 30
seconds and by the signed decision, redacts its representation, can be delivered once,
and can be validly redeemed once under a lock. Redemption returns only issuance
metadata, never prompt bytes, credentials, or a transport. A committed but lost bearer
cannot be recreated, and an injected store failure returns no bearer while leaving all
prior state and spend unchanged.

No CLI path exports the secret. CLI commands create and inspect only the hash-bearing
durable store. Provider request transmission, pre-reserved settlement, an fsynced
before-send marker, response handling, cancellation, timeout, crash recovery, and
credentialed conformance remain open. Missing or ambiguous outcomes must never imply
retry or budget release.

### 25.18 Implemented provider-owning pre-reserved transaction

Broker-grant-store policy schema version 2 now pins one provider-transaction-store
policy. The latter pins the grant-store identity, both control anchors, default store,
spend ledger, capacity, and a maximum 60-second provider wait. Before redemption, the
transaction checks exact preparation/issuance request hashes, route, model, pricing,
and existing reservation plus a zero-retry OpenAI transport contract.

Fresh routing-control, skill-control, default, held-spend, and exact-grant read guards
remain open while the capability is burned and an exact send intent commits in a
private rollback-journal SQLite store using `synchronous=EXTRA`. Transport is invoked
only after that commit and at most once. The store persists no bearer, prompt,
credential, request body, or response body.

Verified model/tier/usage settles the existing ledger entry at locally computed actual
cost. Provider errors, malformed or missing usage, timeout, cancellation, and lost
response retain the full reservation as uncertain. Pricing-bound violations retain
the full reservation as a blocking violation. The ledger commits before hash-only
outcome metadata, so either cross-store failure remains conservatively accounted
behind the durable marker. Recovery never authorizes retry or automatic release.

Credentialed conformance and external billing reconciliation remain open. Durable
content-verified response/result publication is the separately pinned next layer.

### 25.19 Implemented content-verified runtime response publication

Provider-transaction policy schema version 2 now pins one complete response-store
policy. That policy binds the exact transaction-store identity, capacity, individual
and aggregate byte limits while structurally denying reasoning or provider-credential
publication, provider retry, and automatic budget release.

Publication accepts only the exact stored `response_received` transaction with its
existing ledger entry settled. It recomputes response bytes, request and response
digests, full preparation/issuance/route/ledger lineage, model, provider request ID,
stop reason, token usage, and locally charged cost. The exact canonical provider
response, reasoning-free result, manifest, send intent, and outcome commit together in
one private rollback-journal SQLite transaction. Unique identities reject replay.

Every subsequent status or result read repeats canonical-record, digest, lineage, and
result-to-raw-response verification. The public result accepts only assistant text;
reasoning, including encrypted provider state, remains retained in the private raw
record. Tool-bearing and reasoning-only responses are not publishable. The CLI can
create and inspect the store and read verified results but has no raw-response export.
Provider credentials are not accepted or added, but model-authored text remains
untrusted and may require a separate sensitive-output policy.

This closes local durable result publication, not external proof. Same-UID access,
trusted transport/parser behavior, store rollback/cloning, retention policy, hardware
durability, provider authorship, invoice reconciliation, and credentialed OpenAI
conformance remain open. A separately authorized credentialed run must traverse this
exact zero-retry boundary before stronger operational claims are made.

### 25.20 Implemented authenticated runtime conformance attestation

A separate conformance policy now pins the exact response-store policy, UTC validity
and freshness bounds, canonical trusted Ed25519 observer identities and keys, reviewed
OpenAI SDK versions, production origin, Responses API family, API-key credential mode,
official SDK, zero-retry, no-storage, and no-truncation requirements.

After an operator actually observes a credentialed exchange, signable metadata binds
the exact verified publication, result, transaction, model, effort, provider request
ID, SDK version, and a digest of separately retained redacted transport evidence. The
derive CLI requires explicit credentialed-exchange acknowledgement and never accepts a
provider credential or signing key. External signing retains private-key custody.

Authentication verifies the enrolled observer's domain-separated Ed25519 signature,
policy and observation freshness, allowlisted SDK, and the exact private publication.
Loading that publication repeats canonical raw-response, result, settled transaction,
and ledger-lineage verification. Output carries hashes and metadata only, not prompt,
answer, reasoning, raw response, API credential, or signing key.

This authenticates an observer claim, not the truth of every claimed transport fact.
Provider authorship, TLS peer identity, invoice reconciliation, quality, promotion,
and routing activation remain structurally false. The observer can lie or collude;
the external evidence digest is not fetched. No live or paid request was made for this
milestone. Next, a separately authorized run must traverse the exact path, followed by
external billing/provider-receipt reconciliation and the repeated blinded quality
study before stronger operational or routing claims.

### 25.21 Implemented portable publication-history witness

Response-store policy schema version 2 now persists and validates an explicit,
gap-free publication sequence rather than SQLite's mutable implicit row ID. The store
computes a domain-separated rolling SHA-256 commitment over publication-manifest
digests in that order only after fully reverifying every canonical raw response,
result, manifest, transaction, and ledger relationship. The hash-only
history includes store-policy identity, count, rolling digest, and latest publication
identifiers, never raw response or published assistant content.

A separate witness policy pins that exact store, UTC validity and freshness bounds,
positive minimum publication count, and canonical trusted Ed25519 witness identities
and keys. Signable checkpoints bind the policy, full current history, and witness time.
Verification authenticates the signature and requires that checkpoint history remain
an exact prefix of the current store. Legitimate later publications remain valid;
deletion, reordering, or divergence at or before the checkpoint fails closed.

The CLI derives and verifies hash-only artifacts but never accepts signing private
keys. A useful signed checkpoint must be retained in a separate trust or storage
domain. Both checkpoint and verification schemas explicitly deny proof of external
retention or newest-checkpoint delivery, as well as response/result export, retry, and
budget release. A matching old store and old checkpoint can still be presented if a
newer external checkpoint is suppressed. External delivery, latest-state service,
clock integrity, key custody, and availability remain open, as do provider billing
reconciliation and separately authorized credentialed conformance.

### 25.22 Implemented authenticated aggregate billing evidence

A billing policy now pins the exact response-store and conformance policies, UTC
validity and freshness bounds, the documented OpenAI organization completion-usage and
cost endpoints, their narrowest supported bucket widths and grouping dimensions, and
canonical trusted Ed25519 billing auditors. Billing identities and keys must be
disjoint from every enrolled conformance observer at authentication time.

Signable evidence reauthenticates the full historical conformance receipt and private
publication before binding transaction, outcome, ledger, provider response identifier,
route, local usage and cost, exactly matching external aggregate values, closed bucket
windows, hashes of project/API-key identifiers, and digests of separately retained
complete Admin API pages. The attested scope must contain exactly one request. Evidence
retrieval must follow both the one-minute usage bucket and one-day cost bucket.

The documented aggregates do not expose a response ID, and Mos Eisley does not fetch or
parse the retained evidence in this layer. Consequently every artifact fixes exact
request-cost attribution, provider authorship, and invoice finality to false even when
the exclusive aggregate matches exactly. Ledger mutation, automatic budget release,
retry, quality, promotion, and routing activation are also structurally denied. The CLI
only derives and authenticates metadata, never accepts provider credentials or signing
private keys, and does not export content or raw billing pages.

No live or paid request was made for this milestone. Next, separately authorized
credentialed conformance and a credential-isolated strict Admin API evidence collector
must exercise the real boundary. Request-level claims require a future documented
provider field rather than inference from aggregate isolation.

### 25.23 Implemented credential-isolated Admin API billing collection

An explicit-consent `openai-billing-collect` process now owns `OPENAI_ADMIN_KEY` only
for bounded OpenAI organization completion-usage and cost reads. It first
reauthenticates the exact conformance publication and current billing policy, rejects
open reporting windows and unusable output paths before credential access, then uses
the official SDK with automatic retries, environment proxies, redirects, and streaming
disabled. Each decoded response and the complete cursor chain are bounded.

The retained private bundle strictly validates one exact one-minute completion group,
project/API-key/model/default-tier equality, one model request, one closed daily cost
bucket, exact project/API-key cost groups, no duplicate line items, and an integer
microusd total. Canonical rolling digests over the retained raw pages feed the existing
signable observation path; the collector neither holds a signing key nor mutates the
spend ledger. Console output omits raw pages, identifiers, totals, prompts, responses,
and the Admin credential.

The adversarial boundary is narrower than “exclusive request receipt.” The completion
endpoint proves only one request in the selected minute, while the costs endpoint is a
daily aggregate with no response ID. Collection therefore fixes complete daily
API-key exclusivity and exact request-cost attribution to false. The existing derive
step still requires a separate completeness/exclusivity attestation, and authenticated
evidence continues to deny invoice finality, ledger release, retry, quality, promotion,
and activation. Fixture HTTP tests exercise the SDK boundary without a paid model
request. A separately authorized real conformance run and real Admin read remain
operator work.

### 25.24 Implemented failure-preserving brokered evaluation assembly

Broker audit outcome schema version 3 now requires bounded elapsed latency for every
terminal state and distinguishes a generic provider execution error, an actual broker
deadline, and caller cancellation. Successful outcomes continue to bind exact reply
bytes. Failed and cancelled outcomes carry no response hash or provider request ID;
their recovery state preserves absent, held, uncertain, or violation ledger exposure
without authorizing retry or release. Older outcomes remain readable for recovery but
cannot mint failure evidence without the new latency and error fields.

A verification-only failure compiler requires an independently supplied assignment
authorization, the exact private audit chain, and the named shared ledger. It emits no
invented response, usage, critique, or cost when no reservation exists. A separate
assembler revalidates every artifact against the blinded execution batch, requires
exact sample coverage and unique authorization, outcome, response, provider-request,
and ledger identities, and restores canonical batch order. Omission, duplication,
route substitution, and mixed-ledger assembly fail closed.

The assembled `BrokeredEvaluationResultSet` is intentionally not `RawResultSet`. Its
contract and CLI output fix credentialed conformance proof, live-result issuance,
grading, scoring, promotion, retry, and automatic budget release to false. This closes
failure-preserving coverage composition only. A real provider conformance run,
authenticated live-execution policy, and separately reviewed conversion remain
mandatory before empirical scoring. No provider or paid request was made.

### 25.25 Implemented authenticated brokered evaluation conformance receipt

A pre-registered evaluation-conformance policy now fixes one exact blinded OpenAI
assignment before an observer claim can be accepted: plan, batch, sample, candidate,
evaluation request, serialized provider request, spend policy, ledger, ledger entry,
UTC window, observation age, SDK allowlist, and sorted unique Ed25519 observer keys.
Provider, endpoint, Responses family, API-key mode, explicit conformance command,
official SDK, bounded client, isolated broker, zero retries, disabled storage, and
disabled truncation are strict literals rather than signable free text.

Derivation requires explicit credentialed-exchange attestation plus the successful
broker artifact, exact blinded batch, independently retained assignment authorization,
private audit, and shared ledger. Authentication verifies the domain-separated
signature and freshness, then reparses every contract and reopens the audit and ledger.
The terminal response and outcome hashes, measured latency, settled status, and
charged amount must continue to match. Trust anchors or derived inputs inside the
audit tree, symlink aliases, hard links to the audit authorization, and output/input
overlap fail closed. CLI output omits prompt, critique, usage, provider request ID,
raw response, credential, and signing key.

This authenticates a trusted observer statement, not OpenAI authorship or billing.
The observer can lie; transport-evidence bytes are externally retained and not fetched;
the observation time and host clock are trusted. Only successful settled token-usage
artifacts qualify because current failure state does not prove whether a provider send
occurred. One probe cannot establish complete-batch conformance and every policy,
observation, receipt, and event fixes conversion, grading, scoring, quality, promotion,
and routing activation to false. A separately authorized real probe is still required;
tests use synthetic artifacts and keys and make no provider or paid request.

### 25.26 Implemented no-send evaluation conformance ceremony preflight

A dedicated preparation command now deterministically derives the exact
evaluation-conformance policy from one blinded assignment, reviewed spend policy,
existing shared ledger, planned fresh audit path, UTC window, sorted observer roster,
and sorted installed-SDK allowlist. It reconstructs the strict OpenAI request and
pins its hash plus every assignment and spending identity. The ceremony reads no
provider credential, creates no audit, makes no reservation, starts no container,
and sends no request; its event reports those facts explicitly.

The paid-capable `openai-conformance` command now requires that prepared policy.
Before reading `OPENAI_API_KEY`, it reconstructs the authorization and rejects any
request, assignment, spend-policy, ledger, audit-derived entry, installed SDK, or
validity mismatch. The policy window must fit inside the spend-policy window and
cover the configured request timeout. Both preparation and live preflight require an
unblocked ledger, unused exact entry, fresh audit path, and non-overlapping inputs and
outputs. Atomic spending admission remains authoritative against concurrent changes.

This is a local pre-credential commitment, not a spend reservation, provider
authorization, conformance result, or observer signature. File custody, host clocks,
same-UID races, and ledger rollback/cloning remain outside the local proof. All
conversion, grading, scoring, promotion, and routing flags remain false. Tests use
synthetic provider and Docker behavior and make no credentialed or paid request.

### 25.27 Implemented signed evaluation conformance authorization

The paid-capable evaluation conformance boundary now requires an independent,
short-lived Ed25519 authorization in addition to explicit local transfer confirmation.
A strict authority policy enrolls sorted unique identities and keys and caps each
authorization at one hour. Every enrolled authority must be disjoint by both identity
and key from every post-run observer in the exact conformance policy.

Unsigned derivation binds the authority and conformance policy hashes, complete
assignment and provider-request identity, spend policy, ledger and entry, maximum
micro-USD exposure, issue time, and expiry. It reads no provider credential or private
key, reserves no money, creates no audit, and sends nothing. Signing is out of process
under a distinct domain. Before API-key access, the live command verifies enrollment,
signature, exact reconstructed content, authority separation, nested authority,
conformance and spend windows, and enough signed lifetime for the request timeout.

The signature authorizes one exact blinded transfer, credential access, and bounded
spend; it explicitly denies unblinded transfer, retry, automatic budget release,
conversion, grading, scoring, promotion, and routing activation. It proves possession
of an enrolled key, not human identity or informed judgment. Trust-policy custody,
signer independence, clocks, same-UID replacement, and ledger rollback/cloning remain
external. Tests use synthetic keys and transport behavior and make no credentialed or
paid request.

### 25.28 Recorded first authenticated Terra/medium live conformance success

The first committed Terra/medium campaign probe traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled the shared campaign ledger at 3,468 micro-USD, and
published a strict artifact with 384 input tokens, 225 combined visible/reasoning
output tokens, and 6,642 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and freshness
lineage.

This is one qualifying Terra/medium success under the frozen live-conformance gate.
Together with the earlier Luna/low result, progress is 2 of 18 required successes:
Luna/low and Terra/medium are each 1 of 3. The unused expired no-send authorization
package did not access a credential, create an audit, reserve spend, or contact the
provider and does not count as a live attempt.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. The observer statement, local clock, host and key custody,
and retained evidence remain trusted. Four probes remain in the initial campaign,
followed by 12 newly precommitted successes and the five frozen failure boundaries.
No calibration conversion is authorized.

### 25.29 Recorded first authenticated Sol/medium live conformance success

The committed Sol/medium campaign probe traversed the exact independently signed,
explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 8,448 micro-USD against the shared campaign ledger,
and published a strict artifact with 377 input tokens, 347 combined
visible/reasoning output tokens, and 9,300 ms measured latency. A separately enrolled
observer signed the derived record, and local authentication reverified the exact
batch, request, authorization, policy, artifact, audit, ledger entry, response hash,
SDK, and freshness lineage.

This is one qualifying Sol/medium success under the frozen live-conformance gate.
Together with the earlier Luna/low and Terra/medium results, progress is 3 of 18:
each of those profiles is 1 of 3. The shared success ledger contains two settled
campaign entries, 11,916 micro-USD charged in total, no unresolved entries, and
138,084 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. The observer statement, local clock, host and key
custody, and retained evidence remain trusted. Three probes remain in the initial
campaign, followed by 12 newly precommitted successes and the five frozen failure
boundaries. No calibration conversion is authorized.

### 25.30 Recorded first authenticated Sol/high live conformance success

The committed Sol/high campaign probe traversed the exact independently signed,
explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 3,008 micro-USD against the shared campaign ledger,
and published a strict artifact with 392 input tokens, 72 combined visible/reasoning
output tokens, and 5,625 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

This is one qualifying Sol/high success under the frozen live-conformance gate.
Together with the Luna/low, Terra/medium, and Sol/medium results, progress is 4 of 18:
each of those profiles is 1 of 3. The shared success ledger contains three settled
campaign entries, 14,924 micro-USD charged in total, no unresolved entries, and
135,076 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. The observer statement, local clock, host and key
custody, and retained evidence remain trusted. Two probes remain in the initial
campaign, followed by 12 newly precommitted successes and the five frozen failure
boundaries. No calibration conversion is authorized.

### 25.31 Recorded first authenticated Astra/high live conformance success

The committed Astra/high campaign probe traversed the exact independently signed,
explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 18,050 micro-USD against the shared campaign ledger,
and published a strict artifact with 390 input tokens, 283 combined
visible/reasoning output tokens, and 9,569 ms measured latency. A separately enrolled
observer signed the derived record, and local authentication reverified the exact
batch, request, authorization, policy, artifact, audit, ledger entry, response hash,
SDK, and freshness lineage.

This is one qualifying Astra/high success under the frozen live-conformance gate.
Together with the Luna/low, Terra/medium, Sol/medium, and Sol/high results, progress
is 5 of 18: each of those profiles is 1 of 3. The shared success ledger contains four
settled campaign entries, 32,974 micro-USD charged in total, no unresolved entries,
and 117,026 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. The observer statement, local clock, host and key
custody, and retained evidence remain trusted. One Astra/max probe remains in the
initial campaign, followed by 12 newly precommitted successes and the five frozen
failure boundaries. No calibration conversion is authorized.

### 25.32 Recorded first authenticated Astra/max live conformance success

The committed Astra/max campaign probe traversed the exact independently signed,
explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 12,450 micro-USD against the shared campaign ledger,
and published a strict artifact with 385 input tokens, 172 combined
visible/reasoning output tokens, and 8,143 ms measured latency. A separately enrolled
observer signed the derived record, and local authentication reverified the exact
batch, request, authorization, policy, artifact, audit, ledger entry, response hash,
SDK, and freshness lineage.

This is one qualifying Astra/max success under the frozen live-conformance gate.
Together with the Luna/low, Terra/medium, Sol/medium, Sol/high, and Astra/high
results, progress is 6 of 18: every profile is now 1 of 3. The initial sealed
five-probe campaign is complete. Its shared success ledger contains five settled
entries, 45,424 micro-USD charged in total, no unresolved entries, and 104,576
micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. The observer statement, local clock, host and key
custody, and retained evidence remain trusted. Twelve newly precommitted successful
probes and the five frozen failure boundaries remain. No calibration conversion is
authorized.

### 25.33 Sealed the second OpenAI live-conformance campaign

A second private campaign manifest now commits the 12 remaining success-matrix
attempts before any of their provider outcomes are known: two distinct assignments
for each of Luna/low, Terra/medium, Sol/medium, Sol/high, Astra/high, and Astra/max.
Selection is mechanical—the two lexicographically smallest sample IDs for each exact
profile that are absent from the six authenticated prior-success receipts. The
manifest binds those receipts, the existing blinded batch and plan, the exact route,
execution sequence, standard pricing source and rates, token caps, and a fresh shared
ledger. It also requires the campaign to stop after any non-success.

The private manifest digest is
`c16548cebc197d4515a8cb01226201e1db23412de4c1b92d3bd5ec2e1853b5c8`.
Its fresh ledger identity is
`3a70da17b19c50af40722f1746e3ab9b0a0eb5ce32851a89029cfe9a656bfae7`,
with a 300,000 micro-USD ceiling. Two capped attempts per profile produce a 217,278
micro-USD worst case and 82,722 micro-USD headroom. At sealing, the ledger contained
zero entries, zero charged exposure, and no unresolved or blocking state.

The sealing path read no credential, made no provider request, reserved no spend,
and authorized no data transfer, conformance, retry, grading, scoring, promotion, or
routing activation. The committed attempts are not presumed successes: every outcome
must remain in chronology, and any failure requires a reviewed disposition and a new
commitment under the frozen gate rules. Fresh per-attempt policies, independent
signature, and explicit local consent remain mandatory.

### 25.34 Recorded second authenticated Luna/low live conformance success

The first committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 335 micro-USD against the campaign ledger, and
published a strict artifact with 377 input tokens, 216 combined visible/reasoning
output tokens, and 13,302 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

This is the second qualifying Luna/low success under the frozen live-conformance
gate and the first completed attempt from the second campaign. Overall progress is 7
of 18: Luna/low is 2 of 3 and Terra/medium, Sol/medium, Sol/high, Astra/high, and
Astra/max are each 1 of 3. The second campaign ledger contains one settled entry,
335 micro-USD charged, no unresolved entries, and 299,665 micro-USD available.

After the provider request had completed, the operator exposed the credential in an
interactive shell input. The credential was treated as compromised and revoked
before campaign continuation; a repository scan found no persisted project copy.
This post-run handling incident does not alter the retained request lineage, but it
requires a new credential for every later live attempt and remains an operator- and
shell-history boundary rather than machine-verifiable proof of revocation.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion,
and routing activation to false. Eleven precommitted successful probes and the five
frozen failure boundaries remain. No calibration conversion is authorized.

### 25.35 Completed the Luna/low live-conformance profile

The second committed attempt in the second campaign traversed the exact
independently signed, explicit-consent, zero-retry broker path on 2026-09-08. The
broker retained a response-received audit, settled 314 micro-USD against the campaign
ledger, and published a strict artifact with 386 input tokens, 197 combined
visible/reasoning output tokens, and 6,254 ms measured latency. A separately enrolled
observer signed the derived record, and local authentication reverified the exact
batch, request, authorization, policy, artifact, audit, ledger entry, response hash,
SDK, and freshness lineage.

This is the third qualifying Luna/low success under the frozen live-conformance gate
and completes that exact profile at 3 of 3 consecutive authenticated successes.
Overall progress is 8 of 18: Terra/medium, Sol/medium, Sol/high, Astra/high, and
Astra/max remain 1 of 3. The second campaign ledger contains two settled entries,
649 micro-USD charged, no unresolved entries, and 299,351 micro-USD available.

Profile completion is not gate completion. The authenticated receipt continues to
fix provider authorship, billing reconciliation, complete-batch conformance, grading,
scoring, quality, promotion, and routing activation to false. Ten precommitted
successful probes and the five frozen failure boundaries remain. No calibration
conversion is authorized.

### 25.36 Recorded second authenticated Terra/medium live conformance success

The third committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 2,590 micro-USD against the campaign ledger, and
published a strict artifact with 377 input tokens, 153 output tokens, and 5,024 ms
measured latency. The provider usage record reported zero reasoning tokens; that is
retained as usage data rather than interpreted as proof about provider-internal
reasoning. A separately enrolled observer signed the derived record, and local
authentication reverified the exact batch, request, authorization, policy, artifact,
audit, ledger entry, response hash, SDK, and freshness lineage.

This is the second qualifying Terra/medium success under the frozen live-conformance
gate. Overall progress is 9 of 18: Luna/low is complete at 3 of 3, Terra/medium is 2
of 3, and Sol/medium, Sol/high, Astra/high, and Astra/max are each 1 of 3. The second
campaign ledger contains three settled entries, 3,239 micro-USD charged, no unresolved
entries, and 296,761 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. Nine precommitted successful probes and the five frozen
failure boundaries remain. No calibration conversion is authorized.

### 25.37 Completed the Terra/medium live-conformance profile

The fourth committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 6,766 micro-USD against the campaign ledger, and
published a strict artifact with 425 input tokens, 493 combined visible/reasoning
output tokens, and 9,419 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

This is the third qualifying Terra/medium success under the frozen live-conformance
gate and completes that exact profile at 3 of 3 consecutive authenticated successes.
Overall progress is 10 of 18: Luna/low and Terra/medium are complete, while
Sol/medium, Sol/high, Astra/high, and Astra/max are each 1 of 3. The second campaign
ledger contains four settled entries, 10,005 micro-USD charged, no unresolved
entries, and 289,995 micro-USD available.

Profile completion is not gate completion. The authenticated receipt continues to
fix provider authorship, billing reconciliation, complete-batch conformance, grading,
scoring, quality, promotion, and routing activation to false. Eight precommitted
successful probes and the five frozen failure boundaries remain. No calibration
conversion is authorized.

### 25.38 Recorded second authenticated Sol/medium live conformance success

The fifth committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 4,712 micro-USD against the campaign ledger, and
published a strict artifact with 393 input tokens, 157 combined visible/reasoning
output tokens, and 6,887 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

An earlier no-send preparation for the same committed sequence expired before
signature, credential access, reservation, or provider contact. It remains retained
privately under an explicit archival name. Regeneration preserved the exact committed
sample, request, ledger entry, model, effort, token caps, and maximum while creating
fresh policy and authorization windows; it did not create or conceal a live provider
outcome.

This is the second qualifying Sol/medium success under the frozen live-conformance
gate. Overall progress is 11 of 18: Luna/low and Terra/medium are complete at 3 of 3,
Sol/medium is 2 of 3, and Sol/high, Astra/high, and Astra/max are each 1 of 3. The
second campaign ledger contains five settled entries, 14,717 micro-USD charged, no
unresolved entries, and 285,283 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. Seven precommitted successful probes and the five frozen
failure boundaries remain. No calibration conversion is authorized.

### 25.39 Completed the Sol/medium live-conformance profile

The sixth committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 4,608 micro-USD against the campaign ledger, and
published a strict artifact with 377 input tokens, 155 combined visible/reasoning
output tokens, and 5,565 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

This is the third qualifying Sol/medium success under the frozen live-conformance
gate and completes that exact profile at 3 of 3 consecutive authenticated successes.
Overall progress is 12 of 18: Luna/low, Terra/medium, and Sol/medium are complete,
while Sol/high, Astra/high, and Astra/max are each 1 of 3. The second campaign ledger
contains six settled entries, 19,325 micro-USD charged, no unresolved entries, and
280,675 micro-USD available.

Profile completion is not gate completion. The authenticated receipt continues to
fix provider authorship, billing reconciliation, complete-batch conformance, grading,
scoring, quality, promotion, and routing activation to false. Six precommitted
successful probes and the five frozen failure boundaries remain. No calibration
conversion is authorized.

### 25.40 Recorded second authenticated Sol/high live conformance success

The seventh committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 4,788 micro-USD against the campaign ledger, and
published a strict artifact with 397 input tokens, 160 combined visible/reasoning
output tokens, and 5,736 ms measured latency. A separately enrolled observer signed
the derived record, and local authentication reverified the exact batch, request,
authorization, policy, artifact, audit, ledger entry, response hash, SDK, and
freshness lineage.

This is the second qualifying Sol/high success under the frozen live-conformance
gate. Overall progress is 13 of 18: Luna/low, Terra/medium, and Sol/medium are
complete at 3 of 3, Sol/high is 2 of 3, and Astra/high and Astra/max are each 1 of 3.
The second campaign ledger contains seven settled entries, 24,113 micro-USD charged,
no unresolved entries, and 275,887 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion, and
routing activation to false. Five precommitted successful probes and the five frozen
failure boundaries remain. No calibration conversion is authorized.

### 25.41 Completed the Sol/high live-conformance profile

The eighth committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 3,776 micro-USD against the campaign ledger, and
published a strict artifact with 399 input tokens, 109 combined visible/reasoning
output tokens, including 84 reported reasoning tokens, and 5,334 ms measured latency.
A separately enrolled observer signed the derived record, and local authentication
reverified the exact batch, request, authorization, policy, artifact, audit, ledger
entry, response hash, SDK, and freshness lineage.

This is the third qualifying Sol/high success under the frozen live-conformance gate
and completes that exact profile at 3 of 3 consecutive authenticated successes.
Overall progress is 14 of 18: Luna/low, Terra/medium, Sol/medium, and Sol/high are
complete, while Astra/high and Astra/max are each 1 of 3. The second campaign ledger
contains eight settled entries, 27,889 micro-USD charged, no unresolved entries, and
272,111 micro-USD available.

Profile completion is not gate completion. The authenticated receipt continues to
fix provider authorship, billing reconciliation, complete-batch conformance, grading,
scoring, quality, promotion, and routing activation to false. Four precommitted
successful probes and the five frozen failure boundaries remain. No calibration
conversion is authorized.

### 25.42 Recorded second authenticated Astra/high live conformance success

The ninth committed attempt in the second campaign traversed the exact independently
signed, explicit-consent, zero-retry broker path on 2026-09-08. The broker retained a
response-received audit, settled 25,700 micro-USD against the campaign ledger, and
published a strict artifact with 375 input tokens, 439 combined visible/reasoning
output tokens, including 285 reported reasoning tokens, and 13,846 ms measured
latency. A separately enrolled observer signed the derived record, and local
authentication reverified the exact batch, request, authorization, policy, artifact,
audit, ledger entry, response hash, SDK, and freshness lineage.

This is the second qualifying Astra/high success under the frozen live-conformance
gate. Overall progress is 15 of 18: Luna/low, Terra/medium, Sol/medium, and Sol/high
are complete at 3 of 3, Astra/high is 2 of 3, and Astra/max is 1 of 3. The second
campaign ledger contains nine settled entries, 53,589 micro-USD charged, no
unresolved entries, and 246,411 micro-USD available.

The authenticated receipt continues to fix provider authorship, billing
reconciliation, complete-batch conformance, grading, scoring, quality, promotion,
and routing activation to false. Three precommitted successful probes and the five
frozen failure boundaries remain. No calibration conversion is authorized.

### 25.43 Recovered the Astra/high output-limit failure

The tenth committed attempt in the second campaign reached the provider on
2026-09-08, received a hash-bound response, settled 29,850 micro-USD, and removed its
container. The receipt recorded 425 input tokens and exactly the configured 512
combined output tokens over 18,437 ms. Strict critique compilation failed, so the
attempt produced no success artifact. Exact use of the output ceiling strongly
supports truncation, consistent with OpenAI's definition of `max_output_tokens` as
including visible and reasoning generation, but retained evidence does not prove the
provider's exact terminal status or expose its raw body.

Brokered evaluation artifact schema 4 now preserves this distinct post-response
validation boundary. The repaired offline compiler bound sequence 10's independent
authorization, response-received audit, response hash, settled ledger entry, latency,
and cost into a non-scoreable `invalid_response` / `validation` artifact. The normal
live command now performs the same publication automatically with a structured
rejection event and exit code 2. It retains no raw response, prompt, provider request
ID, critique, or invented usage and fixes retry, automatic release, live-result
eligibility, and promotion to false. Recorded regression coverage exercises
incomplete output, automatic publication, offline recovery, reply-hash substitution,
and credential non-persistence.

Campaign v2 is halted and its unused eleventh and twelfth requests are not
authorized to run. The failed attempt breaks the Astra/high streak: although 15
authenticated successes remain historical evidence, current gate credit is 13 of
18. The four lower profiles remain complete, Astra/high requires three newly
precommitted consecutive successes, and Astra/max retains its first success. This
natural failure does not satisfy controlled boundary F4. A new public campaign and
budget disposition are required before any further provider request.

### 25.44 Sealed the replacement Astra campaign

A third private conformance manifest is sealed against the same blinded batch and
plan, the halted v2 manifest, and its terminal sequence-10 failure artifact. It
commits three fresh Astra/high attempts for a new consecutive streak followed by two
fresh Astra/max attempts for positions two and three. A deterministic lexical
selector excludes all six pre-v2 success IDs and all 12 v2 commitments, including
the failed request and unused sequences 11 and 12. The manifest commitment is
`df66aba92b145d243bf3cb5b378ec477ea81adafcf072286a250078b8f44b885`.

The sequence-10 boundary showed that 512 combined visible/reasoning output tokens
were insufficient. The replacement fixes each request at no more than 1,000 input,
2,048 combined output tokens, 60 seconds, and 112,400 micro-USD using the checked
Astra standard rates. Five per-request maxima total 562,000 micro-USD. A fresh
600,000 micro-USD ledger
`771cc6fcb438d44cbe2f51502bce2c9adc20bd26a89aa25fa17d57321c0ca9c6`
retains 38,000 micro-USD aggregate headroom and was empty and unblocked at sealing.

Sealing accessed no credential, reserved no spend, transferred no data, and sent no
provider request. It authorizes neither execution nor continuation of v2. Sequence 1
still requires fresh short-lived policies, independent authorization, operator
review, and explicit local consent. Any non-success stops v3. The current gate
remains 13 of 18, and successful completion of all five attempts would still leave
the five controlled failure boundaries and every downstream quality, calibration,
promotion, and activation gate outstanding.

### 25.45 Preserved the v3 pre-dispatch image failure

The first v3 sequence-1 invocation failed closed because its previously pinned
Docker image was absent locally. Policy and signature verification completed and the
API key entered ephemeral process memory, but the broker never recorded admission.
The audit remained `prepared`, the ledger remained `absent` with zero entries and
zero exposure, no container lifecycle existed, and no prompt or provider request
crossed the execution boundary. This is a local preparation failure, not a campaign
result, retry, controlled boundary, or change to the 13-of-18 gate.

The expired signed stub is preserved intact and cannot mint conformance evidence. A
locked rebuild produced no-volume image
`sha256:929977cba2903c990b567b1341f0d97b965ef31e670c73a4db30638204856dc7`,
which completed an offline, read-only, no-network smoke invocation and is now pinned
in the private v3 runner. A fresh authorization identity may be prepared against the
same committed sequence only after this public disposition. It still provides no
send authority without independent signing and new explicit operator consent; any
admitted non-success will halt v3.

### 25.46 Authenticated the first replacement Astra/high success

The first admitted v3 sequence completed against the corrected immutable container
boundary and was independently authenticated. It used 409 input and 438 combined
output tokens, including 203 reported reasoning tokens, over 13,730 ms. The shared
ledger settled 25,990 micro-USD against the 112,400 micro-USD request maximum and
retains 574,010 micro-USD with no unresolved or blocking state. Container cleanup
reached `removed` on its first attempt.

The completed artifact is
`2c94ce6d6126874368afa26fe0af9f30997615fc80670225d541120288590185`, the
observer-signed observation is
`fc821ec9ba65a54587c75f20ecae0b9b80e17ca36a278f681fdb407c3fea0b9d`, and fresh
authentication produced receipt
`07e85687a8093574301c37a1470edeef612606beb7dc9e8edd1b77c03cd604eb`.
All provider-authorship, billing, complete-batch, conversion, grading, scoring,
quality, promotion, and activation claims remain false.

This result begins a new Astra/high streak rather than joining successes across the
sequence-10 failure. Current qualifying progress is 14 of 18: four lower profiles
remain complete, Astra/high is 1 of 3, and Astra/max is 1 of 3. Sequence 2 requires
fresh no-send preparation, independent authorization, and explicit local consent.

### 25.47 Authenticated the second replacement Astra/high success

The second admitted v3 sequence completed through the same corrected immutable
container boundary and was independently authenticated. It used 373 input and 149
combined output tokens, including 124 reported reasoning tokens, over 8,701 ms. The
shared ledger settled 11,180 micro-USD against the 112,400 micro-USD request maximum
and now retains 562,830 micro-USD with no unresolved or blocking state. Container
cleanup reached `removed` on its first attempt.

The completed artifact is
`4c78321bfc90adb0fbb2149192af5d7522dcc07d6a85b357bbe852667f257b80`, the
observer-signed observation payload is
`450a050bae6f5eb3230be6e0ab0c05bf54c4b8b968e3f49ae5fa996ebc43f361`, and fresh
authentication produced receipt
`a637226ad6119f4b9878637613d8d4837ccdfc2d5e7675fd634dee42df971add`.
The distinct sample, request, authorization, audit, ledger-entry, response,
artifact, signature, and receipt identities prevent sequence-1 replay from
supplying this position. All provider-authorship, billing, complete-batch,
conversion, grading, scoring, quality, promotion, and activation claims remain
false.

This result is position two of the new Astra/high streak. Current qualifying
progress is 15 of 18: four lower profiles remain complete, Astra/high is 2 of 3,
and Astra/max is 1 of 3. Sequence 3 requires fresh no-send preparation, independent
authorization, and explicit local consent.

### 25.48 Completed the replacement Astra/high streak

The third admitted v3 sequence completed through the corrected immutable container
boundary and was independently authenticated. It used 392 input and 71 combined
output tokens, including 46 reported reasoning tokens, over 5,087 ms. The shared
ledger settled 7,470 micro-USD against the 112,400 micro-USD request maximum and now
retains 555,360 micro-USD with no unresolved or blocking state. Container cleanup
reached `removed` on its first attempt.

The completed artifact is
`7e5fa9b48e38ac21b69921a621e3af95235f00c3806a227f65a75898d30d86c8`, the
observer-signed observation payload is
`3301fb4d710c0108ade8ff1031c4c7af713e80ef19d36773796430b4f2610861`, and fresh
authentication produced receipt
`140022e6666d9d69a9e93d9afcf361ad856a7a58f2d307cd7226cdbb69c48101`.
All three replacement positions have distinct sample, request, authorization,
audit, ledger-entry, response, artifact, signature, and receipt identities. All
provider-authorship, billing, complete-batch, conversion, grading, scoring, quality,
promotion, and activation claims remain false.

This result completes the new Astra/high streak at 3 of 3. Current qualifying
progress is 16 of 18: five profiles are complete and Astra/max remains 1 of 3.
Sequence 4 begins the remaining Astra/max tranche and requires fresh no-send
preparation, independent authorization, and explicit local consent.

### 25.49 Authenticated the second Astra/max success

The fourth admitted v3 sequence completed through the corrected immutable container
boundary and was independently authenticated. It used 373 input and 206 combined
output tokens, including 181 reported reasoning tokens, over 6,411 ms. The shared
ledger settled 14,030 micro-USD against the 112,400 micro-USD request maximum and
now retains 541,330 micro-USD with no unresolved or blocking state. Container
cleanup reached `removed` on its first attempt.

The completed artifact is
`08490de0e3f399ff63813525103fd2e337b31d0c89e6b7809d78f00cf692f528`, the
observer-signed observation payload is
`01e47b33d54776f8991ab59777fdd3e784c68ff495e8df325e67257f118c5fa3`, and fresh
authentication produced receipt
`d27e63abf37d6d0e58999841ea7f8a3309e17ca8a29d950f1526351c953bb0da`.
Its sample, request, authorization, audit, ledger-entry, response, artifact,
signature, and receipt identities are distinct from the earlier Astra/max result.
All provider-authorship, billing, complete-batch, conversion, grading, scoring,
quality, promotion, and activation claims remain false.

This result is position two of the Astra/max profile. Current qualifying progress is
17 of 18: five profiles are complete and Astra/max is 2 of 3. Sequence 5 is the
remaining success assignment and requires fresh no-send preparation, independent
authorization, and explicit local consent. The success matrix alone will not satisfy
the gate because all five controlled failure boundaries remain outstanding.

### 25.50 Completed the OpenAI live success matrix

The fifth and final admitted v3 sequence completed through the corrected immutable
container boundary and was independently authenticated. It used 399 input and 349
combined output tokens, including 324 reported reasoning tokens, over 9,976 ms. The
shared ledger settled 21,440 micro-USD against the 112,400 micro-USD request maximum
and retains 519,890 micro-USD of unused campaign capacity with no unresolved or
blocking state. Container cleanup reached `removed` on its first attempt.

The completed artifact is
`937c80e6f0bb31da1114a1733f13379c275e2a4afe1888c78019cc2cc2ae3d55`, the
observer-signed observation payload is
`c7d8e67ce75dd4b80b4dfcf165b73daeee4f3dd230ac3de2563e98bd41604232`, and fresh
authentication produced receipt
`42f593529a9052da8d1d776b4955d7945b0e854f492ba012bdfe7cefa2b3c1fe`.
The three Astra/max positions have distinct sample, request, authorization, audit,
ledger-entry, response, artifact, signature, and receipt identities. All
provider-authorship, billing, complete-batch, conversion, grading, scoring, quality,
promotion, and activation claims remain false.

All six registered profiles now have three qualifying consecutive authenticated
successes, completing the 18-of-18 success matrix. Twenty successes remain in
historical evidence because the two pre-failure Astra/high results are retained but
do not count across the reset. The five-request v3 campaign is closed and its unused
ledger headroom authorizes no further send. The OpenAI live-conformance exit gate
remains incomplete until controlled boundaries F1 through F5 pass; only then may a
reviewed gate report consider calibration conversion.

### 25.51 Made F1 precredential rejection retainable

The real `openai-conformance` path can now write a canonical, content-addressed F1
receipt when an authentic signed authorization is expired or mismatched against the
current exact policy binding. The receipt binds the batch, sample, candidate,
request, spend policy, conformance policy, authority policy, signed authorization,
ledger, installed Mos Eisley version, and OpenAI SDK version. It records identical
before/after ledger snapshots and fixes credential access, audit creation, normal
output publication, container start, provider send, spend reservation, retry,
grading, scoring, promotion, and routing activation to false.

Receipt production is fail closed: malformed or invalidly signed authority cannot
mint one; an existing or overlapping receipt path is rejected; and any ledger entry,
ledger mutation, audit, assignment output, artifact, or lifecycle observation blocks
issuance. Tests exercise the actual CLI path while independently asserting that the
credential accessor and broker dispatcher are never called. This completes the F1
instrumentation, not F1 itself. The boundary still requires a reviewed run from an
installed wheel with retained operational evidence. F2 through F5 and all downstream
conversion, quality, promotion, and activation gates also remain outstanding.

### 25.52 Passed the installed-wheel F1 boundary

The first controlled failure boundary ran through a separately installed 0.1.0
wheel with SHA-256
`a7519afe7df26cc66ca94695e6e90be41723bb0b0e6b27c480af77f856702545`.
The operator independently signed authorization payload
`9d8fd80cfa82952f5581b8fe4acd188134936b45450a727321d5dd0227466cba`
against source conformance policy
`ae921f5eaf46c023b23b07b55e578c7532362b9fedefc7d8b63e1bbfaa2011f6`.
The installed command received target policy
`304ce847061259308de7e55ca6bccede82e1509dc1e9dbadf7e293836973834b`,
which differed only in the reviewed policy identity, and retained F1 receipt
`6a0d132074a27272851ddc0affe08ba3ce096a59e0f7ff68dc450489080941bf`.

Dedicated ledger
`5fa56e12fa183b0af7b18a4eb601560390e0b6b986e9c181272003ef5b9d95ad`
remained byte-for-byte unchanged with zero entries, zero charged, 10,000 micro-USD
available, no unresolved exposure, and no block. The exact ledger entry was absent
before and after. The receipt and independent filesystem check show no credential
access, audit, assignment output, conformance artifact, container lifecycle,
provider request, spend reservation, retry, grading, scoring, promotion, or routing
activation.

The first private verifier invocation completed and verified the one-use F1 command,
then failed while serializing only its final local summary because it passed a plain
dictionary to the contract serializer. The reporting wrapper was corrected and
resumed from the already-retained receipt; the controlled command was not rerun.
This post-boundary tooling defect does not alter the receipt or ledger evidence but
is retained in the disposition. F1 is complete; F2 through F5 and the reviewed gate
report remain outstanding.

### 25.53 Made F2 authentication rejection retainable

The real `openai-conformance` path can now retain a canonical status-`error` artifact
when an admitted request terminates specifically with `authentication_error` during
`token_count`. The artifact is compiled against the independently persisted
assignment authorization, terminal broker audit, and dedicated ledger. It requires
absent ledger state and null cost, while retry, automatic release, live-result,
grading, scoring, promotion, and routing authority remain false.

This path is intentionally narrower than generic provider-failure recovery. The
terminal audit classification and compiled artifact must agree on the exact F2
tuple. Partial audits and all other failure stages or categories
remain unable to publish an artifact; post-reservation ambiguity therefore retains
the existing conservative F3 behavior. Automated tests additionally prove the token
count is attempted once, generation is never attempted, no reservation or ledger
entry appears, and the full ledger snapshot is unchanged.

This completes F2 instrumentation, not F2 itself. A separately installed reviewed
wheel, disposable ledger, independently signed short-lived authorization, explicit
local consent, one deliberately invalid credentialed request, and retained
operational verification are still required. F3 through F5 and the aggregate gate
report also remain outstanding, and no provider request or downstream authority is
granted by this implementation.

### 25.54 Passed the installed-wheel F2 boundary

The second controlled failure boundary ran once through a separately installed
Mos Eisley 0.1.0 wheel with SHA-256
`6da01d8b82f5ac1de884be8c83e4daf351fdba84cfe7a0bdc3cbc7675d1bde17`
and immutable image
`sha256:711d60232e9f7c49da6a5e26ef2ec0b663f182f2f22b02731e679dc1dab74efe`.
The operator independently signed authorization payload
`f19b0576522be558de6a85c3f1254e1cabab4d515486c6a7659778d03bee3e40`
and explicitly consented to one exact live token-count request using a deliberately
invalid disposable credential.

The request terminated after 1,498 ms with `authentication_error` at `token_count`.
Assignment authorization
`43c67406e1698bccbc401426278285c919906c6e81af777a2875e69a1754a8f2`
and terminal outcome
`c44cac0621f94234ee5029c3ccfc2dde9250924f1f2f7de0899fb3037d51cc14`
bind canonical failure artifact
`ee6cb8800a13985b38978d16b2d6cc54809fca23e6a1aa8930b0f466cb3bb3fa`.
It contains no response, provider request ID, usage, critique, or cost; generation was
never requested and retry, automatic release, live-result, promotion, and activation
authority remain false.

Dedicated ledger
`e00ec143a109677ce9e4be5cb7c0858e2e5099820b24e00843cd33b9ba0115a8`
remained unchanged at zero entries and zero charged with no unresolved or blocked
state. The exact prospective entry and both spend files are absent. Container cleanup
reached `removed` on its first attempt. This completes F2 but does not prove that
OpenAI inspected a particular request body or establish provider billing. The
18-of-18 success matrix plus F1 and F2 are complete; F3 through F5 and the reviewed
aggregate gate report remain outstanding.

### 25.55 Passed the installed-wheel F3 boundary

The third controlled failure boundary ran once through the separately installed
Mos Eisley 0.1.0 wheel with SHA-256
`6da01d8b82f5ac1de884be8c83e4daf351fdba84cfe7a0bdc3cbc7675d1bde17`
and immutable image
`sha256:711d60232e9f7c49da6a5e26ef2ec0b663f182f2f22b02731e679dc1dab74efe`.
The operator independently signed exact authorization payload
`582c3e0f4455e11e65344c806b7527979d6b805b44178027483ca89150661dbd`.
The installed harness refused to run with an OpenAI credential available, used a
precommitted synthetic input count only to trigger normal spending admission, and
then injected one controlled `transport_error` at the `response` stage. No provider
request was sent.

Assignment authorization
`3ae79a0f3255f72943237a67213b15e029e82cd399312cc3c44afd0328907722`
and terminal outcome
`3e6b99a8e473ffecc28d940a3511f8f412d90a529f4790762dbc71534504b2ee`
bind reservation
`7aee410d8e0ff1118d0623f328c41377049792655d5e35d8f181b40c316c1914`
to uncertain spend receipt
`93d0aef34a888b5e08bc5bfa809db86f11a9107829a1e4cbf66ca101318e805f`.
The full 635-micro-USD reservation remains charged with null actual usage, and no
conformance artifact was published.

Dedicated disposable ledger
`70bae33b7b19656582d5f36c1bf669c2194d82e0adb83aa3e8b5e603e6296de7`
now contains exactly one unresolved `uncertain` entry, 635 micro-USD charged, and
9,365 micro-USD available. It will never be reset, released, or reused for a
successful probe. Retry and automatic release remain false; the container reached
`removed` on its first cleanup attempt. This completes controlled local boundary F3
but proves no OpenAI behavior, provider receipt, real token accounting, or billing.
The 18-of-18 success matrix plus F1 through F3 are complete; F4, F5, and the reviewed
aggregate gate report remain outstanding.

### 25.56 Passed the installed-wheel F4 boundary

The fourth controlled failure boundary ran through a separate installation of the
same Mos Eisley 0.1.0 wheel and immutable image used for F3. The operator
independently signed exact authorization payload
`20645429198674bf74229005fc78805f47aee358ba01fcca91c42af0c2a1b7b9`.
The installed harness refused to run with an OpenAI credential available and
returned one controlled Responses envelope with precommitted synthetic usage of 100
input and 20 output tokens but deliberately invalid `Critique` JSON. No provider
request was sent.

Assignment authorization
`d575a9b6cdc99fd78ba160878aa9255429239c8a3d1f9310c65a93c77b7db230`
and terminal response outcome
`0955e1b82225476fc75fb033d8f9e8fb72d2ff98daf1a15dac1780f1cfd56c8b`
bind response hash
`3a1034b648e1c6de05def3b031ccfd88accba49a0a248c1b852a1f2399d99c4f`.
The strict compiler rejected it and retained status-`error` artifact
`16304946b61a491af26010f35350c2b24d1ced3b08f3a54f04b64ba11363098d`
with `invalid_response` at `validation`. The artifact contains no provider request
ID, usage, critique, completed-result eligibility, retry, automatic-release, or
promotion authority.

Reservation
`67baaf6b9825d35837813a57957a5739eefd55d94688cc4c2c9faebb7029d7cc`
and settled receipt
`954bf0bad92ee966771d321b3b4cdeeaba2f7e2e0aa4ac6f8f2f1498ca78f2b0`
leave dedicated disposable ledger
`a89d76056904c1eb7702b52deea22c5706be1592e8b6d17279bb5ae2d7da4233`
with one settled entry, 44 micro-USD charged, 9,956 available, no unresolved
exposure, and no block. The ledger will not be reused for a successful probe, and
the container reached `removed` on its first cleanup attempt. This completes F4 but
proves no OpenAI behavior, provider authorship, real token accounting, or billing.
The 18-of-18 success matrix plus F1 through F4 are complete; only F5 and the reviewed
aggregate gate report remain outstanding.

### 25.57 Passed the installed-wheel F5 boundary

The fifth controlled failure boundary ran through another separate installation of
the reviewed Mos Eisley 0.1.0 wheel and the immutable image used for F3 and F4. The
operator independently signed exact authorization payload
`fcb4077d726d4c924b49d28c3121066c9efa53511814573fb869393db5647f25`.
The installed harness refused to run with an OpenAI credential available and used a
no-network transport that blocked only after normal broker admission and spending
reservation. No provider request was sent.

Assignment authorization
`a1da497479fa4ceb729c5c7c2f22233d0aa97100fa0b324826722d36fbaaebf3`
and admission
`414adef78d436f07fa4a78cb51d20cf6687cc2866b3db57b8daf6ee7d809f5d3`
preceded held reservation
`d61a95be7e621a2ebb49cc55c30aaeee37e094ca2769cc8a77c10c0e7c8dbf1c`.
After independently observing the held entry and armed watchdog, the harness killed
its own launcher with SIGKILL. The launcher could not execute normal cleanup.
Independent watchdog result
`5166fca1bd66c9755ae6c82a6eb761830f2b0ca3f87077b930f6c73f5580a1a2`
removed exact container
`890bb4c6c1190c86c590d8910bcdc34cf6d85fedd9c9c0b1650c76278a480e30`
on its first attempt, and a separate Docker query confirmed that it is absent.

Dedicated disposable ledger
`156724341d384d8746e90b240875633178d7fd0945f6a0d40562ef8be38e3635`
now contains exactly one unresolved `held` entry, 635 micro-USD charged, and 9,365
available. It will never be reset, released, retried, or reused. Read-only recovery
reports phase `admitted`, with no terminal outcome, spend receipt, conformance
artifact, success, or failure claim. Retry, automatic release, and promotion remain
false. This completes F5 but proves no OpenAI behavior, provider receipt, or billing.

All 18 success positions and F1 through F5 now exist, completing the 23 required
execution positions. The overall gate remains open until a reviewed aggregate report
reverifies the complete lineage and fixes every unsupported downstream claim to
false. No calibration conversion or provider request is authorized by this result.

### 25.58 Passed the aggregate OpenAI live-conformance gate

An offline, credential-refusing compiler reauthenticated all 20 retained successful
exchanges at their original authentication timestamps against the exact frozen batch,
policy, observer signature, assignment, artifact, broker audit, and ledger source.
It counted 18 qualifying positions across the six required profiles and separately
retained the two earlier Astra/high successes invalidated by the sequence-10 break.
Every sample, receipt, signature, artifact, authorization, outcome, provider request,
provider response, and ledger-entry identity is distinct.

The aggregate also reverified the v2 terminal validation failure, the v3 pre-dispatch
no-send event, both expired unsigned preparations, both forbidden v2 continuations,
all three campaign manifests, every success-ledger entry, and F1 through F5 from
their authoritative sources. The private 32,624-byte sorted compact report hashes to
`e58dc274b5087271fe1f241724fdd1f319956b4fffba8bf1e83e086db26ea72a`
and records 23 of 23 required execution positions with `outcome=pass`.

The compiler accessed no credential and sent no request. Provider authorship,
billing reconciliation, quality, complete-batch conformance, calibration conversion,
grading, scoring, promotion, routing activation, and additional-request authority
remain literal false. Passing this gate permits only the design of a separate,
reviewed offline converter for the 18 qualifying records. No conversion or empirical
routing claim exists yet.

### 25.59 Implemented partial OpenAI conformance calibration conversion

A committed conversion policy now pins the exact passed aggregate-report digest,
frozen plan and 360-assignment batch, six profiles, and 18 qualifying position names.
The offline converter requires exactly those 18 authenticated receipts and their
matching brokered artifacts. It rechecks canonical receipt/artifact hashes and every
sample, route, request, authorization, outcome, response, ledger, latency, cost,
usage, and critique binding against the aggregate before restoring frozen batch
order. Invalidated historical successes, omissions, additions, substitutions,
noncanonical reports, changed pass claims, and any newly granted authority fail
closed.

The command requires explicit offline consent and refuses to run while either
supported OpenAI key variable is present. Its first real conversion accessed no
credential, sent no request, and produced a private 30,592-byte seed with SHA-256
`c67dfcfac073ba4946afd59b2f2960fb9de10740654cdaf8ad1183f91e8cf570`.
The seed contains 18 of 360 assignments and the same 135,812 micro-USD local cost
total as its sources. It is deliberately incompatible with `RawResultSet`, exposes
route identity, and fixes complete-batch coverage, provider authorship, billing,
quality, grading, scoring, promotion, activation, and further request authority to
false. A complete-batch brokered calibration and separately reviewed gradeable
issuance boundary remain required.
