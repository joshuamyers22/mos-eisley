# Installation and updates delivery

- Status: candidate prepared; exact-head CI, accountable review and publisher/platform inputs remain open
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
- Combined `make check` completed successfully with host access: source suite 3,616 cases with 17 skips and 85% coverage, dependency-export verification, wheel/source builds and installed-wheel suite 2,601 cases with 13 skips. The earlier sandbox attempt stopped at static checking, before full tests. Later affected source cases passed in the 32-test run.
- The 32 new installation/account boundary cases also passed against a fresh installed wheel with locked runtime hashes. They are now included in future installed-wheel CI selection. Dependency installation failed in the sandbox; the host-access repeat succeeded. No skipped or failed sandbox check was counted passing.
- Package smoke tools no longer select a hardcoded 0.1.0 wheel. A disposable future-version 0.1.1 wheel built, installed into an isolated target and reported its correct version. This is packaging evidence, not a release. Stable/preview filename selection now follows project metadata.
- Affected installed file/identity smoke passed with host access: 164 cases, 8 platform skips, plus two legacy-fixture cases. The sandbox attempt failed at the required local Unix socket and was not counted passing.
- Native CI initially passed Linux arm64/x86_64 and macOS arm64, but Intel failed loading cryptography: its bundled libssl lacked `_SSL_get0_group_name`. Distribution builds now require managed Python 3.12.14 and record TLS/platform build inputs; the local runtime reports OpenSSL 3.5.7. All four native distribution jobs passed at `ed094be`, including actual macOS npm/Homebrew journeys. Container, secret scan, Windows file contracts and both POSIX storage jobs also passed. The final package-test selection/record update requires its own exact-head CI; actual WSL2 remains unqualified.
- Locked runtime audit passed: 54 packages, no known vulnerabilities or adverse project statuses. No paid provider requests were made.
- Owner selected existing provider account browser sign-in. `mos auth` delegates to native clients, excludes explicit API/token environment variables and relative/project PATH entries, and does not copy native auth storage. Tests use stubs: no real account login or subscription inference qualification was performed.
- A dedicated owner-only Ed25519 publisher key was enrolled outside Git; only the public root is in source. GitHub secret custody and release-environment protection were not configured. The owner supplied npm username `joshuamyers22` and delegated organization-scope selection. `@mos-eisley` is selected; organization creation/ownership remain unverified, and local npm reports ENEEDAUTH. The Homebrew tap does not exist. Actual WSL2 qualification requires a Windows-hosted runner; none is registered, and Linux CI cannot substitute.

## Accountable review and release disposition

Delivery draft: [PR #289](https://github.com/joshuamyers22/mos-eisley/pull/289).
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

## Selected npm organization

The owner requested review before approving candidate `15899a1`; PR #289 stays
in draft. The selected organization scope is `@mos-eisley`, separate from the
owner's supplied personal npm account `joshuamyers22`. Generator, launcher and
update instructions use `@mos-eisley/mos-eisley` together. No organization was
created, credentials inspected, package published or account converted. Public
package lookup cannot establish organization availability or ownership. The scope
change creates a new candidate requiring its own CI and accountable review.

Affected scope-change checks: all 32 installation/account tests and Ruff
check/format passed. Actual local npm pack/install/launch passed under the new
organization names; the generated Homebrew formula passed syntax validation.
This uses the retained native fixture and does not claim a rebuilt current-head
runtime or registry publication. Strict Pyright passed with zero errors or warnings; new exact-head CI remains pending.
