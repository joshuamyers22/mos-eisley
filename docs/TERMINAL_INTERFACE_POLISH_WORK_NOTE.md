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
