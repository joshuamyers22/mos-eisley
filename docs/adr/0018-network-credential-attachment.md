# ADR 0018: Resolve native credentials at the socket write boundary

Status: implemented; production activation requires existing conformance and
accountable review. Requirement: plan §31.5. Date: 2026-10-22.

The request-bound worker broker already owns one-use admission and spending, but
legacy ephemeral provider clients retain a literal key. Add a separately selected
host-only transport using typed owner-scoped native references and immutable
endpoint policy. Preserve the existing broker, wire contracts, spending controller,
durable operation journal and publisher separation.

Resolve the native key after pinned DNS/TCP/TLS and immediately before writing the
HTTP/1.1 headers; never hand it to the provider SDK or worker. Revalidate each body
write and abort on generation/secret changes. No redirect/proxy/retry/custom-client
options exist. Use a fresh pool per exchange and explicit CA policy. Suppress only
these exchanges' client wire logs because even response headers can echo secrets.

Consequences: endpoint IP drift needs fresh host approval; the initial provider
facade covers counted OpenAI requests, while other services require separately
admitted adapters. Native reads can outlive cancellation but cannot dispatch late.
Revocation cannot undo transmitted bytes. Credential changes do not repair or retry
uncertain operations. Legacy key/SDK paths remain available and default pending
separate qualification. No storage migration or new provider/publisher authority
is introduced.

Alternatives rejected: environment injection into workers (ambient secret access),
SDK-owned literal credentials (cached lifecycle and broad client configuration),
URL-only allowlists (DNS pivot), and replacing existing claim/journal identity on
reauthentication (duplicate effects).
