# Session scheduling and explicit loop controls

This covers §31.15's inert fixtures, recorded durable controller admission and
explicit plain/JSON/TUI controls, active-session recorded timer driving and
qualified bounded local-result handlers, inert authenticated external ingress and
explicit credentialed loopback transport.
The transition contracts in
`conversation_schedule.py` accept an explicit clock and local fixture metadata;
they do not read a clock, start tasks, dispatch providers/tools or install terminal
controls themselves. Ordinary durable goals do not activate scheduling. The active
recorded timer adapter owns wakeups only while the session terminal is open;
trusted reads and signed envelopes are bounded. The optional loopback transport
shares that owner; remote service deployments remain separate qualification.

## Explicit controls

Plain, JSON and TUI terminals share one command handler. Creation requires a
selected working durable goal and explicit limits within its frozen ceiling and
deadline. Creation starts no immediate model call or queue entry; the active
session driver waits for the cadence deadline. A bounded example:

```text
/goal new Inspect committed CI results
/loop create {"schedule_id":"ci-watch","task_id":"ci","prompt":"Inspect committed CI results","interval_seconds":60,"expires_in_seconds":300,"maximum_fires":2,"input_bytes":32000,"output_bytes":24000}
/loop status ci-watch
/loop status ci-watch --json
/loop cancel ci-watch
```

| Command | Effect |
| --- | --- |
| `/loop` or `/loop status [ID]` | Inspect all schedules or one retained schedule without changing state or spend. |
| `/loop status [ID] --json` or `/loop --json` | Emit the same structured report as JSON. |
| `/loop create JSON` | Persist a bounded recorded schedule with explicit task, cadence, expiry and resource limits. |
| `/loop cancel ID` | Stop future admission and retire queued intents while retaining charges and unresolved exposure. |
| `/loop resume ID` | Revalidate an eligible paused schedule without resetting limits or dispatching work. |
| `/loop help` | Show creation fields and command syntax. |

Creation requires `schedule_id`, `task_id`, `prompt`, `interval_seconds`,
`expires_in_seconds`, `maximum_fires`, `input_bytes` and `output_bytes`.
Intervals and lifetime are bounded to 1–86,400 seconds, fires to 1–16, and
input/output allowances to 1–1,000,000 bytes, further constrained by the goal.
Attempts equal maximum fires; paid spend, corrections and reviews have zero
allowance. Fixed cadence is the default. For dynamic cadence, supply
`"cadence":"dynamic"` and explicit `minimum_interval_seconds` and
`maximum_interval_seconds`. The trusted `set_schedule_cadence` host API revalidates scope and retains bounded
cadence changes; terminal/model text cannot change cadence implicitly.

The CLI derives owner/session/workspace, observed revision, goal definition and
recorded policy bindings; command JSON cannot provide authority or event sources.
Its read-only workspace observer uses the trusted Git broker for supported Git
workspaces and stable owned-directory identity for other directories. The policy
pins the recorded cassette, goal definition and active-session recorded timer
capability. Schedules made under the earlier non-driving policy do not migrate
implicitly: their mismatched policy prevents resume/admission. This recorded text-only slice
grants no tools or paid execution. An API controller without a qualified observer
rejects creation and resume, but can still inspect or cancel retained schedules.

Inspection includes effective cadence/history, expiry, fire counts, remaining
schedule and aggregate task budgets, pending notifications, stop reasons, and
reserved/uncertain operation IDs with their queue states. Reports capture one
immutable session revision. Clock-expired records are visibly ineligible without
an inspection write. JSON terminal events retain structured schedule records for
every successful control. TUI reports preserve drafts; rejected typed commands
remain in the editor. Pasted commands and multiline submissions stay literal.

Resume requires a working goal, current bindings, a safe queue boundary and
remaining budgets/lifetime. Cancelled, expired, exhausted, blocked or uncertain
work cannot be reopened by the command. Cold restart pauses clean schedules and
requires explicit revalidation. Resume restarts the interval from the current
validated clock; it discards old pending timer notifications and does not replay
missed or uncertain work. There is no `/loop run`, `fire` or external event command.

