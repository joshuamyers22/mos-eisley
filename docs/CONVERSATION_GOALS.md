# Durable goals

The recorded conversation controller implements [plan §31.10](mos-eisley-plan.md#3110-durable-goals),
after explicit planning in [§31.13](mos-eisley-plan.md#3113-delivery-order-and-optional-development-review).
An objective becomes durable only when explicitly created. Ordinary sessions keep
normal direct answers and reviews. Creating or inspecting a goal starts no model
call. Goal state grants no execution, publication or scheduling authority.

## Controls

The TUI, plain terminal and JSON terminal share these commands:

| Command | Effect |
| --- | --- |
| `/goal new TEXT` | Create a goal with TEXT as its objective, success criterion and remaining obligation. |
| `/goal create JSON` | Create a goal with explicit criteria, verification identities, work inventory and limits. |
| `/goal` or `/goal status` | Show state, definition revision, progress, missing requirements and remaining budgets. |
| `/goal history` | Inspect retained goals, including cleared objectives. |
| `/goal run TEXT` | Submit an explicit author turn for the working goal through ordinary admission. |
| `/goal check` | Revalidate mechanical evidence at a safe boundary; start no evaluator call. |
| `/goal edit JSON` | Compare the expected revision, append a definition revision and pause the goal. |
| `/goal pause` | Stop subsequent goal dispatch; retain an already running call and its charges. |
| `/goal resume` | Revalidate and reopen eligible work without resetting counters or budgets. |
| `/goal cancel` | Cancel the objective while retaining its evidence and charges. |
| `/goal clear` | Remove selection and pause unfinished work; retain private goal history. |

For a working goal, ordinary admitted messages also carry its ID and definition
hash. `/goal run` refuses an inactive or stopped goal. Pasted commands and composed
multiline drafts remain literal messages. Rejected controls preserve the editor
text. `/stop` also cancels the selected unfinished objective.

A definition can be supplied on one line, for example:

```text
/goal create {"objective":"Fix the cache","success_criteria":["Correct bounded cache"],"remaining_work":["Implement cache","Verify cache"],"verification_requirements":["cache-tests"],"minimum_tests":1,"independent_review_required":true,"max_seconds":3600,"no_progress_limit":3,"repeated_failure_limit":3}
```

Defaults reserve at most eight attempts, 128,000 input bytes and 32,000 output
bytes, with zero paid spend. The structured `ceiling` also includes correction,
review and cost ceilings from the existing aggregate task ledger. Definitions,
revisions, jobs, decisions and receipts have bounded inventories; ordinary terminal
input limits apply. An edit supplies `{"expected_revision":1,"definition":{...}}`
with the complete new definition. Edits and replacement goals cannot enlarge retained resource or time ceilings.

## Completion and progress

`end_turn` closes an author turn, while the controller retains the objective.
Each boundary records a decision and the outstanding requirements. Completion
requires current goal/definition, workspace and input identities; complete evidence;
committed receipts; every declared work and verification obligation; enough actually
executed tests; any required independent review acceptance; a passing semantic
verdict; and no unresolved required jobs or uncertain effects. A stale receipt,
author assertion, zero-test success or missing evidence cannot prove completion.

Trusted controller adapters may register `observe_goal_inputs`,
`observe_goal_evidence` and a separately invoked `goal_evaluator`. They supply
permitted evidence, never evidence parsed from author prose or terminal commands.
The evaluator receives frozen success criteria and the bounded evidence view;
mechanical guards run first and dominate its verdict. A blocked verdict retains
its rationale. Qualified goal turns invoke this check at completion; adapters can
also call `evaluate_goal` explicitly. Valid semantic results are reused only for
unchanged evidence and invalidated when bindings change.

The evaluator has a bounded deadline and schema-validated result. Input/output
exposure and an attempt are persisted before invocation. Timeout, interruption,
malformed output or adapter failure retain the reservation and uncertainty. A late
result cannot reopen a paused, cancelled, cleared, edited or completed goal.

Fresh qualified receipts and completed obligations establish progress. Repeated
prose, tool activity and duplicate receipts do not. No-progress and repeated-failure
counters survive pause, edits and restart. Reaching a threshold shows `stalled`;
waiting for required results, blocked work, exhausted budgets, pause, cancellation
and completion remain distinct states. Explicit resume retains the counters.

## Required jobs and recovery

The controller exposes trusted registration and reporting methods for qualified
child/test/tool adapters. Each operation is bound to the goal definition and a
committed result identity. Required running jobs put the goal in `waiting` and
prevent evaluation and completion; optional jobs do not. Duplicate committed results
are idempotent, changed duplicates are rejected, and late results cannot reopen
stop states. Check-ins occur only at explicit safe controller checks, use declared
intervals with bounded backoff and maximum counts, and eventually expose a lost
report as stuck/blocked. They do not launch commands or model calls.

Trusted failure reports distinguish transient, usage-exhaustion, authentication,
configuration and uncertain-effect causes. They stop dispatch and show required
action. Retryable metadata does not initiate a retry. Reconciliation requires the
exact pending operation and a qualified receipt after the operation has ended;
it preserves all charges and does not automatically resume. No terminal command
can manufacture recovery receipts.

JSON and SQLite persist goal selection, definition history, message bindings,
reservations, jobs, counters and decisions, including archived transcript bindings.
Interrupted author calls and pending evaluator calls recover as uncertain blocked
work; reopening the session does not redispatch them. Clearing or creating another
goal carries cumulative charges and the original time origin. Retained in-flight
operations must be reconciled before a new goal can be created. Task-scoped goals
require an observer of the existing aggregate task ledger. Completed-milestone
closure also requires current artifact-backed executed-test receipts and retains
checkpoint task usage before publishing the conversation checkpoint link.

## Qualification boundary

The shipped recorded terminal has no trusted execution-evidence adapter or live
semantic evaluator. It can persist, steer and inspect a goal, but cannot certify
repository work from chat text. Goal-associated turns reject selected task-tool
profiles until a qualified integration supplies their execution and recovery
boundaries. This slice adds no unattended continuation, child launch, embedded
terminal, automatic retries, paid provider calls, limit-reset wakeups or scheduler.
Those integrations retain §§6.7, 14, 30, 31.4 and 31.15 gates. Ordinary `/review`
keeps its existing independent-review isolation and admission rules.

Acceptance is exercised by `tests/test_conversation_goal.py`: false completion,
stale/omitted evidence, budgets/time, steering, revision conflicts, JSON/SQLite
persistence, interrupted operations, semantic timeout/malformed/failing/late output,
stall loops, required/optional jobs, duplicate and lost reports, classified failures,
trusted reconciliation, checkpoint test counts and terminal status parity.
