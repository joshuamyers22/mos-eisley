# One bounded live structured-output and quorum retest

## Scope and authority

- Revision: `fe8659b507263f9c46aabe4cb4ff0c0d71208c04`
- Manifest: `70262ce1b06bbb3ef864f199f1a664edc46c97863abdd64833dba24439231050`
- Profile: one attempt, three `gpt-5.6-luna` low-effort critics with threshold
  two and one conditional judge; schema-2 requests; native strict JSON Schema;
  `store: false`; empty tools; zero retries
- Ceiling: 83,664 micro-USD, exactly approved before sealing and dispatch
- Non-authority: no retry, qualification, launch, or routing activation

This was a fresh standalone retest of commit `fe8659b`. It used a new private ledger,
process key, policies, manifest, and exact phase approvals. No historical seal, ledger,
key, or provider result was reused or changed.

## Outcome

All three critic token-count and generation exchanges completed and passed strict
local response decoding. Each retained critic request carried the native strict
`mos_eisley_critique` JSON Schema, and every object node in the three exact schemas
had all properties required and `additionalProperties: false`. The two-of-three
quorum was met without retry. The separately authorized judge carried the equivalent
strict `mos_eisley_judge_decision` schema and completed successfully.

The judge returned `reject` and upheld two findings:

1. `strict_json_schema` only applies object strictness when `properties` is already a
   dictionary. The exact generated critic and judge schemas did not contain such an
   object, so this did not invalidate the transferred live schemas, but the generic
   normalizer does not itself reject or normalize every possible object shape.
2. The three-critic fault regression reaches the judge but does not itself exercise
   signed post-result observation construction. This live attempt did exercise that
   path successfully across three critic exchanges and one judge exchange, but the
   deterministic regression remains incomplete for the stated lifecycle claim.

The exact retained result is
`29f1faae2f6ca4968f4b3cc8931d427fc870c708c39a8a8747561dd9da34d78a`.
Post-result construction succeeded, and Joshua Myers signed observation
`2b4f46a2636189628f0220a0d035e7bed46b2dc39de9ccfb7940f28a6bcbe13d`;
the retained signed-observation hash is
`11ae0b03658c0ba9704492d2ac03ddfc773cfd4348e07a9766eb83542ebd50fa`.
This supplies live evidence that the corrected semantic phase mapping handles three
critic exchanges plus the judge. It does not override the review verdict.

The standalone harness retained the signed observation but not the complete authority
policy, observation policy, or signed phase authorizations needed by
`authenticate_review_probe` after the owning process exited. The observation was
constructed from verified in-process inputs and signed by the ephemeral operator key,
but its complete historical authentication cannot now be replayed independently.
Treat this as an evidence-retention limitation, not qualification evidence.

## Accounting and cleanup

All four role reservations settled locally at 17,191 micro-USD total. Ledger
`37e40766…` reports five entries, zero unresolved entries, 66,473 micro-USD available,
and is not blocked. This is local policy accounting, not provider invoice
reconciliation.

All four lifecycle results end in `removed`, and a filtered Docker inventory found no
remaining container for the pinned image. A bounded scan of retained non-database
artifacts found no API-key-shaped text. The attempt is consumed and grants no retry,
qualification, launch, or routing authority.
