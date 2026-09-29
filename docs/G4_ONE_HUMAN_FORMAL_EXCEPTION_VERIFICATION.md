# G4 one-human formal review exception verification

- Exact target commit: `f54e815987c1e51941abf4c2f2138a7268dcf0a7`.
- Existing signed single-operator review record SHA-256:
  `cb5fcb86a55a11e23c3dd0aba783daa4f0e051f8decbf9398977eb4fdecdc448`.
- Joshua-signed exception artifact SHA-256:
  `6db568e979e634b49438c34d3ecbe9c0e58b53aa5460e2ce3a83feddeedd6643`.
- Decision: [ADR-0008](adr/0008-g4-one-human-formal-review-exception.md), whose
  exact bytes are bound into the signed artifact.

The private verifier replayed the passing integrated final suites, both retained
critic observations and live audits, the judge observation and live audit, ledger
entries, Joshua's signed `accept` decision, and the separate exception signature.
It reported `Amended formal implementation-review requirement passed: true`.
It also reported `Original independent-review gate passed: false`,
`Independent human review proven: false`, and `G4 acceptance authorized: false`.

Focused checks: eight synthetic one-human exception and existing one-owner tests
passed. Ruff check, Ruff format check, and Pyright passed on the affected Python
files. The signer preflight and post-signature private replay passed. The aggregate
`make check` was not completed for this local branch; no publication or merge was
performed.
