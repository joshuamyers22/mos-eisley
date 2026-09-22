# Formal three-slot live review qualification campaign

## Scope and authority

- Revision: `0010970a8960161266841dc59a64c0ef58c48221`
- Production image: Linux/arm64
  `sha256:25fd33683fbe4418c3f290e55e61b8ee623b224821ecc02e689f2944dacd9504`
- Runtime: Python 3.12.14, Mos Eisley 0.1.0 and OpenAI SDK 3.11.0
- Campaign bundle:
  `7f6a484d2ef3d0521c06a60bb494a55164a057e3eae627a6a1d08fc26d2fee2b`
- Campaign seal:
  `fb7611f454fe7278857e0b1ae0f03e8abb3d25d4f68389b66227ef501236adfa`
- Profile: three precommitted fixed slots; each used three `gpt-5.6-luna`
  low-effort critics, threshold two and one conditional judge; strict structured
  output, content-bound citations, `store: false`, no tools and no retries
- Operator: Joshua Myers under ADR-0005 single-operator mode
- Local planned ceiling: 83,664 micro-USD per dedicated slot ledger; 250,992
  micro-USD total
- Verification method: production-template survey
  `8879be48f3b760e65f6bed32f8740314fe92910d`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`, and
  `templates/AGENTIC_VERIFICATION_LOOP.md`
- Non-authority: the campaign status does not approve the reviewed code, reconcile
  provider invoices, prove provider authorship, authorize retry, or admit a launch

The campaign was wholly fresh and bound every live call to the revision, immutable
image, new private guidance, dedicated ledgers, sealed commitment, phase authority
and local approval. Historical failed or standalone campaigns were not reused or
modified.

## Qualification result

All three slots completed in fixed order. Each slot retained three completed critic
responses and one conditional judge response, received its exact post-result
observation, and passed fresh campaign-evidence reconstruction before the next slot.
The formal campaign result is `accepted` with three qualifying attempts.

| Slot | Review-result SHA-256 | Verdict | Findings | Local charge |
|---:|---|---|---:|---:|
| 1 | `9a78f29f02e95847e06508083255ee18a194307d6ca1198eddd640fa809efae7` | reject | 3 | 11,366 micro-USD |
| 2 | `5dfd63ee9c78b6dfbd2f38ef03483972838ecf84829d5b3fe7d4210037ca8715` | revise | 2 | 9,774 micro-USD |
| 3 | `244a236db596b489ada4e49f7ca3763b47c5633379f538395aa9c6f7d30e3469` | reject | 3 | 9,855 micro-USD |

The human observation-confirmation hashes were, in slot order,
`473735b77acc0f671ded5cbef3255224b07fcc74f194ff6636523485caafdc59`,
`e6afed29913c59a383f612b2cb98b5792e2783dd27661eb5ca9a55c6482f6c94`
and `0049d6cc607e198de01270038cce378723feaf11b5a586e8f32b760af948113f`.
The final campaign result independently binds authenticated observation records
`738b5cc6488261dc20edb3ab46e607cdea71aa84e26d210c98a0e52250b86c43`,
`cfe55ee61601021d8aa1aa1b1c6feb5352ee57ac33f8ebeb80f7dc3c3926b8fc`
and `4f72713c1dbab13b0cc490d52b4ea4dce6df606cadb06c7d0d7008c35725215c`.

The reconstructed campaign-evidence SHA-256 is
`b10871e4c8d83bcaee78ae9e32b1da5e0ace29739441070220cbe74cdc68b8bc`.
The canonical campaign-result SHA-256 is
`982e8fb8d42ee313964e386563c878215dbf011258d64ff0521340dcee51cb91`.
The result explicitly keeps provider dispatch, live activation, provider-authorship
proof and provider billing reconciliation false.

## Review findings and disposition

Campaign acceptance measures authenticated completion of the fixed qualification
protocol; it does not replace the critic/judge verdict. The content verdicts were
`reject`, `revise`, `reject`. Their repeated evidence reduced to two actionable
finding classes:

1. The verification record named `bac7dd24...` as the starting worktree state in a
   way reviewers interpreted as the implementation revision, while the live boundary
   was pinned to `0010970a...`.
2. The 30-minute preparation window in `PreparedReviewCall` applied to every review
   call rather than only the manually gated formal campaign.

Both findings were accepted for offline correction. The verification record now
distinguishes original base, implementation/live revision and correction base. The
ordinary preparation window is restored to 10 minutes; the 30-minute value is bound
to an explicit `formal_campaign` authorization/configuration scope, propagated to
the deferred judge, and rejected before approval, credentials or reservation unless
the owned probe has the exact sealed-campaign binding. No live call was used to make
or verify those corrections.

## Accounting, retention and cleanup

The three slot ledgers contain five terminal entries each, zero unresolved local
reservations and are not blocked. Total recorded local charge is 30,995 micro-USD
($0.030995). This is conservative local policy accounting, not provider invoice
reconciliation.

Twelve worker lifecycles were retained and ended in `removed`. A post-campaign
inventory found no container derived from the pinned image. Campaign evidence and
result files are private mode 0600 beneath a private mode-0700 artifact root outside
Git. Provider payloads, credentials, signing material and private campaign content
are not copied into this repository record.

## G2 disposition

This is the first successful formal three-precommitted-slot execution of the G2
production-qualification protocol. It establishes that the exact `0010970a` image
can complete the sealed sequence, quorum/judge flow, signed observation handoffs,
evidence reconstruction, local accounting and worker cleanup.

It does not authorize launch. Its own content verdicts required the offline
correction documented above, so its exact-commit evidence cannot be transferred to
the corrected commit or image. Any later launch decision must use current evidence
for the exact proposed artifact and separately satisfy launch admission. No further
live call is authorized by this record.
