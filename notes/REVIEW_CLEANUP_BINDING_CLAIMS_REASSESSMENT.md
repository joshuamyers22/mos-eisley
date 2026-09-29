# Work Note: cleanup binding claims reassessment

- Status: reassessment and offline regression correction complete
- Owner: Joshua Myers
- Started (UTC): 2026-09-23T23:34:29Z
- Last updated (UTC): 2026-09-24T00:22:43Z
- Review or delete by: corrected-artifact G2 qualification closure
- Related records: `docs/REVIEW_CLEANUP_BINDING_CLAIMS_REASSESSMENT.md` and
  `docs/REVIEW_CLEANUP_BINDING_CLAIMS_THREAT_MODEL.md`

## Objective and completion evidence

- Intended outcome: determine whether the latest mutable-binding, campaign-ID and
  terminal-window findings describe reachable defects.
- Completion evidence: exact live findings normalized; contract/construction/seal
  traces completed; frozen-assignment probe passed; all 21 campaign-dispatch tests
  passed before correction; two boundary regressions were added and all 23 tests
  passed afterward.

## Observations and attempts

| Time (UTC) | Type | Observation or result | Evidence | Decision |
|---|---|---|---|---|
| 2026-09-23 | observation | Critic cited subclass fields but not inherited frozen `Contract` configuration | `core/models.py`, `review_campaign_binding.py` | Test actual assignment and trace ownership |
| 2026-09-23 | result | Assignment raised `frozen_instance`; retained scalar model was unchanged | Offline `uv run --frozen` probe | Reject mutable-binding claim |
| 2026-09-23 | observation | No separate campaign-ID contract exists; the independent seal digest binds seal, bundle, policy and slots | Campaign and dispatch sources | Reject separate-ID claim and correct terminology |
| 2026-09-23 | result | 21 campaign-dispatch tests passed in 24.044 seconds | Focused `unittest discover` command | Existing post-start seal-tamper terminal coverage is valid |
| 2026-09-23 | observation | Cleanup implements both time bounds, but tests do not directly assert terminal retirement denial at those boundaries | Controller predicate and affected tests | Accept one test-evidence gap |
| 2026-09-23 | result | New pre-seal and exact-expiry terminal tests preserve the held allowance, report no retirement and make no judge call; all 23 campaign-dispatch tests pass | `tests/test_review_campaign_dispatch.py` | Close the only confirmed gap without runtime changes |
| 2026-09-24 | result | Ruff, formatting, Pyright and `git diff --check` passed; full discovery ran 2,431 tests and its only 31 errors were the managed sandbox's denied loopback binds | `make check` | Isolate the environment-only failures |
| 2026-09-24 | result | All 68 MCP tests passed with local-loopback permission; four optional data-MCP integrations skipped as configured | `test_mcp*.py` discovery | Complete repository verification for this correction |

## Handoff

- Current state: no runtime code defect is confirmed, and the focused lower/upper
  terminal cleanup regressions now close the only test-evidence gap. Repository gates
  are complete, including a clean loopback-enabled rerun of the sandbox-denied family.
- Next smallest safe action: commit this offline correction, then rebuild the exact
  production image before preparing another wholly fresh campaign.
- No live call or retry is authorized by this note.
