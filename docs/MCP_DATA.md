# Data MCP client

Mos Eisley can launch an explicitly configured stdio server or connect to a
Streamable HTTP endpoint, discover selected tools, and read/write through them. The first target is
[data-mcp](https://github.com/joshuamyers22/data-mcp): HDD Parquet and local/cloud
PostgreSQL, plus Ana Lite's promoted semantic manifest and named metrics.

Streamable HTTP with token authentication (M11A) and OAuth for pre-registered
public clients (M11B) are implemented on their feature branches. See
[the remote milestones](mos-eisley-plan.md#133-remote-mcp-connections--planned-m11a-and-m11b).
Schema expansion and paid analytical-agent integration have separate gates.

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

## Connect your own hosted server

Copy [the remote example](../examples/mcp-remote.json), set your server's final
HTTPS endpoint and actual tool names, and provide the token through the named
environment variable. Use the same `mcp-list` and `mcp-call` commands above with
that config. Classifying a tool as `write` requires `allow_writes: true`.

`transport: "streamable_http"` requires an `http` object and excludes stdio launch
fields. `authentication: "bearer"` requires `token_env`; explicitly public servers
use `authentication: "none"` without a credential reference. Secrets stay out of
config. Each connection snapshots its token and binds it to the endpoint and
current OS user; optional `token_owner_uid` requires a particular effective UID.
This is a single-user controller boundary, not a multi-user credential vault.
Disconnect by leaving `connect_mcp` or exiting the command; remove the config to
remove the connection. No tokens, cookies or sessions are saved to disk.

Remote endpoints require HTTPS with certificate and hostname validation. For a
private CA, set an absolute `ca_file`. Public addresses are allowed; private HTTPS
addresses require explicit `private_networks` CIDRs, for example `["10.2.0.0/16"]`.
Every DNS answer must pass the address policy, and the socket connects to a
validated literal address while preserving the original TLS identity. Link-local,
metadata, multicast and special transition addresses remain denied. Proxy and CA
environment settings are not inherited. For local testing only, a literal loopback
HTTP URL also requires `allow_loopback_http: true`.

The client supports protocol revisions `2026-07-28`, `2025-11-25` and `2025-06-18`,
with JSON and request-scoped SSE responses. URLs with credentials, query strings
or fragments, redirects, compressed responses and stream resumptions are rejected.
Configure the final endpoint directly. `http.max_response_bytes` defaults to
262144 bytes and bounds each complete JSON/SSE response before SDK decoding;
`max_result_bytes` separately bounds the canonical tool result. These limits can
reject large catalogs or long streams. Connection/discovery and calls have finite
deadlines. The client never automatically resubmits a tool call. Cancellation closes
the client response but cannot guarantee that server work stopped or a write rolled
back; inspect a submitted write before retrying after any failure.

See [HTTP verification](MCP_HTTP_VERIFICATION.md) and
[OAuth verification](MCP_OAUTH_VERIFICATION.md) for the tested boundaries.
Remote hosting/deployment, broader schemas and paid-model tool use remain separate.

## OAuth login and logout

Use [the OAuth example](../examples/mcp-oauth.json) for a server whose authorization
provider offers a **pre-registered public native client** with PKCE S256. Obtain a
client ID from that provider and register the exact callback
`http://127.0.0.1:8765/oauth/callback` (or change `callback_port` in both places).
Set your final MCP URL, expected issuer, a local account label, exact requested
scopes and allowed tool names. This release supports public clients with token
endpoint authentication `none`; confidential clients, dynamic registration, and
hosted client metadata documents are not implemented.

```sh
mos mcp-login --config /absolute/path/mcp-oauth.json --open-browser
mos mcp-list --config /absolute/path/mcp-oauth.json
mos mcp-call --config /absolute/path/mcp-oauth.json --call /absolute/path/call.json
mos mcp-logout --config /absolute/path/mcp-oauth.json
```

Without `--open-browser`, login prints the authorization URL and waits for you to
open it. Login expires after 180 seconds by default. The callback listener binds
only IPv4 loopback and closes on completion or cancellation. It validates state,
issuer and one-use callback handling before exchanging the authorization code.
Keep the authorization URL private while the login is pending. You approve the
requested scopes at the provider; login never changes the configured tool grants.

Protected-resource discovery uses the server's challenge or standard well-known
locations. The configured issuer must match resource and authorization metadata.
OAuth and OpenID discovery formats are supported. The resource metadata stays on
the MCP origin; authorization/token/revocation endpoints stay on the issuer origin
unless `allowed_auth_origins` explicitly names additional origins. All controller
requests retain HTTPS, DNS/address checks, no redirects and pre-decoding byte
limits. Discovery cannot introduce credential destinations outside those grants.
The browser handles the provider's login pages and their navigation; its networking
is outside Mos Eisley's socket transport. Use a trusted browser and issuer.

Access and refresh tokens are stored in macOS Keychain or Linux Secret Service.
An available, unlocked native keychain is required; there is no plaintext fallback.
Credentials bind to the effective OS user, local account label, MCP resource,
issuer, client ID and exact configured scopes. Account labels select independent
local credential slots; they do not verify the human identity at the provider.
Lock files in `~/.mos-eisley-oauth-locks` contain no credentials and must remain
user-owned with directory mode 0700 and file mode 0600. Do not remove active locks.
OS keychain unlock prompts may outlast network deadlines; an in-progress keychain
mutation finishes before its lock is released so cancellation cannot undo logout.

Tokens refresh before a request when expiry is within 30 seconds. Concurrent
controllers serialize refreshes. The old local token record is removed before a
refresh exchange: a lost response requires an explicit new login. An MCP 401/403
removes the local credential and fails the session without retrying the request.
Servers must return a positive integer `expires_in`, bearer tokens and the exact
requested scope set (or omit `scope` to retain it). Different grants fail closed.
Change scopes explicitly, then log in again; no automatic scope escalation occurs.

Logout removes the selected local record first and attempts revocation of both
access and refresh tokens when an approved endpoint is available. Its JSON output
distinguishes provider acceptance, unavailable revocation, and failed/incomplete
revocation; acceptance is not proof of revocation at every downstream service.
Existing connections check the keychain before their next request. Requests already
in flight can still complete. Log out with the original configuration before
changing its identity/scope fields or deleting it, otherwise its old slot remains.
Reauthentication replaces the selected local record; previously issued provider
tokens can remain valid until revoked or expired.

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

- Configuration is explicit trusted operator input. Stdio executes code with the
  user's privileges and is **not a process or network sandbox**. A local server can
  reach cloud PostgreSQL. HTTP applies the destination controls below. No automatic
  repository discovery or critic registration occurs. OAuth login is explicit. There are no sampling, elicitation or filesystem-roots callbacks.
- For stdio, environment values pass only for named variables, which must be set.
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
- For stdio, these application limits apply after SDK decoding. They are **not a hard
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
