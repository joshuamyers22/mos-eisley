# Subscription client compatibility and local setup

- Owner: Joshua Myers
- Status: closed — local setup and validation complete, 2026-10-22 UTC
- Baseline: rc.5 / `b04906553f2622210adc82c43893777a6b98aa44`
- Branch: `feat/subscription-client-setup`

The owner requested support for the installed Codex 0.162.1 and configuration of
both ChatGPT and Claude subscription TUI routes. Preserve Codex 0.161.0 and Claude
Code 2.1.283 compatibility. Add a bounded subscription chat launcher using the
existing immutable authorization and saved-session machinery. Configure local
shortcuts against an isolated patched runtime; preserve the published rc.5 runtime.
Native clients retain all login credentials. Read native status metadata only.

Selected guidance: `AGENTS.md`, `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/THREAT_MODEL.md`, `templates/WORK_NOTE.md`, and
`docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`. Existing session/usage contracts in
`docs/SUBSCRIPTION_SESSIONS.md` remain authoritative. Official protocol guidance:
https://learn.chatgpt.com/docs/non-interactive-mode

Invariants: exact version admission, no API fallback, explicit transfer/quota
consent, bounded private session scope, native tools disabled, no automatic replay
or renewal after uncertain usage, and unchanged existing sessions/configuration.
Unknown native versions must refuse before auth or inference. Receipt metadata
must identify the actual admitted client version. Launching a new chat creates a
fresh scope; resuming uses that session's original scope and expiry.

Threats: project-local executable injection, ambient credential/config leakage,
tool activation after a client update, permissive scope/state storage, accidental
dispatch before consent, and lost or uncertain usage on cancellation. Preserve
trusted absolute executable selection, stripped environment, ignored native user
configuration/rules, exact tool-free native fixture evidence, checked private
storage, and existing immutable usage accounting. The owner requested setup,
not new live provider probes. Native status and loopback fixtures are permitted;
no real prompts, quota purchases, API requests, or sampling-store access.

Acceptance: supported/unsupported-version regression tests; actual Codex 0.162.1
loopback fixture with empty tools and exact model/effort; launcher tests covering
consent, readiness, private storage, immutable scope, and chat delegation; focused
subscription regressions; one combined `make check`; actual source/wheel status
and zero-prompt TUI launch checks for both routes. Configure user shortcuts only
after focused checks. Stop on unsafe native tools, changed credentials, unexpected
storage changes, failing checks, or missing login; report the exact remaining
owner interaction without claiming live reliability. Agent review is not an
independent security review. Merge/publication remain separate.

## Verification and local configuration

- All 81 focused Codex/Claude/authorization/launcher tests passed, including both
  admitted Codex versions, unknown-version refusal before auth, actual dispatch
  version receipts, consent refusal, private scope creation, unchanged resume
  scope/ledger and refusal after route/workspace/client/expiry changes.
- Actual macOS Codex 0.162.1 completed one loopback-only fixture request with the exact
  `gpt-6-sol` / `medium` profile and an empty tool inventory. The fixture now uses
  a disposable home and Codex home. Its first run failed because that new Codex
  home had not been created; creating it fixed the fixture, with no production
  trust exception or real credentials. The adapter's tool restrictions and native
  output parser needed no relaxation.
- Native sanitized status reports both existing accounts signed in. Neither
  browser login nor credential-cache inspection was needed.
- Source and isolated installed-wheel TUIs each opened and quit with empty
  composers for both providers. Both configured shell shortcuts also passed
  their actual interactive consent/start/empty-quit journeys. Usage directories
  remained empty and terminal modes restored. The shell PTY check uses its master
  after macOS detaches the slave; the initial slave-only observation failed with
  ENOTTY rather than identifying a product failure.
- Lint/format and canonical `uv run --frozen pyright` pass. An initial direct
  checker invocation selected the wrong interpreter and reported missing imports;
  the canonical environment checked 729 files with zero errors or warnings.
- The combined `make check audit` gate passed: 3,773 source tests run with
  21 skips and 85% coverage; 2,741 installed-wheel tests run with 17 skips;
  lint, format, typing, export, build and smoke checks passed; the audit found no
  known vulnerabilities or adverse project statuses across 54 packages.
  The installed-wheel smoke list now also includes the
  launcher tests; its changed file passed focused lint/format checks before the
  gate reaches package smoke. No runtime code changed after the gate started.
  The fully checked wheel is byte-identical to the installed
  local preview: SHA-256
  `35916451efb09349cfb74fcd52a5827e6408f1d2a1dc8fbdb38fd14f3addc704`.

The local isolated wheel lives under the owner's private
`~/.local/share/mos-eisley-subscription-preview`, with `mos-chatgpt` and
`mos-claude` shortcuts on the existing local bin path. Their default storage root
`~/.mos-eisley-subscriptions` passed native private-directory admission. No scope
is issued until launch, so setup does not leave an expired default authorization.
The signed public rc.5 runtime/launcher, native clients and credentials remain
unchanged. Local preview wheel identity and setup records stay outside Git. No
real provider prompt or paid inference was sent; these checks do not establish
new live reliability or billing qualification.

Exit: the requested compatibility and both local routes are configured and
verified. Existing controls remain intact; no blocking finding remains for this
local setup. The new runtime and shortcuts are development configuration rather
than a signed public update. Changes remain local on the feature branch; commit,
merge, cross-platform release qualification and publication are separate steps.
