# Conversation `/diff` panel threat model

## Scope and ownership

- System: full-screen conversation `/diff` panel and selected-line prompt attachments at stacked PR #255 (`511fbbf` baseline).
- Owner: Mos Eisley product owner; this record prepares technical evidence for accountable review.
- Trigger: release qualification of a new Git-to-terminal-to-prompt data path.
- In scope: selected workspace, bounded Git snapshot and patch reads, terminal rendering, attachment preview, local chat admission and persistence.
- Out of scope: provider dispatch authority, general repository editing, staging, and untracked content preview.

## Assets and boundaries

| Asset | Need | Boundary |
|---|---|---|
| Selected workspace and Git state | Path isolation and current-source identity | Filesystem/Git to reader |
| Patch excerpt | Exact bytes, bounded size, untrusted meaning | Reader to TUI to chat context |
| Draft and attachments | Preserve on refusal; clear on accepted queueing or discard | Composer to persisted conversation |
| Session identity and provenance | Same owner/workspace and immutable admitted record | TUI to session store |

The actor may control repository files, names, Git configuration and patch text. A same-user local process can race filesystem reads. Terminal input may be keyboard or mouse escape sequences. The panel has no provider, Git write, or review-dispatch authority merely because a line is selected.

## Abuse cases and controls

| Abuse case | Control and evidence to verify | Residual limit |
|---|---|---|
| Malicious patch text injects terminal controls or model instructions | Render controls as inert text; attach escaped JSON with an explicit untrusted-source instruction; terminal and excerpt tests | The model can still misinterpret source content; no edit authority follows. |
| Changed source is silently sent | Frozen bytes/digests; send-time workspace, snapshot and patch re-read; stale rejection test | A same-user process can race after the final check; the saved excerpt stays frozen. |
| Old workspace result appears after directory switch | Generation and workspace checks; switch test | Same-user filesystem replacement between checks remains possible. |
| Large patch or repeated refresh exhausts UI | Reader caps, off-loop reads, sequential work within each poll cycle, bounded excerpts; churn and responsiveness tests | Cancellation discards an obsolete result but does not stop an already running worker-thread Git read. Rapid restarts can briefly overlap reads; each Git call still has its own deadline and output cap. |
| Mouse or keyboard selection names wrong lines | Select only displayed content inside one hunk; exact-byte and mouse selection tests | Terminal mouse reporting varies by emulator. |
| Untracked or out-of-scope content leaks | Untracked path-only reader and workspace-relative admission; scoped-reader tests | An admitted tracked patch is intentionally shown to the owner. |
| Selection escalates to review or provider spend | Selection only mutates the local composer; ordinary chat still requires an explicit send and its separate policy | A sent chat with excerpts remains subject to the selected chat mode. |

## Decision boundary

The acceptance matrix in `CONVERSATION_DIFF_ACCEPTANCE_VERIFICATION.md` maps
each boundary to behavioral checks. The final unrestricted `make check` passed
on the exact source: 2,670 repository tests (4 skipped) and 1,918 installed-wheel
tests, plus lint, typing, export verification and build. No product defect was
found in this technical review.

The accountable owner accepted the exact stacked candidate for the trusted local
owner-operated scope on 2026-10-03 UTC, with hardening conditions recorded in
`CONVERSATION_DIFF_OWNER_SECURITY_REVIEW.md`. The security decision does not
approve merge, release, provider use, or spending.
