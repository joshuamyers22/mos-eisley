# Reviewable analytical answers and artifacts

The analytical result envelope is now schema version 2. Answers display values from
specific captured cells. The controller checks each proposed value against the
selected result, row and column, then renders the answer itself. Unsupported model
prose cannot introduce another number into the checked answer. `clarify` and
`unavailable` keep explanatory text and cannot carry value claims.

A model answer proposal looks like this:

```json
{
  "status": "answer",
  "text": "The controller will render the checked cells.",
  "result_ids": ["result-0002"],
  "claims": [
    {"result_id": "result-0002", "row": 0, "column": "total", "value": 42}
  ]
}
```

Rows are zero-based. Values must preserve the returned JSON type: `42`, `42.0`,
`"42"`, and `true` are distinct. Null is supported as a captured value; it is not
silently converted to zero. Results must explicitly report `truncated=false`, have
unique nonempty column names and coherent row widths. Missing, duplicate, malformed,
non-finite and out-of-range references fail. An empty table cannot support an invented
zero; obtain a count through SQL when needed. Compute sums, ratios, rounding and other
transformations in SQL and refer to the returned cells. Arbitrary narrative claims
and controller-side arithmetic are outside this first checked-answer format.

`value_verification="returned_cells"` means the displayed values match captured
source cells. It does not prove the correct metric/time period was chosen, the query
was sound, the database was accurate, or a causal claim was justified.
`claims_independently_verified` and `source_snapshot_verified` remain false. Source
labels and strings are quoted returned data, not trusted instructions. Model quality
and semantic ambiguity still need the planned domain evaluation.

## What the envelope records

- The question and its hash, provider/model, controller start/end timestamps, each
  provider response's reported usage, and aggregate byte/turn/tool counts.
- Every attempted tool call in a completed conversation, including original wrapped
  arguments, controller timestamps and outcome. Accepted calls retain the exact
  canonical MCP response used for evidence hashing. Failed calls retain their
  arguments and an error outcome; raw error messages are omitted.
- Successful result IDs/hashes, the promoted semantic revision and checked cell
  claims. The model selects result IDs explicitly; the last tool result has no
  special status as an answer or export source.
- A SQL trail for `run_metric`, `query_parquet` and `query_postgres`: submitted SQL
  from the request or metric response, normalized SQL when the server reports it,
  arguments and source-reported metadata. Missing normalized SQL stays null.
  Third-party tool calls remain in the full trace even without a recognized SQL
  operation name.

Source metadata includes reported metric/revision, backend/source/paths, units,
grain/timezone, query timestamps and snapshot identifiers when available. These
remain source assertions. Controller timestamps delimit the MCP call, not a proven
source snapshot. A definition revision never becomes a data-snapshot identifier.
The current data-mcp metric endpoint reports `data_snapshot=null`.

The legacy `evidence.complete` flag records accepted tool responses without declared
truncation, including non-tabular metadata. It alone does not establish table
completeness. Cell validation and exports require an explicit `truncated=false`
on the table; the SQL trail records this stronger completeness condition.

The trace has a 2 MB aggregate limit and the envelope an 8 MB limit, in addition to
the existing request/result limits. Limit failures do not silently shorten data.
Failed runs do not produce completed result bundles; their spending ledger remains
conservative according to the existing analytical spending policy.

## Optional private retention

The default remains `retention: "memory"`. To persist a live result, explicitly set
`retention: "private"` and `artifact_ttl_seconds` (60–604800, default 86400) in the
private analysis configuration, and add both `--allow-result-retention` and
`--result-root /absolute/private/analysis-runs` to `analysis-run`. The existing root
must be owned by the current OS user with no group/other permissions. Retention
admission is checked before credentials, spending reservation or MCP connection.
Provider transfer consent is separate.

Try the entire workflow with synthetic data:

```sh
mkdir -m 700 /absolute/private/analysis-runs
uv run --frozen mos analysis-demo \
  --allow-result-retention \
  --result-root /absolute/private/analysis-runs \
  --artifact-ttl-seconds 86400
# Use the returned artifact_path:
uv run --frozen mos analysis-verify /absolute/private/analysis-runs/RUN_ID
```

Each completed bundle has a random UUID directory (0700), a `result.json` containing
the envelope and optional spending receipt (0600), and a hashed `manifest.json`
completion marker (0600). Only metadata goes to the spending ledger; the explicitly
retained result file contains private question, SQL, arguments and returned data.
It does not store provider credentials, full model responses or the model's unused
answer prose. stdout also carries the result and may be retained by the caller.

`analysis-verify` reads locally, checks ownership/modes, file set, final-component
symlinks/hardlinks, manifest hashes and expiry, then rechecks response/SQL/cell lineage.
It does not contact a model, MCP server or source database. A partial bundle without
its completion manifest cannot verify or export. The destination and its ancestors
are trusted; this is not isolation from another process with the same UID. Hashes
check integrity and internal consistency, not authorship or an owner rewriting the
entire bundle consistently. This is captured-result verification, not provider replay.

Expiry blocks read/verify/export through these commands. It does not erase bytes
from the filesystem or revoke copies already made. Use the explicit cleanup command
for each expired complete bundle, or arrange an owner-controlled cleanup schedule:

```sh
uv run --frozen mos analysis-delete-expired /absolute/private/analysis-runs/RUN_ID
```

Cleanup refuses unexpired bundles, unknown files, symlinks and invalid manifests.
It deletes only that verified expired bundle, without scanning or recursively
removing arbitrary paths. Partial/corrupted bundles need explicit operator cleanup.
No scheduler or automatic deletion service is installed by this milestone.

## Export one captured complete result

```sh
uv run --frozen mos analysis-export /absolute/private/analysis-runs/RUN_ID \
  --result-id result-0002 \
  --result-root /absolute/private/analysis-runs
# Use the returned export path and its original source bundle:
uv run --frozen mos analysis-verify /absolute/private/analysis-runs/EXPORT_ID \
  --source /absolute/private/analysis-runs/RUN_ID
```

The export is a separate bounded CSV bundle. Its manifest binds the original bundle
hash, selected result ID, response hash and CSV hash. Verification reconstructs the
CSV from the saved rows and compares it exactly. It never reruns a changing query.
Only explicitly complete, well-shaped tables export. “Complete” describes the
captured query result, not all rows in the source database or a stronger snapshot
claim. Both bundles must still be within their access windows for verification;
an export inherits its parent's expiry.

CSV is a text representation. Null is written as `null`; the original JSON preserves
cell types. String cells/headers that could introduce spreadsheet formulas receive
a leading apostrophe, and `escaped_csv_cells` records the count. The unmodified
source values remain in the private JSON bundle. This export supplies result lineage
for a future chart/table UI; it does not implement charts or a web download service.

See [verification evidence](ANALYSIS_EVIDENCE_VERIFICATION.md).
