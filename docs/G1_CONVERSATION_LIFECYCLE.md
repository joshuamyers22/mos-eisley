# G1 conversation, review, cancellation and resume

The bounded G1 acceptance path composes the recorded conversation controller with
one explicitly claimed task-state continuation. It demonstrates the recorded G1
product slice required by `docs/mos-eisley-plan.md` §26.4; it does not activate a
live provider, repository writes, tool execution or automatic review.

## Conversation to frozen review

An author message reacquires the selected task state, revalidates its live workspace
and any referenced approval, and saves the exact temporary task context and request
admission before recorded dispatch. An explicit `/review` then retains its already
validated review packet before starting critics. The packet, rather than the author
conversation or task-state context, is the complete review input.

Critics receive only the frozen brief and their own persona. The judge receives only
the brief and identity-free findings. The resulting report is saved on the review
entry, and its bounded summary becomes ordinary visible conversation context for a
later author follow-up. Review does not consume a chat-cassette position or inherit
author tools, task instructions, approval evidence or execution authority.

## Cancellation and same-session resume

`/stop` cancels an in-flight author request and saves its text, exact request
admission and task-state context with terminal `cancelled` status. A dispatched
recorded position remains consumed. Reopening the saved conversation with the same
explicit continuation selection must reproduce the existing one-session claim and
revalidate current workspace and approval evidence. Resume does not dispatch any
message until the user supplies new work or explicitly continues a queued item.

A later request uses the next recorded position. The cancelled request is neither
replayed nor admitted as successful history, while the original checkpoint work,
aggregate resource ledger and uncertain-effect count remain intact. Changed task
selections, another session identity, stale workspace state or expired approval still
fail through the ordinary continuation boundary.

## Acceptance

`tests/test_g1_conversation_lifecycle.py` exercises both paths against the real
recorded controller and private snapshot store. It verifies:

- continued author request admission followed by an explicit frozen review;
- absence of conversation and task-state material from critic and judge requests;
- retained review evidence and its visible bounded follow-up context;
- terminal `/stop`, durable cancellation and burned-attempt accounting;
- passive same-session resume with an unchanged continuation claim;
- no replay of cancelled input and successful later work on the next position; and
- exact preservation of the selected work identity and checkpoint resource ledger.

These deterministic fixtures prove controller composition and fail-closed state
handling. They are not evidence of live model quality or machine containment.
