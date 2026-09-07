# Request-bound provider grants and private IPC (fixture-tested)

`run.provider_broker.RequestBoundBroker` gives trusted host code a short-lived,
single-use bearer grant for one exact host-approved request. The
`run.isolated_broker.run_isolated_broker` library now connects it to an offline
container through private subprocess pipes. An explicitly acknowledged
`openai-conformance` CLI now composes these pieces for exactly one assignment;
there is no socket listener or live evaluation sweep. Tests use synthetic host
responses, not live evidence, and no credentialed run has been recorded.

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

## Assignment audit and crash inventory

Trusted host code binds each conformance grant to a blinded batch, sample,
candidate, evaluation-request hash, exact provider-request hash, reviewed spending
policy, ledger identity and ledger-entry identity. The claim includes the resulting
authorization hash, so a claim cannot move between otherwise similar assignments.
Private `authorization.json`, `admission.json`, and `outcome.json` files form a
hash-linked sequence. Admission is fsynced before token counting or spending
reservation; outcomes record only a generic status and an optional response hash.
They contain neither bearer capabilities nor raw provider errors.

`inspect_broker_recovery` compares one audit with an independently trusted expected
authorization and the named shared ledger. It classifies `prepared`, `admitted`,
and `finished` phases alongside `absent`, `held`, `settled`, `uncertain`, or
`violation` ledger state. Missing outcomes never become successful evidence, even
if spend settled: the response may have been lost. Every recovery state sets
`retry_permitted=false`; recovery is inventory, not replay or budget release.
Corrupt, substituted, partial, or incorrectly chained records fail closed.

The read-only CLI exposes that single-audit inspection without directory scanning:

```console
mos broker-audit-status \
  --audit-dir .mos-eisley/broker-audits/RUN \
  --expected-authorization trusted/RUN-authorization.json \
  --spend-ledger .mos-eisley/spend.sqlite
```

The expected authorization must be a separately supplied regular file; the CLI
rejects using the audit's own `authorization.json` as its trust anchor. Output is
one JSON event containing phase, ledger state, hashes, and
`retry_permitted: false`. The command does not scan for audits, contact a provider,
write recovery files, settle ledger entries, remove containers, or authorize a
replacement call. Operators must separately establish that old processes and
guardians are no longer active before investigating incomplete states.

## Remaining gates

- Strict response and terminal-failure validation now produces separate, non-scoreable
  [brokered conformance artifacts](BROKERED_EVALUATION.md). Exact-batch assembly
  preserves failures but explicitly does not issue live raw results. Promote it into
  live evaluation provenance only after credentialed conformance passes; grants remain
  process-local and cannot be resumed. Add broader audit inventory only if it retains
  an independently trusted expected-authorization set.
- Run the implemented command under separate operator authorization and preserve
  its credentialed conformance result. Decoded upstream HTTP bodies are independently
  bounded for non-streaming SDK operations, but async
  cancellation cannot stop blocking
  adapters, guarantee remote cancellation, or establish invoice-level cost caps.
- Retain explicit data-transfer consent and reviewed shared-spend admission for
  every paid entry point. No automatic retries or paid sweeps exist.
