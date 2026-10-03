# Conversation `/diff` acceptance verification

## Objective and scope

- Requirement: plan §16.4.1 and the stacked draft panel PR #255, starting at `511fbbf`.
- User outcome: a terminal user can inspect and attach exact changed lines while refresh, resize, and directory switching preserve the draft and workspace boundary.
- Invariants: attachment bytes and provenance stay frozen; stale or wrong-workspace data cannot be sent; selection does not dispatch; untracked content remains path-only; Git reads remain bounded and outside the UI loop.
- Non-goals: provider calls, Git mutation, automatic edits, merge or release approval.
- Risk: material UI and untrusted-data boundary. Accountable owner security review is required before release.
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, and `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`.
- Resource ceiling: recorded conversation only; disposable Git workspaces; no provider spend; existing patch and excerpt caps. Add focused tests for uncovered behavior, then run the full gate once on the combined change.

## Blocking rubric

| Dimension | Pass evidence |
|---|---|
| Real terminal behavior | PTY open, attach, resize, remove, close and quit complete; in-process panel check preserves a nonempty draft. |
| Selection and refresh | Mouse-selected lines map to exact patch bytes; rapid edits and obsolete refresh generations cannot replace current source or a frozen attachment. |
| Workspace isolation | Directory switch rejects unsent attachments and discards old refresh results after a completed switch. |
| Admission and safety | A stale excerpt never reaches queued chat; rejected submission retains draft; untracked paths remain path-only. |
| Delivery | Focused checks, strict typing, `make check`, and a reviewable threat model pass. |

## Iterations and findings

| Pass | New evidence | Finding and correction | Result |
|---|---|---|---|
| 1 | Four new behavioral checks: SGR mouse range, rapid edit refresh, blocked switch plus obsolete read, real PTY attach/resize/remove/close/quit | Initial failures exposed test harness assumptions: a direct switch bypassed the terminal command flow; PTY repaint interleaved cursor sequences with notice text and needed output draining before process exit. Corrected the harness; no product defect found. | Four checks pass. |
| 2 | Existing reader, panel and attachment suites exercised alongside new checks | No new defect. | 24 existing checks pass; Ruff and Pyright pass. |
| 3 | Full `make check` in the workspace sandbox | All 31 test errors came from localhost MCP fixtures receiving `PermissionError` at `socket.bind`; no assertion failures. | Not a product gate result; rerun with fixture socket access. |
| 4 | Unrestricted full gate | Two review fixture errors appeared under full-suite load, then both affected suites passed in isolation: operator probe 2/2, launch admission 26/26. No `/diff` failure. | Timing-sensitive gate needed one more full run. |
| 5 | Final unrestricted `make check` on the same source | No code changes between the three full runs. | Pass: Ruff, Pyright, 2,670 repository tests (4 skipped), export verification, build, and 1,918 installed-wheel tests. |

## Acceptance coverage

| Planned case | Evidence |
|---|---|
| Real PTY open, focus, resize, attach, remove, close and quit | `tests/test_conversation_diff_acceptance.py::DiffPTYTests`; the test drives actual terminal input and a resize signal. `tests/test_conversation_diff_panel.py::test_open_refresh_edit_select_and_close_preserves_draft` checks draft retention and pane focus. |
| Mouse selection, exact lines, provenance, selection without send | `DiffAcceptanceTests::test_mouse_range_selects_exact_hunk_lines`; `tests/test_conversation_diff_attachment.py::test_freezes_exact_lines_and_coordinates`. |
| Rapid refresh, stale selection, rejected send, retry and draft retention | `DiffAcceptanceTests::test_rapid_refresh_keeps_frozen_attachment_and_latest_patch`; `tests/test_conversation_diff_panel.py::test_selected_line_attach_stale_reject_and_remove`. |
| Directory switch and obsolete result isolation | `DiffAcceptanceTests::test_switch_blocks_attached_source_and_discards_old_generation`; `tests/test_conversation_diff_panel.py::test_slow_read_does_not_block_editor_and_closed_generation_is_discarded`. |
| Staged, unstaged, untracked, renamed, deleted, binary, unborn, non-Git and oversized input | `tests/test_conversation_git.py` and `tests/test_conversation_diff_panel.py`; untracked entries are path only. |
| Hostile paths, Git helper configuration, terminal controls | `tests/test_conversation_git.py::test_hostile_git_helpers_do_not_execute`, `test_unsafe_filenames_are_omitted_with_incomplete_notice`, and `tests/test_conversation_tui.py::test_editor_history_bounds_and_control_rendering`. |
| Continued conversation, cancellation and draft preservation | Existing `tests/test_conversation_diff_panel.py` covers composer continuity; ordinary conversation cancellation is covered by the conversation TUI suite in `make check`. |

The PTY check uses stable notice prefixes because prompt_toolkit emits cursor moves
between unchanged and changed characters. The exact attachment bytes, coordinates,
admission and refusal behavior are asserted in the in-process checks.

## Exit

- Stop rule reached: all blocking rubric rows pass on the exact acceptance branch. The earlier sandbox socket errors and intermittent review fixture errors remain documented above; the final full run passed without changes to the tested source.
- Accountable owner security decision: accepted for the trusted local owner-operated scope with conditions on 2026-10-03 UTC; see `CONVERSATION_DIFF_OWNER_SECURITY_REVIEW.md`. This technical verification and security acceptance grant no merge or release authority.
