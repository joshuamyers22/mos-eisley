# Metric output-contract integration — 2026-09-09

The optional data-mcp integration now verifies the native output contract on its
parameterized Parquet metric. January and February return the expected checked
integer cells, and the original tool-response evidence retains `column_types` and
`output_contract_verified`.

A negative case changes the query to return text while retaining the numeric
contract. The scripted client proposes the exact resulting string it would expect
without the contract. data-mcp rejects that result before it becomes accepted MCP
evidence, so Mos cannot construct a checked answer from it.

Run with a data-mcp installation containing
[output contracts](https://github.com/joshuamyers22/data-mcp/blob/main/docs/METRIC_OUTPUT_CONTRACTS.md):

```sh
DATA_MCP_TEST_PYTHON=/absolute/data-mcp/.venv/bin/python \
  uv run --frozen python -m unittest \
  tests.test_mcp_data_integration.DataMCPIntegrationTests.test_parameterized_parquet_metrics
```

The marker is evidence reported by the connected server. It does not establish
independent source trust, unit correctness, schema authenticity or snapshot
identity. Mos retains its existing scalar-cell validation. No Mos production
behavior changes; this milestone extends the optional regression and operator
documentation. The requests are scripted and make no provider calls.

All four cross-repository tests passed locally with synthetic Parquet files and an
explicit disposable PostgreSQL database, including the prior read/write paths.
The full quality gate passed: 725 tests (four optional integration skips),
88% branch-inclusive coverage, strict typing, lint/format, locked export, build,
and 106 installed-wheel smoke tests.
