# Work Note: exact G4 G3 quality scope

- Status: preparing exact owner decision
- Owner: Joshua Myers
- Started (UTC): 2026-09-27
- Selected guidance: `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/WORK_NOTE.md`, `templates/THREAT_MODEL.md`, `templates/ADR.md`

## Objective and completion evidence

Resolve which G3 quality gate applies to the integrated bounded-quote
correction-path qualification. Joshua confirmed the only intended claim is
isolated G4 correction quality. Completion requires replay of the final suites,
accepted two-provider review, signed ADR-0008 exception and reconciled ledger,
followed by Joshua's exact signature on the narrow applicability decision.

## Invariants and stopping rules

- G3 empirical study completion and representative quality remain false.
- No context/routing/savings or full initial-child qualification is claimed.
- No provider call or new spending is authorized. G4 acceptance remains false.
- Stop on changed plan, source, signed evidence, ADR bytes or enrolled owner key.

## Evidence

The approved task plan is embedded in the review subject and explicitly limits
the qualification to the correction path. The final-suite and review status
commands replay the exact integrated revision; the signed one-human exception
and spend reconciliation replay separately. Private artifacts and raw provider
responses remain outside Git. See ADR-0009 for the scope decision and its risk.
