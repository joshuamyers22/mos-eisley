# `/diff` attachment destination and authority hardening

- Status: implementation complete; accountable review pending
- Owner: Josh Myers
- Started (UTC): 2026-10-04
- Related review: [owner `/diff` security review](CONVERSATION_DIFF_OWNER_SECURITY_REVIEW.md)

## Objective and completion evidence

- Before a selected-line attachment is queued, show its complete frozen excerpt and the recorded or live chat destination in a scrollable TUI view. Require a second explicit send bound to the same draft, attachments, and destination. Keep the draft on cancellation or stale-source refusal.
- Keep excerpts as untrusted user data. Selection and confirmation add no Git edit, tool, review, provider-selection, or spending authority. Existing source verification and live admission continue to gate dispatch.
- Add an adversarial source-instruction test that tries to trigger review, tool use, or provider escalation from an excerpt and asserts the request remains ordinary tool-free chat with the source in a user text block.

Selected guidance: [Python engineering](PYTHON_ENGINEERING_GUIDE.md), [bounded verification](AGENTIC_VERIFICATION_GUIDE.md), [verification template](../templates/AGENTIC_VERIFICATION_LOOP.md), [work-note template](../templates/WORK_NOTE.md), and the existing [panel threat model](CONVERSATION_DIFF_PANEL_THREAT_MODEL.md). The [v1 `/diff` plan](mos-eisley-plan.md) and [TUI](../src/mos_eisley/conversation_tui.py) define the product behavior.

Risk class: material security and admission correctness. Budget: one implementation pass, up to two correction passes, focused TUI/policy tests, then one full `make check` before publication. Stop if the review can be bypassed for attached sends, preview bytes differ from queued bytes, or malicious source acquires a tool/review/spend path.

| Dimension | Pass rule |
|---|---|
| Exact owner view | Full frozen excerpt and destination are available before queueing; changing the draft or attachments requires a new review |
| Admission | First send opens review; confirm queues only after existing source verification; cancel preserves the draft |
| Source authority | Adversarial source text remains user data in a tool-free ordinary chat request |
| Regression | Focused `/diff` tests and full `make check` pass |

## Handoff

- Current state: bound TUI confirmation, recorded/live destination text, adversarial policy test, and threat-model follow-up implemented on `feat/diff-attachment-authority`, stacked on combined Git-isolation head `bd68450`.
- Next smallest safe action: publish a stacked draft PR for accountable security review.
- Blocker and required authority/input: none for implementation; accountable owner review remains required for broader security or release approval.
- Checks already run: 19 focused `/diff` tests passed on the final session-label candidate. Full `make check` passed: Ruff, format, strict Pyright, 2,724 source tests (4 skipped), export verification, wheel build, and 1,978 installed-wheel smoke tests. The new `/diff` test files run in the focused and source suites; wheel smoke exercises general TUI and Git-isolation integration.
- Residual limit: a model can still misinterpret malicious source text, but excerpts carry no tool, review, provider-selection or spending authority in code. A same-user concurrent writer can race after the final source check; the frozen bytes are preserved and the accepted owner-operated trust scope is unchanged.
