# Credential attachment threat model

Requirement: plan §§4.5, 19.2–19.4 and 31.5. High-risk credential boundary.
Assets: native provider/service secrets, owner identity, endpoint/data-transfer
approval, spending reservations and one-use operation identity.

Trusted: host policy issuer, native OS credential service, broker, pinned
HTTP/1.1/runtime dependencies and TLS CA policy. Untrusted: agent/project/tool
content, response bodies/headers, network/DNS changes and ambient proxy/TLS config.
An authenticated destination receives its own credential by design; destination
compromise can misuse a received key. This boundary cannot repair a malicious
administrator, compromised host/OS/native store or breached approved service.

| Attack | Control | Deciding evidence |
|---|---|---|
| URL/header instructions in prompts or tools | No model-selected transport settings; exact policy operation lookup | Destination and marker injection tests |
| Cross-owner or cross-service reference | Actual real/effective UID and exact record/reference/endpoint/operation matching | Owner/scope/expiry negatives |
| DNS pivot, metadata/private/multicast access | Public unicast or explicit loopback class; full answer-set match; literal IP connect | DNS drift negatives and socket captures |
| TLS hostname substitution or ambient CA/key-log/proxy changes | Original-host verification/SNI, explicit CA bundle, no proxy backend | Real TLS and ambient-config tests |
| Redirect credential forwarding | No follow logic; every non-200 rejects | Second-socket redirect trap |
| Native rotation/revocation while active | No cached key; read at each write; generation/secret drift aborts mid-operation | Rotation, revocation-during-connect and header/body race tests |
| Leaked native error, echoed body/header | Fixed public failure without native chain; decoded-body echo rejection; task-local wire-log suppression | Native failures, escaped echo and debug-header tests |
| Secret in worker environment, artifacts or replay | Marker-only HTTP request until socket write; no env/files mutation; existing no-network workers | Child environment and real broker evidence scans |
| Lost response followed by rotation | No retries; existing consumed claim and conservative durable spend exposure | Lost-response/rotation broker test and existing recovery suite |
| Interrupted or blocked native read | Finite exchange deadline; native work off event loop; cancellation prevents late socket write | Cancellation and blocked-read timeout tests |

Write admission is the revocation linearization point. Already transmitted bytes
cannot be recalled, and a later failure can be uncertain even when no response is
available. Native administration must use fresh generation IDs and serialize its
own provisioning changes; this read-only transport adds no credential-mutation
API. It does not change publisher authority or enable a tool/network capability.

Host library composition is additive. Existing production credential routes remain
default until exact provider/tool conformance and accountable review approve use.
No security/release approval is asserted by this implementation's own review.
