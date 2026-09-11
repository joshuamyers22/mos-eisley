# Parameterized metric integration — 2026-09-09

Mos Eisley's analytical controller now has a cross-repository regression for
parameterized data-mcp metrics. It retrieves the current catalog, sends declared
dates through the existing JSON argument wrapper, checks the returned scalar
cell, and retains the exact parameter object, reviewed SQL and manifest revision
in the answer evidence. The same definition returns 8 units for January and 7
for February in the temporary fixture.

Use a data-mcp installation containing the
[typed-parameter implementation](https://github.com/joshuamyers22/data-mcp/blob/main/docs/METRIC_PARAMETERS.md):

```sh
DATA_MCP_TEST_PYTHON=/absolute/data-mcp/.venv/bin/python \
  uv run --frozen python -m unittest \
  tests.test_mcp_data_integration.DataMCPIntegrationTests.test_parameterized_parquet_metrics
```

Parameterized catalogs advertise a richer `run_metric` input schema. Analytical
conversations already use `arguments_json`; direct canonical dispatch must follow
the discovered schema too. MCP wire arguments carry ordinary nested JSON. Fixed-only
catalogs retain their original input schema. A parameterized example is available
in data-mcp's `ontology/parameters.example.toml`.

No Mos production controller or provider behavior changes in this milestone. The
new test scripts its requests and expected answers. It establishes the tool/schema
and evidence path, not independent domain correctness or model query-selection
quality. Callers still need a reviewed metric and source configuration for their
own data, and must use the current run identity when freezing an evaluation suite.

Verification: all four optional cross-repository tests passed on the updated
`4d50ece` base with explicit disposable PostgreSQL inputs, covering committed writes,
the two new date windows and the preceding fixed-metric and six-case raw/promoted
paths. The full source suite passed 725 tests with four optional cross-repository
skips and 88% branch-inclusive coverage. Ruff, strict Pyright, locked-export
verification and the package build passed. All 106 installed-wheel tests passed
outside the checkout, completing `make check`. No provider calls or real-data
access were used. The base PR #117 has since merged into main.
