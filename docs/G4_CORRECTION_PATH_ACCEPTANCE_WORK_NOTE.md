# Work Note: final G4 correction-path decision

- Status: signed and replay-verified
- Owner: Joshua Myers
- Started (UTC): 2026-09-27
- Selected guidance: `templates/WORK_NOTE.md`, `templates/THREAT_MODEL.md`, `docs/AGENTIC_VERIFICATION_GUIDE.md`

## Objective and evidence

Record Joshua's stated acceptance of the exact `f54e815` correction-path
qualification in a separate enrolled-key artifact. Replay the approved plan,
real child receipt, passing final suites, accepted two-provider review,
ADR-0008 exception, settled spend and signed ADR-0009 quality-scope decision.

## Invariants

- No G3 empirical study pass, independent human review or full initial-child
  workflow qualification is claimed.
- No Git merge, release, activation, provider call or spending is authorized.
- Changed source, document, receipt, signature or owner key fails closed.

The private signed artifact and provider responses remain outside Git.

## Completion

Joshua signed the separate domain-bound acceptance with his enrolled key. The
private artifact SHA-256 is
`931bd68d04c36a2dc2015acc4998ba1f70e88c9b54efdafd53b5321c94da11b3`.
The verifier replayed the exact evidence and confirmed the isolated correction
path accepted while full G4, merge, release, activation, and new provider calls
remain unauthorized. A disposable foreign key was rejected by the same verifier.

The local signer passed Ruff lint/format and Python compilation checks. The
repository `make check` passed lint and Pyright, then its broad test run was
stopped after the exact acceptance had been verified; no full-suite result is
claimed for this documentation-only branch.
