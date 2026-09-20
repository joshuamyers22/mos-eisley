# One bounded live citation-fidelity retest

## Scope and authority

- Revision: `81e9ff5b62b645ea2f71364355f845af5f0e762d`
- Manifest: `d92bdfa744a81ca0734d62274a431314597d6d973b03f1d191c81f13b2fc38b0`
- Result: `f1e59022c19a68e787f2741c724a2debaa3c9c15a2c98a3b5f7016c71bd1dd50`
- Profile: one attempt, two `gpt-5.6-luna` low-effort critics and one judge,
  schema-2 critic requests, `store: false`, empty tools and zero retries
- Fresh ceiling: 62,748 micro-USD; user approved before sealing or dispatch
- Non-authority: no retry, qualification credit, launch decision or routing activation

This was a standalone retest of ADR-0006, not a replacement qualification campaign.
It used a fresh private directory, ledger, process key, policies, seal and approvals.
Earlier failed campaigns and their artifacts were not reused or changed.

## Outcome

Both critic requests carried 54 deterministic content-bound citation units. Both
critic exchanges completed and passed request/evidence reconstruction, so quorum
reached a separately approved judge exchange. Each critic returned zero findings;
the judge returned `accept`. Fresh offline reconstruction verified the complete
retained result and the controller's `finished` terminal binding.

Because the critics returned no findings, this live result proves that the schema-2
catalog/prompt contract is accepted end to end without regression, but it does not
directly exercise a positive live `source_unit` citation. The exact multiline
postimage acceptance and invented/stale/normalized/cross-hunk rejections remain
established by the retained-shape and adversarial offline regressions documented in
`REVIEW_CITATION_FIDELITY_FIX_VERIFICATION.md`.

The three exchanges settled locally at 5,180, 5,211 and 2,770 micro-USD: 13,161
micro-USD total. The ledger has zero unresolved entries. All three worker lifecycle
records say `removed`, no matching Docker container remains, and a bounded scan found
no API-key-shaped retained value. These are local policy amounts, not invoice
reconciliation.

## Post-result evidence limitation

After the controller retained its verified `accept` result, the private orchestration
script failed while constructing the observer exchange tuple with `runtime operation
differs from its approved exchange`. The process then exited and destroyed its
ephemeral signing-key reference. No signed observation was produced.

The retained runtime operation, response, ledger and cleanup records remain available,
but the process-local signed phase authorizations were not persisted independently;
the exact failed comparison cannot be reconstructed after exit without manufacturing
authority. No retry or replacement run is authorized. This limits the retest's
operational evidence and prevents qualification credit; it does not alter the already
retained and freshly reconstructed controller result.

## Verification summary

- Production template and GitHub source revisions were freshly checked before work.
- Official OpenAI model pricing and default data controls were re-reviewed.
- Fresh preview confirmed two schema-2 requests with 54 units each.
- Retained result reconstruction passed with decision `accept` and zero findings.
- Ledger: 13,161 micro-USD charged, zero unresolved entries.
- Cleanup: three `removed` records and no remaining matching container.
- Secret scan: no API-key-shaped retained value.
- Signed observation: absent; qualification and launch authority remain false.
