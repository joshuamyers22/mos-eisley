# Narrow-terminal keyboard hints

- Owner: Joshua Myers
- Status: implementation complete; validation results recorded below
- Baseline: main `1b5267d`; existing installed/published rc.3 remains unchanged
- Scope: adaptive footer/composer hints in ordinary and Git-review renderers

The rc.3 Mac test showed the final character of the keyboard footer wrapping at
64 columns. Bound status/hints in terminal cells and select whole shorter hints
as width decreases. Reserve two conversation footer rows and three diff rows;
keep full keyboard instructions inspectable with F2 or `/status`. Do not change
bindings, controllers, storage, provider access or execution/approval policy.

Selected guides: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/WORK_NOTE.md` and
`templates/AGENTIC_VERIFICATION_LOOP.md`. Rubric: no overflow at 64x24, 48x20,
40x18 and 32x16; dark/light/plain; both renderers; drafts, cursor/focus and scroll
anchors survive resize and incoming updates; full controls remain inspectable.
Use recorded fixtures and temporary homes, with zero paid calls. Bound work to
one combined full gate, focused regressions and one real-PTY visual matrix;
rerun affected checks for evidence-changing corrections. Stop on lost input,
focus/scroll corruption, unusable composer or changed execution semantics.

Implementation: select complete hint variants by terminal-cell width, leaving
the last column unused; disable footer/hint wrapping. Allocate exactly two footer
rows normally and three with a diff open. Below 24 rows, omit the spacer and
separate activity summary; the ordinary status footer and F2 details remain.
The file picker may shrink to one row. Preserve the three-row composer minimum
and its existing growth behavior. Queue/diff notices no longer repeat key lists.

Focused evidence: 10 presentation tests pass, including both renderers and all
three themes while cycling through 64x24, 48x20, 40x18, 32x16 and 80x28. Draft
text/cursor, composer focus and transcript cursor anchor survive incoming updates;
F2 exposes omitted keys without submitting the draft. All 23 conversation TUI
tests also pass after the final queue-notice change. Lint, formatting and type
checking pass. A real-PTY matrix covers normal/diff views at those sizes in all
themes: all 60 layouts pass, including draft typing after resize and clean terminal
restoration. Visual inspection covered dark, light and plain captures. The run
uses disposable homes and recorded responses. Captures and disposable
logs live outside Git in `mos-eisley-narrow-footer-preview` and `/private/tmp`.

Validation closeout (2026-10-19): all 1,416 affected conversation tests passed
(five skipped). The combined `make check` ran 3,762 tests with one failure and
17 skips: `test_cli_opens_live_tui_session_without_dispatching` rejected the
resume subprocess. A targeted rerun of its complete live-chat module passed all
10 tests; the cause of the full-suite failure is not established. Do not describe
the original full gate as passing. Export verification and package build passed
when resumed separately; installed-wheel smoke validation is still running in
`/private/tmp/mos-narrow-footer-package-check.log` at branch publication. No
release publication or installed rc.3 update is included in this change.
