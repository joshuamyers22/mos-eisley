# Mos Eisley

A foundation for independent, multi-provider adversarial review of code changes.
**Current maturity: live-provider preview.** Recorded review remains the default;
an explicit one-prompt OpenAI command is available. This version does not yet run
the adversarial critic/judge workflow live or expose host tools to a model. It can
plan and score offline model/effort evaluations, but automatic routing is disabled.

Generated from the `python-cli` archetype of
[production-project-template](https://github.com/joshuamyers22/production-project-template)
at commit `3d467040ba760efe9795f67f07d5a2ccf364282b`.

## Quick start

Requires Python 3.12+ and uv; supported development targets are macOS and Linux.
The recorded commands require no credentials or external services.

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

Review exit codes: **0** accept; **1** revise/reject; **2** invalid input or
infrastructure failure. Replay exits **0** when the recorded result reproduces,
even if that result is revise/reject. `mos` is a short alias for `mos-eisley`.

## Implemented

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
- Opt-in `openai-run` with a 64,000-byte prompt bound, 4,096-token output ceiling,
  one-request limit, no tools, generic diagnostics and content-verified artifacts.
- Reviewed pricing policies, pre-generation token-count reservations and private
  spending receipts; uncertain outcomes retain the full reservation without retry.
- A non-streaming OpenAI HTTP client that bounds decoded response bodies before SDK
  JSON construction, including compressed and chunked responses.
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
  strict critiques to response, audit, assignment, usage, latency and settled spend;
  these artifacts are explicitly non-scoreable.
- A fixture-tested [OpenAI conformance request contract](docs/OPENAI_CONFORMANCE.md)
  using blinded input and strict structured `Critique` output, plus an explicit
  one-assignment CLI whose provider and container boundaries are fixture-substituted.
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
- NDJSON result output, typed code, coverage, CI, package and container delivery.

## Boundaries and limitations

The OpenAI adapter and paid-capable conformance CLI are tested against captured
response shapes but have not completed a credentialed conformance run in this
repository. Model availability depends on
account access. Live critic fan-out and judging are not wired yet. There is no
machine-capable tool, live sandbox executor, shell, Git checkout, test execution,
publisher, MCP, or TUI. The fixture agent tool remains a bounded in-memory lookup.
Byte and provider-token accounting are separate. Spending admission applies only
to the explicit one-prompt command, relies on operator-reviewed rates and provider
limits, and bounds participating runs sharing one local ledger. It does not provide
account-wide enforcement or enable the unimplemented live evaluation executor.

Only user-supplied input files are opened. Unknown schema fields are rejected;
repository `.mos-eisley/config.toml` and `AGENTS.md` have no authority in this milestone.
The controller and parent directories are trusted. Symlink rejection applies to
the final file component, not to every ancestor; this is not a host sandbox.

Run files contain the supplied brief and recorded responses. Keep the output root
private. File hashes detect accidental changes, not a malicious owner who can
replace the manifest. Recorded agent runs fsync boundary events as they happen, but
the journal contains hashes and status—not a standalone full transcript. Incomplete
runs lack a valid manifest and cannot be replayed. Live runs preserve full canonical
responses for inspection but cannot replay a provider execution. Retention is manual.

See the [project brief](PROJECT_BRIEF.md),
[OpenAI provider ADR](docs/adr/0003-openai-first-provider.md),
[empirical routing ADR](docs/adr/0004-empirical-difficulty-routing.md),
[evaluation foundation](docs/EVALUATION.md),
[routing study protocol](docs/ROUTING_STUDY_PROTOCOL.md),
[routing calibration](docs/ROUTING_CALIBRATION.md),
[candidate policy freezing](docs/ROUTING_POLICY_FREEZE.md),
[frozen-policy holdout evaluation](docs/ROUTING_HOLDOUT.md),
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
