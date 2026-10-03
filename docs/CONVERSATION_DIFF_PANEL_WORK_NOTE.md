# Conversation `/diff` panel work note

- Objective: add a navigable full-screen TUI panel backed by the bounded read-only Git reader in plan §16.4.1.
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, and `templates/WORK_NOTE.md`.
- Invariants: Git reads stay outside the UI loop; the selected directory and result generation remain bound; no untracked content, Git writes, provider calls, or implicit prompt submission; failed or partial reads are labeled.
- Initial coherent slice: toggle, layout and focus, staged/unstaged file inventory, bounded patch navigation, refresh, and lifecycle cleanup.
- Selected-line slice: F12 freezes the focused patch line or selected lines from one hunk; Shift-Up/Down and supported mouse selection extend the range. The composer shows up to three removable previews with workspace, path, basis, old/new ranges, snapshot digest and current/changed state. Ctrl-X removes the latest excerpt; Ctrl-U discards draft and excerpts.
- A send re-reads the selected workspace and each attached patch off the UI loop. Changed or unreadable sources retain the draft and require re-selection. Accepted input stores the frozen excerpt and provenance, counts the serialized source data against pending/context limits, and binds an attachment fingerprint to the request admission record. Excerpts remain untrusted source data; selection never starts a request or an automatic review.
- Risk class: new untrusted data rendering surface. Accountable owner security review is required before release.
- Resource ceiling: existing reader limits, plus bounded rendered patch lines, three excerpts of at most 40 lines and 2,048 bytes each, and a single serialized refresh loop while the panel or attachments are active.
- Acceptance evidence: focused TUI and Git tests, real keyboard/resize PTY checks, then `make check` once before publication.
- Stopping rule: no publication if the read boundary or full gate fails.

## Evidence and handoff

- Focused diff suite: 4 tests passed, including a real checkout refresh, a slow-read cancellation, stale-read labeling, keyboard focus, and hostile control-character display.
- Existing TUI suite: 22 tests passed. Ruff and strict Pyright passed for the changed Python files.
- Real PTY check passed for a 120-column open, changed-file display, resize to 80 columns, F10 close, and clean quit.
- The sandboxed `make check` reached 2,659 tests and failed with 31 socket-permission errors. A focused OAuth fixture reproduced `PermissionError` on `127.0.0.1` binding. The elevated `make check` then exited successfully, including tests, export verification, build, and smoke checks.
- The selected-line slice adds focused contract and TUI tests for line coordinates, frozen bytes, stale rejection, removal, retry, request admission, pending byte limits, and a three-attachment preview. The exact final-candidate `make check` passed: lint, strict Pyright, 2,666 repository tests (four skipped), coverage report, export verification, wheel build, and 1,918 installed-wheel smoke tests. Accountable owner security review remains the release gate.
