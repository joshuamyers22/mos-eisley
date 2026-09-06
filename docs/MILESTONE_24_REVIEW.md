# Milestone 24 adversarial review: signed skill promotion

## Disposition implemented

Mos Eisley now separates measured persona-skill evidence from an independent,
short-lived promotion decision. Both registered split reports and their complete
authenticated lineages are recomputed before one trusted Ed25519 signature can mint
a promotion-readiness receipt. No path mutates configuration or activates a skill.

## Adversarial findings addressed

- A holdout-only win can hide calibration regressions, so both split reports must
  match the same seal and pass their registered gates.
- A report boolean is not authority, so the unsigned derived decision contains no
  `promotion_ready` field; only signature authentication can mint that field.
- A signer could also grade its own experiment, so authority IDs and public keys
  must be disjoint from every grader and resolver in both split lineages.
- Trust-policy substitution could validate an attacker's key, so the exact authority
  policy digest is inside the signed decision.
- Old approvals can outlive their evidence context, so policies and decisions have
  explicit UTC windows and bounded decision lifetimes.
- A forged decision can change source hashes or split results, so authentication
  recomputes both reports and the complete decision before checking the signature.
- A signed failure could be misread as success, so receipt promotion readiness must
  equal the conjunction of the two recomputed registered-gate results.
- Evidence promotion could be confused with installation, so every decision and
  receipt literally denies activation and configuration mutation.

## Remaining limits

The CLI trusts the host UTC clock; a compromised clock can admit a stale decision.
Authority-policy distribution remains an external root of trust, and one signature
is not a quorum. Receipt verification at its historical authentication time proves
past validity, not current validity.

There is still no retained package archive, author signature, revocation anchor,
rollback target, installation transaction, default-persona mutation, or drift
monitor. Promotion readiness must remain disconnected from runtime until those
boundaries are independently designed and tested.
