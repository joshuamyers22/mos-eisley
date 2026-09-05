# Mos Eisley

A foundation for independent, multi-provider adversarial review of code changes.
**Current maturity: offline agent foundation.** All responses and tool values come
from explicit recorded fixtures. This version cannot assess new code using a live
model or touch the host through model-selected tools.

Generated from the `python-cli` archetype of
[production-project-template](https://github.com/joshuamyers22/production-project-template)
at commit `3d467040ba760efe9795f67f07d5a2ccf364282b`.

## Quick start

Requires Python 3.12+ and uv; supported development targets are macOS and Linux.
No credentials or external services are required at runtime.

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
- NDJSON result output, typed code, coverage, CI, package and container delivery.

## Boundaries and limitations

There is no live provider, machine-capable tool, sandbox backend, shell, Git
checkout, test execution, publisher, MCP, or TUI yet. The only agent tool reads a
bounded in-memory fixture. Provider names in fixtures are labels, not proof of real
model diversity. Judge order is deterministic by finding hash; randomized bias
experiments are deferred. Byte accounting is a conservative serialization bound,
not provider token, price, or context-window accounting.

Only user-supplied input files are opened. Unknown schema fields are rejected;
repository `.mos-eisley/config.toml` and `AGENTS.md` have no authority in this milestone.
The controller and parent directories are trusted. Symlink rejection applies to
the final file component, not to every ancestor; this is not a host sandbox.

Run files contain the supplied brief and recorded responses. Keep the output root
private. File hashes detect accidental changes, not a malicious owner who can
replace the manifest. Recorded agent runs fsync boundary events as they happen, but
the journal contains hashes and status—not a standalone full transcript. Incomplete
runs lack a valid manifest and cannot be replayed. Retention is manual.

See the [project brief](PROJECT_BRIEF.md), [agent protocol ADR](docs/adr/0002-canonical-agent-protocol.md),
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
