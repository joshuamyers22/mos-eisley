# Mos Eisley

A foundation for independent, multi-provider adversarial review of code changes.
**Current maturity: live-provider preview.** Recorded review remains the default;
an explicit one-prompt OpenAI command is available. Paid commands remain tool-free;
an explicit MCP adapter supplies data tools to the canonical agent port. This
version does not yet run the adversarial critic/judge workflow live. It can
plan and score offline model/effort evaluations, but automatic routing is disabled.

Generated from the `python-cli` archetype of
[production-project-template](https://github.com/joshuamyers22/production-project-template)
at commit `3d467040ba760efe9795f67f07d5a2ccf364282b`.

## Quick start

Requires Python 3.12+ and uv; supported development targets are macOS and Linux.
The recorded commands require no credentials or external services.

Start the interactive recorded conversation from your project directory:

```sh
uv run --frozen mos
# After installing the CLI on PATH, simply run: mos
uv run --frozen mos resume --last
uv run --frozen mos -- "Remember that the fixture boundary is ten."
```

The welcome screen shows the workspace and supported preview messages. Sessions
save privately in `~/.mos-eisley-sessions`; `-C PATH` selects a workspace and
`--storage PATH` overrides storage. Live conversation is still pending. See the
[terminal guide](docs/CONVERSATION_TUI.md) for controls and recorded limits.
Use `mos chat "PROMPT"` or `mos -- "PROMPT"` to submit an initial literal message;
launch options may precede it, as in `mos -C /path/to/project "PROMPT"`.

[Named sessions](docs/CONVERSATION_NAMES.md) support `mos chat --name "Parser cleanup"`,
`/rename NAME`, and `mos resume --name "Parser cleanup"`. Bare `mos resume` opens
a keyboard picker with name/ID filtering; duplicate names require explicit
selection. Resumed queued work stays paused until you continue it.

Use `mos --choose-directory` or `mos resume --choose-directory` to open the
[startup directory selector](docs/CONVERSATION_DIRECTORY.md). Edit the path,
press Enter to preview its resolved target, then Ctrl-S to select it.
During a conversation, F9 or `/directory switch` selects another project and opens
a fresh session. Active work and unsent drafts must be resolved first; the old
session and its queued messages remain saved.
The terminal shows the working directory and detected Git-marker project root
separately. `/directory` shows full paths and the effective project-memory identity.
Use [`--memory-project-root PATH`](docs/CONVERSATION_MEMORY_PROJECT.md) to select
shared project memory explicitly for a new session. `memory-project-preview` compares
workspace and root documents before adoption. `memory-project-migrate` previews
and applies a guarded copy to an empty root, preserving the source document.
`memory-project-recover` provides explicit, preview-bound cleanup of a verified
extra staging link left by interrupted publication.
`memory-project-resolve` reviews existing-document collisions and preserves a
private prior-root backup before applying an explicit text resolution.
Use `--memory-project-map PATH` to explicitly share another existing directory's
memory across unrelated worktrees. The choice is saved per session; directory
switching clears it, and workspace/tool authority stays with the working directory.

Explicit [user and project memory](docs/CONVERSATION_MEMORY.md) now loads at startup.
Use `mos memory append --scope user --text "..."` for personal preferences, or
`--scope project` for the current project. `/memory` inspects active context and
`mos --no-memory` bypasses it. Use `/memory refresh` to apply changes to the
current session, or `/memory off` to disable its memory; `/continue` resumes work.

[Session storage budgets](docs/CONVERSATION_STORAGE.md) are now configurable:
`mos --session-max-bytes 8000000` saves an 8 MB budget, and the same flag on
`mos resume --last` changes an existing session. `mos sessions` reports usage.
[Incremental SQLite storage](docs/CONVERSATION_SQLITE.md) is now available with
`mos --storage-backend sqlite`; use the same option to resume or list its sessions.
Metadata listing supports `--limit` and `--cursor`. `mos session-migrate SESSION_ID`
previews a JSON-to-SQLite import; apply it with `--apply --expected-sha256 HASH`.
`mos session-migrate-batch ID_A ID_B` previews up to 32 selected sessions under a
64 MB source budget; apply with its batch hash and retry to verify completed copies.
`mos session-transfer SESSION_ID --destination-storage PATH` previews a copy into
SQLite in another existing private directory; apply with its transfer hash.
`mos session-transfer-batch ID_A ID_B --destination-storage PATH` does the same
for a bounded selection, using its batch transfer hash and per-session transactions.
`mos session-export SESSION_ID` previews the reverse SQLite-to-JSON copy in the
same storage directory; `--destination-storage PATH` selects another private
directory. Apply with the returned export hash.
`mos session-export-batch ID_A ID_B` previews up to 32 selected SQLite sessions
and 64 MB of JSON output; apply with its batch hash and retry partial exports safely.
`mos session-cleanup SESSION_ID` previews unpublished JSON temporary files left by
interrupted writes; apply with its cleanup hash. This is explicit storage-owner
maintenance, including orphans without a published session. See the
[cleanup and recovery guide](docs/CONVERSATION_CLEANUP.md).
`mos session-retention --before 2026-08-01T00:00:00Z` now previews a SQLite retention
policy for the current workspace, protecting the newest 20 sessions and active or
noncompleted work. It reports indexed sizes and retention reasons without deleting
anything. See the [retention preview guide](docs/CONVERSATION_RETENTION.md).
`mos session-prune SESSION_ID --before 2026-08-01T00:00:00Z` provides a separate
full-state preview for one eligible SQLite session. Apply its prune hash to delete
that session and its records atomically; see the [pruning guide](docs/CONVERSATION_PRUNE.md).
`mos session-prune-batch SESSION_A SESSION_B --before 2026-08-01T00:00:00Z` extends
that workflow to 1–32 explicit eligible sessions, with a separate batch hash and one
atomic deletion transaction. See the [batch pruning guide](docs/CONVERSATION_BATCH_PRUNE.md).
Original JSON files are retained. `mos session-transcript SESSION_ID --limit 4` reads
verified SQLite transcript pages without loading retained artifacts. In SQLite's
terminal, F5 browses that history, Page Up/Down navigates, and F6 reloads. F7 selects
a memory or review reference; F8 opens/closes its verified content, one artifact
at a time. `mos session-artifact SELECTION --json` also opens a reference returned
by the transcript CLI, with an explicit `--max-bytes` override.
`mos resume --last --storage-backend sqlite --inspect` now previews a verified,
bounded working set without resuming work. SQLite's controller verifies historical
entries one at a time on cold resume, retains artifact references, and streams their
bytes when saving. External commits force the same incremental verification again. See
[controller working state](docs/CONVERSATION_SQLITE.md#controller-working-state).
Chat requests check a separate saved
`--context-max-bytes` budget before consuming an attempt; oversized messages stay
queued with their history intact. See [context admission](docs/CONVERSATION_STORAGE.md#independent-chat-context-budget).
Active input limits are now independent, per-launch settings:
`--active-memory-max-bytes` (default 131072) and `--recording-max-bytes` (default
2000000). SQLite checks stored sizes before loading either active artifact; opening
with larger limits preserves saved hashes. See [input limits](docs/CONVERSATION_STORAGE.md#active-memory-and-recording-input-limits).
Active size/hash checks stream canonical JSON and reuse the checked recording digest
within startup and refresh. Smaller state transitions and longer conversation
limits remain planned.

To install `mos` on your PATH from this checkout with the pinned runtime versions:

```sh
make build
uv tool install --python 3.12 --constraints requirements.runtime.txt dist/mos_eisley-0.1.0-py3-none-any.whl
```

Then run `mos` from any project directory. The standalone installation must be
updated after later source changes; it does not track the checkout automatically.

```sh
make setup
uv run --frozen mos demo --json
# Expected exit 1: the synthetic fixture contains a discount-boundary defect.
uv run --frozen mos replay .mos-eisley/runs/<run-id>

# Separate canonical agent-loop demonstration (expected exit 0).
uv run --frozen mos agent-demo --output .mos-eisley/agent-runs --json
uv run --frozen mos agent-replay .mos-eisley/agent-runs/<run-id>
```

`demo` saves an explicit brief and cassette, which can also exercise `review`:

```sh
uv run --frozen mos review \
  --brief .mos-eisley/runs/<run-id>/brief.json \
  --cassette .mos-eisley/runs/<run-id>/cassette.json --json
```

Prompt-only [skills](docs/SKILLS.md) can bind exact, digest-pinned personas to a
recorded cassette without changing its requests. Discovery roots and project-source
approval are always explicit; validation grants no trust or authority.

The first live provider uses OpenAI's Responses API with the documented default
`gpt-6-astra` model. The command reads only the named files, requires an environment
credential and explicit acknowledgement, sends `store=false`, exposes no tools, and
writes private local artifacts:

```sh
export OPENAI_API_KEY="..."
uv run --frozen mos spend-ledger-create spending.sqlite --ceiling-microusd 5000000
uv run --frozen mos openai-run \
  --prompt prompt.txt \
  --instructions instructions.txt \
  --spend-policy spend-policy.json \
  --spend-ledger spending.sqlite \
  --allow-data-transfer --json
```

The acknowledgement means the prompt and optional instructions will leave the
machine. The request sends `store=false`; your OpenAI organization and data
retention settings still govern provider-side handling.
Create a reviewed, expiring [spending policy](docs/OPENAI_SPENDING.md) first. Input
counting also sends prompt data; generation starts only after its maximum token
cost fits the per-invocation ceiling. This is not an account-wide invoice cap.
Reuse the same [shared ledger](docs/SHARED_SPENDING.md) to bound participating runs
collectively. Missing ledgers fail closed; creation never overwrites an existing scope.

Before a separately authorized generation probe, the narrower
[`openai-readiness`](docs/OPENAI_READINESS.md) command can make one fixed
`gpt-5.6-luna` model-metadata request without sending a prompt. Its private receipt
proves neither billing readiness nor Responses access and cannot enable routing.

The independently signed [synthetic Responses canary](docs/OPENAI_RESPONSES_CANARY.md)
then tests one fixed, tool-free `gpt-5.6-luna` generation under a 32-token cap and
shared spending ledger. It accepts no user prompt and grants no evaluation, billing,
scoring, promotion, or routing authority.

Review exit codes: **0** accept; **1** revise/reject; **2** invalid input or
infrastructure failure. Replay exits **0** when the recorded result reproduces,
even if that result is revise/reject. `mos` is a short alias for `mos-eisley`.

## Data MCP connection

The [MCP client](docs/MCP_DATA.md) connects to the local `data-mcp` server for
read/write Parquet and PostgreSQL access, including Ana Lite's analysis profile.
It also connects to user-selected Streamable HTTP servers with bearer tokens or explicit OAuth login.
OAuth uses a pre-registered public client and the OS keychain.
Explicit configuration selects the executable or URL, credential references and
allowed tools. `mos mcp-list` discovers them; `mos mcp-call` executes one named call.
Schema adapters support bounded local references and JSON argument wrappers for
nullable fields, unions and dictionaries. The dispatcher implements the canonical
agent port. Paid provider commands
and critic/judge workflows retain their existing tool-free boundaries.

## Implemented

- A [recorded conversation terminal](docs/CONVERSATIONS.md) with contextual
  follow-ups, queued messages, cancellation, private saving and explicit same-user,
  same-workspace resume, metadata-only session listing, latest-session selection
  and exact-snapshot deletion. Bounded multiline drafts support code blocks and
  explicit send/discard while work runs. Queued steering links refinements to
  active chat tasks and preserves unanswered intent across resume. Live
  conversation remains planned. An [interactive terminal](docs/CONVERSATION_TUI.md)
  now opens for terminal chat/resume, with multiline editing, bracketed paste,
  a scrollable transcript, review details and persistent status.
- An [explicit recorded review inside the conversation](docs/CONVERSATION_REVIEW.md),
  with isolated critic requests, retained review evidence and contextual follow-ups.
- Immutable, versioned Pydantic contracts with strict input validation.
- Explicit briefs identified by content hash; no automatic repository/config reads.
- Concurrent critic calls with separate brief/persona requests and timeouts.
- Minimum critic/provider quorum; outages cannot produce acceptance.
- Exact-content dedupe retaining original contributions; identity-free judge input.
- Citation presence checks and policy-derived blocking impact. Citation presence
  does not establish that the claim is true. No commands are executed as evidence.
- Cassettes bound to exact critic/judge request hashes.
- Private run artifacts, hash verification, deterministic replay, and SQLite index.
- Provider-neutral multi-turn content blocks and strict tool-call/result sequencing.
- Explicit model capability registry with deterministic effort fallback and byte
  budgets that reserve model output and safety headroom.
- Bounded agent iterations, tool calls, provider/tool deadlines, and cooperative
  cancellation. Unexpected adapter failures are reported without their raw detail.
- Append-and-fsync request/tool boundary journals and exact, request-hash-bound
  replay for a pure in-memory fixture tool.
- OpenAI Responses adapter with strict function schemas, provider call-ID mapping,
  stateless encrypted-reasoning carry-forward and token usage accounting.
- Opt-in fixed-model OpenAI readiness check with no prompt or generation, zero retries,
  safe failure categories, exclusive private output, and literal downstream denials.
- Independently authorized fixed-model Responses canary with synthetic-only input,
  exact count/generation request binding, bounded spend, manifest-last evidence, and
  offline ledger-backed verification.
- Opt-in `openai-run` with a 64,000-byte prompt bound, 4,096-token output ceiling,
  one-request limit, no tools, generic diagnostics and content-verified artifacts.
- Reviewed pricing policies, pre-generation token-count reservations and private
  spending receipts; uncertain outcomes retain the full reservation without retry.
- A non-streaming OpenAI HTTP client that bounds decoded response bodies before SDK
  JSON construction, forces identity encoding after a credentialed decode failure,
  and still fails closed on compressed or chunked responses that ignore the request.
- Transactional shared spending ledger with cross-process admission, conservative
  crash handling and a scope-wide block after recorded pricing violations.
- Content-addressed backend × model × effort sweep plans with pre-registered gates,
  deterministic assignment order and exact-coverage calibration/holdout scoring.
- Group-aware detection, clean-review risk and completion gates with simultaneous
  confidence bounds; repetitions never add independent evidence. Missing group
  declarations or cost required by a cost gate prevent eligibility.
- HMAC-blinded evaluation batches, exact request-bound fixture execution, route-blind
  grading packets and provenance-bound observation compilation.
- Per-finding adjudication with derived detection counts and a two-grader comparison
  report that preserves disagreement and unresolved findings.
- [Container-isolated recorded evaluation](docs/ISOLATED_EVALUATION.md), with no
  host mounts/network, bounded pipes/resources and real containment probes in CI.
- [Detached cleanup watchdog](docs/CONTAINER_LIFECYCLE.md) with a readiness gate,
  independent lifetime, private receipts and launcher-SIGKILL recovery tests.
- [Request-bound provider grants and private IPC](docs/PROVIDER_BROKER.md), with
  fixture-tested container roundtrips, host-only spending, disconnect cancellation,
  assignment audit chains and read-only crash inventory.
- [Brokered evaluation conformance artifacts](docs/BROKERED_EVALUATION.md) binding
  strict critiques or terminal failures to audit, assignment, latency and conservative
  spend state, plus exact-batch inert assembly; these artifacts remain non-scoreable.
- A fixture-tested [OpenAI conformance request contract](docs/OPENAI_CONFORMANCE.md)
  using blinded input and strict structured `Critique` output, plus an explicit
  one-assignment CLI whose provider and container boundaries are fixture-substituted.
- An offline [one-assignment calibration execution decision](docs/OPENAI_CALIBRATION_EXECUTION.md)
  that fully reverifies the frozen campaign, binds an independent signature to one
  exact request and schema-2 spend envelope, then atomically consumes that authority
  into held worst-case spend without credential access or provider dispatch.
- A guarded [held-reservation credentialed transport](docs/MILESTONE_91_REVIEW.md)
  that rechecks an exact held entry before token counting and generation, then settles
  that same entry at most once.
- [Ed25519 adjudication authentication](docs/ADJUDICATION_AUTHENTICATION.md)
  binding exact human grades to an independently supplied public-key trust policy.
- [Dual authenticated grading](docs/DUAL_GRADE_RESOLUTION.md) that preserves both
  signed originals and requires a disjoint signed resolver to exactly cover every
  conflict. Its output remains deliberately disconnected from scoring promotion.
- [Dual-lineage observation compilation](docs/DUAL_LINEAGE_OBSERVATIONS.md) that
  reverifies the complete private source chain into a distinct schema rejected by
  legacy scoring.
- [Dual-lineage scoring](docs/DUAL_LINEAGE_SCORING.md) that recomputes provenance,
  shares the registered statistical formulas, and always denies promotion.
- A [pre-registered routing study protocol](docs/ROUTING_STUDY_PROTOCOL.md) that
  seals label-free feature bins, role floors, fallbacks, selection rules, and
  holdout discipline without reading outcomes or granting activation authority.
- [Profile-aware calibration scoring](docs/ROUTING_CALIBRATION.md) from fully
  reverified dual-grade lineage, with confidence correction across all sealed
  profiles and no holdout outcome or route-selection input.
- [Calibration-only candidate policy freezing](docs/ROUTING_POLICY_FREEZE.md) that
  enforces role floors and complete-cost evidence before applying the sealed
  cost/latency/digest objective, while remaining unusable for runtime activation.
- [One-attempt frozen-policy holdout evaluation](docs/ROUTING_HOLDOUT.md) with an
  exclusive local claim, full calibration and holdout lineage recomputation,
  under-routing and cost/latency-regret measurement, and literal promotion denial.
- [Independently authenticated routing promotion](docs/ROUTING_PROMOTION.md) with
  pre-holdout policy-level thresholds, full evidence recomputation, signer separation,
  and continued runtime-activation denial.
- [Short-lived routing activation eligibility](docs/ROUTING_ACTIVATION_ELIGIBILITY.md)
  from three distinct signatures over exact route policy, operational attestations,
  and revocation control, with no model substitution or runtime/configuration power.
- A pinned [monotonic routing-control anchor and read-only runtime preflight](docs/ROUTING_RUNTIME_PREFLIGHT.md)
  that reject older-message replay and preserve revocations while granting no
  dispatch, activation, or configuration authority.
- [Prompt-only Agent Skills packages](docs/SKILLS.md) with bounded YAML parsing,
  whole-package digests, immutable progressive loading, non-shadowing source
  identities, explicit project opt-in, and replay-verified run provenance.
- [Paired persona-skill evaluation](docs/SKILL_EVALUATION.md) that seals exact
  prompt-only controls, consumes holdout once, reverifies dual-human-grade lineage,
  and reports simultaneous group bounds without promotion or activation authority.
- [Independently signed persona-skill promotion](docs/SKILL_PROMOTION.md) that
  recomputes both split lineages, enforces evaluator/authority separation and expiry,
  and issues evidence readiness without configuration or runtime authority.
- [Deterministic retained skill-package archives](docs/SKILL_ARCHIVES.md) that
  preserve every validated byte, rebuild semantic identity without extraction, and
  literally deny installation, activation, and configuration authority.
- [Current skill-release evidence](docs/SKILL_RELEASE_EVIDENCE.md) that recomputes
  both evaluation lineages and binds an exact archive to its still-valid signed
  promotion receipt without granting deployment authority.
- [Authenticated skill-release control](docs/SKILL_RELEASE_CONTROL.md) with an
  independent expiring allow/revoke signature, exact retained rollback nomination,
  and a release-scoped monotonic local anchor that grants no deployment power.
- [Transactional skill quarantine staging](docs/SKILL_QUARANTINE_STAGING.md) that
  reauthenticates the full latest-controlled lineage, materializes exact bytes behind
  a crash-conservative atomic commit, and remains disconnected from configuration.
- [One-use skill installation authorization](docs/SKILL_INSTALLATION_AUTHORIZATION.md)
  that binds an independent signature to one exact staged package, target, latest
  control entry, and private claim ledger without performing installation or activation.
- [Atomic inert skill installation](docs/SKILL_ATOMIC_INSTALLATION.md) that consumes
  that authority under the revocation guard, reconstructs exact bytes behind a
  durable content-addressed commit, and exposes conservative read-only recovery.
- [Atomic skill default selection](docs/SKILL_DEFAULT_SELECTION.md) with an independent
  signature, exact prior-pointer compare-and-swap, and one transaction for immutable
  consumption plus pointer mutation; no runtime reads it.
- [Post-selection skill health and drift evidence](docs/SKILL_HEALTH_EVIDENCE.md)
  with distinct policy/observer signatures, exact pointer and control binding, and
  recomputed empirical thresholds; the expiring result grants no dispatch authority.
- [One-use skill runtime preparation](docs/SKILL_RUNTIME_PREFLIGHT.md) that rebuilds
  exact installed prompt bytes and atomically burns signed authority into a worst-case
  shared-spend reservation while issuing no broker grant or provider request.
- [Guarded skill runtime broker admission](docs/SKILL_RUNTIME_ADMISSION.md) that
  recomputes the complete routing and skill lineages and claims the existing held
  reservation in one pinned private store while still issuing no grant or request.
- [Independent skill runtime dispatch authority](docs/SKILL_RUNTIME_DISPATCH_AUTHORITY.md)
  that signs and consumes one exact admission under fresh guards while remaining a
  non-bearer, non-sending prerequisite to future broker-grant issuance.
- [Ephemeral skill runtime broker grant](docs/SKILL_RUNTIME_BROKER_GRANT.md) that
  durably consumes that claim into one memory-only, maximum-30-second bearer with
  single redemption while remaining disconnected from provider transport.
- [Skill runtime provider transaction](docs/SKILL_RUNTIME_PROVIDER_TRANSACTION.md)
  that commits an fsynced before-send marker, invokes one exact zero-retry OpenAI
  transport request, and conservatively settles the existing reservation.
- [Skill runtime response publication](docs/SKILL_RUNTIME_RESPONSE_PUBLICATION.md)
  that atomically retains exact private provider bytes while exposing only a
  content-verified, reasoning-free result bound to settled runtime lineage.
- [Skill runtime OpenAI conformance attestation](docs/SKILL_RUNTIME_CONFORMANCE.md)
  that authenticates one trusted observer's narrow, freshness-bounded claim against
  an exact verified publication without granting quality or activation authority.
- [Brokered evaluation conformance receipt](docs/EVALUATION_CONFORMANCE.md) that
  authenticates one pre-registered successful OpenAI probe against its exact blinded
  assignment, audit, and settled ledger without enabling batch conversion or scoring.
- [No-send OpenAI conformance ceremony](docs/CONFORMANCE_CEREMONY.md) that prepares
  and rechecks the exact request, spend scope, fresh audit identity, observer roster,
  SDK allowlist, and time window before the paid-capable process reads an API key.
- [Independent signed conformance authorization](docs/EVALUATION_CONFORMANCE_AUTHORIZATION.md)
  that binds one short-lived blinded transfer and maximum spend to the exact ceremony
  policy before credential access, while keeping the authorizer separate from observers.
- [Skill runtime publication witness](docs/SKILL_RUNTIME_PUBLICATION_WITNESS.md)
  that signs a rolling hash-only history checkpoint for separately retained rollback
  and divergence detection without exporting response or result content.
- [Skill runtime aggregate billing evidence](docs/SKILL_RUNTIME_BILLING_EVIDENCE.md)
  that independently authenticates complete exclusive OpenAI usage/cost aggregates
  against exact conformance and publication lineage without claiming response-level
  attribution, invoice finality, refund authority, quality, or activation.
- [Credential-isolated OpenAI billing collection](docs/SKILL_RUNTIME_BILLING_COLLECTION.md)
  that explicitly reads and strictly retains bounded Admin API pages without sending
  a model request or overstating daily exclusivity and response-level attribution.
- NDJSON result output, typed code, coverage, CI, package and container delivery.

## Bounded analytical conversations

`mos analysis-demo` answers a synthetic metric through a real local MCP server.
The opt-in `analysis-run` command adds OpenAI tool conversations with a read-only
profile, revision-bound metrics and whole-run spending reservations. Answers now
use checked cell references, with a SQL/result trail and optional private
[artifacts and captured-result exports](docs/ANALYSIS_EVIDENCE.md). The
[offline evaluator](docs/ANALYSIS_EVALUATION.md) grades those bundles against reviewed
SQL/source/cell expectations and counts missing or failed runs. An explicit
[raw-data baseline](docs/ANALYSIS_RAW_BASELINE.md) uses source discovery and SQL
without the promoted catalog: `mos analysis-demo --context-mode raw`. Try
`mos analysis-eval-demo --result-root /absolute/private/directory`. A
[frozen comparison schedule](docs/ANALYSIS_COMPARISON_SCHEDULE.md) balances arm order
and checks recorded timing; `mos analysis-comparison-demo --result-root /absolute/private/directory`
exercises both arms. The optional
[Parquet case integration](docs/ANALYSIS_PARQUET_CASES.md) also checks six
nonconstant cases through the real data-mcp server.
[Parameterized metric integration](docs/ANALYSIS_METRIC_PARAMETERS.md) adds checked
date-window calls using the same controller. See the
[configuration and limits](docs/ANALYSIS.md) and
[verification record](docs/ANALYSIS_VERIFICATION.md).

## Boundaries and limitations

The OpenAI adapter and paid-capable conformance CLI are tested against captured
response shapes. One independently authorized and observed credentialed
`gpt-5.6-luna` conformance assignment completed on 2026-09-07; it verifies only that
exact blinded request and does not establish provider authorship, billing, batch
conformance, or quality. The readiness command checks only model metadata; model
availability, billing, and endpoint permissions remain account-dependent. The
synthetic Responses canary also completed one operator-signed live generation that
day, verifying only its exact fixed request; billing and future availability remain
unverified. Live critic fan-out and judging are not wired yet. The explicit local
MCP adapter can execute configured data tools. There is no live sandbox executor,
shell tool, Git checkout, test execution, publisher, or TUI. The fixture agent tool
remains a bounded in-memory lookup.
Byte and provider-token accounting are separate. The explicit one-prompt and analytical commands use separate spending controllers.
Both rely on operator-reviewed rates and provider limits and bound participating
runs sharing one local ledger. It does not provide
account-wide enforcement or enable the unimplemented live evaluation executor.

Recorded workflows open only user-supplied input files. Explicit MCP commands
also launch the configured executable, which can access its configured sources.
Unknown schema fields are rejected;
repository `.mos-eisley/config.toml` and `AGENTS.md` have no authority in this milestone.
The controller and parent directories are trusted. Symlink rejection applies to
the final file component, not to every ancestor; this is not a host sandbox.

Skills are inert prompt content. Scripts, tool bundles, `allowed-tools`, remote
registries, persistent trust, automatic discovery, SecretRef, and doctor fixes are
not implemented. Archives retain exact bytes but provide no authorship, extraction,
installation, configuration, or activation authority. Release evidence now proves
that retained bytes match current promotion evidence. Independent release control
can revoke that exact artifact and nominate exact rollback bytes, but still cannot
deploy either package. Its anchor resists older-message replay, not owner-driven
whole-database rollback. Exact bytes can be transactionally staged in an inert
private quarantine store, but the store is not an install or runtime search path.
An independent signer can now authorize one exact installation target, and a private
claim ledger can burn that authority at most once while holding the release-control
guard. The atomic installer can materialize those exact bytes into a separate private
content-addressed store. A second independent signer can authorize one exact atomic
default-pointer transition, but no runtime reads that pointer and no activation occurs.
Installation recovery is inspection-only; store deletion, rollback, or cloning remains
an owner-controlled replay risk.
Skill quality and persona changes remain evaluation-gated.

Run files contain the supplied brief and recorded responses. Keep the output root
private. File hashes detect accidental changes, not a malicious owner who can
replace the manifest. Recorded agent runs fsync boundary events as they happen, but
the journal contains hashes and status—not a standalone full transcript. Incomplete
runs lack a valid manifest and cannot be replayed. The original one-prompt live runs preserve full canonical
responses for inspection but cannot replay a provider execution. Retention is manual.
The analytical command defaults to memory-only content and emits its result on
stdout. Explicit retention consent enables private result bundles and exports;
the ledger still contains only spending metadata.

The [planned storage contract](docs/mos-eisley-plan.md#17-run-artifacts-and-telemetry)
keeps retained data under one user's ownership while allowing user-configured local
or cloud backends. It prohibits cross-user aggregation, including model-selection
statistics, and automatic retrieval of full prior conversations in fresh sessions.
The first [user/project memory implementation](docs/CONVERSATION_MEMORY.md)
adds explicitly curated facts and preferences with separate scopes and CLI controls;
explicit in-session refresh is available; natural-language saving remains planned.
Remote storage adapters and comprehensive user-isolation enforcement are not yet
implemented; the current private-file behavior is not a claim of those guarantees.

The [planned storage contract](docs/mos-eisley-plan.md#17-run-artifacts-and-telemetry)
keeps retained data under one user's ownership while allowing user-configured local
or cloud backends. It prohibits cross-user aggregation, including model-selection
statistics, and automatic reuse of prior conversational content in fresh sessions.
Remote storage adapters and comprehensive user-isolation enforcement are not yet
implemented; the current private-file behavior is not a claim of those guarantees.

See the [project brief](PROJECT_BRIEF.md),
[integrated project review](docs/PROJECT_REVIEW_2026-09-08.md),
[revised adaptive routing design](docs/adaptive-reasoning-routing.md),
[revised adversarial-loop plan](docs/adversarial-review-loop-project-plan.md),
[OpenAI provider ADR](docs/adr/0003-openai-first-provider.md),
[OpenAI model readiness](docs/OPENAI_READINESS.md),
[OpenAI Responses canary](docs/OPENAI_RESPONSES_CANARY.md),
[one-assignment OpenAI calibration execution](docs/OPENAI_CALIBRATION_EXECUTION.md),
[empirical routing ADR](docs/adr/0004-empirical-difficulty-routing.md),
[evaluation foundation](docs/EVALUATION.md),
[routing study protocol](docs/ROUTING_STUDY_PROTOCOL.md),
[routing calibration](docs/ROUTING_CALIBRATION.md),
[candidate policy freezing](docs/ROUTING_POLICY_FREEZE.md),
[frozen-policy holdout evaluation](docs/ROUTING_HOLDOUT.md),
[routing promotion](docs/ROUTING_PROMOTION.md),
[routing activation eligibility](docs/ROUTING_ACTIVATION_ELIGIBILITY.md),
[routing runtime preflight](docs/ROUTING_RUNTIME_PREFLIGHT.md),
[prompt-only skills](docs/SKILLS.md),
[retained skill archives](docs/SKILL_ARCHIVES.md),
[skill-release evidence](docs/SKILL_RELEASE_EVIDENCE.md),
[authenticated skill-release control](docs/SKILL_RELEASE_CONTROL.md),
[transactional skill quarantine staging](docs/SKILL_QUARANTINE_STAGING.md),
[one-use skill installation authorization](docs/SKILL_INSTALLATION_AUTHORIZATION.md),
[atomic inert skill installation](docs/SKILL_ATOMIC_INSTALLATION.md),
[atomic skill default selection](docs/SKILL_DEFAULT_SELECTION.md),
[post-selection skill health evidence](docs/SKILL_HEALTH_EVIDENCE.md),
[one-use skill runtime preparation](docs/SKILL_RUNTIME_PREFLIGHT.md),
[guarded skill runtime broker admission](docs/SKILL_RUNTIME_ADMISSION.md),
[independent skill runtime dispatch authority](docs/SKILL_RUNTIME_DISPATCH_AUTHORITY.md),
[ephemeral skill runtime broker grant](docs/SKILL_RUNTIME_BROKER_GRANT.md),
[skill runtime provider transaction](docs/SKILL_RUNTIME_PROVIDER_TRANSACTION.md),
[skill runtime response publication](docs/SKILL_RUNTIME_RESPONSE_PUBLICATION.md),
[skill runtime OpenAI conformance attestation](docs/SKILL_RUNTIME_CONFORMANCE.md),
[skill runtime publication witness](docs/SKILL_RUNTIME_PUBLICATION_WITNESS.md),
[skill runtime aggregate billing evidence](docs/SKILL_RUNTIME_BILLING_EVIDENCE.md),
[prompt-only skills adversarial review](docs/MILESTONE_22_REVIEW.md),
[retained skill archives adversarial review](docs/MILESTONE_25_REVIEW.md),
[skill-release control adversarial review](docs/MILESTONE_27_REVIEW.md),
[skill quarantine-staging adversarial review](docs/MILESTONE_28_REVIEW.md),
[skill installation-authorization adversarial review](docs/MILESTONE_29_REVIEW.md),
[atomic skill-installation adversarial review](docs/MILESTONE_30_REVIEW.md),
[atomic skill-default adversarial review](docs/MILESTONE_31_REVIEW.md),
[skill health-evidence adversarial review](docs/MILESTONE_32_REVIEW.md),
[skill runtime-preparation adversarial review](docs/MILESTONE_33_REVIEW.md),
[runtime broker-admission adversarial review](docs/MILESTONE_34_REVIEW.md),
[runtime dispatch-authority adversarial review](docs/MILESTONE_35_REVIEW.md),
[runtime broker-grant adversarial review](docs/MILESTONE_36_REVIEW.md),
[runtime provider-transaction adversarial review](docs/MILESTONE_37_REVIEW.md),
[runtime response-publication adversarial review](docs/MILESTONE_38_REVIEW.md),
[runtime conformance-attestation adversarial review](docs/MILESTONE_39_REVIEW.md),
[publication-history witness adversarial review](docs/MILESTONE_40_REVIEW.md),
[aggregate billing-evidence adversarial review](docs/MILESTONE_41_REVIEW.md),
[billing-collector adversarial review](docs/MILESTONE_42_REVIEW.md),
[failure-preserving broker-assembly review](docs/MILESTONE_43_REVIEW.md),
[evaluation conformance-receipt review](docs/MILESTONE_44_REVIEW.md),
[OpenAI model-readiness adversarial review](docs/MILESTONE_48_REVIEW.md),
[OpenAI response-encoding adversarial review](docs/MILESTONE_49_REVIEW.md),
[synthetic Responses canary adversarial review](docs/MILESTONE_50_REVIEW.md),
[conformance request-boundary adversarial review](docs/MILESTONE_51_REVIEW.md),
[live blinded-conformance adversarial review](docs/MILESTONE_52_REVIEW.md),
[registry-bound model-readiness adversarial review](docs/MILESTONE_53_REVIEW.md),
[OpenAI conformance-campaign commitment review](docs/MILESTONE_54_REVIEW.md),
[calibration execution-decision adversarial review](docs/MILESTONE_89_REVIEW.md),
[calibration execution-consumption adversarial review](docs/MILESTONE_90_REVIEW.md),
[held-reservation credentialed-transport adversarial review](docs/MILESTONE_91_REVIEW.md),
[OpenAI live-conformance exit gate](docs/OPENAI_LIVE_CONFORMANCE_GATE.md),
[blinded evaluation review](docs/MILESTONE_5_REVIEW.md),
[statistical design](docs/STATISTICAL_DESIGN.md),
[threat model](docs/THREAT_MODEL.md), and [roadmap](docs/ROADMAP.md).

## Development and delivery

```sh
make check          # lint, format, strict typing, tests, coverage, build, wheel smoke
make audit          # network-backed dependency audit
make container      # build pinned image and smoke-test as non-root
```

CI also verifies the runtime dependency export and builds the image. No GitHub
repository or published release is created by local setup. Template ownership,
proprietary license, action pins, Dependabot and release controls are inherited.

```sh
docker run --rm --network none --read-only --tmpfs /tmp mos-eisley:local --help
docker run --rm --network none --read-only --tmpfs /tmp \
  mos-eisley:local demo --output /tmp/runs --json
```

The second command intentionally exits 1; its temporary artifacts disappear when
the container exits. Mount a private writable output directory to retain runs.
