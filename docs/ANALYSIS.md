# Bounded MCP analysis

`analysis-run` connects Mos Eisley's existing OpenAI adapter to an explicit read-only
MCP profile. It first fetches promoted semantic context, binds metric calls and
results to that definition revision, and returns an `answer`, `clarify`, or
`unavailable` result. It runs against local stdio or the existing Streamable HTTP
client. `analysis-demo` uses a packaged synthetic MCP server and scripted model
responses; it does not require a provider account.

```sh
uv run --frozen mos analysis-demo
uv run --frozen mos analysis-demo --scenario clarify
uv run --frozen mos analysis-demo --scenario unavailable
```

## Configure a live run

Start with `examples/analysis-openai.json` and the read-only MCP configuration in
[MCP_DATA.md](MCP_DATA.md). For data-mcp, use `config.ana.toml` with the server's
`access_mode="analysis"`, a promoted ontology, and dedicated read-only database
credentials. The client must select `get_semantic_context`; select `run_metric` and
only the other read tools needed for your sources. The analytical controller rejects
write grants and known data-mcp mutation tool names, and forces validated JSON
argument wrappers for the OpenAI strict schema representation. The ordinary MCP
commands retain their explicit read/write access. Analytical tools must return
structured JSON objects. The default `context_mode="promoted"` requires a SHA-256
definition `revision`, and
`run_metric` results must carry that same revision. Text-only/binary results cannot
serve as analytical evidence in this milestone.

For a no-promoted-catalog control arm, explicitly select `context_mode="raw"` and
its raw tool profile. It bootstraps source discovery and records a null semantic
revision while sharing the same limits and spending controls. See the
[raw-data baseline guide](ANALYSIS_RAW_BASELINE.md). Missing context never triggers
an automatic fallback.

Tool labels are operator grants, not proof that a third-party server cannot mutate
its backend. Review the server and enforce read-only source permissions. Source
values, descriptions and semantic notes are untrusted model input; they cannot add
tools or change the controller's limits. The fixture injection test proves dispatch
denial for an attempted out-of-profile write; it does not establish model immunity
to misleading source text.

Choose an available OpenAI model from `mos models` and review a schema-2
`SpendPolicy` with current rates, including cache writes, model ID, validity window,
per-request token limits and total accepted cost. No production pricing policy is
shipped. The validity window must cover the entire configured run deadline.
The first integration uses OpenAI; Anthropic and Google analysis remain future work.
The existing [OpenAI function-calling](https://developers.openai.com/api/docs/guides/function-calling)
and [input-token counting](https://developers.openai.com/api/reference/python/resources/responses/subresources/input_tokens)
interfaces are reused. Live analytical conformance has not been exercised.

Use one pre-existing private SQLite spending ledger for all participating runs for
the same OS user/provider account. The `account` field is an operator label, not an
API-verified account identity. Copy the ledger ID from `mos spend-ledger-status /absolute/private/account-ledger.sqlite`; it
must match the explicitly supplied `--ledger-id`. Never create a fresh ledger per
run to evade the aggregate ceiling. For example, after preparing private input files:

```sh
uv run --frozen mos analysis-run \
  --config /absolute/private/analysis.json \
  --mcp-config /absolute/private/mcp-ana.json \
  --spend-policy /absolute/private/reviewed-pricing.json \
  --spend-ledger /absolute/private/account-ledger.sqlite \
  --ledger-id LEDGER_SHA256 \
  --accept-max-cost-microusd REVIEWED_MAXIMUM \
  --allow-data-transfer
```

The command reads `OPENAI_API_KEY` only after local admission. Transfer opt-in covers
the question, tool schemas, promoted context, results and conversation sent to both
the provider's token-count endpoint and generation endpoint. It also connects the
explicitly configured MCP server, whose existing credential/endpoint rules apply.
There are no automatic provider or tool retries. The original one-prompt spending
controller and separately authorized evaluation workflows remain separate.

## Limits and spending semantics

Defaults: six model turns, twelve tool attempts including context fetch, two pending
tool calls per response, one admitted analytical run per shared ledger, 120 seconds overall,
30 seconds per model request and 15 seconds per tool call. Tool calls run serially;
there is no waiting queue. Excess admission is rejected in the same SQLite write
transaction as the reservation. Uncertain and crash-held entries occupy slots.
Other legacy commands sharing this ledger still respect its spending ceiling but
do not participate in the new analytical concurrency limit.

Default run token ceilings are 64,000 input tokens and 8,192 output tokens, with
2,048 output tokens per response. Aggregate canonical input/output byte caps are
512,000/64,000 and each canonical result is capped at 4,000 bytes. These are separate
limits; tokens are counted before each live generation and reconciled with usage.
No per-request input cap exceeds 200,000 tokens. Oversized or truncated tool results
are rejected as evidence; results are never silently shortened.

Before credentials or transfer, the ledger reserves the whole-run worst case:
`SpendPolicy.reservation_cost(total_input_cap, total_output_cap) + max_turns - 1`.
The extra microdollars cover rounding each response separately. This must fit both
the reviewed policy and `--accept-max-cost-microusd`, plus the ledger's remaining
aggregate ceiling. Successful responses settle their summed conservative cost.
A failure before generation releases unused funds. A response with unknown billing,
a cancelled/in-flight generation, or process crash retains the full run reservation;
a pricing-assumption violation also blocks the ledger. Missing API credentials settle
at zero. A tool or answer validation failure after known billing still charges those
completed responses. Held/uncertain entries have no automatic reset or retry path.

This is local accounting for cooperating runs using one trusted ledger. It is not
a distributed quota, authenticated account authority, invoice reconciliation, or
protection against the ledger owner replacing/rolling back the database. SQLite
lock waiting is bounded separately (250 ms). Cancellation propagates to client
operations; it cannot guarantee that a remote query or provider generation stopped.

## Checked answers, retention and remaining work

The schema-2 envelope now includes a SQL/result trail, timestamps, usage and explicit
cell claims. The controller checks values against captured cells and renders answer
text itself. Complete result IDs alone are no longer sufficient for an `answer`.
This checks returned values, not source truth or metric selection; both
`claims_independently_verified` and `source_snapshot_verified` remain false.

Memory-only content retention remains the default. An explicit private retention
configuration plus CLI consent enables bounded UUID bundles, offline verification,
expiry checks and exports tied to a chosen captured result. The ledger continues to
store only monetary/identity metadata. See the
[answer format, retention and export guide](ANALYSIS_EVIDENCE.md) and
[verification record](ANALYSIS_EVIDENCE_VERIFICATION.md).

New results also carry configuration, system-prompt and tool-catalog hashes for
[offline comparison with reviewed expectations](ANALYSIS_EVALUATION.md). The grader
checks saved evidence and counts missing/failed runs without provider calls.

Arbitrary narrative/arithmetic verification, a chart/download UI, actual domain
quality measurement, native OAuth/vault deployment, production HDD/cloud databases
and paid multi-turn analytical conformance remain future work.
