# Work Note: review campaign preparation window

- Status: closed
- Owner: Joshua Myers
- Started (UTC): 2026-09-21
- Last updated (UTC): 2026-09-21
- Review or delete by: G2 qualification closure
- Related incident: fresh `bac7dd2` formal campaign slot 3 deadline failure

## Objective and completion evidence

- Intended outcome: give a manually gated, fixed three-slot campaign enough time to finish without weakening any provider-operation or runtime deadline.
- Required invariants: preparation remains inert; exact hashes and pricing expiry still bind every call; provider operations remain capped at 60 seconds; exchanges remain derived to at most 120 seconds and absolutely capped at 300 seconds; controllers remain capped at 360 seconds; guardians remain capped at 305 seconds; phase authority remains one use and at most 300 seconds; spending remains reserved before dispatch; retries remain unauthorized.
- Evidence that will show completion: deterministic approval-window tests, unchanged runtime-deadline tests, documentation review, and one passing `make check`.

## Context retrieved

- `docs/PYTHON_ENGINEERING_GUIDE.md`
- `docs/AGENTIC_VERIFICATION_GUIDE.md`
- `templates/AGENTIC_VERIFICATION_LOOP.md`
- `templates/THREAT_MODEL.md`
- `docs/REVIEW_BROKER_ADMISSION.md`
- `docs/REVIEW_CAMPAIGN_CEREMONY.md`
- `docs/REVIEW_CAMPAIGN_RUNNER.md`
- `src/mos_eisley/run/review_broker.py`
- `src/mos_eisley/run/review_controller.py`
- focused broker, controller, campaign, and runner tests

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-21 | observation | Every prepared review call receives an absolute expiry of preparation time plus ten minutes, clipped by pricing expiry. | `PreparedReviewCall` constructor | Add a failing 30-minute boundary test. |
| 2026-09-21 | observation | A controller uses the earlier of its own 360-second limit and its prepared envelope expiry. | `BrokeredReviewController.run_critics` | Preserve this composition. |
| 2026-09-21 | observation | The failed slot began with only 13.1 seconds left because all three slots were prepared before the manual seal and phase ceremony. | Private terminal campaign evidence | Extend only pre-dispatch freshness. |
| 2026-09-21 | attempt | The deterministic 30-minute regression failed against the old ten-minute behavior. | Focused `unittest` discovery run: 1 failure among 24 tests | Introduce one named bounded constant. |
| 2026-09-21 | attempt | The named 1,800-second freshness cap and pricing clipping passed broker, envelope, controller, campaign, runner, provider and guardian suites. | 107 focused tests passed | Run the complete repository gate. |
| 2026-09-21 | observation | The sandboxed source suite could not bind loopback sockets in 31 MCP HTTP/OAuth/schema cases; all other cases completed without assertion failures. | 2,498 discovered; 2,463 passed, 4 skipped, 31 environment errors | Rerun the affected modules with loopback access. |
| 2026-09-21 | attempt | The affected MCP modules passed with loopback access, and the remaining export, build, coverage and installed-wheel gates passed. | 68 MCP tests passed with 4 skips; 88% coverage; 1,856 wheel tests passed | Audit constants and diff. |
| 2026-09-21 | observation | Constant and diff audit found the 1,800-second change only at prepared authorization; runtime and spending bounds remain unchanged. | `rg`, `git diff --check` | Close the offline correction. |

## Handoff

- Current state: offline implementation and verification complete; no live campaign has been prepared or dispatched from this worktree.
- Next smallest safe action: commit this slice, rebuild the production image from that commit, then prepare a wholly fresh campaign and approval artifacts.
- Blocker and required authority/input: none for offline implementation and tests.
- Checks already run: 107 focused tests; Ruff lint and format; Pyright; 2,498-test source discovery with 31 sandbox-only socket errors; all 68 affected MCP tests outside the socket sandbox; coverage report; export verification; sdist/wheel build; 1,856 installed-wheel smoke tests; constant audit; `git diff --check`.

## Close and promote

- Outcome and verification: prepared review authorization freshness is capped at 30 minutes and still clipped by pricing expiry; equivalent full quality gates pass when localhost-dependent tests are run with loopback access.
- Durable fact promoted to `PROJECT_MEMORY.md`: none; current memory has unrelated user edits and will not be overwritten.
- Decision promoted to ADR/documentation: `docs/REVIEW_BROKER_ADMISSION.md` and `docs/REVIEW_CAMPAIGN_CEREMONY.md` distinguish preparation freshness from runtime authority.
- Regression test, issue, or improvement-plan link: `tests/test_review_broker_admission.py`.
- Temporary artifacts removed: isolated smoke environments were automatically removed; normal ignored build artifacts remain under `dist/`.
