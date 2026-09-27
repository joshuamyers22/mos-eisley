# Work Note: exact G4 G3 quality scope

- Status: closed for the exact correction-path claim
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

The private preflight replayed the production child receipt, passing final
creator/reviewer suites, accepted OpenAI/Anthropic review, signed formal exception
and zero-unresolved review ledger. A disposable foreign-key signature was rejected.
Joshua signed the exact applicability decision; artifact SHA-256
`396ec0d2c000d28f76447f1d1c70b1433f2b4eeb51aadcef71e706bd4912a9ab`.
`/Users/josh/g4-g3-quality-status` replayed it successfully. The decision
records that no G3 empirical study applies to this narrow claim and that no G3
study pass, full initial-child workflow, G4 acceptance or release is claimed.