## Active-session recorded timer driving

One `ActiveSessionTimers` owner serves the shared plain/JSON/TUI terminal. A
monotonic async waiter wakes that existing owner at the nearest retained deadline,
checking the wall clock at most one second apart. It never starts a separate
provider worker. The timer owner requires the trusted schedule observer and
recorded scope; live task controllers and missing observers cannot drive timers.
The JSON report's `automatic_dispatch` flag describes current qualified terminal
ownership, while each fixture record continues to grant no execution authority.

The owner lets the input reader expose waiting user controls before either
admission or dispatch. After an atomic admission it yields another input boundary:
user steering can retire that queued intent before it starts. Side/diff work, author
turns, goal evaluation/reservations, queued user work and plain composition defer
timers without repeatedly writing due records. TUI editor drafts remain unsent and
are preserved across timer reports and author rendering.

At an idle boundary, timers admit at most one recorded intent per owner turn,
ordered by deadline and ID. Missed intervals coalesce into one fire, and the next
deadline advances from the observed time. Multiple schedules share the same queue,
so no task dispatch overlaps. Every admission and dispatch retains the existing
owner/workspace/revision/policy/goal, expiry, exact request and resource guards.
Known undispatched holds are included in the shared goal budget for other schedules
and ordinary author turns, without double charging the intent being dispatched.
Inherited fork allowances include the same known holds and appear in inspection.
Input/context/scope rejection pauses or blocks the schedule rather than retrying
each interval; lost persistence acknowledgements remain fatal and restart-safe.
Backwards or nonfinite clocks pause work for explicit revalidation. Exhausted,
expired, cancelled and uncertain records have no active waiter.

EOF, quit, directory handoff and cancellation release the waiter. Clean active
schedules pause before controller ownership is released; queued intents become
known skipped entries with conservative charges retained. Already running work
uses the existing cancellation/result accounting. Closed sessions start no timers,
and cold resume requires `/loop resume ID` after revalidation. A replacement timer
owner cannot enter while shutdown is persisting. No paid/provider-network calls,
tools, daemon, closed-session work or external event ingress are enabled by this
recorded qualification.

## Durable-goal and queue assessment

The existing conversation controller serializes author requests in one queue. It
reserves goal resources before dispatch, settles known usage, retains uncertain
reservations after failure/cancellation, and converts persisted running entries
to interrupted entries on restart. Lost semantic-evaluator responses retain
uncertainty. Goal resume rejects in-flight, uncertain or exhausted operations;
it does not reset their budgets. Both private snapshot and SQLite stores preserve
these records. Terminal resume displays pending work and requires explicit input
before dispatching it.

The recorded controller now has explicit trusted host admission APIs, described
below. The active-session recorded timer adapter and qualified local-result
adapters are connected. Goal jobs retain controller-owned commit revisions, and
the existing child inspection port supplies authorized retained implementation
reports. The separate inert signed adapter below authenticates external
notifications without a network listener. Goal completion still
requires qualified evidence/semantic adapters; result notifications do not
prove completion or grant integration authority. The stopped review inventory
remains outside this source boundary. Live background/execution/MCP gates remain
required.

## Trusted handler qualification and bounded timeouts

Assessment found synchronous observer/validator calls without whole-operation
read deadlines, and no adapter connecting retained results to schedule admission.
`ScheduleReads` now bounds read operations with a monotonic deadline: two seconds
by default, explicitly configurable by the trusted host up to ten seconds.
Creation, admission, polling, registration, cadence changes, resume and dispatch
revalidation share their deadline across nested reads; the owner checks that
it remains valid before committing. Cancellation invalidates the active read
operation. Exceptions produce bounded generic rejection messages without callback
payloads or paths; failed timer handling pauses for explicit revalidation.
Persistence failures retain the existing fatal recovery behavior.

