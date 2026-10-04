# Work Note: Coalescing `/diff` Git reads

- Status: implementation complete; draft review pending
- Owner: Josh Myers
- Started (UTC): 2026-10-04
- Related review: [owner `/diff` security review](CONVERSATION_DIFF_OWNER_SECURITY_REVIEW.md)

## Objective and completion evidence

- Keep at most one `/diff` Git read active per TUI. A refresh during a read retains only the latest generation and workspace request; obsolete results never update the panel.
- Keep the existing selected-file navigation, attachment, stale-result, close, switch, and shutdown behavior. Preserve the Git reader's process and resource boundary. No Git mutation or provider authority is added.
- Acceptance: a deterministic rapid-refresh test records a maximum active read count of one, observes the latest workspace state, and shows that burst requests coalesce. Existing `/diff` tests and the full `make check` gate pass.

## Context and verification plan

Selected guidance: [Python engineering](PYTHON_ENGINEERING_GUIDE.md), [bounded verification](AGENTIC_VERIFICATION_GUIDE.md), [verification template](../templates/AGENTIC_VERIFICATION_LOOP.md), and [work-note template](../templates/WORK_NOTE.md). Relevant code and tests: [TUI worker](../src/mos_eisley/conversation_tui.py), [acceptance tests](../tests/test_conversation_diff_acceptance.py), and [panel tests](../tests/test_conversation_diff_panel.py).

Risk class: material availability and stale-result correctness. Budget: one coherent implementation, up to two correction passes, focused tests, then one full gate before publication. Stop if the worker can overlap reads, publish an obsolete result, or leave shutdown unable to complete a bounded in-flight read.

| Dimension | Pass rule |
|---|---|
| No overlap | Burst refresh test records maximum active reads of one |
| Latest result | Result after the burst matches the final workspace content; earlier generation is discarded |
| Existing behavior | `/diff` panel and acceptance suites pass, including directory switch and attachments |
| Delivery | `make check` passes on the combined slice before publication |

## Handoff

- Current state: implementation and focused verification complete on `feat/diff-coalescing-worker`, stacked on `/diff` Git isolation commit `3b2d9f0`. One poll task retains the latest generation across restarts; one single-thread executor serializes panel and send-time attachment Git reads.
- Next smallest safe action: publish a stacked draft PR and complete accountable review before merge.
- Blocker and required authority/input: none for implementation; any later merge or release follows repository owner-review rules.
- Checks already run: the rapid-refresh and close/reopen test passed with one maximum active reader and exactly two reads for eight content changes; the complete `/diff` panel and acceptance suites passed (10 tests). Full `make check` passed: Ruff, format, strict Pyright, 2,721 source tests (4 skipped), export verification, wheel build, and 1,978 installed-wheel smoke tests.
- Residual limit: an in-flight Git read remains bounded by the Git reader's deadline during shutdown; the executor does not start another panel or attachment read concurrently. This change does not grant a wider trust scope or resolve the separate source-instruction condition in the owner review.
