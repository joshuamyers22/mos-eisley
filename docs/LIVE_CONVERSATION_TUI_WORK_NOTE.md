# Work Note: Live conversation in the TUI

- Status: exact-candidate live validation passed; draft PR awaiting release review
- Owner: Joshua Myers
- Started (UTC): 2026-10-01
- Last updated (UTC): 2026-10-02
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
| 2026-10-01 | owner decision | Joshua Myers accepted the corrected security/spending implementation review for code commit `c29c1f5`, including its documented limits. This grants no particular spend, provider dispatch, merge or release authority. | [Review record](LIVE_CONVERSATION_TUI_SECURITY_SPENDING_REVIEW.md) |
| 2026-10-01 | owner decision | Joshua Myers separately approved scope SHA-256 `734b1c8756ee6eb7deb0e4e69ad6560a00a4ca8467db613707fa4c03b23f08e8` for two synthetic live TUI turns under a dedicated $0.002664 local reservation ceiling. | Owner-private `private/live-tui-validation-20261001/HANDOFF.md` and `approval.json` |
| 2026-10-01 | live validation | Installed wheel SHA-256 `98bfb02c9fe8e55df8eeacf626e70db49a5ea721471a7279aa3211bb16a52f33` from commit `eb456509822133f2cb19bbf502f8a73398378936` opened the full-screen TUI, completed one synthetic turn, saved the session, resumed that exact session, and completed its contextual follow-up. Both answers matched the expected one-word result. The schema-2 policy SHA-256 was `25b30c8d3d7e140bf7f03128653ad15806e4652379ebc5d705e0199d3003eb30`; the dedicated ledger settled two receipts totaling $0.000034 with zero unresolved reservations. | Owner-private `private/live-tui-validation-20261001/validation-result.json`; session SHA-256 `1053e9a52e5f2f03cb75f47ac96dffa557bee444f60afc373f3eba4369bfdd61` |
| 2026-10-02 | test | PR head `eb45650` passed GitHub source, package, container, quality and secret checks. A local final-tree rerun passed lint, typing, source tests, export and build, then was manually interrupted during duplicate installed-wheel smoke. That interruption is not a passing smoke result; final-head CI remains the publication gate. | [PR checks](https://github.com/joshuamyers22/mos-eisley/pull/252/checks) and local `make check` attempt |

## Handoff

- Current state: implementation, offline quality gates, accountable owner
  security/spending review, and exact-candidate live validation are complete.
- Next action: finish PR #252 CI and accountable production release review before
  merging. The live validation does not itself approve release or expand G2
  review authority.
- Provider generations made by this work: two, both settled under the separate
  approved scope.
