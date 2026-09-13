# Asynchronous isolated broker lifecycle

`run_isolated_broker_async` makes the existing request-bound broker usable from an
async caller. `OfflineContainer.exchange_async` awaits the same private worker
claim/reply protocol, then confirms worker exit and exact container cleanup before
returning. This is a library prerequisite for live reviews; the terminal still
uses recorded reviews and no new paid command or authorization path is exposed.

Both container entry points share one create-command builder. Immutable image
identity, implicit-volume rejection, no host mounts, no network, read-only image,
unprivileged UID, resource limits and a ready detached cleanup guardian remain
mandatory. Claims travel over private stdin/stdout; provider credentials remain on
the trusted host. The broker still binds one exact payload, consumes its grant
before dispatch and requires the shared spending ledger. The async wrapper returns
the host-held response only after validating the worker's hash acknowledgement.

Docker setup/inspection and guardian operations run off the event loop. Cancellation
waits for each owned operation to finish so its newly created container ID or
guardian handle can be captured and cleaned up. A lost create result triggers
cleanup using that invocation's generated name; a known ID uses exact-ID removal.
The event loop remains available during these waits. Each parallel review needs its
own container instance; simultaneous async reuse of one instance is rejected.

The active private exchange runs on the caller's event loop. Cancellation reaches
the host handler once, and the caller awaits handler and pipe teardown. Further
caller cancellations cannot interrupt that teardown or the later container/guardian
cleanup. The pipe layer also avoids cancelling tasks a second time when `gather`
has already cancelled them: a second cancellation could interrupt a handler's
spending cleanup. Cancellation during successful response inspection or cleanup
still discards the response. Cleanup failures never return success.

A cancelled provider exchange can still incur charges. Existing spending behavior
retains an uncertain reservation after dispatch; the broker grant remains consumed.
Cancellation does not authorize replay, retry or release of an uncertain charge.
Setup and cleanup retain their existing operation bounds; the 1–60 second argument
covers the cooperative private exchange and informs the guardian lease. It is not
a whole-lifecycle deadline. Awaited cleanup can delay cancellation, and trusted
host handlers must cooperate with cancellation. This does not claim a hard deadline
against hostile host code or an unresponsive Docker daemon.

Validation includes real subprocess pipes with controlled lifecycle operations,
shared-ledger tests for in-flight cancellation, repeated cancellation, setup races,
cleanup failure, malformed acknowledgements and unchanged confinement flags. The
Docker smoke suite also exercises the async path with real containers: tampered
claims, valid roundtrip, replay denial, disconnect, oversized frames, explicit
cancellation, retained spending and confirmed removal. Passing these synthetic
checks does not establish credentialed provider conformance or live review quality.

See [the model-review bridge](MODEL_REVIEWER.md) and [the roadmap](ROADMAP.md).
G2 still needs exact-request review admission, aggregate critic/judge spending,
audit retention, dynamic judge-request binding and authorized credentialed tests.
Rollback removes the async entry points; synchronous callers and saved artifact
schemas remain compatible. Retain the pipe cancellation fix to preserve handler
cleanup in the existing synchronous broker path too.
