# Request-bound provider grants (library foundation)

`run.provider_broker.RequestBoundBroker` gives trusted host code a short-lived,
single-use bearer grant for one exact host-approved request. It is not yet wired
to a container, CLI, socket, or live evaluation sweep. No paid calls are needed
for its tests, and this milestone does not enable live evaluation evidence.

The host snapshots the canonical request and configures the OpenAI spending
transport, credentials, endpoint, reviewed pricing, and shared ledger. A claim
contains only a random 256-bit capability and the request hash. Unknown fields,
wrong capabilities/hashes, malformed or oversized claims, expiry, and replay fail
before token counting or spending admission. A process-local lock consumes a valid
grant before any await. Concurrent claims cannot dispatch twice. The worker cannot
submit replacement prompts, model/effort settings, tools, endpoints, or budgets.

The broker requires the existing shared-ledger spending controller. Failure,
timeout, or cancellation burns the grant; uncertain generation retains its full
reservation under the controller's existing rules. The grant lifetime (at most
60 seconds) also bounds the cooperative provider deadline. API errors are generic.
Request snapshots have a 1 MiB serialized ceiling; claims have a 1 KiB wire ceiling.

OpenAI's [authentication guidance](https://developers.openai.com/api/reference/overview#authentication)
informs keeping provider keys exclusively in trusted host configuration, never in
the worker claim. The claim itself is a secret: its repr omits the capability,
but explicit JSON serialization intentionally includes it for future private IPC.
Do not log or persist claims. This is capability possession, not worker identity
authentication; theft permits that single approved call. It does not defend
against trusted host code, same-UID memory access, or a compromised host.

## Remaining gates

- Add bounded private container/host request-response IPC, fail-closed framing,
  disconnect cancellation, and real-container negative probes before integration.
- Bind grants to evaluation assignment/provenance and persist host audit boundaries
  without capability secrets. Grants are process-local and cannot be resumed.
- Independently bound upstream HTTP response buffering and run explicitly
  authorized credentialed conformance. Async cancellation cannot stop blocking
  adapters, guarantee remote cancellation, or establish invoice-level cost caps.
- Retain explicit data-transfer consent and reviewed shared-spend admission when
  introducing any paid entry point. No automatic retries or paid sweeps yet.
