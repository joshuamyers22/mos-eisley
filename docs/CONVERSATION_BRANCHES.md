# Conversation forks and side chats

The recorded terminal implements the conversational slice of
[plan §31.11](mos-eisley-plan.md#3111-conversation-forks-and-side-chats).
The TUI, plain terminal and JSON terminal share explicit controls. These aids
carry author context; they cannot provide independent critic or judge evidence.

| Command | Effect |
| --- | --- |
| `/fork BOUNDARY POSITIONS` | Save a separate session with selected completed author messages at or before BOUNDARY. |
| `/fork BOUNDARY` | Select only the completed author message at BOUNDARY. |
| `/fork status` | Inspect saved branch IDs, allowances and publication states. |
| `/fork revalidate` | Explicitly admit the current checkout for this saved fork at a safe boundary. |
| `/side POSITIONS QUESTION` | Ask a bounded read-only question using only selected completed author context. |
| `/side status` | Inspect accounting and transient-answer availability. |
| `/side attach ID` | Queue the identified question and answer in the main author context with provenance. |
| `/side discard ID` | Discard an unattached answer while retaining its accounting receipt. |
| `/side cancel` | Cancel the side call without cancelling the active main request. |

Positions are zero-based retained message indices, written as an ordered comma
list such as `0,2`. Use `-` to select no context. Select at most four messages;
the full selected context is bounded to 24,000 canonical bytes. `/status` and
the transcript identify retained positions. Controller APIs require an exact
source revision and reject changed revisions or another owner. Typed commands
are controls; literal or pasted command text remains ordinary author text.

Forks preserve parent, branch, source revision, selected record hashes and artifact
references. They copy no ambient memory, review packets, tool grants, checkpoint
claims or uncertain executable operations. The main session, queued steering and
editor draft remain separate. Resume the returned session ID explicitly. A fork
does not undo filesystem effects; dispatch revalidates the current checkout.
Changed sources require explicit `/fork revalidate` and fresh request admission.
Worktree creation requires the qualified broker and workspace binding and is
currently rejected by these controls.

The parent reserves each fork's entire allowance before publication: by default
one attempt, 32,000 input bytes and 16,384 output bytes, with zero live cost and
no review or correction allowance. Reservations remain charged after publication
failure or uncertainty. Children keep the original cassette cursor and retained
goal obligations, cumulative exposure and time origin. Goals are paused in the
child and completion evidence is invalidated. Each child has a separate bounded
allowance that prevents its use from competing with the parent's remaining share.
Resuming, creating another goal or branching again cannot reset that allowance.

Side requests have no tools or implicit memory, consume the same recorded cassette
and reserve input, output and an attempt before dispatch. They are also charged to
retained goal budgets. Main work and steering can continue during a side call.
The editor is released after side admission. Failed, cancelled or interrupted calls
retain reserved exposure and uncertainty; restarting does not retry them.

Side questions and answers remain transient until explicit attachment. Durable
minimum metadata consists of operation IDs, source revision and positions,
question/request/answer hashes, resource reservations, usage, state and attachment
position. JSON and SQLite retain this accounting under existing owner and retention
rules. Unattached answers disappear on restart, discard or process exit. Explicit
attachment retains the content as ordinary author input, subject to the same
storage and context limits. No side answer is inserted into a review packet.

This slice uses recorded responses and requires matching recordings for arbitrary
side questions and fork follow-ups. Live providers, task-controller tools, managed
worktrees and shared live-task lifecycle integration remain gated by the plan's
existing execution, budget, recovery and platform qualification requirements.