Only one read worker may run per controller. Timeout/cancellation discards its
late result and quarantines the lane. Python cannot forcibly stop an arbitrary
thread: an abandoned read may finish later, but cannot admit work through its
returned result. No replacement reader starts while it runs. Explicit reset/resume
requires an idle controller and a finished reader, and preserves all counters,
charges and uncertain exposure. Host callbacks must remain read-only and must
not dispatch providers/tools or modify controller/store state. This deadline
wrapper is a qualification boundary for trusted readers, not containment for
untrusted executable code or a guarantee that their underlying I/O is killed.

Trusted hosts create local sources with `LocalResultAuthorization`, freeze the
resulting `authorization.pin` in `InertScheduleSpec.local_source_pins` alongside
its source allowlist, and call `register_schedule_source` with the current session
revision. The pin includes source kind, the entire owner/session/task/workspace/
revision/policy/goal binding and explicit result target identities. Registration
changes no durable state or spend. It is unavailable to command/model text.
At restart the host must register the exact authorized source again before
resume or dispatch; retained pins do not manufacture access credentials.

`CommittedChildResults` wraps the existing `ChildInspectionSource`. It checks the
frozen implementation assignment digest, parent task, workspace and currentness
before requesting a report. The existing controller verifies the retained report
reference and guards concurrent revision changes. Review children are rejected
before any sealed report read. Completed, failed and cancelled children may notify
only with an available complete retained report; missing/partial output cannot
wake the queue. These notifications grant no success or integration approval.

`CommittedTestResults` wraps durable `GoalJob` records and a trusted artifact
lookup. `report_goal_job` stamps terminal retained results with the acknowledged
parent commit revision; caller-supplied revisions and replacement results are
rejected. The adapter verifies registered operations, the current goal definition,
artifact digest, an executed nonempty `GoalTestReceipt`, result consistency and
explicit execution workspace/input hashes. Those execution hashes are separate
from session workspace identity. Legacy unstamped jobs emit no notifications:
no commit sequence is inferred or migrated. Empty optional fields are omitted
from old spec/job serialization to preserve frozen hashes and operation IDs.

`poll_schedule_sources` reads bounded batches and admits at most one metadata
notification per idle owner turn. The active terminal checks sources at its
bounded one-second wake boundary, without model polling. A working goal can wake
before the cadence deadline. A waiting goal can retain result metadata but cannot
dispatch until the existing goal controller independently permits work; it never
implicitly resumes a stopped goal. Input, side/diff work and queued/running work
retain priority. Source batches cap at 16 events and 32,000 metadata bytes; each
result caps at 4096 bytes with payload omitted. Durable sequence cursors, 16 recent
IDs and a 64-event lifetime ceiling bound duplicate/out-of-order/flood handling.
Duplicates do not reread qualified artifacts, enqueue work or reserve exposure.

Both session stores preserve metadata cursors separately from the atomic
intent/queue commit. Lost acknowledgements stop the owner; recovery retains
cursor progress, skipped/uncertain intent identities and charges without replay
or budget reset. Tests cover stale bindings/assignments, source substitution,
failed/cancelled children, invalid and legacy test receipts, handler failure,
deadlines/cancellation, late completion, bounded floods, dispatch rejection,
user steering and metadata/queue acknowledgement loss on snapshot and SQLite.
The credentialed loopback slice is qualified below. Remote deployments,
live/paid tools/providers and closed-session execution remain separate work.

## Inert authenticated external event ingress

`InertExternalIngress` is an explicit owner API adapter, without a listener,
network/MCP session, credential lookup, subprocess runner or outbound response
channel. It verifies owner-provisioned Ed25519 public keys; it holds no signing
key. This qualifies signed envelope admission and recovery in recorded sessions,
not any credentialed service or remote transport deployment.

The host freezes `ExternalSourceAuthorization.pin` in the existing source
allowlist and `local_source_pins` field (the retained field names also cover
external sources). The authorization binds source/key IDs, verification-key
digest, full owner/session/task/workspace/revision/policy/goal scope, expiry,
maximum event age and rolling rate allowance. Registration cannot extend schedule
lifetime or obtain a key from project/model text. Resume requires exact trusted
registration; swapping a key, scope or rate policy changes the pin and is rejected.

