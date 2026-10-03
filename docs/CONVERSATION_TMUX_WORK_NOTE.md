# Work Note: external tmux compatibility

- Status: closed
- Owner: Josh Myers
- Started: 2026-10-02
- Review by: 2026-10-16
- Base: GitHub main `a1cb38bcfcbe332a7db2c22322fa72fb560db672`

## Objective and completion evidence

Deliver the external workspace guide and real tmux compatibility tests against
current main. Preserve ordinary launch, conversation/storage ownership, literal
paste and user/provider authority. No embedded backend, paid calls, merge or
release. Risk: material test/process integration, with no runtime authority change.

Blocking rubric: drafts and process identity survive detach/reattach; queued work
remains paused; a competing controller is rejected; paste stays literal; resize
and exit preserve usability; server loss leaves saved state available for explicit
reopening. Test resources use private temporary sockets/storage and bounded
subprocess deadlines; cleanup affects only the created server and clients.

Selected guidance: [Python guide](PYTHON_ENGINEERING_GUIDE.md),
[verification guide](AGENTIC_VERIFICATION_GUIDE.md),
[work-note template](../templates/WORK_NOTE.md), and
[verification-loop template](../templates/AGENTIC_VERIFICATION_LOOP.md).
Evidence-changing passes: focused real tmux tests, static checks and source/
installed-wheel gate. Stop when these pass; report platform evidence separately.
Initial ceiling: four correction passes and two hours; no provider spending.

## Observations and verification

The implementation reuses the current conversation CLI and controller. A private
tmux server is test infrastructure; source and installed-wheel suites use the
same test file. CI installs tmux and requires its presence instead of silently
skipping. Actual WSL2 qualification remains external to Ubuntu CI.

## Handoff and close

macOS 15.1 with tmux 3.7c: four focused source tests passed, then four tests passed
from a built wheel in a temporary environment outside the checkout with hash-pinned
runtime dependencies. Lint, strict typing, documentation links and diff checks
passed. Missing-tmux behavior was separately verified: four explicit skips locally
and a failure when required. `MOS_REQUIRE_TMUX=1 make check` passed: 2,646 source
tests with four existing optional skips, 86% branch-inclusive coverage, 1,922
installed-wheel tests with no skips, lint/format, strict typing, runtime export
verification and wheel/sdist builds. The full source and installed-wheel runs
took approximately 37 and 25 minutes respectively; no correction was needed after
the passing focused checks. Documentation-only follow-ups received link and diff
checks.
Passing Ubuntu CI and actual WSL2 evidence remain pending. The original checkout's
uncommitted plan amendment remains untouched.

Ubuntu 24.04 CI with tmux 3.4 left `pane_dead_status` empty in three clean-exit
checks even after waiting for it. The fixture now writes the launched application's
exit code to its private temporary directory through a shell wrapper, then waits
for pane death and requires that recorded code to be `0`. Saved state and terminal
restoration remain separate assertions; no application runtime code changed.
All four focused tests passed in an Ubuntu 24.04 container with tmux 3.4 from an
installed package. Ubuntu source and wheel CI must pass on this correction before
merge.

The guide, tests and required CI wiring complete this implementation slice;
all-platform qualification remains open. Durable retrieval was added to
`PROJECT_MEMORY.md` under `conversation.external-tmux`. No provider calls, merge,
release or publication occurred. Test servers, clients and temporary wheel
environments were cleaned up by their fixtures.
