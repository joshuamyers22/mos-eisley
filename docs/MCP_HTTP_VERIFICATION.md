# Remote MCP verification — M11A

Date: 2026-09-09. Scope: the Mos Eisley Streamable HTTP client on
`feat/remote-mcp-http`, stacked on the stdio client in PR #108.

## Objective and acceptance boundary

Connect an operator-selected hosted server, discover only configured tools and
perform authorized reads/writes without widening destination or credential access.
A transport failure must never automatically resubmit a possibly committed write.
Pass threshold: focused real HTTP/TLS fault tests, stdio regression tests, strict
static checks, the repository coverage gate, a clean wheel install with HTTP
read/write calls, and dependency audit. Stop after this gate; production endpoints,
paid model calls and OAuth require separate work and evidence.

## Evidence

`tests/test_mcp_http.py` exercises real SDK servers over localhost HTTP and TLS:

- JSON and SSE discovery/read/write; explicit tool and write grants.
- Current protocol plus both allowed 2025 revisions; unsupported negotiation fails.
- Invalid/revoked tokens, isolated concurrent token snapshots, and wrong OS owner.
- Same-origin and cross-origin redirects rejected without reaching the target.
- Untrusted certificates and hostname mismatches rejected; explicit CA succeeds.
- Malformed JSON, compressed bodies, oversized JSON and chunked SSE fail closed.
- Lost response after a committed write: exactly one submission and one mutation.
- Timeout/cancellation, disabled subsequent dispatch and redacted CLI diagnostics.

Policy tests exercise public/private address grants and DNS changes. A mock
resolver proves the socket backend receives a validated literal address and rejects
a later private answer. These tests do not contact a real public DNS service or
prove isolation between separate operating-system accounts. The current credential
boundary is one controller process/effective UID, with per-connection token snapshots;
a multi-user hosted controller and credential vault belong to M11B.

The focused MCP suite passes 33 tests (two optional cross-repository data tests
skipped). `tools/smoke_package.py` installs the built wheel into a clean temporary
environment and invokes its CLI outside the checkout against stdio and HTTP
fixtures, including an HTTP write followed by a verifying read.

Full repository gate and CI results are recorded in the pull request. The locked
runtime audit found no known vulnerabilities or adverse statuses in 40 packages.

## Findings resolved during implementation

The SDK may follow redirects independently of the HTTP client's default, so the
transport rejects every redirect before it reaches SDK handling. Stream resumption
is rejected before transmission. DNS validation pins the actual socket destination
rather than performing an unrelated preliminary lookup. Compression is rejected
before decoding; the total wire-response budget applies before SDK parsing.

The SDK's background request task can propagate early transport exceptions as
caller cancellation. The HTTP client converts these failures into a fixed local
502 response so the SDK resolves the outstanding request as failed. This conversion
performs no new request. Actual caller cancellation remains cancellation.

JSON-response server work may continue after the client disconnects. The client
closes its response, disables the dispatcher and warns that writes may have committed;
it does not promise server cancellation, rollback, or exactly-once semantics across
separate CLI invocations. The original response content and credentials are excluded
from transport diagnostics.

## Remaining scope

OAuth login/refresh/logout (M11B), schema expansion, paid analytical-agent execution,
remote hosting and real HDD/database deployment are separate. No production data
or paid provider was used in this verification. Review the final PR before merging.
