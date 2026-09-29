# Work Note: review campaign preparation window

- Status: corrected production image verified; live work unauthorized
- Owner: Joshua Myers
- Started (UTC): 2026-09-21
- Last updated (UTC): 2026-09-22
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
- `docs/PRODUCTION_REPOSITORY_STANDARD.md`
- `Dockerfile`, `.dockerignore`, `Makefile`, and container smoke tools
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
| 2026-09-21 | observation | The exact `0010970a` production image completed all three fixed live slots, but the retained content verdicts independently found that the 1,800-second freshness cap applied to ordinary calls and that the verification record described the base revision ambiguously. | `docs/LIVE_REVIEW_FORMAL_QUALIFICATION_2026-09-21.md`; retained result hashes | Reopen once offline; make the extended window campaign-specific and reconcile provenance. |
| 2026-09-21 | decision | Preserve the 600-second ordinary default and introduce an authorization/configuration `formal_campaign` scope capped at 1,800 seconds. A formal-scope probe cannot run without an exact sealed campaign, and a campaign-bound probe rejects standard scope. | Broker, launch, campaign and probe source | Add regression coverage across positive and negative boundaries. |
| 2026-09-21 | attempt | Scope-specific expiry, unbound-formal denial, sealed formal dispatch, three-slot sequencing and evidence reconstruction all pass without credentials or provider access. Standard-scope defaults are omitted from canonical bytes so historical artifacts remain stable; formal scope remains explicit. | 107 focused `unittest` cases | Run and account for the complete repository gate. |
| 2026-09-21 | observation | The correction's sandboxed `make check` reached 2,416 source tests: 2,381 passed, 4 skipped and only 31 loopback-bind setups were denied. The three affected MCP modules passed all 48 tests with loopback access. | Source test output; bounded loopback rerun | Finish packaging checks and close offline. |
| 2026-09-22 | production verification | From clean exact commit `6d079cadf2a57da54acf445b6c364ad7aad50bd4`, `make container` rebuilt `mos-eisley:local` as immutable Linux/arm64 image `sha256:6672c404f33d595e1a6ce53cebafdf24af5867313882e30fc420a074082c7929` and passed every offline smoke. Separate network-disabled, read-only inspection confirmed UID/GID `10001:10001`, Python 3.12.14, Mos Eisley 0.1.0, OpenAI SDK 3.11.0, 600/1,800-second preparation constants, exact matching hashes for the four corrected source modules, no tests/build tools, and an empty post-test ancestor inventory. | Agentic verification loop; Docker build, smoke and inspection output | Require separate authority before preparing any fresh campaign artifacts. |
| 2026-09-22 | live finding | Fresh campaign slot 1 returned retained rejection `aa2bcdc27a785934b6dbfeea70572f8f4cf1904be058326de6fad00c312a0d4e`; the campaign was cancelled before slot 2 and retained as incomplete. | Private sealed campaign evidence | Harden the implicit deferred-judge scope inheritance offline. |
| 2026-09-22 | implementation | The judge allowance now commits the critic preparation scope before reservation; envelope, campaign, probe and retained-transfer validation reject mismatches. | Source plus four tamper-focused regressions | Run focused and full repository gates; no further live call. |
| 2026-09-22 | verification | Ruff, format and Pyright passed; the authoritative source suite passed all 2,419 tests with 4 skips and 89% coverage; export and wheel build passed. The installed-wheel run reached 1,777 tests before one observer-handoff setup lacked a lifecycle path. | Full local gate output | Diagnose the isolated installed-wheel failure without a live call. |
| 2026-09-22 | observation | Formal campaign fixtures issued 20-second synthetic phase certificates. Under a loaded installed-wheel run, expiry before broker handler entry can correctly fail closed yet leave no lifecycle path for observer handoff. | Fixture certificate helper, dispatch checks and handoff invariant | Use the existing bounded policy maximum only for formal campaign fixtures. |
| 2026-09-22 | implementation | The certificate helper retains its 20-second default for expiry tests, while formal campaign loaders request the authority policy's 60-second maximum. Exact scope expiry still clips the judge fixture to its remaining controller window; a runner regression asserts both layers. | Campaign-runner and conformance-admission fixtures | Rerun focused admission/handoff suites, static checks and installed-wheel smoke. |
| 2026-09-22 | verification | Focused campaign-runner/observer and admission/expiry regressions pass; Ruff, format and Pyright remain clean; the installed wheel passed all 1,777 tests in 989.228 seconds under the accumulated load that previously exposed W-005. | Local gate output | Close the offline slice; require commit and image rebuild before another live campaign. |
| 2026-09-22 | production verification | From clean exact commit `9300de46bc67bcbfeccdee061599130cceae8d17`, `make container` rebuilt `mos-eisley:local` as immutable Linux/arm64 image `sha256:c7f634464887b534de8ee6b803c52c3fe65afb665b0314db2e9385c77e16b990` and passed every offline smoke. Separate network-disabled, read-only inspection confirmed UID/GID `10001:10001`, Python 3.12.14, Mos Eisley 0.1.0, OpenAI SDK 3.11.0, 600/1,800-second preparation constants, exact matching hashes for all three corrected source modules, no Git/compiler/pytest/tests/source tree, no declared volumes or ports, and an empty post-test ancestor inventory. | Agentic verification loop; Docker build, smoke, metadata and installed-source inspection | Require separate authority before preparing a wholly fresh campaign. |

## Handoff

- Current state: the fresh `6d079ca` campaign is terminal and incomplete; exact correction commit `9300de46bc67bcbfeccdee061599130cceae8d17` and image `sha256:c7f634464887b534de8ee6b803c52c3fe65afb665b0314db2e9385c77e16b990` are verified. No further live call was made after slot 1.
- Next smallest safe action: after separate user direction, prepare a wholly fresh formal campaign and approval artifacts bound to exact commit `9300de46bc67bcbfeccdee061599130cceae8d17` and the verified image. Do not reuse the terminal `6d079ca` campaign.
- Blocker and required authority/input: none for offline implementation and tests.
- Checks already run: 162 focused review tests; 26 post-hardening campaign-runner/observer tests; 20 admission/expiry tests; Ruff lint and format; Pyright; authoritative 2,419-test source suite with 4 skips and 89% coverage; export verification; sdist/wheel build; all 1,777 post-hardening installed-wheel tests in 989.228 seconds; constant audit; exact-`9300de4` `make container` and immutable-image inspection.

## Close and promote

- Outcome and verification: ordinary freshness is again capped at 10 minutes; the 30-minute cap is explicit, pricing-clipped and executable only through a matching sealed formal campaign. Focused broker/probe/campaign coverage passes; the final full-gate result is recorded in the verification document.
- Durable fact promoted to `PROJECT_MEMORY.md`: updated `delivery.next.live-review` with the accepted formal campaign, its content verdicts, and the no-launch limitation.
- Decision promoted to ADR/documentation: `docs/REVIEW_BROKER_ADMISSION.md`, `docs/REVIEW_CAMPAIGN_CEREMONY.md`, and `docs/REVIEW_LAUNCH_PREVIEW.md` define the scoped preparation boundary.
- Regression test, issue, or improvement-plan link: `tests/test_review_broker_admission.py`, `tests/test_review_conformance_probe.py`, and formal campaign/dispatch suites.
- Temporary artifacts removed: isolated smoke environments were automatically removed; normal ignored build artifacts remain under `dist/`.
