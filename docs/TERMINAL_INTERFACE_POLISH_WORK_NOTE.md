# Terminal interface polish: approved direction and first slice

- Status: active
- Owner: Joshua Myers
- Started: 2026-10-14
- Requirement: [plan §16.0.6](mos-eisley-plan.md#1606-clean-professional-terminal-interface)
- Starting revision: `4df32f89ff6c864a7cc8b5d66c1406e69f2e66b7`, clean isolated worktree

## Approved direction

Joshua approved the six-state visual proposal on 2026-10-14. The approved
direction uses a restrained accent, neutral backgrounds, compact workspace and
session headers, a borderless transcript, a ruled multiline composer, concise
status, and explicit access to full diagnostic details. Approval applies to the
visual direction; it is not implementation acceptance or release qualification.
The local review artifact is `mos-eisley-ui-proposal.html`, also copied to Downloads.

## Objective, scope and invariants

Implement the shared visual foundation and conversation header, transcript,
composer and status first. Preserve editing, literal paste, cancellation,
focus, history, directory identity, capability labels and saved state. Keep
diagnostics inspectable. Auxiliary screens and richer tool activity remain later
slices. Do not change execution, spending, approval or persistence authority.

Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md` and
`templates/AGENTIC_VERIFICATION_LOOP.md`.

## Rubric and stopping rules

| Dimension | Evidence | Required result |
|---|---|---|
| Visual outcome | Synthetic real-PTY captures at wide/narrow sizes | Compact header, readable transcript, distinct composer; no diagnostic wall on startup |
| Interaction | Existing affected terminal/controller tests and focused regression checks | Drafts, paste, focus, scrolling and controls preserved |
| Capability truth | Recorded/live fixtures, explicit diagnostic inspection | Accurate mode; complete diagnostics remain accessible |
| Portability | Light/dark/plain styling and terminal resize checks | No color-only state or width overflow in essential labels |
| Static/package quality | Lint, formatting, typing and wheel build | Pass affected checks; report any unrun full gate |

Risk: material presentation change. Maximum three evidence-changing correction
passes; review window 60 minutes before reassessing scope. No paid provider calls.
Stop when the first slice meets the rubric, or report a specific remaining
failure. Full `make check` remains required before publication; this slice does
not itself authorize publication or mark the overall milestone complete.

## Verification and handoff

The local first slice implements shared presentation in both conversation
renderers, a compact header/footer, an unboxed transcript and a ruled composer.
F2 invokes the existing read-only `/status` command; complete launch details and
current metadata remain inspectable. Message indices remain visible because
existing memory-selection commands require exact message attribution. Themes
are per launch, with an explicit choice when automatic background inference does
not match the terminal. `NO_COLOR` also covers built-in widget colors.

Evidence-changing verification:

| Pass | Evidence and findings | Disposition |
|---|---|---|
| Foundation | Core terminal/memory/project/planning suites: 95 tests passed after correcting composer processor initialization and test fixtures. | Preserved controller state and keyboard behavior. |
| Integration | Affected terminal/diff/history/directory/switch/live-chat suites: 103 tests passed. Two parent-sandbox Git read timeouts passed when Mos's own isolation was permitted; an obsolete frame-title assertion was updated to check mode and transcript content. | No Git reader or execution policy was changed. |
| Terminal/artifact | Real macOS PTYs exercised dark/light/plain, the Git-panel renderer and an installed wheel; each passed multiline drafts, 112-to-64-column resize, F2 details, passive quit and terminal restoration. This exposed default widget colors in plain mode and surplus composer height. | Monochrome output now uses one-bit color depth; composer height follows content within its bounds. New regressions cover both. |

After the final layout adjustments, 30 presentation/conversation tests and six
diff-panel/real-PTY regressions passed. Source and installed-wheel recorded chat,
JSON/plain output and cold resume were checked without paid calls; cold resume
preserved entries and attempt counts. Source/wheel builds, lint,
formatting and strict typing passed. Counts refer to overlapping
suites and must not be summed into a unique-test claim.

Local synthetic screenshots are retained in
`mos-eisley-ui-implementation-preview` alongside the project checkouts. No real
session content or credentials were used. The package smoke used a private
temporary environment, leaving the existing user installation alone.

The full `make check`, security/container gates and cross-platform visual
qualification have not been run for this change. They remain required before
publication; no merge or release is claimed. Stop this slice after its focused
checks and captures, with broader delivery checks deferred to publication.
Next slices: activity/error presentation, approval companion view, then
session/directory/diff consistency. Implementation acceptance of those slices
remains separate from the approved overall visual direction.

## Activity and error slice (2026-10-14)

Objective: compact current-operation status, observed elapsed time, expandable
bounded details and actionable errors in both renderers. Preserve drafts, focus,
transcript browsing and execution/approval boundaries. Existing controller states
are the source of truth; no individual tool-call telemetry is currently emitted,
so the display must not invent calls or completed durations on cold resume.
Selected guidance remains the Python and bounded-verification guides above.
Risk: material presentation change; at most three evidence-changing passes and a
60-minute review window. Acceptance: deterministic timer/lifecycle tests, keyboard
and update preservation tests for both renderers, existing terminal regressions,
lint/format/type checks and a built-wheel smoke. No paid calls or publication.

Activity/error acceptance evidence:

- The focused activity/presentation/TUI set passed 34 tests after the final notice
  deduplication. Its keyboard tests exercise both renderers, timer redraws,
  expansion and detail scrolling without focus transfer, persistent/dismissible
  errors, unchanged drafts/cursors, and an unchanged transcript viewport when a
  queued message arrives. Event-loop rendering exceptions are test failures.
- The wider terminal/history/memory/composer/context set passed 106 tests. These
  suites overlap the focused set. Six Git-panel and real-PTY regressions passed
  outside the parent sandbox, permitting Mos's own Git isolation; two Git-reader
  tests had timed out inside that parent sandbox.
- Real macOS PTYs checked source dark/light/plain, the Git renderer and an isolated
  installed wheel: recoverable error, detail expansion/scrolling, multiline draft,
  112-to-64-column resize, dismissal, F2 inspection, passive quit, and restored
  terminal modes. Synthetic captures use the `activity-` prefix in the existing
  local implementation-preview directory. No provider calls or real sessions.
- Lint, formatting, strict typing, sdist and wheel builds passed. The user-installed
  CLI remains unchanged; the smoke environment is temporary and private.

Corrections from evidence: use a toolkit filter for the details pane's bounded
height; make asynchronous render exceptions fail the keyboard test; explicitly
return the PTY contract test to the latest output after browsing; suppress a
failure's duplicate routine notice. Retained error details are bounded to 1,200
characters, operation prompt details to 800 terminal cells, and the details pane
is scrollable. The strip reports operations and declared scope, not invented
individual tool calls. Elapsed time freezes at terminal state and restarts for
the next observed operation; cold resume has no fabricated prior timer.

Stop this slice after these focused and packaged checks. Full `make check`,
security/container gates and other-platform visual qualification remain unrun;
no publication or overall milestone acceptance is claimed. Next: approval
companion view, followed by session/directory/diff consistency.

## Review/approval companion slice (2026-10-14)

Objective: a read-only companion in both conversation renderers showing action,
scope, reason and exact inspectable identities for selected recorded/live review
packets, Git scope receipts and memory approval previews. Polish the actual
critic/judge terminal ceremony using the same hierarchy and unchanged exact
`show`, `approve <hash>`, `cancel` input behavior. Closing an inspector is distinct
from cancelling a pending mutation or controller run. Preserve the draft,
cursor, focus and transcript browsing during inspection and dismissal.

Guidance: Python engineering, bounded verification and its loop template above;
`templates/THREAT_MODEL.md` for approval-display failure cases. Risk: material
presentation at an existing approval boundary, with no new authorization path.
Budget: three evidence-changing passes, 60-minute review window, no paid calls.
Acceptance: exact-hash/no-write tests, both-renderer keyboard/draft/focus tests,
existing approval/memory/live-review regression tests, static checks and built-wheel
PTY smoke. Full publication gate remains deferred until publication.

Failure cases and controls: source/model text must not forge UI labels or terminal
controls (ASCII JSON detail and sanitized summaries); shortened hashes must not
become authorizations (exact original hashes retained, inspector has no apply
callback); stale views must not imply current approval (receipt identity/status
labels, no one-key confirmation, existing backend revalidation); cancellation
must not silently clear drafts or mutate pending approvals (close inspector only,
explicit existing discard/cancel operations). No credentials or operating paths
are fetched for inspection. Verification is offline and does not accept a new
live-review, spend or release profile.

Companion verification and handoff:

- Exact-identity and interaction tests cover live packet hashes and complete brief,
  escaped untrusted content, missing-hash refusal, stale and discarded receipts,
  opening/scrolling/closing from composer and transcript focus, and preserved
  drafts, cursors and pending memory bytes. A suspended conversation exercises
  the real terminal approval renderer with `show` then `cancel`: no request is
  dispatched, no reservation is created, and draft/focus return unchanged.
- The approval/memory/live-review/presentation set passed 113 tests; the affected
  Git-panel/diff/history/switch set passed 52 tests outside the parent sandbox so
  Mos's own Git isolation could run. After preview deduplication, 94 affected
  approval/memory/history/TUI tests passed. These suites overlap.
- Real macOS PTYs checked source dark/light/plain, the Git renderer and the
  isolated installed wheel: selected packet inspection, a genuine local memory
  preview, complete hash detail, multiline draft, 112-to-64-column resize,
  scroll/close, diagnostic inspection, passive quit and terminal restoration.
  Synthetic `approval-` captures are in the existing implementation-preview
  directory. No real session data, credential access or paid calls were used.
- The combined error + companion + draft case initially exceeded a 64x24
  terminal's height. The companion now substitutes for routine activity details
  while errors remain visible, and its detail pane can shrink to one line.
  A rendered-window regression checks the composer stays visible with both an
  error and previously expanded activity. The final core set passed 40 tests;
  the six companion tests also passed separately. Source, Git-renderer and
  installed-wheel PTYs passed this combined error/resize/close/draft case.
- Final lint, formatting, strict typing, sdist and wheel builds passed. The wheel
  was reinstalled only into the private smoke environment. The existing user
  installation was not changed. The full publication gate and other-platform
  visual qualification remain unrun.

The companion retains full detail rather than abbreviated approval tokens; its
summary may abbreviate long scope/reason labels, which remain complete in the
scrollable detail. Pending-memory details now appear in the companion instead of
a duplicate transcript wall, and preview events preserve an open saved-history
view. Existing exact-hash approval parsing, signed admission, expiry, spending,
backend freshness checks and one-use dispatch are unchanged. Closing the inspector
is a UI-only operation; explicit backend discard/cancel still has its existing
meaning. Stop this slice after the stated evidence. Next: session picker,
directory selector and diff-view consistency, then remaining platform/visual and
publication gates before overall milestone acceptance.

## Session, directory and diff consistency slice (2026-10-14)

Objective: apply shared themes, compact headers, selection emphasis and deliberate
spacing to both pickers and both diff renderers. Session names lead list rows;
full identities remain inspectable. Directory editing remains preview-before-use.
Preserve metadata-only listing, active-session exclusion, stale catalog/directory
checks, literal drafts, focus, keyboard controls and exact diff/source coordinates.
No acquisition, persistence, execution, approval or spending changes.

Guidance: Python engineering and bounded verification guides and loop template
selected above. Risk: material presentation and navigation change. Budget: three
evidence-changing passes and a 60-minute review window; no paid calls. Acceptance:
existing picker/directory/diff regression suites, focused Unicode/narrow/theme and
selection tests, static checks, builds and real macOS source/installed-wheel PTYs.
Stop when those checks pass; full publication and other-platform visual gates
remain separate. Screenshot fixtures use synthetic sessions and local repositories.

Auxiliary-screen verification and handoff:

- Shared list selection uses a distinct accent/bold class and `›` marker, leaving
  prompt-toolkit's text-selection treatment intact. The first PTY capture exposed
  an inherited reverse-video row; the separate list style corrected it. Patch
  lexing preserves every displayed character and coordinate prefix, including
  source containing literal pipe separators. Selected paths stay in pane headings
  while source scrolls; stale/historical headings retain their labels.
- The auxiliary/presentation/picker/directory/companion set passed 36 tests, with
  four new tests for Unicode cell bounds, adaptive paging, selection-preserving
  catalog refresh, scrolling complete identity details, explicit theme forwarding,
  narrow directory preview/edit/cancel, and byte-preserving patch styling.
  The switch/TUI/activity set passed 35 tests after its picker factory accepted the
  new theme keyword. Assertions formerly expecting IDs in list rows now inspect
  the complete selected-session detail instead.
- Existing Git/diff checks exercised source coordinates, frozen attachments,
  freshness, draft/focus preservation and terminal resize. The final affected
  diff-panel and real-PTY regression set passed all six tests after the selected
  heading adjustment, outside the parent sandbox so Mos's own Git isolation could
  run. No isolation policy or reader implementation was changed.
- Names/project-memory/registry portions passed in the expanded run; the mapped
  memory module passed all ten tests after its startup-picker mock accepted and
  checked the theme keyword. Existing owner/workspace, stale selection, active
  session, path revalidation and memory-identity guards remain in place.
- Real macOS PTYs checked source dark/light/plain, the Git-review renderer, and
  installed-wheel ordinary/Git-review renderers. Each exercised session filtering
  and full details, directory preview/edit/cancel, a multiline draft beside a live
  local diff, 112x36 to 64x24 resize, patch focus/scroll/close, paused queues and
  terminal restoration. Saved seeded-session bytes remained unchanged; the new
  diff session had no submitted entries. No paid calls or real user sessions.
  The harness waits for the bounded patch to load before paging and for the final
  footer hints before capture. `aux-` screenshots are retained in the existing
  local implementation-preview directory, outside Git.
- Final lint, formatting, strict typing, source/wheel builds and the private
  installed-wheel checks passed. Suite counts overlap and must not be summed.
  The existing user-installed CLI remains unchanged. Full `make check`, security/
  container gates, other-platform visual qualification and final owner visual
  acceptance remain pending before publication or overall milestone acceptance.

The selected theme now reaches startup pickers and in-session directory switching;
this is a per-launch preference, not saved-session authority. Type-only controller
annotations keep shared presentation independent of the directory/Git import path.
No session capacity, catalog acquisition, directory admission, source selection or
approval boundary was expanded. Stop this slice after the stated checks. Next:
review the combined visual result and complete the combined delivery/qualification
checks; individual tool-call streaming remains separate work.

## Combined local review (2026-10-14)

The [combined review record](TERMINAL_INTERFACE_COMBINED_REVIEW.md) closes the
local review of revision `114a09e`: welcome, conversation, active operation,
errors, approval, session picker, directory selector and both diff renderers.
Focused regressions, source/installed-wheel PTYs and visual inspection found no
blocking issues. A one-character footer wrap at 64 columns remains cosmetic.
The standalone eight-screen gallery is also in Downloads. No application code
changed. Joshua accepted the combined visual result on 2026-10-14, including the
cosmetic footer wrap. Full delivery gates and other-platform visual qualification
remain pending; this does not close the overall milestone.

## PR #306 delivery validation

Objective: complete the PR's source, package, security, container and platform
checks after owner visual acceptance. Existing bounded verification guidance and
loop template apply. Preserve runtime behavior, approval boundaries and test
assertions for source attachment and saved-state identity. Risk: routine test
maintenance within a material delivery batch. Bound: three evidence-changing
correction passes, no paid requests, each CI attempt within its configured timeout.
Stop when the final candidate's required checks pass; do not merge or release as
part of validation.

The initial local `make check` passed lint/formatting/typing but hit diff timeouts
under the parent sandbox. That run was stopped and replaced by `make check`
outside the parent sandbox so Mos's own Git isolation could run. The replacement
found a separate obsolete PTY assertion in
`test_conversation_diff_acceptance.DiffPTYTests`: it still waited for the removed
`Message` frame title at startup. The test now waits for `Type a message`, retaining
its existing attachment, snapshot, resize, removal and close checks. The corrected
real-PTY reproducer passed. Application code and isolation policies are unchanged.
Full local and final-head GitHub validation results remain pending at this entry.

The expanded run also identified two remaining fixture updates: tmux startup
waited for the same removed frame title, and memory-selection inspection still
asserted detailed preview text in the transcript. The tmux startup check now uses
the composer prompt; all four private-tmux tests passed with tmux required.
Memory-selection assertions now inspect the companion's complete details, adding
an explicit exact-hash check while retaining full-source, sanitization and discard
checks. All 17 memory-selection/companion tests passed. These are test-only
corrections; final-head CI and the expanded local reports remain pending.
