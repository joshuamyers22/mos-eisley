# Evidence and artifact verification — 2026-09-09

Scope: `feat/analysis-evidence-artifacts`, stacked on the bounded analytical client.
No paid calls, production sources or native credential stores were used.

Acceptance invariants and evidence:

- `tests/test_analysis_evidence.py` rejects incorrect numeric values, JSON-type
  confusion, absent/repeated/context-only claims, duplicate columns, malformed row
  widths, truncation, empty tables, non-finite numbers and duplicate source fields.
  A real MCP conversation with a deliberately wrong value fails validation.
- Answer prose is rendered from checked cells. A model's extra numeric assertion
  does not enter the checked answer. Source/causal correctness and snapshots remain
  explicitly unverified.
- The result envelope retains question, original calls/responses, SQL trail,
  controller/source-reported timing, promoted revision, completeness and usage.
  Tampered question/SQL/response/cell lineage fails offline validation.
- Private roundtrips check ownership/modes, file sets, symlinks/hardlinks, payload
  hashes, retention opt-in and access expiry. Expired results cannot verify/export;
  explicit cleanup refuses unexpired bundles and deletes only the verified bundle.
- Exports choose an explicit result, including a result earlier than the last call.
  CSV verification compares reconstructed bytes and parent/result lineage. Rehashed
  wrong answers and rehashed altered CSV bytes still fail internal consistency.
  Spreadsheet formula strings are escaped with a recorded count.
- CLI save/verify/export tests run through the packaged synthetic MCP source without
  a provider call. Default runs create no content artifacts. The installed-wheel
  smoke runs the evidence tests outside the checkout.
- The optional installed-data-mcp Parquet conversation returns a checked cell claim
  from the actual promoted metric. PostgreSQL is unchanged and remains an opt-in
  disposable-source integration check.

Focused validation: 42 analytical tests (24 existing and 18 evidence/artifact tests)
pass. `make check` passes lint/format, strict Pyright, 689 tests (two optional
cross-repository skips), 88% branch-inclusive coverage, locked-export verification,
package build and 75 installed-wheel tests outside the checkout. The additional
synthetic OpenAI CLI retention case verifies a private result bundle and its settled
usage receipt; its focused spending suite and strict typing also pass. The actual
data-mcp Parquet conversation passes, with the disposable PostgreSQL case skipped.
The change adds no dependencies.

Limits: deterministic cell matching and internal artifact consistency do not prove
source truth, correct metric selection, provider authorship, billing accuracy or
source snapshots. Retention expiry is an application access deadline; physical
cleanup is explicit. Parents/current-UID processes are trusted. See the
[operator contract](ANALYSIS_EVIDENCE.md).
