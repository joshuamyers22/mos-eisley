# Installation and updates delivery

- Status: active
- Owner: Joshua Myers
- Started: 2026-10-06
- Objective: plan §§28–29; standalone, direct download, npm and Homebrew share verified self-contained artifacts, first-launch guidance, bounded discovery, transactional replacement and compatible recovery.
- Baseline: merged main `758f3e4` in isolated `feat/installation-updates` worktree.
- Selected production-project-template guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, `templates/WORK_NOTE.md`, `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md` (repository pin `8879be4`).
- Retrieved: README, PROJECT_BRIEF, PROJECT_MEMORY, release workflow, CLI/conversation/TUI boundaries, plan §§27–29 and package smoke tests.
- Risk: high; executable supply chain, user-owned installation and state preservation. Accountable publisher review is required before activation.
- Invariants: signed inert release metadata; pinned publisher key; bounded HTTPS origins/downloads/extraction; no key or workspace transmission; no downgrade; stage and verify before atomic activation; old runnable version retained; no migration or replay of session/spend state; active sessions block replacement; package-manager ownership respected.
- Non-goals: API requests, study evidence, new storage migrations, native Windows, automatic restart of paid work, automatic public publication.
- Rubric: real self-contained install/version/help/session and upgrade/recovery (blocking); tamper/path/ownership/concurrency rejection (blocking); static/combined/package checks (blocking); real OS/package-manager qualification and reviewed publication (blocking for availability claims).
- Verification ceiling: three evidence-changing passes (implementation/fault tests; real frozen artifact and package-manager journeys; combined gate/CI). Zero paid provider calls. Stop publication on missing signing custody, package ownership, platform evidence or accountable approval; report remaining gates explicitly.

## Verification

- Implementation/fault evidence: 32 focused tests passed, including account-login PATH selection and custom installation-root selection. Tamper, wrong publisher, channel/schema/platform/epoch substitution, malicious archive entries, launcher/root conflicts, active-client locks, downgrade/binary failure, pre/post-activation interruption, damaged recovery and preserved user state are exercised. Full-source static checks passed; later edits require affected checks.
- Actual committed `80b104c` macOS arm64 frozen runtime passed credential-free setup, version/help, recorded chat/cold resume, upgrade/rollback/recovery and state preservation without Python/Node on PATH. Archive SHA256: `cccad076741e13b1a62bcb750edb498318a94e763a821ba02aa524499fa6ac83`. Upgrade evidence uses an explicitly synthetic predecessor with older distribution metadata and the same code; real prior-release compatibility is not proven.
- Real local npm tarball pack/install/launch passed; Homebrew Ruby syntax passed. Actual isolated Homebrew install revealed dylib-ID rewriting of the frozen runtime; the formula now preserves rpaths and excludes libexec from cleaning. The corrected actual install/launch/formula-test/uninstall journey passed. Native bootstrap build/help also passed with host access; sandboxed one-file loading cannot create its required macOS semaphore.
- The final committed-archive Homebrew rerun initially failed after uninstall when the fixture forced a full core-tap clone and the network reset. Removing that fixture-only override restored Homebrew's normal API configuration; the full install/launch/formula-test/uninstall journey passed. The owner Cellar and taps were not modified.
- The native bootstrap then installed the committed archive offline using the enrolled public root and locally signed candidate metadata. With Python/Node absent from PATH, the installed command selected its custom root, reported disabled discovery, recovered and uninstalled successfully. Tampered signed metadata was rejected. This local signature binds a private qualification artifact, not a public release or accountable review approval.
- Combined `make check` is running with host access for the repository's socket/Git/tmux tests. It must not be reported passed before source and installed-wheel results finish. The earlier sandbox attempt stopped at static checking, before the full tests.
- Locked runtime audit passed: 54 packages, no known vulnerabilities or adverse project statuses. No paid provider requests were made.
- Owner selected existing provider account browser sign-in. `mos auth` delegates to native clients, excludes explicit API/token environment variables and relative/project PATH entries, and does not copy native auth storage. Tests use stubs: no real account login or subscription inference qualification was performed.
- A dedicated owner-only Ed25519 publisher key was enrolled outside Git; only the public root is in source. GitHub secret custody and release-environment protection were not configured. The owner has no npm account/scope; the selected scope is provisional. The Homebrew tap does not exist. Actual WSL2 qualification requires a Windows-hosted runner; none is registered, and Linux CI cannot substitute.

## Accountable review and release disposition

Pending review of the exact committed candidate and its CI. The user request
authorizes implementation and a reviewable draft; it does not provide independent
security review of the new executable-publisher trust boundary. Per `AGENTS.md`,
security and release approval require accountable review beyond this agent's own
assessment. No official release, npm package or public tap has been published.

Review must address the enrolled publisher identity/custody, bootstrap HTTPS
trust, bounded download/extraction, transaction fault recovery, state separation,
manager provenance/ownership, platform support and the explicit limitation that
browser login does not yet supply Mos inference. npm/Homebrew upgrades are fixed
manual manager instructions; automated manager transaction/rollback and a complete
first-launch subscription adapter remain incomplete.
