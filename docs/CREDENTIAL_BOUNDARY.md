# Credential attachment at the approved network boundary

Plan §31.5 has an additive trusted-host implementation. It is available as a
library transport for the existing request-bound provider broker. Current CLI
credential paths remain supported and default. Provider/tool production activation
still requires the existing exact credentialed conformance, data-policy and
accountable review gates; fixture evidence does not qualify a new live profile.

`CredentialRef` version 1 names a native-keychain entry bound to the actual OS
owner. The native service is `mos-eisley.network-attachment.v1`; the account is the
canonical reference digest. `NativeNetworkCredentials` selects macOS Keychain or
Linux Secret Service directly, using the existing native backend selector. It
never selects an environment-configured keyring plugin or plaintext fallback.
Environment keys, OAuth stores and provider-native subscription identities retain
their existing paths; this new reference kind does not silently adopt them.

The trusted administrator provisions a native JSON `NetworkCredential` record
containing the exact reference, a fresh generation ID, endpoint identity,
operation names, timezone-aware expiry and secret. Provision through the native
store or a trusted host using its credential backend, never command arguments,
repository files or environment variables. `SecretStr` deliberately redacts normal
model serialization: producing the native record with the actual secret is an
explicit private provisioning action. A replacement record rotates the key; a
missing record revokes it. Never reuse generations or allow untrusted callers to
provision this namespace. Normal application code has no lifecycle tool or endpoint
that could invoke these administrator actions.

`NetworkEndpoint` is a separately trusted version-1 policy record. It pins scheme,
host, port, the complete resolved IP set, exact POST paths, authentication header
kind and approval expiry. Public services require TLS and global unicast addresses;
an explicit loopback exception admits only loopback addresses. DNS/address changes
require a new approved endpoint, even for ordinary CDN changes. The connector
validates DNS and connects a pinned literal address, preserving the original
hostname for certificate verification and SNI. CA trust uses an explicit bundled
CA file; ambient TLS trust, key-log and proxy variables have no effect. A separately trusted
private CA PEM may be supplied by the host. There is no arbitrary client, redirect,
proxy, header dictionary, retry, HTTP/2, streaming or executable extension option.

The host supplies `CredentialNetwork` with the endpoint, reference, native holder
and a mandatory current-policy admission callback. That callback must recheck the
existing owner, data-transfer, operation and spending authority; the new transport
does not issue authority. It runs before networking and immediately before each
socket write, alongside the shared task-local dispatch guard. The transport reads
the native record after DNS/TCP/TLS and rechecks policy after the read, then attaches
the secret only in the socket stream. It rechecks the native record for later body
writes. Rotation during one dispatch aborts it; a later separately admitted call
can use the replacement without restarting the session. Revocation is effective at
the next write admission, not retroactive removal of bytes already sent.

Use `CredentialedOpenAITransport(network)` as the existing counted transport:

| Operation | Trusted OpenAI endpoint path |
|---|---|
| `count_input_tokens` | `/v1/responses/input_tokens` |
| `create_response` | `/v1/responses` |

The trusted OpenAI endpoint is `https://api.openai.com:443`; approve its actual IP
set and data policy separately. Wrap this transport in the existing budgeted or
pre-reserved OpenAI controller, then issue the existing `RequestBoundBroker` through
the approved review/coding composition. Its claim contains no endpoint or provider
secret. Do not expose `CredentialNetwork.post` directly as an agent tool. Other
service adapters can use exact admitted JSON POST operations, but require their
own semantic, authorization and conformance gates. No GitHub publisher is routed
through this component; the separate publisher boundary remains authoritative.

Each exchange has a positive deadline of at most 60 seconds, a 1 MB request/body response ceiling,
HTTP/1.1 framing limits from the pinned client, a fresh one-connection pool and no
connection reuse. Encoded responses, non-200 statuses and unsupported behavior
fail closed. A native read runs off the event loop; a cancelled read cannot later
send anything. The underlying native read may finish after cancellation. Cancellation
propagates; network/parser/native failures expose a fixed diagnostic with no
retained native exception chain. Body echo checks reject credentials even when
JSON-escaped. Credentials may exist in trusted holder/connector memory; Python
cannot guarantee memory zeroization or protect against a compromised host.

The pinned HTTP client can debug-log arbitrary response headers and protocol
exceptions. A task-local producing-logger filter suppresses that wire logging only
for these exchanges; ordinary concurrent transports retain diagnostics. Recheck
this logger inventory and stream framing when changing the HTTP dependency.
No raw captures or resolved credentials enter events, snapshots, exported/replayed
artifacts, prompts, tool arguments, sandbox files or subprocess environments.

There is no authentication retry. Broker grants stay consumed after failure or
cancellation. Existing spend reservations and §31.4 durable operation journals stay
authoritative, including across rotation/revocation. A changed key is never evidence
that an uncertain effect did not occur and never justifies reconstructing a grant.

See the [threat model](CREDENTIAL_BOUNDARY_THREAT_MODEL.md),
[ADR](adr/0018-network-credential-attachment.md) and
[verification record](CREDENTIAL_BOUNDARY_VERIFICATION.md).
