# Work note: separate initial-child creator decision

- Status: Joshua signed; exact acceptance status replay passed
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

The private signed acceptance artifact has SHA-256
`82442ed2f2b8a67d128394aea625a7f6f063b8ce0ebafa5c2b413123a587ba4f`.
Its exact status replay passed and confirms acceptance of only the isolated
real initial-child path at `d7237f5`. The combined creator-led G4 workflow and
independent human review remain unproven. This decision grants no G3 study pass,
Git merge, release, production activation, provider call or spending authority.
The private signed artifact and provider responses remain outside Git.
