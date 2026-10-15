# Combined terminal interface review

- Status: local review complete; owner visual acceptance recorded; delivery gates pending
- Reviewed source: `114a09e`, clean `feat/terminal-interface-polish` worktree
- Date: 2026-10-14
- Requirement: [plan §16.0.6](mos-eisley-plan.md#1606-clean-professional-terminal-interface)
- Implementation: [work note](TERMINAL_INTERFACE_POLISH_WORK_NOTE.md)

## Objective and rubric

Review the completed presentation slices together, including overlapping panels,
against the approved restrained colors, compact headers, shared spacing and clear
composer. Preserve keyboard controls, drafts/cursors, focus, transcript browsing,
session identity and explicit approval. No provider calls, execution changes,
release approval or user installation changes are part of this review.

Selected guidance: `docs/AGENTIC_VERIFICATION_GUIDE.md`,
`templates/AGENTIC_VERIFICATION_LOOP.md` and `templates/WORK_NOTE.md`.
Risk: material interaction review. Bound: three evidence-changing passes within
60 minutes; no paid requests. Stop after screen inspection, focused interaction
regressions and source/installed-wheel PTYs meet the rubric, or record a specific
remaining defect. The full publication gate remains separate.

| Dimension | Evidence and threshold | Result |
|---|---|---|
| Shared hierarchy | Real renderer captures: compact header, restrained accent, readable content, distinct composer | Pass locally |
| Narrow layout | 112x36 to 64x24 resize; error plus approval plus multiline draft remains usable | Pass; cosmetic footer wrap noted below |
| Interaction continuity | Keyboard tests and PTYs preserve drafts, focus, browsing and explicit selection | Pass locally |
| Inspectable decisions | Full approval identities, scope, paths and reasons remain available through details | Pass locally |
| Themes and packaging | Dark/light/plain source, both diff renderers, isolated installed wheel | Pass in macOS PTYs; broader platform gates pending |

## Screen findings

| Screen | Inspection and behavior | Disposition |
|---|---|---|
| Welcome | Mode and workspace are visible without a diagnostic wall; F2 exposes details; composer is distinct | No blocking finding |
| Conversation | A completed recorded exchange retains message identity and restrained role emphasis; multiline draft remains visible | No blocking finding |
| Active operation | Synthetic running/queued state in the real renderer shows action, observed elapsed time and expandable scope/route detail | No blocking finding; individual calls are not streamed |
| Errors | Error and next step remain visible; expansion, detail scrolling and dismissal preserve draft/focus | No blocking finding |
| Review/approval | Action/scope/reason, exact hashes and explicit commands remain inspectable; cancellation and closing preserve draft/focus | No blocking finding; combined error/approval/draft fits 64x24 |
| Session picker | Names lead rows, selection is restrained and non-color-only; filtering/details, paging and refresh retain keyboard usability | No blocking finding |
| Directory selector | Editable path is distinct from resolved target, Git root and memory identity; preview/edit/cancel remain explicit | No blocking finding |
| Diff | Both renderers retain selected filename, restrained +/- styling, coordinates where applicable and contextual controls while scrolling | No blocking finding; draft survives focus/resize/close |

At 64 columns the ordinary footer's final `history` label can wrap by one
character. This is a nonblocking cosmetic finding: controls remain visible and
functional. Long paths, reasons and scope labels deliberately abbreviate; complete
details remain inspectable. The screenshot rasterizer's Menlo font lacks some CJK
glyphs; Unicode cell-width behavior is checked separately by the keyboard suite.
No application-code correction was required in this review.

## Verification evidence

1. **Combined regression pass.** Ran the 76-test presentation/activity/companion/
   auxiliary/TUI/picker/directory/switch/diff-panel set. Seventy-four passed;
   two diff integration tests timed out because the parent sandbox prevented
   Mos's own OS Git isolation. The six-test diff-panel and real-PTY regression
   rerun outside that parent sandbox passed, including both failed tests. No
   isolation policy or reader was changed. These counts overlap.
2. **Final combined revision in PTYs.** Foundation, errors, approval and concurrent
   approval/error scripts passed source dark/light/plain, Git-renderer and
   installed-wheel variants. Auxiliary PTYs passed those variants plus installed
   Git renderer. Checks include filtering/full identities, directory preview/edit/
   cancel, multiline drafts, panel scrolling, resize, passive quit, terminal mode
   restoration and unchanged seeded session bytes. Focused tests additionally
   cover literal paste, stop/queue, cold resume, cursor/focus and transcript scroll
   preservation during updates and inspection/cancellation. A recorded exchange
   and synthetic running/queued state were captured through both real renderers;
   no repository operation or provider request was dispatched for that state.
3. **Visual inspection.** Inspected combined contact sheets spanning all eight
   screens, dark/light/plain, narrow layouts and installed Git diff. Early
   captures could stop partway through a terminal redraw; the disposable capture
   scripts now drain for a fixed settling interval before saving. The resulting
   settled captures show the complete footer. This was a capture-harness issue.

Commands for the combined regression and affected rerun:

```sh
PYTHONPATH=src:tests .venv/bin/python -m unittest \
  test_conversation_presentation test_conversation_activity \
  test_conversation_review_companion test_conversation_auxiliary_presentation \
  test_conversation_tui test_conversation_picker test_conversation_directory \
  test_conversation_switch test_conversation_diff_panel

PYTHONPATH=src:tests .venv/bin/python -m unittest \
  test_conversation_diff_panel \
  test_conversation_diff.DiffTests.test_real_pty_panel_focus_resize_and_draft_preservation
```

Synthetic captures, terminal-cell evidence and the self-contained gallery remain
outside Git under `/Users/josh/Projects/mos-eisley-ui-implementation-preview/`.
The gallery is `combined-review.html`; a standalone copy is available at
`/Users/josh/Downloads/mos-eisley-combined-interface-review.html`.
Disposable capture scripts are `/private/tmp/mos-ui-*-pty-check.py`, with
`mos-ui-combined-capture.py` and `mos-ui-combined-fixture.py` for conversation and
active-state captures. These local artifacts are not portable release evidence.

## Exit and handoff

Stop reason: local rubric passed with no blocking findings. The cosmetic footer
wrap remains accepted for this review scope. This is an agent review of the
implementation. Joshua accepted the combined visual result on 2026-10-14,
including the noted cosmetic footer wrap. This acceptance does not authorize a
release or certify the remaining delivery gates.

No application code changed. Earlier lint, typing and build evidence remains in
the implementation note; those checks were not rerun as part of this review.
Full `make check`, security/container delivery checks and other-platform visual
qualification remain unrun. Next: commit the review/acceptance record and run
the combined delivery gates before merge/publication. Individual tool-call
streaming remains a separate feature.
