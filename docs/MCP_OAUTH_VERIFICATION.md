# OAuth verification — M11B public-client profile

Date: 2026-09-09. Branch: `feat/mcp-oauth`, stacked on HTTP PR #109.

## Objective and gate

Provide explicit login, authenticated MCP discovery/read/write, expiry/refresh,
reauthentication and logout for pre-registered public native clients using PKCE
S256. Bind credentials to the OS user, selected account label, resource, issuer,
client and scopes. Never resubmit a possibly committed MCP write after auth failure.

Pass threshold: real HTTP authorization/resource fixtures, existing MCP regression
suite, strict static checks, full repository coverage/build gate, installed-wheel
OAuth contract tests and locked dependency audit. No production endpoint, actual
browser login, real keychain mutation, or paid model call is needed for this gate.
Stop at that threshold; native vault integration and provider deployment require
separate operator evidence.

## Evidence and fault coverage

`tests/test_mcp_oauth.py` contains 20 tests. Together with HTTP and stdio tests, the
focused MCP suite passes 53 tests with two optional data integrations skipped.
The fixture implements authorization codes, PKCE validation, rotating refresh
tokens, resource checks, revocation and actual SDK MCP reads/writes over HTTP.

Coverage includes successful login/read/write/refresh/logout, concurrent refresh
serialization, separate account/server/client/scope slots, changed effective UID,
revoked access, explicit reauthentication, OAuth/OpenID discovery, denied login,
wrong issuer/resource, malicious metadata destinations/redirects, unsupported PKCE,
insufficient configured scopes, wrong returned scope/resource, callback state and
issuer checks, duplicate/replayed callbacks, cancellation and callback timeout.

A committed write with a dropped response executes once. Failed or lost refresh
responses remove the old record, so later requests cannot reuse a potentially
rotated token. Failed revocation still clears local credentials and reports its
limited outcome. Corrupt/unavailable keychain records produce fixed diagnostics.
A delayed credential save with repeated cancellation retains its lock until a
concurrent logout can remove the final record. Private lock permissions and symlink
rejection are tested.

The keychain test double is in memory and receives only synthetic fixture tokens.
Tests verify controller bindings and a simulated effective-UID change; they do not
claim an integration test across two logged-in operating-system users. Native
backends are explicitly selected (macOS Keychain or Linux Secret Service); no
plaintext backend or environment-selected keyring plugin is accepted.

`tools/smoke_package.py` copies only fixtures/tests into a temporary directory and
runs these OAuth tests using a clean installation of the built wheel outside the
checkout. The keychain remains a test double. Full gate and CI results are recorded
in the PR. The locked runtime audit found no known vulnerabilities or adverse
statuses in 48 packages.

## Supported boundary and limitations

This profile supports pre-registered public clients with token endpoint auth
`none`, exact configured scopes, bearer tokens and positive integer `expires_in`.
Confidential clients, dynamic registration and client metadata documents remain
unsupported; the CLI guide makes this explicit. Real provider configuration and
native keychain unlock/access have not been exercised in this development gate.

Controller HTTP requests use endpoint/address/TLS controls and bounded responses.
The authorization URL is validated before opening; subsequent browser networking
and provider page redirects are managed by the browser. The OS keychain can prompt
for unlock and an already-started mutation cannot be forcibly cancelled safely;
the controller retains its lock until that operation finishes. Logout cannot stop
requests already in flight or prove remote revocation from a provider's acceptance.

OAuth account labels are local credential selectors, not an OpenID identity check.
Before changing a configuration's identity/scopes, log out using the original
configuration to remove its slot. Reauthentication deletes the local prior record
but does not prove all prior provider tokens were revoked. No new tool grants,
paid-model transfer, schema expansion or service hosting is introduced.

References: [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization),
[discovery](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/authorization-server-discovery),
and [registration](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration).
