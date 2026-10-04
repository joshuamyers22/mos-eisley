# Explicit planning mode

Use `/plan` or `/mode plan` to select planning for new conversation messages.
The TUI status bar displays `plan`; `/plan status`, `/mode` and `/status` report
that selection in plain or JSON output. Mode selection is a local control and
consumes no model attempt. `/plan TEXT` selects planning and admits the request
atomically. Input rejection preserves the previous mode and unsent draft.

Planning asks the author to investigate requirements, clarify and revise intent,
and produce an exploratory plan covering scope, assumptions, interfaces,
subtasks, verification, aggregate cost/time ceilings and stopping conditions.
Clarification and revision turns share the session's existing attempt, pending
text, context and provider-input limits. The complete planning instructions count
in context previews, request fingerprints and admission budgets.

The current conversation uses recorded responses: a matching recording must
include the planning instructions in its request fingerprint. Selecting planning
does not make the built-in demo recording answer arbitrary planning questions.
The planning contract is exercised by recorded replay tests, including a revision
turn. Live author execution retains its existing qualification requirements.

## Read-only investigation

Planning offers no author task tools. Selected task-tool profiles fail before
request dispatch or attempt consumption, even when resumed from a checkpoint.
Use the existing trusted local read controls, such as `/diff`, and frozen source
attachments for permitted exploration. Saved history, reusable memory and task
instructions retain their existing scoped admission checks. Model-generated text
and attached source cannot change the selected mode or confer authority.

Planning cannot write repository files, dispatch coding children or publish.
Selecting planning never automatically launches a review. An explicit `/review`
continues to use its separate scoped, frozen review packet and current gates.
An exploratory plan is not a frozen creator plan/test package or an approval.

## Request implementation

Use `/implement TEXT` to explicitly request implementation and select conversation
mode in the same successful admission. `/diff fix KEY` also marks its admitted
correction request as an explicit implementation handoff. Rejected requests keep
planning selected and preserve the command/source attachments for retry.
`/plan off` or `/mode conversation` simply selects ordinary conversation; it does
not authorize implementation. Plain messages in planning mode remain planning
messages, so quoting or discussing an implementation request cannot exit the mode.
Pasted commands, multiline drafts and launch prompts remain literal text.

The handoff directs the author through [plan §15.7](mos-eisley-plan.md#157-plan-review-creator-approval-and-delegated-implementation):
freeze the creator plan and tests, independently review/adjudicate them, record
creator approval for exact revisions, then dispatch qualified children, integrate,
verify and independently review the result within cumulative budgets. Changed
plans/tests require renewed dependent approval. No routine human confirmation is
added for an already-authorized request.

This recorded conversation can describe that handoff; it does not implement live
creator approval, child dispatch, writes or verification. Implementation handoff
requests also reject selected task tools before dispatch. Mode changes cannot
revive expired grants or bypass the existing execution/policy/revision gates.

## Queued work and resume

A successful mode change records a session revision at a new-message admission
boundary. Each admitted author message freezes its own mode and implementation
intent. Changing the selection while an answer runs affects only later admissions;
running and already queued messages retain their original mode. Their prompts
remain stable even if the selection changes before dispatch.

JSON and SQLite saves, including archived SQLite entries and cold resume, retain
the selected mode and each admitted message's intent. Resume displays pending work
without dispatching it; `/continue` follows the existing continuation behavior.
Legacy snapshots default to ordinary conversation and keep their serialized bytes
unchanged until a new mode or implementation intent is recorded. Mode persistence
adds no approval, execution or scheduling authority.
