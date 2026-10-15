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
