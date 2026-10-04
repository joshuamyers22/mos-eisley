# Implementation-agent inspection

`/agent` and `/subagents` are equivalent read-only terminal controls for §31.12.
They share plain, JSON and TUI handling and never become author model turns.

```text
/agent
/subagents
/agent CHILD_ID
/subagents CHILD_ID --json
```

Listing shows creator-authorized implementation assignments, task and parent IDs,
model/effort, workspace/worktree, currentness, recorded lifecycle state, bounded
usage/spend, verification, unresolved work and retained report availability.
Selecting an implementation child reads its retained report and permitted evidence
through the trusted controller. Missing usage is disclosed rather than inferred
from an allowance. Reports are implementation claims; inspection does not certify
tests, accept a patch or approve creator integration. Partial and missing output
are explicitly marked, including completed, failed and cancelled children.

Inspection checks the owner, parent session and workspace, the frozen assignment's
plan/test identity and the retained report digest. Stale assignments remain visible
as stale, but their reports cannot be opened. Reassignment, cancellation or resume
changing the controller snapshot during a report read rejects that read before
display. Readers never follow stored paths, dispatch, repair spend, persist results
or add report content to the author context. Typed rejections retain the editor
draft; pasted commands remain ordinary literal author input.

Independent review children expose only child identity, role and operational state.
Their sealed readings, findings, assignments, reports and evidence are never read
by this command, even when selected by ID. Revealed review evidence stays in the
existing review/adjudication workflow. Review operational projections must be made
by the trusted controller before opening sealed evidence, rather than filtering
already-read findings at the terminal.

`/agent` cannot spawn, resume, cancel or steer agents. These actions still require
the qualified child lifecycle, frozen plan/test authorization and task budget.
No additional registry or conversation-state field is introduced.

## Substrate assessment and current boundary

The repository currently has owner-scoped task/checkpoint records, canonical
standalone recorded-agent artifacts, and a stopped review-controller inventory.
None represents a qualified implementation-child lifecycle with creator-authorized
assignments and retained child reports. Conversation forks are conversational aids,
not implementation children. The review inventory is not a creator-facing blinded
child projection and must not be used to fill this view.

The shipped terminal therefore reports that no qualified inspection source is
connected. It does not discover agents by scanning private run directories.
`ConversationController(child_inspection=...)` accepts a trusted
`ChildInspectionSource` for controller integration. That source must provide
bounded, internally consistent, owner/parent/workspace-scoped operational snapshots
and revision-bound retained implementation reports. It must independently establish
creator authorization and assignment currentness from the existing child records;
an assignment digest alone grants no authority. Adapter exceptions are replaced
with a generic terminal error to avoid revealing private paths or sealed findings.

This slice implements the inspection interface and command boundaries, exercised
with retained-controller test doubles. Production connection remains gated on the
§14.2 implementation-child controller and its execution/VCS/E2 qualification.
Session scheduling (§31.15) follows in the delivery order and remains separate work.

## Verification

`tests/test_conversation_agents.py` covers authorized report reads and aliases,
plain/JSON equivalence, mixed implementation/review activity, ownership and workspace
denials, stale assignments, report integrity, failed/cancelled children, partial and
missing output, concurrent report changes, inspection during author activity,
terminal acknowledgements, editor preservation and unchanged state/spend. Installed
wheel smoke coverage includes this test module.
