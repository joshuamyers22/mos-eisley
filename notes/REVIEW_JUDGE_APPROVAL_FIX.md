# Work Note: formal judge approval and unused allowance cleanup

- Status: closed offline; commit/image/live qualification open
- Owner: Joshua Myers
- Started (UTC): 2026-09-22
- Last updated (UTC): 2026-09-22
- Review or delete by: G2 qualification closure
- Related issue/incident/ADR: `docs/REVIEW_JUDGE_APPROVAL_TIMEOUT_INCIDENT_2026-09-22.md`

## Objective and completion evidence

- Intended outcome: let a human complete the formal-campaign judge approval ceremony without consuming the remaining execution budget, and settle an unused judge allowance on graceful terminal exit.
- Required invariants: standard timing stays byte-compatible; formal grace is fixed, hash-bound, and envelope-clipped; provider/exchange limits do not change; only an exact still-held non-dispatch allowance can be retired; uncertain or transferred request exposure stays charged; no retry or live authority is added.
- Evidence that will show completion: pre-fix regressions fail, focused review suites pass, documentation and threat-model review pass, and one final `make check` passes.

## Context retrieved

- `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, and `AGENTS.md`
- `docs/PYTHON_ENGINEERING_GUIDE.md` and `docs/AGENTIC_VERIFICATION_GUIDE.md`
- `templates/WORK_NOTE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, and `templates/INCIDENT_REVIEW.md`
- Controller, approval, conformance, inspection, broker, ledger, campaign and launch source/tests
- The terminal formal-campaign records, inspected offline without credential or provider access

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-22 | observation | The controller's 360-second wall clock covered critic execution and both human approvals; the judge phase was reached after its usable approval time was exhausted. | Terminal controller timing records | Separate formal approval time from active execution time. |
| 2026-09-22 | observation | Terminal cancellation left the never-transferred deferred judge allowance held. | Offline ledger/controller inspection | Add exact non-dispatch retirement. |
| 2026-09-22 | attempt | New timing and cleanup regressions failed against the old implementation. | Focused `unittest` run: one error and one failure | Implement the bounded correction. |
| 2026-09-22 | decision | Schema 2 binds a fixed 600-second formal judge-approval grace; standard schema 1 remains unchanged. | Controller contract and canonical tests | Exercise campaign and signed-admission compatibility. |
| 2026-09-22 | decision | Terminal cleanup may settle only the exact still-held source allowance at zero; a transfer destination, critic hold, or uncertain request is never released. | Ledger transition and inspection tests | Complete focused and full gates. |
| 2026-09-22 | observation | The first full source gate exposed that ledger-wide entry equality was too strict for a ledger shared with unrelated reviews; the other 31 errors were sandbox-denied loopback fixtures. | 2,422-test source run | Bind successful cleanup explicitly in the terminal record and rerun affected tests. |
| 2026-09-22 | attempt | Atomic cleanup now reports whether it performed the transition; only that path writes the schema-2 terminal marker. Shared-ledger acceptance and missing-transfer attribution both retain their intended layer. | 86 focused tests passed | Run the final repository gate with loopback access. |

## Handoff

- Current state: the offline correction and complete repository gate pass; no live call was made. The worktree is intentionally uncommitted pending separate user direction.
- Next smallest safe action: complete the offline gates, commit separately if requested, then rebuild the production image before preparing another campaign.
- Blocker and required authority/input: none for offline work; fresh live work requires a new explicit authorization.
- Checks already run: red regressions; 211 review compatibility tests; 86 corrective controller/campaign/acceptance/ledger tests; Ruff, format and Pyright; 2,422 source tests with 4 skips and 89% coverage; export/build verification; 1,779 installed-wheel tests.

## Close and promote

- Outcome and verification: fixed 600-second formal approval grace, preserved active execution remainder, exact unused-source cleanup, explicit terminal attribution, and all offline gates pass.
- Durable fact promoted to `PROJECT_MEMORY.md`: `delivery.next.live-review` now records the failed ceremony, offline correction and required commit/image boundary.
- Decision promoted to ADR/documentation: controller, approval, conformance, spending, transfer, and inspection documentation updated.
- Regression test, issue, or improvement-plan link: controller timing, ledger retirement, campaign, launch, runtime-evidence, conformance and inspection suites.
- Temporary artifacts removed: isolated wheel/smoke environments were automatically removed; normal ignored build output remains under `dist/`.
