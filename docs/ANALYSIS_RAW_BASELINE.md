# Raw-data analytical baseline

Set `context_mode: "raw"` to run the analytical controller without promoted
semantic tools. It starts with `list_sources`, exposes only configured raw read
tools, and uses a prompt for source/schema discovery and SQL. The default remains
`promoted`; missing semantic context never silently switches modes.

```sh
uv run --frozen mos analysis-demo --context-mode raw
```

This scripted synthetic MCP conversation returns a checked total of 42, with
`context_mode: "raw"` and `semantic_revision: null`. It demonstrates the execution
path; it does not measure model quality or validate a business metric.

## Configure the control arm

Start from `examples/analysis-openai-raw.json` and `examples/mcp-data-raw.json`.
Use the same reviewed question, provider/model, effort, budgets, retention policy
and source fixture as the promoted arm. Copy data-mcp's
`config.ana-raw.example.toml` to a private `config.ana-raw.toml`, adapt source paths
and credential references, and keep `access_mode="analysis"` with no `ontology_file`.
The raw server should expose the same source objects under the same read-only
permissions as the promoted server. Remove unused PostgreSQL sources and environment
references for a Parquet-only run. Cloud sources still require the existing TLS
and role configuration.

Raw profiles require `list_sources` and allow only this subset of data-mcp's tools:

- `list_sources`
- `list_parquet`, `describe_parquet`, `query_parquet`
- `list_postgres_tables`, `describe_postgres`, `query_postgres`

Select only the needed tools. Semantic tools (`get_semantic_context`, `list_metrics`,
`run_metric`), mutation tools and custom tool names reject the profile before MCP
connection; the paid path validates it before reading the provider key or reserving
spending. An attempted out-of-profile call is also denied before dispatch and
counts against the tool budget. This narrow raw profile is for a comparable control
arm; ordinary user-configured MCP connections retain their existing extensibility
and read/write grants.

Run `analysis-run` with the raw config and MCP config using the same
[transfer, ledger and retention controls](ANALYSIS.md#configure-a-live-run). Raw mode
shares the controller, whole-run reservation, concurrency admission, deadlines,
turn/tool/token/byte limits, cancellation behavior, returned-cell validation and
private artifact/export implementation. Both modes count one bootstrap tool call.
A missing/failed bootstrap stops before generation. Raw mode makes no automatic
semantic fallback and does not invent a revision for source discovery.

## Record and compare

New raw artifacts explicitly identify their context mode. Offline verification
requires `list_sources` as the first accepted call, rejects accepted nonraw tools
and requires a null semantic revision. Promoted artifacts still require promoted
context and its revision. Known source/schema discovery tools cannot provide
numeric answer claims even if they return table-shaped metadata.

Default promoted fields remain omitted from canonical serialization, preserving
existing configuration, suite and result hashes. Existing promoted metric/query
bundles still verify/export with the new reader. Metadata-only numeric claims now
reject in both modes. A raw bundle requires this updated reader;
older clients may reject its explicit mode/null revision.

In an [evaluation suite](ANALYSIS_EVALUATION.md), give the raw arm
`context_mode: "raw"` and `semantic_revision: null`. Use its own run identity:
`run_identity(config, definitions)` after
`analysis_mcp_config(mcp, config.context_mode)` and tool discovery. The resolved
configuration, prompt and tool-catalog hashes distinguish the arms. Raw
expectations must use `query_parquet` or `query_postgres`; an expected named metric
is invalid. Pin exact source/root/path arguments, SQL, columns, rows, values and
reviewed units. Query units remain a review assertion when the source does not
report them. Keep labels outside runtime-served directories.

The existing evaluator can grade raw and promoted results for the same question
in one suite. Swapping their assignments mismatches the context mode, identity and
revision. Failed and missing runs remain in the planned totals. No automatic live
scheduler, retries, holdout-driven edits or promotion is introduced.
[Frozen comparison schedules](ANALYSIS_COMPARISON_SCHEDULE.md) now support offline
ordering and assessment of recorded execution timestamps.

## Interpretation and remaining work

This implements a no-promoted-catalog execution path, not proof of an unbiased
experiment. Tool names do not prove server behavior; descriptions, schema comments,
views and source values can still encode domain knowledge. Review the server,
source contents and exposed schemas, and omit the ontology from its raw launch.
Both arms may benefit from the model's prior knowledge and the question itself.

The prompts intentionally differ in their treatment-specific instructions, and the
catalog arm may execute reviewed SQL unavailable to the raw arm. Record those
information/tool differences when interpreting any benefit. Hashes do not freeze
database contents or remote model versions. Reviewed domain fixtures, automatic
assignment execution, probe/maintenance accounting, appropriate statistical design
and actual paid analytical conformance remain open. All reports continue to leave
controlled comparison, source truth, snapshots and promotion readiness unverified.
