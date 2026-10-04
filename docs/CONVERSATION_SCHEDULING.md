# Session scheduling and explicit loop controls

This covers §31.15's inert fixtures, recorded durable controller admission and
explicit plain/JSON/TUI controls and active-session recorded timer driving.
The transition contracts in
`conversation_schedule.py` accept an explicit clock and local fixture metadata;
they do not read a clock, start tasks, dispatch providers/tools or install terminal
controls themselves. Ordinary durable goals do not activate scheduling. The active
recorded timer adapter owns wakeups only while the session terminal is open;
production handlers and external event adapters remain later work.

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
below. The active-session recorded timer adapter is connected; production event
adapters are not connected. Existing goal jobs record
check-ins and committed results but do not authenticate external notifications or
schedule wakeups. Goal completion still requires qualified evidence/semantic
adapters. Neither the child inspection port nor the stopped review inventory is a
qualified implementation-child event source. Live background/execution/MCP gates
remain required.

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
`schedule_event_validator` for committed-result provenance; neither a declared
source ID nor an event payload grants authority. Task-scoped live scheduling is
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

Remaining work includes bounded trusted handler timeouts and external ingress
authentication.
The observer/validator ports must be supplied by qualified host adapters, not by
project/model text. Production settlement/refunds and reconciliation must verify
exact receipts against qualified controllers. Live event ingress and production
handlers retain the applicable background, execution, MCP, network, credential
and owner-isolation gates. This slice promises no daemon or work while a session is
closed.
