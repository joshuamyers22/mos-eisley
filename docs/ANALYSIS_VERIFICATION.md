# Analytical integration verification — 2026-09-09

Scope: `feat/bounded-mcp-analysis`, stacked above the MCP schema compatibility
branch. The implementation is opt-in and uses synthetic provider responses for all
checks recorded here. No provider key, paid generation, native credential-vault
login or production data source was used.

Acceptance invariants and evidence:

- `tests/test_analysis.py`: real stdio fixture conversations answer, clarify and
  report unavailable input; unknown writes attempted after reading an injected
  source note do not become successful evidence. Tool profiles reject mutation
  grants; metric input/output revisions must match context. Truncated, malformed,
  oversized and context-only evidence cannot support a completed answer.
- The same suite exercises turn/tool/aggregate-byte/pending-call limits and whole-run
  cancellation. CLI diagnostics omit source content, and demos create no artifacts.
- `tests/test_analysis_spending.py`: reserve before dispatch; settle the sum of
  multiple responses; retain full exposure on cancellation and unknown usage;
  block on pricing violations; reject changed tools, model/tier/storage settings;
  enforce aggregate tokens and turns; serialize admission across independent ledger
  instances; reject overlapping dispatch and finishing an in-flight request.
- The synthetic live CLI test uses the real OpenAI request/response adapter and a
  real local MCP session for two model turns. It verifies receipts, missing-key
  settlement and absence of content artifacts without an external provider call.
- `tests/test_mcp_data_integration.py` extends the existing optional Parquet fixture
  to complete an analytical conversation through the installed data-mcp package,
  using its promoted ontology, server analysis profile and actual SQL result.
- `tools/smoke_package.py` runs the demo and analytical tests from an installed wheel
  outside the checkout, alongside existing OAuth and schema tests.

Results: all 24 focused analytical tests pass. `make check` passes Ruff, strict
Pyright, 671 tests (two optional cross-repository skips), 88% branch-inclusive
coverage, locked-export verification, package build and installed-wheel smoke.
The wheel test runs 57 analytical/OAuth/schema tests outside the checkout, all
passing. The separate installed-data-mcp Parquet integration passes; its PostgreSQL
case skips because no disposable DSN was supplied for this milestone. After adding
that optional conversation check, lint, format and strict typing also pass.
The current change adds no dependencies.

Limits of the evidence: scripted conversations test controller behavior, not model
quality or injection immunity. Result IDs/hashes do not independently verify numerical
claims, source snapshots or replayability. Paid conformance and a production account
mapping are not established by these tests. See [operator contract](ANALYSIS.md).
