# G4 OpenAI critic live grant verification

- Requirement: `notes/G4_OPENAI_CRITIC_LIVE_GRANT.md`.
- Risk: high. Owner: Joshua Myers. Reviewer: owner before live dispatch.
- Starting revision: `58a9845` on `feat/g4-anthropic-review-transport`.
- Rubric: signed subject/roster/request lineage, exact body, conservative
  spending hold, one-use claim, private audit, and no acceptance authority.
- Focused evidence: five offline tests cover exact signature, body, price,
  tampering, expiry, changed request, one-use dispatch, and settlement.
- Full quality gate, 2026-09-27: permissioned `make check` passed Ruff,
  Pyright, 2,540 source tests, 88% coverage, export, build, and 1,894
  installed-wheel tests.
- Creator signature, 2026-09-27: Joshua Myers signed the exact one-use grant.
  Signed artifact SHA-256:
  `6bf1878b542b91e2fa6240ac4698ad6623004b4d65fbf0b57b6c723baedff95c`.
  Provider body SHA-256:
  `895b641757cfb5c0eb8b2ab05c9caf264fbcf669ba7841516c5b27eb64a8ed8a`.
  The signature, frozen lineage, unclaimed ledger entry, and 20,916 micro-USD
  maximum hold verified. The artifact is owner-only and expires at
  2026-09-27T02:18:22Z.
- Credentialed call, 2026-09-27: the exact signed claim was consumed once.
  `gpt-5.6-luna` returned a completed response, and citation validation
  issued a completed full-subject critic observation with one finding.
  Observation SHA-256:
  `6dfffb0418092b21360a7d8da02f35abbf412ef939c8b282b32a0b7573e205f0`.
  Request, response, and audit hashes match their private files. The ledger
  entry settled at 1,206 micro-USD, leaving the shared ledger unblocked with
  no unresolved entries. Raw critique and provider response remain in the
  owner-only claim directory.
- Result: the OpenAI critic call completed. The separate judge call and G4
  single-operator review decision remain open; formal independent review and
  acceptance are not inferred from this observation.
