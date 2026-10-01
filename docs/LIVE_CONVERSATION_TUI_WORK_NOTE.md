# Work Note: Live conversation in the TUI

- Status: draft PR open for accountable review
- Owner: Joshua Myers
- Started (UTC): 2026-10-01
- Last updated (UTC): 2026-10-01
- Review by: before v1 G2 release
- Related plan: [§16.0](mos-eisley-plan.md); [PR #252](https://github.com/joshuamyers22/mos-eisley/pull/252)

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
| 2026-10-01 | review | Security/spending trace found that new live sessions admitted schema-1 policies without conservative cache-write pricing. The CLI and runtime now require schema 2; 42 focused tests pass. The owner accepted the earlier assessment, and the corrected candidate awaits an exact decision. | [Review record](LIVE_CONVERSATION_TUI_SECURITY_SPENDING_REVIEW.md) |
| 2026-10-01 | test | Corrected code commit `c29c1f5` passed elevated `make check`: 2,642 source tests (four skips), 86% coverage, build, and 1,918 installed-wheel tests. A sandboxed attempt failed only in local HTTP fixture socket binding. | Full local quality gate log |

## Handoff

- Current state: implementation and offline quality gates pass; the corrected
  security/spending review awaits Joshua's exact-candidate decision, and live
  provider validation remains open.
- Next action: record the owner decision on code commit `c29c1f5`, then conduct
  exact-candidate live validation under a separate approved spend scope.
- Provider calls made by this work: none.
