# Local recorded background qualification

This batch connects active-session timers and a bounded local child to the existing
conversation owner, goal ledger, queue and private snapshot/SQLite stores. The
supported execution route is **recorded, unpaid, read-only analysis**. It offers
no filesystem tools, worktree writes, live provider calls, external ingress or
integration approval. General delegated coding and default delegation policy still
require the execution/VCS/E2 gates in plan §§14.2 and 14.2.1.

## Active session ownership

An open plain, JSON or TUI terminal claims one timer owner. Explicit `/loop`
creation or resume makes an eligible recorded schedule available to that owner;
the terminal uses a bounded asynchronous waiter and its existing dispatch queue.
It admits at most one wakeup per turn, yields to already waiting user input, and
checks input again between admission and dispatch. Busy author, side, diff,
composition and child work defer admission. Missed intervals coalesce, rather than
creating catch-up work. Ordinary goals do not create schedules.

Expiry, resource limits, stopped goals, stale bindings and unsafe clocks stop
admission. Losing the host observer suspends active schedules; reconnecting it
does not reopen them without explicit resume. EOF and terminal exit pause clean
schedules and retire known undispatched intents while retaining charges. Running
or interrupted operations preserve uncertainty. Cold restart never runs a child
or wakeup automatically. There is no daemon or work after the session closes.

## Local child host connection

`ConversationController` accepts `local_child_authorizer` and
`local_child_executor` together. They are trusted host dependencies; model/project
text cannot install them. The authorizer independently approves the exact frozen
`ImplementationAssignment`, owner/session scope, plan and test digests, current
workspace observation and finite expiry. It must obtain approval from the real
creator workflow when used outside an explicit fixture. Declaring digests in
command text does not supply that approval.

The host explicitly calls `run_local_child(assignment, cassette,
expected_revision=REVISION)`. No model or timer can spawn children. Admission
requires a working goal and safe boundary, at most four retained children, one
running child, depth one, a single unpaid attempt and allowances within the parent
goal. Fork/task-tool contexts remain rejected. The child's fresh context contains
only its assigned objective and frozen plan/test identities. Parent transcripts,+memory, review evidence and pending steering are not copied.

One session commit retains the running child and its required parent job and
charges the parent goal before container launch. Resource reservations are
conservative and are not refunded. The child's separate exact recording cannot
reset parent budgets or consume the parent's author cassette cursor. Failure,
cancellation, stale approval, lost acknowledgement and cold restart retain the
reservation and pause the goal with uncertainty; repeated restart does not add
uncertainty again. This route has no retry or reconciliation command.
Goal pause/cancellation propagates to the owned child exchange and waits for its
bounded cleanup. Late failure cannot reopen a cancelled goal.
Terminal stop, quit and EOF likewise await owned child cleanup before returning.

`DockerLocalChild` uses the existing `OfflineContainer` and cancellation-safe
async exchange. An immutable reviewed image executes the exact child worker with
no host mounts, network, inherited credentials or tool dispatcher. The worker
receives only a bounded job over stdin; offer and acknowledgement bind job and
execution hashes. Five-second exchange and existing bounded lifecycle cleanup
limits apply. The host independently replays the deterministic recording and
rejects differing worker output. A matching fixture proves protocol conformance,
not model quality or correctness of a proposed implementation.

The committed report binds owner, parent, assignment, image, request and execution
receipt. `/agent` reads those controller projections without a second registry.
Approval/workspace changes make the report stale and hide its content. Resume
without an authorization adapter exposes retained operational metadata with stale
assignment status. Reports show `verification=not_run` and cannot approve their
own integration, certify executed tests or complete the parent goal.

## Committed child wakeups

A trusted host may explicitly select a child ID in a schedule's bounded
`local_sources`. `local_child_event` derives metadata from that child's committed
report and exact authorized task/goal binding; `validate_local_child_event`
rejects invented sources, hashes, sequences and cross-task reports. The active
timer owner observes these selected committed results at a safe boundary and
admits their wakeup through the same queue. A sequence high-water mark coalesces
repeated observation. Payload content is omitted and never becomes user steering,
an approval or main-model context. External events and sealed reviewer output
remain disconnected.

## Verification

Run `make check` for the complete source and fresh installed-wheel suites. The
focused storage/admission, `/loop`, driver and child tests exercise identity,
reservation, ownership, input priority, cancellation, restart, exact reports and
forged events. `make container` additionally builds the reviewed image, runs the
existing containment/cancellation/cleanup probes and
`tools/smoke_local_child.py`. The child smoke performs the actual worker exchange,
parent reservation and report retention on both storage backends, and proves
revoked approval hides report content. It also cancels a goal while its real worker
waits at the host exchange and verifies retained charges and cancelled stop state.

This is a local macOS Docker qualification path. Linux CI and Windows-hosted WSL2
must run their own containment matrix before claiming platform support. Paid
providers require separate transfer/spending/conformance qualification. Coding
writes require the trusted execution/VCS and E2 workflow gates; the current
read-only child does not satisfy those gates or the required implementation
delegation in a writable creator workflow.
