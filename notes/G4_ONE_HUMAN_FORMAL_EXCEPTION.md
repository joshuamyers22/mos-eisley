# Work Note: Exact one-human G4 formal review exception

- Status: active; pending accountable owner signature
- Owner: Joshua Myers
- Started (UTC): 2026-09-27
- Review or delete by: G4 acceptance decision
- Related decision: [ADR-0008](../docs/adr/0008-g4-one-human-formal-review-exception.md)

## Objective and completion evidence

The exact integrated commit `f54e815` may use its already signed, live-audited
OpenAI/Anthropic single-operator `accept` review as the formal implementation-review
requirement only after Joshua signs an exact exception. The original independent
human-review gate remains false. No new provider call, spending, acceptance, or
release authority follows.

## Context retrieved

- [G4 carry-forward review](../docs/G4_CARRYFORWARD_REVIEW.md)
- [Original independent-review contract](../docs/G4_INDEPENDENT_REVIEW.md)
- [Single-operator review contract](../docs/G4_SINGLE_OPERATOR_REVIEW.md)
- [ADR-0005](../docs/adr/0005-single-operator-review-authorization.md)
- Selected guides: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/THREAT_MODEL.md`, and
  `templates/WORK_NOTE.md`.

## Evidence and stopping rule

The prior signed review record is `cb5fcb86a55a11e23c3dd0aba783daa4f0e051f8decbf9398977eb4fdecdc448`.
Its private verifier replays the exact integrated final-suite chain, two critic
audits, judge audit, ledger, owner signatures, and verdict. The new exception
verifier additionally checks owner identity, scope, ADR hash, and chronology.
Stop without a passing formal alternative if the owner signature is absent, the
review or live-audit replay fails, the worktree changes, or any scope hash differs.

## Handoff

- Current state: proposed exact-run amendment; no exception signature yet.
- Next smallest action: finish focused verification and obtain Joshua's exact
  local signature after reviewing the canonical amendment.
- Blocker: enrolled owner's signature.
