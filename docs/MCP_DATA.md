# Local data MCP client

Mos Eisley can launch an explicitly configured stdio server, discover selected
tools, and read/write data through them. The first target is
[data-mcp](https://github.com/joshuamyers22/data-mcp): HDD Parquet and local/cloud
PostgreSQL, plus Ana Lite's promoted semantic manifest and named metrics.

Remote HTTP connections and OAuth are planned as
[M11A and M11B](mos-eisley-plan.md#133-remote-mcp-connections--planned-m11a-and-m11b):
HTTP with token authentication first, then OAuth login and credential lifecycle.
The current configuration remains local stdio only. Schema expansion and paid
analytical-agent integration have separate acceptance gates.

## Configure and use

Install both projects with `uv sync --frozen --dev`. In data-mcp, copy
`config.example.toml` to `config.toml`, then set actual mounted roots and database
environment references. The server's `--check` validates configuration without
connecting to a database. PostgreSQL DDL and role administration stay outside MCP.

Copy [the read/write example](../examples/mcp-data-rw.json) to a private location.
It uses Josh's `/Users/josh/Projects/data-mcp` checkout; change absolute executable,
working-directory and server-config paths for another installation. Set the named
environment variables in the launching process. Remove unused database sources
and their environment references for a Parquet-only installation.

```sh
uv run --frozen mos mcp-list --config /absolute/path/mcp-data-rw.json
uv run --frozen mos mcp-call --config /absolute/path/mcp-data-rw.json \
  --call examples/mcp-list-sources.json
```

The config contains tool names classified by the operator as `read` or `write`.
Write grants require `allow_writes: true`. This enables the server's Parquet
create/append/replace and PostgreSQL INSERT/UPDATE/DELETE tools; the server's own
root permissions, database grants and transactional restrictions also apply.
Tools absent from the config cannot be dispatched, even if discovery advertises
them as read-only. Every configured tool must exist and have a supported schema.

A call file uses the canonical tool-call format. For example, after inspecting
the schema of an existing file:

```json
{
  "id": "query-1",
  "name": "query_parquet",
  "args": {
    "root": "raw",
    "paths": ["example/items.parquet"],
    "sql": "SELECT COUNT(*) AS row_count FROM data"
  }
}
```

Use `write_parquet` with `root`, `path`, `rows_json` and an explicit `mode`; use
`execute_postgres` with `source` and `sql`. Call files are opened as bounded regular
files and reject final-component symlinks. Command output is JSON, including source
data for a successful call; protect terminal capture and output redirects. This
command creates no transcript or query-history files. Exit 0 means discovery or
the call succeeded; exit 2 means invalid input, tool error or infrastructure failure.

## Ana Lite analysis profile

Copy data-mcp's `config.ana.example.toml` to `config.ana.toml`. Update its mounted
root, promoted ontology path and read-role DSN reference. Use
[the analysis client example](../examples/mcp-data-analysis.json), which grants
only discovery, SELECT and semantic tools. Its server must use
`access_mode = "analysis"`; that profile independently omits and denies mutations.

Call `get_semantic_context`, inspect the definitions, then call `run_metric` with
`name` and the returned `revision`. Stale revisions and incomplete governed
results fail in data-mcp. Returned timestamps and definition hashes do not identify
a source snapshot. Golden evaluation cases, proposals and learning remain separate
from the promoted manifest; connecting the client does not enable automatic learning.

## Agent integration

`connect_mcp(config)` is an async context manager yielding an `MCPDispatcher` that
implements `core.ports.ToolDispatcher`. It can be passed directly to
`run_agent(config, registry, client, dispatcher, journal)`. Keep the entire agent
run inside that context. Tests execute a two-turn canonical agent with an actual
stdio server and a fixture model.

The existing paid `openai-run`, conformance and critic/judge workflows do not
accept MCP configuration. Connecting source data to a paid model also requires
multi-turn spending/transfer admission and retention decisions in those workflows.
This change provides the data connection and agent port without claiming those
provider workflows are implemented.

## Limits and failure behavior

- Only explicit local stdio commands are supported. Configuration is trusted
  operator input; it executes code with the user's privileges. This adapter is
  **not a process or network sandbox**. A local server can reach cloud PostgreSQL.
  No automatic repository discovery, remote MCP URL, OAuth or critic registration
  occurs. There are no sampling, elicitation or filesystem-roots callbacks.
- Environment values pass only for named variables, all of which must be set.
  The SDK's baseline environment keys are explicitly blanked unless allowlisted.
  Keep credentials in those variables, never command arguments or committed files.
  Child stderr is discarded and error diagnostics omit raw server messages.
- The SDK owns negotiation and subprocess cleanup. Protocol requests and tool
  calls have finite deadlines; catalog discovery also has an overall deadline.
  Timeout, cancellation, malformed or oversized results disable further dispatch
  in that session. There are no automatic tool retries, including SDK
  input-required continuations. Call IDs cannot be reused within a session.
  A write can commit before an error, timeout or oversized response: inspect the
  target before issuing a new call. New CLI invocations do not deduplicate IDs.
- Discovery is limited to 16 pages, 256 advertised tools, 64 selected tools and
  256 KiB per decoded catalog page. Input schemas use the canonical subset;
  unsupported constraints, references and unions fail registration. Omitted
  title/default metadata and stricter closed objects appear in `schema_changes`.
  Original input constraints are validated before dispatch. The SDK validates
  structured output against declared output schemas; references are rejected
  before calling to prevent schema retrieval. Binary/resource content is unsupported.
- The default 4,000-byte result limit includes the entire canonical result,
  including JSON escaping. Structured and textual content are retained, so the
  same server data may appear twice. No successful result is silently shortened.
  Narrow SELECTs and reduce data-mcp's row/result limits for exploratory queries.
  Increase the client limit only within the selected agent's resolved output
  reserve (4,000/8,000/12,000 bytes by default for low/medium/high effort).
  The server's default 256 KiB is larger than these agent budgets.
- These application limits apply after SDK decoding. They are **not a hard
  memory bound on hostile wire traffic**. The named server executable and its
  dependencies must be trusted. Process isolation and protocol-frame byte limits
  remain necessary before supporting untrusted servers.
- Source values, descriptions and semantic notes remain untrusted content.
  Server instructions and annotations do not become operator policy. These tools
  are not a replacement for database grants or source-level authorization.

## Verification

`make check` covers real stdio lifecycle, environment filtering, canonical-agent
dispatch, argument validation, pagination, missing tools, schema rejection,
deadlines, cancellation, result bounds and redacted diagnostics.

Optional cross-repository tests run against an installed data-mcp environment:

```sh
export DATA_MCP_TEST_PYTHON=/absolute/path/data-mcp/.venv/bin/python
# Optional: DATA_MCP_TEST_DSN must name a disposable PostgreSQL database.
uv run --frozen python -m unittest discover -s tests -p test_mcp_data_integration.py
```

The Parquet test creates temporary files and a promoted synthetic metric. The
PostgreSQL test creates and removes a unique schema and verifies commits across
separate MCP server sessions. Ordinary CI runs the self-contained MCP tests;
cross-repository tests skip when the explicitly installed server is unavailable.
See [verification evidence](MCP_DATA_VERIFICATION.md) for the executed scope.

The implementation uses the
[official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk),
locked in `uv.lock`; SDK imports remain outside the canonical core.
