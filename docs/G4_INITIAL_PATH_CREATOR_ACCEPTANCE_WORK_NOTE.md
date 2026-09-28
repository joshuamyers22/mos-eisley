# Work note: separate initial-child creator decision

- Status: prepared for Joshua's local signature
- Owner: Joshua Myers
- Date: 2026-09-27
- Risk: governance and scope error
- Resource ceiling: offline replay and local signing only; no provider call
- Selected guidance: `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md` and
  `templates/WORK_NOTE.md`.

## Objective and invariants

Record Joshua's separate decision on the isolated real initial-child path for
`d7237f5`. Completion requires a domain-separated creator signature and exact
status replay. No combined G4 milestone, G3 empirical study, independent human
review, Git merge, release, production activation, provider call or spending
authority follows this path decision.

## Evidence and stopping rule

The signer replays Joshua's signed ADR-0011 G3 scope decision, which itself
replays the approved plan, real child, passing final whole suites, accepted
two-provider review, signed ADR-0010 exception and exact spending dispositions.
It binds the signed scope artifact and this decision document by SHA-256.
Stop on changed source, document, owner key, policy time, signature or claim.

The private signed artifact and provider responses remain outside Git. The
separate ADR-0011 status replay passed before this decision was prepared.
