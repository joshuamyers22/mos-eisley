# Request-bound provider grants and private IPC (fixture-tested)

`run.provider_broker.RequestBoundBroker` gives trusted host code a short-lived,
single-use bearer grant for one exact host-approved request. The
`run.isolated_broker.run_isolated_broker` library now connects it to an offline
container through private subprocess pipes. There is no paid CLI, socket listener,
or live evaluation sweep. Tests use synthetic host responses, not live evidence.

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
but explicit JSON serialization intentionally includes it for private IPC.
Do not log or persist claims. This is capability possession, not worker identity
authentication; theft permits that single approved call. It does not defend
against trusted host code, same-UID memory access, or a compromised host.

## Private pipe protocol

Host sends one grant; worker echoes a claim; host validates and redeems it, then
sends one JSON response; worker returns a hash acknowledgement and exits. The
host verifies that acknowledgement and returns its own retained response, never
worker-authored provider data. Acknowledgement proves receipt of bytes, not that a
review was performed or that a model was called. No evaluation provenance is minted.

`run.duplex.bounded_exchange` limits worker frames/offers to 1 KiB, host replies
to 16 MB, and drained stderr to 64 KiB. Newline framing rejects incomplete, extra,
oversized and early output. One cooperative deadline covers the conversation and
provider work; early output/EOF while provider work is pending cancels that work.
Disconnect detection can race dispatch: a request already sent may still charge,
so the spending controller's conservative uncertainty rules remain necessary.
Killing the attached Docker client is followed by existing exact-container removal
and watchdog receipt checks. No host mount, network access, environment key, or
Docker socket is added to the worker. Claims never appear in command arguments.

`make container` tests real-container success, tampering, replay, disconnect
cancellation and oversized frames alongside existing confinement/crash probes.
Subprocess tests additionally cover pipelining, extra/partial output, stderr
flooding, invalid host frames, caller cancellation, deadlines and nonzero exits.

## Remaining gates

- Bind grants to evaluation assignment/provenance and persist host audit boundaries
  without capability secrets. Grants are process-local and cannot be resumed.
- Independently bound upstream HTTP response buffering and run explicitly
  authorized credentialed conformance. Async cancellation cannot stop blocking
  adapters, guarantee remote cancellation, or establish invoice-level cost caps.
- Retain explicit data-transfer consent and reviewed shared-spend admission when
  introducing any paid entry point. No automatic retries or paid sweeps yet.
