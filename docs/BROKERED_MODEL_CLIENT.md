# Broker-bound canonical model client

`providers.brokered_openai.BrokeredOpenAIClient` connects the canonical `ModelClient`
port to an already-issued `RequestBoundBroker` and its async isolated worker. A
trusted host supplies one frozen request, one broker and one container instance.
This library consumes existing authority; it does not select credentials, approve
transfers, issue grants, construct spending policy or enable a live terminal mode.

Construction revalidates the request and permits only the OpenAI adapter, one user
turn containing text, no tools and an explicit output token cap. The complete
canonical request and provider payload must each fit the broker's 1 MiB request
ceiling. The local canonical response ceiling cannot exceed the existing 16 MB
wire limit. Model/context-specific budgets remain the caller's responsibility;
the model-review bridge applies its resolved budget before invoking this client.

The existing adapter projects the provider payload. Its canonical `ApprovedRequest`
hash must exactly equal the broker's public payload hash, which can now be inspected
without reading its bearer claim. The client also freezes the full canonical request
as bytes. This second binding includes local settings such as `max_output` that
are absent from the provider payload. Changing only a local response limit therefore
still rejects before worker launch, token counting or spending admission.

The first `complete` attempt consumes the client under a lock before validation or
asynchronous work. Changed requests, concurrent calls, retries and later replays
cannot obtain another attempt from that client. A pre-dispatch mismatch does not
redeem the underlying broker; only independently trusted host code holding that
still-unused broker can construct another binding. Once redeemed, the existing
broker enforces its one-use and expiry rules across all bindings.

Successful execution awaits the private claim/reply protocol, worker acknowledgement,
worker exit and exact container/guardian cleanup. It returns the host-held response
through the existing OpenAI response decoder. It checks raw reply size, exact model
identity, complete canonical response size and reported output tokens. Tool calls
are rejected. Non-completion/refusal statuses remain canonical statuses for the
caller to handle; `ModelReviewer` rejects them as review answers.

The adapter's input/output fields follow the existing
[Responses API contract](https://developers.openai.com/api/reference/python/resources/responses/methods/create).
No SDK version, provider payload mapping, price table, effort registry or provider
retry setting changes here. The host must supply the bounded, retry-free transport
and applicable spending controls. These acceptance checks occur after a host reply
exists and cannot replace transport allocation limits or aggregate spending admission.

Provider/worker/cleanup failures become coarse provider errors; cancellation propagates
through the async broker's awaited teardown. A bad response or local decode rejection
does not release an incurred charge. Cancellation after dispatch retains the existing
uncertain reservation and consumed broker grant. This client performs no repair,
retry, refund or new dispatch after failure.

Tests exercise changed request fields and local-only limits, broker payload mismatch,
concurrent attempts, replay, expiry, original-dictionary mutation, malformed/tool
responses, response budgets, retained charges and cancellation. A synthetic review
fixture runs a critic and judge through bound brokers; its explicit one-provider
fixture policy is not evidence for production provider diversity or quorum. The
Docker smoke suite additionally checks a canonical response, mismatch denial before
spending, replay denial and confirmed exact worker removal.

The next G2 work must issue review-specific grants with transfer/audit bindings,
reserve aggregate critic/judge spending, admit the judge payload after findings are
known, retain evidence and complete authorized credentialed conformance. Existing
research-assignment audit records are not relabelled as review authority. Guided
reviews still require current guidance admission independently. See the
[model reviewer](MODEL_REVIEWER.md), [async broker](ASYNC_BROKER.md) and
[roadmap](ROADMAP.md). Rollback removes this library client; existing packet and
artifact schemas, CLI commands and broker grant semantics remain compatible.
