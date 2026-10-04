# Inert session scheduling qualification

This is §31.15's inert timer/event fixture slice. The transition contracts in
`conversation_schedule.py` accept an explicit clock and local fixture metadata;
they do not read a clock, start tasks, dispatch providers/tools or install terminal
controls. Ordinary durable goals do not activate scheduling. `/loop` and production
timer/event adapters remain later work.

## Durable-goal and queue assessment

The existing conversation controller serializes author requests in one queue. It
reserves goal resources before dispatch, settles known usage, retains uncertain
reservations after failure/cancellation, and converts persisted running entries
to interrupted entries on restart. Lost semantic-evaluator responses retain
uncertainty. Goal resume rejects in-flight, uncertain or exhausted operations;
it does not reset their budgets. Both private snapshot and SQLite stores preserve
these records. Terminal resume displays pending work and requires explicit input
before dispatching it.

The queue has no production timer/event admission path. Existing goal jobs record
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

## Verification and remaining qualification

`tests/test_conversation_schedule.py` exercises cadence bounds/history, expiry,
maximum fires, schedule/task limits, backwards/nonfinite clocks, stopped goals,
stale and cross-owner bindings, duplicate/out-of-order/flooded events, request
identity, safe boundaries, steering priority, queue exclusion, acknowledgements,
overages and persistence failure. Real snapshot/SQLite cold resumes preserve goal
uncertainty alongside serialized fixture state. No live provider or credentialed
integration is used. Package smoke coverage includes these fixtures.

The fixture's scheduling snapshot is a serialized qualification artifact, not a
production registry or a new conversation storage format. Production work must
retain schedules and queue admissions through the existing owner-scoped session
store with atomic revision checks, revalidate at final dispatch, enforce source
authorization and bounded handler timeouts, and handle late steering across the
admission/dispatch boundary. The fixture host is sequential; it does not qualify
multi-process admission races. Any production settlement/refund or reconciliation
must verify exact receipts against qualified controllers. Live event ingress and
active-session timers require their own applicable background, execution, MCP,
network, credential and owner-isolation gates. This slice promises no daemon or
execution while a session is closed.
