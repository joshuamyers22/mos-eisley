# Synthetic Parquet case integration — 2026-09-09

The optional data-mcp integration now exercises six development cases using eight
actual Parquet lines. Each case runs once through raw SQL and once through a
revision-bound promoted metric. The Mos checked-answer controller must accept the
expected integer cell, retain both bootstrap and query evidence, and record the
correct context mode and semantic revision.

The data-mcp [case-pack guide](https://github.com/joshuamyers22/data-mcp/blob/main/docs/ANALYTICAL_CASE_PACK.md)
describes creation, pinned verification, hand-worked answers and server configs.
Use a data-mcp installation containing `data_mcp.fixture`:

```sh
DATA_MCP_TEST_PYTHON=/absolute/data-mcp/.venv/bin/python \
  uv run --frozen python -m unittest \
  tests.test_mcp_data_integration.DataMCPIntegrationTests.test_synthetic_parquet_case_pack
```

Both arms read the same private Parquet file, receive the same question and shared
conventions, and use the same limits, including a 12000-byte result allowance.
The script supplies each query/metric and its expected answer. The server's data
root contains no golden labels, and the raw profile loads no ontology. The pack
verifier checks its pinned bytes after all twelve conversations and executes its
own twelve direct MCP answer checks.

Cases cover repeated order IDs across lines, cancellations, signed quantities and
discounts for returns, null discounts, half-open month boundaries and an empty
month. All belong to one development family. Scripted success proves the path
through real SQL and cell checking; it does not measure a model's ability to
choose SQL, establish independent domain review or authenticate an immutable
source snapshot. No provider calls or PostgreSQL credentials are used.

This adds no new Mos production command. The existing `analysis-run` can use the
explicit server configs and corresponding context modes once an operator has
configured its ordinary provider/account/budget inputs. Import into a reviewed
suite, controlled live execution and real-data assessment remain separate work.

Verification: the explicit case-pack integration passed all twelve conversations
and subsequent pinned verification. The full Mos source suite passed 721 tests
with three optional cross-repository skips and 88% branch-inclusive coverage.
Ruff, strict Pyright, locked-export verification and package build passed.
All 106 installed-wheel tests passed outside the checkout, completing `make check`.
Default CI skips the cross-repository cases without
`DATA_MCP_TEST_PYTHON`; they were explicitly enabled locally for this milestone.
