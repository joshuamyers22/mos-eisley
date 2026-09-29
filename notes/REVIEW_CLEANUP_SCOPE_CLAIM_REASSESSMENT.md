# Work Note: repeated cleanup-scope claim reassessment

- Status: closed and formally accepted; repeated claim rejected as unreachable
- Owner: Joshua Myers
- Started (UTC): 2026-09-23T11:44:06Z
- Last updated (UTC): 2026-09-23T14:10:47Z
- Review or delete by: G2 corrected-artifact qualification closure
- Related records: `docs/REVIEW_CLEANUP_SCOPE_CLAIM_REASSESSMENT.md` and `docs/REVIEW_CLEANUP_SCOPE_CLAIM_THREAT_MODEL.md`

## Objective and completion evidence

- Intended outcome: determine whether a schema-2 controller with non-formal scope can reach terminal allowance cleanup through supported source paths.
- Required invariants: standard schema 1 preserves its hold; formal schema 2 retires only its exact unused allowance; formal live execution is seal-bound; inspector rejects false standard cleanup attribution.
- Completion evidence: normalized campaign claim, complete construction trace, executable public-API probe, focused controller/inspection regressions, threat-boundary disposition and durable roadmap/memory update.

## Context retrieved

- Commit `24704aa6fc4aadba2dcec79b8f83bae44f01a02d` and the retained three-slot campaign hashes.
- Controller, broker, launch, conformance-probe, inspection source and affected tests.
- Existing judge-approval correction/reassessment verification and threat models.
- Production-template agentic-verification, threat-model, work-note and adversarial-review guides.

## Observations and attempts

| Time (UTC) | Type | Observation or result | Evidence | Next step |
|---|---|---|---|---|
| 2026-09-23 | observation | Nine upheld findings across three slots reduce to one alleged schema-2/non-formal construction path and cite the same terminal branch. | Retained result hashes in the verification record | Trace reachability instead of counting repetitions. |
| 2026-09-23 | observation | The controller constructor accepts no authorization input and derives schema 2 only from exact `formal_campaign` envelope scope. | `BrokeredReviewController.__init__` | Trace envelope immutability and all composition sites. |
| 2026-09-23 | observation | Envelope validation freezes one matching critic/judge preparation scope; preview validation independently enforces schema-2 iff formal scope. | `PreparedReviewEnvelope`, `ReviewSpendingEnvelope`, `ControllerCriticPreview` | Check production live binding. |
| 2026-09-23 | observation | Production conformance refuses an unbound formal preparation before approval flow or dispatch. | `BrokeredReviewConformanceProbe.run` | Exercise public substitution and existing regressions. |
| 2026-09-23 | result | Public probe produced schema 1/standard and schema 2/formal pairs and rejected assignment to the authorization property. | Offline construction probe | Run focused behavior tests. |
| 2026-09-23 | result | Five substitution, standard/formal cleanup and inspector regressions passed in 0.600 seconds. | Focused `unittest` command in the verification record | Reject the unsupported claim; change no runtime code. |

## Handoff

- Current state: source-level reassessment is complete. The alleged schema-2/non-formal controller is unreachable through supported APIs; no confirmed code defect remains from the repeated claim.
- Next smallest safe action: rebuild and verify a production image from the exact accepted-reassessment commit, then prepare a wholly fresh campaign with its own financial, seal and phase approvals.
- Authority/input: Joshua Myers formally accepted the disposition and directed a fresh campaign on 2026-09-23. That direction does not itself approve a financial ceiling, credential access or provider dispatch.
- Checks already run: all source construction-site trace, executable public-API probe, and five focused controller/inspection regressions.

## Close and promote

- Outcome: CS-001 rejected as a correlated reachability misunderstanding; the lower-level offline/formal-controller and trusted-process mutation boundaries remain explicit residuals.
- Accountable disposition: Joshua Myers accepted the reassessment without a reviewer-legibility code change and requested a wholly fresh campaign.
- Durable fact promoted to `PROJECT_MEMORY.md`: corrected campaign outcome and offline claim disposition.
- Decision promoted to documentation: verification record, threat model and roadmap.
- Regression link: existing controller substitution, standard/formal cleanup and inspection tests; no new test was needed because they already encode the counterexample denial.
- Temporary artifacts removed: public probe used test-owned temporary directories and cleanup hooks; no provider or private campaign artifact was changed.