A sender signs `DOMAIN + canonical_bytes(ExternalEventBody)` with Ed25519, where
`DOMAIN` is `b"mos-eisley:schedule-event:v1\x00"`. The body includes schema version,
source/key/event IDs, monotonic source sequence, full binding, occurrence/expiry
and an opaque UTF-8 payload. `SignedExternalEvent` contains that body and a
128-character lowercase hexadecimal signature. The envelope must equal its
canonical JSON representation; duplicate keys, unknown fields and alternate wire
interpretations are rejected. Payloads cap at 4096 UTF-8 bytes and envelopes at
16,384 bytes. Events from the future, expired events and events outside the pinned
maximum age/lifetime are rejected.

`receive_external_event(schedule_id, source_id, packet, expected_revision=...)`
authenticates and revalidates the envelope through the registered adapter. Its
trusted workspace observer defaults to `observe_branch_workspace`, using the
existing bounded Git/read broker for Git workspaces and stable owned-directory
identity elsewhere. It observes only the host-selected workspace, twice across
verification/admission; sender paths, refs and payload instructions are never
followed. The normal schedule observer still revalidates scope before commit and
again at queue dispatch. Tests use both an explicit inert broker fixture and a
real Git revision change. Reads share the qualified operation deadline; hung or
cancelled reads cannot append late metadata.

Successful ingress commits only the latest per-source payload hash/size omission
receipt (at most four), replay cursor
and rate history through the existing snapshot/SQLite schedule header. Plain
inspection discloses omitted payloads; JSON also exposes their receipt metadata. It creates
no queue entry, provider/tool call, goal completion, approval or user steering.
The existing active owner subsequently coalesces pending notifications at a safe
boundary, using only the owner-selected prompt. User input retains priority before
and after intent admission. External payloads never enter model prompts, review
contexts or inspection output; the adapter has no API for returning private
reports/artifacts to a sender.

Each source has a host-clock rolling window, with an explicit allowance of 1–16
accepted events per 1–3600 seconds. Accepted timestamps and sequence progress
commit atomically, survive restart and are retained across pause/cancellation;
source substitution, rollback clocks and guarded resume cannot reset them. Rate
records must match external cursor identities and valid acceptance times.
Duplicates/out-of-order envelopes remain authenticated but do not reserve work or
spend rate allowance. Durable high-water sequences reject original replays after
the bounded 16-ID recent window evicts them. The shared 64-event lifetime ceiling
and four-source limit still apply. A separate bounded in-memory 16-attempt/second
limiter caps owner-entry parsing/signature work, including forged/replayed packets;
it grants no durable authority and resets with adapter construction. Future remote
transports must also enforce their own connection/admission limits.

A lost acknowledgement after metadata commit retains both cursor and rate charge;
reopening and re-registering cannot reaccept the original envelope or replenish
the rolling allowance. Failure before commit retains neither. Queue/running
acknowledgement loss uses existing known-skipped/uncertain recovery, preserving
all exposure without execution replay or automatic reconciliation. Tests cover
forged keys/signatures/sources, cross-owner/task/workspace claims, wire bounds,
floods, stale broker observations, concurrency, cancellation, late reads, steering
and metadata/queue/running acknowledgement loss on both stores.

The explicit credentialed loopback transport below adds bounded socket admission
and generic sender acknowledgements. Remote deployments retain separate
MCP/network/credential/owner-isolation qualification. No live/paid provider/tool
execution, daemon or closed-session wakeup is enabled here.

## Credentialed loopback transport qualification

The boundary assessment found that `MCPDispatcher`, `mcp_http.py` and
`mcp_oauth_store.py` authorize outbound tool clients. Their endpoint, tool,
execution and OAuth/bearer grants do not authorize inbound schedule events.
The existing HTTP exception permits explicitly selected literal loopback, and
the credential backend selects native macOS Keychain/Linux Secret Service rather
than a plaintext fallback. Schedule ingress uses a separate credential namespace;
it neither shares MCP OAuth tokens nor refreshes/provisions credentials.

