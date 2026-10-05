# Conversation forks and side chats

The recorded conversation implements [plan §31.11](mos-eisley-plan.md#3111-conversation-forks-and-side-chats),
item 5 after durable goals in [§31.13](mos-eisley-plan.md#3113-delivery-order-and-optional-development-review).
Forks and side answers are conversational aids. They grant no execution,
publication, worktree, independent-review or scheduling authority.

## Fork an explicit retained boundary

Use `/fork BOUNDARY [POSITIONS]` with zero-based saved message positions:

```text
/fork 2 0,2
```

This creates a new private session from the completed author boundary at position
2, carrying only completed author messages 0 and 2, their answers and explicitly
attached frozen source references. `/fork 2` selects just position 2; `/fork 2 -`
selects no historical message content. Selection is limited to four messages and
24,000 bytes, within the existing request/storage limits. Reviews, unfinished
messages, duplicate positions, cross-owner context and stale source revisions
are rejected. Selected archived SQLite messages hydrate through their verified
owner-scoped store; unselected archives remain unhydrated.

The fork records parent session, source revision, boundary, branch ID, selected
record hashes, workspace observation and the prior task ledger. It starts with no
queued messages, copied memory, compactions, checkpoint claims or tool grants.
Planning selection and retained goal obligations/counters survive; unfinished goals
start paused and require explicit resume. Uncertain or in-flight task operations
cannot be forked. A fork does not undo filesystem effects or restore old files.

The command reports the new session ID. Open it explicitly using
`mos resume ID` with the same workspace, storage directory and backend as the
parent. Creating a fork does not switch the parent or discard its draft/steering.
The CLI publisher uses the existing private snapshot or SQLite session store.
`/fork status` shows provenance, fork receipts and remaining allowance.

The controller revalidates workspace ownership/identity and, for supported Git
checkouts, the bounded trusted Git view. Changed observations stop author dispatch
before an attempt. `/fork revalidate` explicitly admits the current checkout at a
safe boundary while preserving the historical source observation. In non-Git
folders the observation verifies directory identity, rather than repository
content. Unsupported Git markers/views fail closed. Isolated worktree requests
remain unavailable until §16.0.4's broker and workspace binding are qualified.

## Disjoint allowances and task continuity

The default recorded fork allowance is one author attempt, 32,000 input bytes and
12,000 output bytes, with zero paid spend, review rounds or correction cycles.
Trusted API callers may supply a bounded `ResourceCeiling`; it must fit the
parent's remaining allowance, task limits and retained recording. Parent publication
permanently reserves the entire allowance before the child is saved. Each child
has its own bounded allowance, so concurrent branches cannot reuse the same task
budget or recover allowance by clearing/replacing a goal. This conservative
reservation can exceed a child's eventual actual usage; it is not automatically
returned. Failed/uncertain publication retains the allocation and receipt.

The parent and child retain task obligations, prior aggregate usage and consumed
recording positions. Branch author turns, side calls and goal evaluator calls
reserve before dispatch and account for known usage. Goal creation carries prior
side/branch exposure. Forks cannot acquire selected task tools or inherited review
allowances; live task/child/review execution requires its qualified controller.
A new conversation branch does not constitute a separately authorized task.

Ordinary sessions activate branch accounting only when using these features.
Their local recorded allowance is at most 16 attempts, 1,000,000 input bytes,
64,000 output bytes and zero paid spend, additionally restricted by retained task
ceilings and the recording. Existing ordinary-session behavior/serialization is
unchanged before activation. Task-scoped fork and side integration remains gated
on the qualified lifecycle and aggregate admission adapters.

## Ask a bounded side question

Select context explicitly with `/side POSITIONS QUESTION`:

```text
/side 0,2 Explain the tradeoff between these approaches.
/side - What does bounded backoff mean?
```

A side request includes only the chosen completed author messages and question.
It reads no selected memory, offers no task tools, interrupts no active author
call and does not add its answer to main model context. Main steering can continue
while it runs. Each side call consumes a recording position and shares the task
and branch budget. The response deadline defaults to two seconds; trusted API
configuration may set a positive deadline of at most ten seconds.

The response displays a side ID. Use `/side attach ID` to admit the identified
answer as a new main author message, with question/answer hashes, context hash,
source revision, selected positions and usage provenance. Ordinary input/context
limits and planning/goal admission still apply. Attachment is explicit and cannot
be repeated. An oversized attachment is rejected and remains transient.
`/side discard ID` discards the answer without deleting its accounting receipt.
`/side status` reports receipt state, content availability, attachments and budgets.
`/side cancel` stops the side operation while preserving the main task; `/stop`
and `/quit` cancel active side work through the existing terminal lifecycle.

Side questions and answers stay in bounded process memory by default. The session
persists only minimum operational metadata: request/question/context hashes,
owner/session/source revision, positions, recording index, state, known usage,
answer hash and attachment/recovery links. Unattached content is unavailable after
restart, is not an ambient memory cache, and cannot be restored from its receipt.
Explicitly attached content becomes ordinary retained author input under existing
storage/retention rules. TUI reports do not modify the editor draft; plain and JSON
modes share the same controller and commands. Pasted or composed multiline commands
remain literal author input.

## Interrupted calls and qualification

Timeout, cancellation or a lost response retains conservative exposure and marks
uncertainty before another dispatch. A cancellation-resistant provider can finish
late, but its result cannot revive a side answer or reopen task state. Cold resume
conservatively recovers pending side/author/evaluator operations without replaying
them. A qualified trusted adapter may reconcile one exact ended side operation
against its request hash and committed recovery receipt; it preserves all reserved
charges, is idempotent and restores neither answer content nor automatic retries.
No terminal command can manufacture reconciliation evidence.

The shipped terminal remains recorded-only. A matching recording must include the
exact branch/side context in its request fingerprint; the built-in demo does not
answer arbitrary side or fork prompts. Live provider transfers, paid calls,
creator approval, child execution, worktrees and recovery retain their existing
gates. Independent critics and judges keep their separate permitted evidence
views; branch context and side content never automatically enter their packets.

Acceptance in `tests/test_conversation_branch.py` covers selected/omitted context,
owner/revision checks, private JSON/SQLite persistence, archived source selection,
budget reuse, workspace change/revalidation, no inherited tools/review grants,
concurrent steering, side cancellation/timeout/late output, restart/reconciliation,
explicit attachment, receipt-only storage and live TUI draft preservation.
