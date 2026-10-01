# Conversation live review implementation record

- Status: engineering integration; exact live release-candidate run and owner
  release decision remain open.
- Owner: Joshua Myers. Started and updated: 2026-09-29 UTC.
- Starting source: `540098a` from GitHub `main`; branch
  `feat/conversation-live-review` in a separate worktree.
- Requirement: [plan §16 and §26](mos-eisley-plan.md), [G2 roadmap](ROADMAP.md),
  [live-launch admission](REVIEW_LAUNCH_ADMISSION.md).
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`,
  `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, and
  `templates/ADVERSARIAL_CODE_ARCHITECTURE_REVIEW.md`.

## Objective and checks

Deliver an explicit `/review` path from recorded chat to the existing signed
live-review command. One selected prepared brief, campaign and image must be
rechecked at dispatch. Credentials, signer files and operating paths stay out
of session state. A failed or interrupted attempt cannot be retried by resume.
Ordinary chat remains recorded. No provider call or spend occurs without a
fresh owner-authorized launch.

Risk class: high, because the new child process crosses a credential and spend
boundary. The acceptance threshold is focused identity, state, cancellation and
receipt tests; static checks; full source and installed-wheel gates; container
smoke; exact candidate live qualification and owner review before production.
The engineering loop stops on passing offline checks or a domain-approval gate.
Provider cost ceiling for this engineering work: zero.

| Pass | New evidence | Finding and disposition |
|---|---|---|
| Focused behavior | Frozen packet, TUI trigger, SQLite resume, manifest and receipt tests | Live result is retained only after exact brief and completion checks. |
| Failure behavior | Cancellation, no retry and repeated-interrupt child reap tests | Escalated cleanup keeps ownership through repeated cancellation. |
| Static and artifact | Ruff, Pyright, locked build/audit, wheel and container gates | Record final command results and exact candidate digest below. |

## Handoff and release boundary

The 2026-09-27 G2 campaign applies to its frozen profile and historical image.
It does not qualify this branch, a new brief, or a release candidate. The owner
must provide a qualified exact candidate campaign, signer/credential custody,
fresh launch and spend cap for the full terminal journey, then review release
evidence. No sampling artifacts or study outcomes are part of this task.

Full quality gate: privileged `make check` passed, including lint, type check,
source tests, runtime export verification, wheel build and installed-wheel smoke.
The installed-wheel smoke ran 1,910 tests successfully. The locked `make audit`
also passed with no known vulnerabilities in 50 runtime packages.

Focused final-source checks: 10 live-review tests, Ruff and Pyright passed.

Container gate: `make container` passed with a no-network, read-only runtime
smoke and the existing controller/campaign/launch isolation checks. Candidate
image ID: `sha256:bb5708d633a497268ed5de3e6a3701cc775453752524bb5704ae1edda953530d`.

Owner live campaign, exact candidate journey, and release approval: pending.