`LoopbackEventTransport` is the first qualified network adapter. A trusted host
must explicitly construct `IngressTransportGrant` and
`LoopbackIngressSettings(allow_loopback_http=True)`, register the exact signed
source, and pass the adapter as `terminal(..., ingress_transport=adapter)`.
That shared terminal serves plain, JSON and TUI renderers. No `/loop` argument,
model text, project configuration, startup discovery or sender request enables a
listener or grants credentials. The host chooses the ephemeral or explicit port;
the only address is `127.0.0.1` and the only route is `POST /events`.

The grant freezes the full owner/session/task/workspace/revision/policy/goal
binding, schedule/source identities, signed-source authorization digest,
credential identity/fingerprint and expiry. Provision a cryptographically random
32-byte token encoded as 64 lowercase hex characters through the host's trusted
credential workflow. Its native keychain service is
`mos-eisley.schedule.ingress.v1`; the account is `grant.account`, the canonical
SHA-256 of the entire grant. Provisioning and sender delivery are outside this
read-only adapter. Missing/rotated/revoked credentials fail closed; environment
variables and outbound MCP credentials provide no fallback. Opening requires the
qualified timer owner and current process UID before any vault read or listener.
Each admitted frame rechecks the vault before signature/broker validation and
immediately before owner commit, including duplicates. Revocation observed by
that final check rejects admission; revocation after committed acceptance cannot
undo retained metadata or charges.

Send the exact canonical signed envelope as the JSON body, with exact literal
`Host: 127.0.0.1:PORT`, `Content-Type: application/json`, `Content-Length`, and
`Authorization: Bearer TOKEN`. Duplicate/unknown headers, alternate paths/hosts,
chunked bodies and extra pipelined bytes are rejected. Headers are capped at
4 KiB and signed envelopes at 16 KiB. At most four connections and four buffered
frames are allowed (each configurable downward), with sixteen accepted socket
attempts per second. Over-limit connections close; framed rejections use the same
fixed `400 {"status":"unavailable"}` response. Acceptance and authenticated
retries use the same fixed `200 {"status":"received"}`. Responses expose no
owner, event, schedule, payload, artifact, report, exception or credential detail.

Socket tasks only read bounded frames and await acknowledgement. The active owner
drains at most one frame at an idle boundary, after waiting user input; active
turns, drafts and branch/diff work defer admission. Metadata does not directly
start a provider call. The existing timer queue then revalidates all scope,
expiry, resource and steering gates. Revision claims still use the trusted broker,
and durable duplicate/rate records still commit atomically in snapshot/SQLite.
Requests have a whole-operation monotonic deadline (default 5 seconds, allowed
0.05–30), shortened further by the existing trusted-read deadline. Startup and
response cleanup are bounded too. Hung vault/observer reads quarantine the same
single read lane; late outcomes cannot commit. Closing, EOF, owner loss and
interrupt cancellation discard uncommitted frames and close connections.

A disconnect detected before owner admission cancels its frame. A non-consuming
kernel socket check also catches disconnects during synchronous trusted-read
waits before the final owner commit. Disconnect or
deadline after the commit boundary is an uncertain sender acknowledgement, not a
rollback: retries must authenticate again and cannot replenish rate limits,
reserve another intent or refund exposure. Queued/running restart retains the
existing skipped/uncertain behavior without replay. Listener and credentials
must be explicitly reattached after guarded resume.

`tests/test_conversation_schedule_transport.py` exercises real localhost sockets
with synthetic tokens and a fixture credential backend on both session stores:
owner/source isolation, signature rejection, generic responses, revocation during
validation, rotation, stale revisions, expiry, disconnects, acknowledgement loss,
queue/connection limits, deadlines, hung/cancelled reads, shutdown, restart and
shared terminal dispatch. Backend selection is tested without opening the host
vault. Native keychain provisioning/end-to-end behavior, remote TLS or MCP service
deployments, and live/paid execution remain separate qualification. This slice
provides no public listener, daemon or closed-session execution.

