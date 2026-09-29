# Work Note: live judge-approval finding reassessment

- Status: closed; offline correction verified
- Owner: Joshua Myers
- Started (UTC): 2026-09-23
- Last updated (UTC): 2026-09-23
- Review or delete by: G2 corrected-artifact qualification closure
- Related issue/incident/ADR: `docs/REVIEW_JUDGE_APPROVAL_TIMEOUT_INCIDENT_2026-09-22.md`

## Objective and completion evidence

- Intended outcome: reassess the accepted three-slot campaign's upheld findings, reject correlated misconceptions, and correct every confirmed formal-scope compatibility or inspection defect without another live call.
- Required invariants: schema-1 standard controllers retain their prior terminal and spending behavior; schema-2 formal controllers retain the fixed 600-second human grace and exact unused-source retirement; transferred or uncertain exposure is never released; inspection accepts cleanup only for the exact formal controller/source lineage.
- Evidence that will show completion: finding-by-finding disposition, red regressions for confirmed defects, explicit regressions for rejected claims, focused review suites, and one final `make check`.

## Context retrieved

- `AGENTS.md`, `README.md`, `PROJECT_BRIEF.md`, `PROJECT_MEMORY.md`, `docs/ROADMAP.md`, and ADR-0005
- Python engineering, agentic verification, threat-model, adversarial-review, and work-note guides/templates
- Commit `2ed7f11b19cc7cf470c722207a40219f87f88b97` and the retained three-slot campaign evidence
- Controller, approval flow, broker, ledger, inspection, campaign, conformance, launch, and runtime-evidence source/tests

## Observations and attempts

| Time (UTC) | Type | Observation, action, or concise result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-23 | observation | All three authenticated slot verdicts rejected the change, but all used one provider/model and repeated overlapping interpretations. | Private campaign acceptance and retained slot results | Reassess claims against executable behavior and written invariants. |
| 2026-09-23 | observation | Standard schema-1 controllers currently call the new retirement transition and can emit a schema-2 terminal; this contradicts the explicit compatibility invariant. | `BrokeredReviewController._terminal`; changed standard-path tests | Add red standard-compatibility regressions. |
| 2026-09-23 | observation | Every live judge path completed and wrote a finished terminal after transfer. Transfer atomically settles the source at zero, and repeated retirement returns false for that exact source. | Three live slot terminals; `SpendLedger.transfer_held` and `retire_unused` | Preserve behavior and add an explicit regression; reject the broader post-transfer failure claims. |
| 2026-09-23 | observation | Formal start expiry intentionally adds the fixed grace while remaining clipped by envelope expiry; approval also clips to start expiry. | Controller/approval source, threat model, 630-second regression | Reject the absolute-wall claims as contradicting the approved timing contract. |
| 2026-09-23 | observation | Inspection already binds the allowance through the exact envelope and terminal through the controller hash, but does not reject a cleanup marker on a standard start. | `inspect_review_controller` | Add formal-scope validation without claiming transaction cryptography. |
| 2026-09-23 | attempt | Added red standard-compatibility and formal-marker-scope regressions. | Standard cancellation emitted schema 2; inspector accepted a cleanup marker on a standard start | Correct only the confirmed boundaries. |
| 2026-09-23 | result | Controller retirement is now schema-2-only; inspection requires both schema-2 start authorization and `formal_campaign` preparation scope for a cleanup marker. Standard expectations were restored. | Controller suite: 23 passed; inspection plus launch-admission suites: 47 passed in 114.215s | Run the full offline gate. |
| 2026-09-23 | result | The authoritative offline repository gate passed from source and from the built wheel. | `make check`: Ruff, formatting, Pyright, 2,425 source tests (4 skipped), 89% coverage, export/build/smoke, 1,782 wheel tests | Close offline work; require a clean commit and rebuilt exact image before fresh live authority. |

## Handoff

- Current state: the two confirmed defects are corrected and all offline gates pass; no live call was made. The worktree remains intentionally uncommitted for review.
- Next smallest safe action: review and commit this corrected tree, rebuild and verify the production image from that exact clean commit, then prepare wholly fresh campaign authority.
- Blocker and required authority/input: a commit request is required before creating the immutable source boundary; every later live campaign still requires wholly fresh authority.
- Checks already run: retained-evidence/source/history trace; focused red/green regressions; Ruff; formatting; Pyright; 2,425 source tests; 89% coverage; export verification; build and wheel smoke; 1,782 installed-wheel tests.

## Close and promote

- Outcome and verification: 13 upheld claims normalized to five overlapping clusters: two confirmed defects corrected, three correlated-model misunderstanding clusters rejected with executable counterevidence; full offline gate passed.
- Durable fact promoted to `PROJECT_MEMORY.md`: latest campaign outcome, claim disposition, corrected worktree boundary, and required next steps.
- Decision promoted to ADR/documentation: reassessment verification and threat model, roadmap, changelog, and the superseded original fix record.
- Regression test, issue, or improvement-plan link: `tests/test_review_controller.py` and `tests/test_review_controller_inspection.py`, with restored standard expectations across approval, conformance, launch, and runtime-evidence tests.
- Temporary artifacts removed: the wheel gate used an isolated temporary environment that removed itself; retained campaign evidence is preserved intentionally.
