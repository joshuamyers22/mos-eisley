# Work Note: Live conversation in the TUI

- Status: ready for accountable review
- Owner: Joshua Myers
- Started (UTC): 2026-10-01
- Last updated (UTC): 2026-10-01
- Review by: before v1 G2 release
- Related plan: [§16.0](mos-eisley-plan.md)

## Objective and completion evidence

Connect an explicitly authorized OpenAI text conversation to the existing TUI.
Preserve queued turns, contextual follow-ups, cancellation, saved session identity,
no implicit replay, and the shared spending cap. No repository tools or G2 review
authority are added by this change. A live credentialed validation, owner security
review, and production release decision remain separate gates.

## Context retrieved

- [Terminal behavior](CONVERSATION_TUI.md), [spending policy](OPENAI_SPENDING.md),
  [shared ledger](SHARED_SPENDING.md), and [G2 plan](mos-eisley-plan.md).
- `docs/PYTHON_ENGINEERING_GUIDE.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`,
  `docs/ADVERSARIAL_REVIEW_PLAYBOOK.md`, and `templates/WORK_NOTE.md`.

## Observations and attempts

| Date | Type | Observation or result | Evidence |
| --- | --- | --- | --- |
| 2026-10-01 | observation | Recorded chat used a finite cassette and a saved attempt counter. | `conversation.py`, `conversation_state.py` |
| 2026-10-01 | decision | Save a distinct live mode and provider/spend identity; use the existing one-response spending controller for each turn. | [ADR](ADR-LIVE-CONVERSATION-TUI.md) |
| 2026-10-01 | test | Offline live turns, cancellation, adapter/ledger receipt, CLI launch/resume, and SQLite inspection pass. | `tests/test_conversation_live_chat.py` |
| 2026-10-01 | test | Elevated `make check` passed: 2,642 tests, 86% coverage, export, build, and 1,918 installed-package smoke tests. The later SQLite header and live response byte-reserve corrections passed 40 affected tests, lint, types, and build. | Local quality gate log and focused commands |

## Handoff

- Current state: implementation and offline quality gates pass; accountable
  security/spending review and an exact live provider validation remain open.
- Next action: open the draft PR for review.
- Provider calls made by this work: none.
