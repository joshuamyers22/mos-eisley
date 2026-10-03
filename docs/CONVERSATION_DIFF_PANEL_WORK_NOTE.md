# Conversation `/diff` panel work note

- Objective: add a navigable full-screen TUI panel backed by the bounded read-only Git reader in plan §16.4.1.
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, and `templates/WORK_NOTE.md`.
- Invariants: Git reads stay outside the UI loop; the selected directory and result generation remain bound; no untracked content, Git writes, provider calls, or implicit prompt submission; failed or partial reads are labeled.
- Initial coherent slice: toggle, layout and focus, staged/unstaged file inventory, bounded patch navigation, refresh, and lifecycle cleanup.
- Pending after this slice: selected-line prompt attachments and their admission/provenance contract. This requires separate request/context integration before the full §16.4.1 feature can be called complete.
- Risk class: new untrusted data rendering surface. Accountable owner security review is required before release.
- Resource ceiling: existing reader limits, plus bounded rendered patch lines and a single serialized refresh loop per open panel.
- Acceptance evidence: focused TUI and Git tests, real keyboard/resize PTY checks, then `make check` once before publication.
- Stopping rule: no publication if the read boundary or full gate fails.

## Evidence and handoff

- Focused diff suite: 4 tests passed, including a real checkout refresh, a slow-read cancellation, stale-read labeling, keyboard focus, and hostile control-character display.
- Existing TUI suite: 22 tests passed. Ruff and strict Pyright passed for the changed Python files.
- Real PTY check passed for a 120-column open, changed-file display, resize to 80 columns, F10 close, and clean quit.
- The sandboxed `make check` reached 2,659 tests and failed with 31 socket-permission errors. A focused OAuth fixture reproduced `PermissionError` on `127.0.0.1` binding. The elevated `make check` then exited successfully, including tests, export verification, build, and smoke checks.
- This is an initial panel slice. Selected-line attachments, provenance in admitted requests, and their context-limit handling are still required for full v1 `/diff` acceptance.
