# G4 Anthropic review transport verification

- Requirement: `notes/G4_ANTHROPIC_REVIEW_TRANSPORT.md`.
- Risk: high. Owner: Joshua Myers. Reviewer: owner before live dispatch.
- Starting revision: `8f0d9cc` on `feat/g4-single-operator-review`.
- Rubric: exact grant and one-use claim are blocking; conservative ledger behavior
  is blocking; fixed API scope and private audit are blocking.
- Limit: one implementation pass, one focused fault/replay pass, one full quality
  gate. Live call requires the separate signed grant and stays within USD 10.
- Evidence: HTTP mock tests cover fixed endpoints, redirect and oversize rejection;
  ledger tests cover actual usage, cancellation, wrong tier and over-cap count;
  grant tests cover enrolled signer, tampering, expiry, exact lineage and replay.
- Result, 2026-09-26: focused Anthropic suite 15/15 passed; Ruff and Pyright passed.
  Permissioned `make check` passed: 2,534 source tests (four skipped), 88% total
  coverage, export verification, package build and 1,873 installed-wheel tests.
  A later smoke allowlist addition included both Anthropic test files; the
  affected permissioned `make smoke` passed 1,888 installed-wheel tests.
  The initial sandboxed attempt hit the existing localhost TLS fixture
  restriction and was not counted as a code failure.
- Stop reason: offline transport and exact grant code passed the project checks;
  owner signature and credentialed Messages operation remain external steps.
- Remaining external evidence: owner signature and credentialed Messages response.
  Neither is inferred from the Models API status.
