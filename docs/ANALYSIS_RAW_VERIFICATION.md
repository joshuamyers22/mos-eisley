# Raw-data baseline verification — 2026-09-09

Scope: `feat/analysis-raw-baseline`, stacked on the offline evaluator.
Objective: support a no-promoted-catalog control arm through the same bounded
analytical controller without widening source/write authority or overstating
experimental evidence. This is implementation verification, not independent domain
review. Stop after focused boundary tests, strict static checks, the existing full
quality gate, installed-wheel checks and an actual temporary Parquet conversation.
No paid calls, production data or native credential stores are needed or used.

Eight new tests in `tests/test_analysis_raw.py` cover raw model requests excluding
catalog definitions/revisions, dispatch denial before MCP, rejected-attempt counting,
source-injection attempts, budget exhaustion, clarify/unavailable behavior, private
artifact/CSV roundtrips, mode/revision tampering, metadata-cell rejection, mixed-arm
offline scoring, swapped assignments, invalid raw metric expectations, default
canonical compatibility and the CLI demo. They supplement the existing analytical
controller, evidence, evaluator and spending tests.

The synthetic OpenAI CLI test additionally completes raw query/answer turns with a
settled spending receipt and verified private artifact. It uses a counted fake
transport and no provider connection. The installed data-mcp Parquet integration
runs both arms over the same temporary file; the raw server loads no ontology and
returns the same checked row count through SQL. Optional disposable PostgreSQL is
skipped without its DSN; server implementation and database adapters are unchanged.

Focused analytical validation: all 64 tests pass, including the eight new raw tests.
`make check` passes Ruff lint/format, strict Pyright, 711 tests (two optional
cross-repository skips), 88% branch-inclusive coverage, locked-export verification,
package build and 97 installed-wheel tests outside the checkout. The data-mcp raw
example passes configuration preflight; local documentation links and diff checks
pass. No dependency changes were needed.

Limits: the scripted total and temporary row count prove plumbing, not domain
accuracy. Schema/source text can carry domain knowledge; tool names are not an
independent authority boundary. Mode/prompt/catalog identities are assertions about
local execution, not source snapshots or remote model version proof. The grader
continues to deny controlled-comparison verification and promotion readiness.
See the [operator guide](ANALYSIS_RAW_BASELINE.md).
