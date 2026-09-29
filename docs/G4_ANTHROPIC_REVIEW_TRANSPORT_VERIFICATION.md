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
- Live evidence, 2026-09-26: Joshua Myers signed the review authority and a
  separate one-use Anthropic grant. The credentialed Messages call reached
  `claude-sonnet-5`, and the shared ledger settled 48,688 micro-USD. The
  response stopped at `max_tokens` with a thinking block and no text. No
  critic observation was issued, so this call does not qualify a completed
  review. The grant and claim are consumed. Private response content stays in
  the claim directory; this note records only response metadata.
- Correction: Sonnet 5 enables adaptive thinking by default. The exact request
  now explicitly disables thinking so the 4,096-token output bound is usable
  for the JSON critique. Normalization rejects missing or altered thinking
  control. Focused Anthropic tests passed 16/16. Permissioned `make check`
  passed on 2026-09-27, including Ruff, Pyright, source tests, export, build,
  and 1,889 installed-wheel tests.
- Credentialed qualification, 2026-09-27: Joshua Myers signed a fresh exact
  grant for the corrected request. Sonnet 5 returned one JSON text block with
  `end_turn`; citation validation issued a completed full-subject critic
  observation with six findings. Observation SHA-256:
  `d670b2d20a8b413094c99a9376ed2f0a6c4cb03bdfbe5be9cb868887c50e63d8`.
  Its response and audit hashes match the private files. The second ledger
  entry settled at 27,488 micro-USD; both Anthropic calls total 76,176
  micro-USD. The shared ledger is unblocked, with no unresolved entries.
  Raw critique and provider response remain in the private claim directory.
- Result: Anthropic critic transport qualified for this frozen G4 request. The
  formal independent-review gate and G4 acceptance remain open.