## Fixture behavior

The frozen fixture spec binds an explicit prompt/task to its owner, session,
workspace identity, observed revision, policy and goal definition. Fixed cadence
has one interval; dynamic cadence changes stay within frozen minimum/maximum
intervals and retain their effective interval history. The spec requires expiry,
at most 16 fires, explicit resource ceilings, and zero paid allowance. Creating a
spec or observing a timer/event does not enqueue or execute work.

Timers coalesce missed intervals into one notification and move the next due time
forward from the observed time. A backwards clock pauses the fixture until explicit
revalidation; expiry and cancellation prevent further admission. Dynamic interval
history is capped at 16 entries.

Local test/child fixture events use an allowlist of at most four source identities,
stable event IDs and monotonically increasing per-source sequences. Duplicate and
out-of-order events are ignored. A source retains a 16-ID replay window and a
durable sequence high-water mark; accepted notifications are capped at 64 for the
schedule lifetime. Original replayed sequences cannot bypass the window after
eviction. Payload size is capped at 4096 bytes and explicitly omitted; payload
content never becomes the prompt, user steering, approval or publication authority.
These local records are test inputs, not an authenticated external ingress API.

The test-only `QueueFixture` derives a gate from the real controller and prepares
the exact candidate request using a copied controller. Wakeups wait while author,
review or side work is running, user messages are queued, a goal reservation or
evaluation is held, or the task already has pending work. User steering is processed
first. Timer and event notifications combine into one intent. Two fixtures targeting
the same task use the existing queue exclusion rather than another runnable queue.

Admission reserves one unpaid author attempt, input bytes and worst-case output
before the host persists an intent and appends the selected prompt to the existing
queue. Its stable operation ID binds the frozen schedule, fire ordinal and exact
request hash. Schedule ceilings and the existing aggregate task ceiling both apply.
The real controller separately enforces its goal/branch budgets at dispatch.
Completion requires the exact reserved operation and known fixture usage; duplicate
receipts are idempotent only when their usage and result identity match. Conservative
reserved charges remain retained and overages are added rather than refunded.

Cold restart never dispatches or assumes an admission succeeded. A reserved intent
with a lost acknowledgement becomes uncertain exactly once; its operation identity,
fire count and charges remain. It cannot resume, replay or self-reconcile. Clean
restart pauses for explicit owner/workspace/revision/policy/goal revalidation and
preserves exposure. One already-coalesced notification can remain pending; missed
intervals do not form a catch-up backlog. A paused/cancelled/completed/blocked,
expired or uncertain goal cannot be advanced or resumed by a wakeup.

## Durable storage and recorded controller admission

`ConversationController` accepts a trusted `schedule_observer` that independently
observes current owner/session/workspace, revision, policy and goal bindings.
`add_schedule`, `admit_schedule`, `cancel_schedule` and `resume_schedule` require
an explicit expected session revision. Creation preserves existing task exposure
and cannot enlarge its lifetime/ceilings. Admission is a synchronous host tick,
not a timer task. Local event admission additionally requires a trusted
`schedule_event_validator` for legacy fixture provenance, or a registered
qualified source matching the schedule’s durable authorization pin; neither a
declared source ID nor an event payload grants authority. Task-scoped live scheduling is
still rejected.

The optional `schedules` header field retains bounded `StoredSchedule` records
and operation-to-message bindings in the existing session snapshot/SQLite store.
Old sessions omit the field. One revision update contains the reservation, exact
request digest and queue entry. Validation rejects orphaned, duplicated, cross-owner
or mismatched bindings, including their goal definitions and lifecycle states.
SQLite working states preserve bindings alongside archived history. Normal author,
memory, branch and goal updates retain schedule records; forks do not clone them.

The stores' held session locks prevent competing writer/resume owners. Schedule
control methods also serialize concurrent host calls and reject stale revisions.
No separate scheduling registry or runnable work queue is introduced. A failed save
stops the controller. An acknowledgement lost after commit leaves both intent and
queue entry durable; a failure before commit leaves neither.

Dispatch re-observes the current binding and expiry and verifies the exact prepared
request digest before persisting running state. It checks cancellation/binding again
after the running callback and before calling a provider. User input arriving while
a wakeup is still queued atomically cancels that old queue entry and marks its intent
`skipped`, with a visible reason. The schedule pauses for explicit revalidation and
a future tick. This preserves user priority and avoids executing an older prompt
without the newer user context. Its fire count and conservative schedule exposure
remain charged; no author exchange was consumed by the skipped entry.

Queued wakeups on cold restart are likewise known undispatched: they are skipped,
their entries cancelled, and their charges retained. Running wakeups become
interrupted/uncertain alongside the existing goal/branch recovery. Repeated resume
does not increment uncertainty again, reset charges or recreate the intent. Clean
schedules pause for explicit revalidation. Cancellation stops future admissions;
already-entered provider work may return its retained result while the schedule
stays cancelled. Unknown cancellation/failure preserves uncertainty. There is no
automatic retry or scheduling reconciliation adapter.

## Verification and remaining qualification

`tests/test_conversation_schedule.py` exercises cadence bounds/history, expiry,
maximum fires, schedule/task limits, backwards/nonfinite clocks, stopped goals,
stale and cross-owner bindings, duplicate/out-of-order/flooded events, request
identity, safe boundaries, steering priority, queue exclusion, acknowledgements,
overages and persistence failure. Real snapshot/SQLite cold resumes preserve goal
uncertainty alongside serialized fixture state. No live provider or credentialed
integration is used. Package smoke coverage includes these fixtures.

`tests/test_conversation_schedule_storage.py` exercises atomic header/queue commits
on both backends, exact dispatch revalidation, late user priority, cancellation
before/during provider work, lost admission/running acknowledgements, repeated cold
resume, retained charges, concurrent host admission/cancellation, competing store
owners, committed-source validation and SQLite archived history. Recorded fixture
clients provide results; no live provider or credential is used.

`tests/test_conversation_loop.py` covers explicit creation, strict authority/limit
validation, shared command routing and acknowledgements, read-only plain/JSON
reports, retained exposure, both storage backends, guarded restart/resume,
uncertain operations, stale revisions/policies, fatal persistence failures,
literal paste and TUI draft preservation.

`tests/test_conversation_schedule_driver.py` exercises bounded wall/monotonic
waiting, fixed/dynamic cadence, missed intervals, expiry/resource caps, busy
sessions, input priority before and after admission, cancel/stop/EOF, composition
and editor preservation, owner exclusion, unsafe clocks and bindings, failed
pre-dispatch validation, lost acknowledgements, clean/uncertain restart and no
replay. Real CLI subprocesses consume an exact recorded timer request on both
storage backends. Package smoke coverage includes the driver.

`tests/test_conversation_schedule_handlers.py` and
`tests/test_conversation_schedule_sources.py` qualify bounded reads and committed
local notifications, including cancellation, hung handlers, late completion,
stale sources, floods and lost acknowledgements. Package smoke includes both.

`tests/test_conversation_schedule_ingress.py` qualifies the inert signed adapter,
real broker revision checks and durable rate/replay recovery on both stores.
Package smoke includes the same coverage. The credentialed loopback socket
fixtures are also included in package smoke.

Remaining work includes remote credentialed transport deployments, native vault
end-to-end qualification and live/paid execution adapters.
The observer/validator ports must be supplied by qualified host adapters, not by
project/model text. Production settlement/refunds and reconciliation must verify
exact receipts against qualified controllers. External event ingress and live/paid
handlers retain the applicable background, execution, MCP, network, credential
and owner-isolation gates. This slice promises no daemon or work while a session is
closed.
