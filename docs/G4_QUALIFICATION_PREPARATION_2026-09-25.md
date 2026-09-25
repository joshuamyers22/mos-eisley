# G4 first qualification: offline preparation packet

Status: **draft inputs approved in chat; no signed G4 artifact or dispatch readiness**.
Owner: Joshua Myers. Exercise ID: `g4-q1-quote-half-up`. This packet follows
the [G4 roadmap](ROADMAP.md), [plan §26.2](mos-eisley-plan.md#262-review-loop-contract)
and the existing G4 gate contracts. The owner approved the independent-review
gate code at `752c350` in conversation; that earlier code-review approval alone
did not approve this task, any signed G4 artifact, provider spend, or final
implementation.

The owner subsequently approved the exact draft `PLAN.md` and protected creator
`tests/test_quote.py` identified below, and specified a **$10 task-wide spend
cap** (10,000,000 micro-USD) and a **2026-09-26T23:59:00-04:00** deadline
(America/Indiana/Indianapolis; 2026-09-27T03:59:00Z) in conversation. This human approval is
not a signed G4 creator artifact, a reviewer-custody attestation, a child grant,
or permission to make a live call. The interface, rubric, reviewer tests and
later resource grants still need their own required review and binding.

## Exact controller and isolated target

| Item | Offline identity and result |
|---|---|
| Mos Eisley controller source | Clean source commit `752c350` (`fix(g4): bound independent judge review request`). |
| Controller checkout | A separate, clean detached worktree is pinned at `752c350`; future G4 commands must use that exact checkout or the pinned image, not a later documentation-branch `HEAD`. |
| Locally built runtime/worker image | `sha256:462ab0f72f3a97a23b9155a340f9d36c4163bd207835c7daf09fef91329c900f`, `linux/arm64`, local tag `mos-eisley:g4-752c350`. Use the immutable ID, not the tag, in future signed requests. |
| Image check | Pinned Dockerfile build passed; read-only, network-disabled CLI and `g4-assemble-independent-review --help` started. The installed G4 gate file SHA-256 matched the source file at `752c350`: `203fe6937c7461a040853ea73a2c809ba287735deed683578ccbcde671dc9797`. |
| Isolated target base | Separate clean Git repository at commit `699f345eeab3a663b8372c01220972af2ab62842`; tree `9267e59409518978c093e5abae4eb492e27187bc`. It has no remote and is not a Mos Eisley product change. |
| Proposed child scope | Only the existing `src/quote_lab/price.py`; no test, manifest, lock, metadata, new-file or deletion authority. |

The first `docker build --network=none` attempt failed before image creation
because the pinned `uv` wheel was not cached. The unchanged pinned Dockerfile
then built successfully with package downloads. No model/provider call occurred.
The image is a local artifact, not a published registry digest or a production
qualification result. Rebuild and reverify if controller source, locks, Dockerfile,
platform or trust assumptions change.

## Draft task and protected material

The private, owner-scoped preparation directory outside both repositories holds
`PLAN.md`, `INTERFACE.md`, `RUBRIC.md`, draft reviewer tests and known-control
trees. Do not send the reviewer tests to the coding child. The plan defines a
standard-library-only `quote_cents` function with strict integer/range checks and
half-up discounted-cent rounding. The target repository contains five protected
creator tests and a deliberately failing seed implementation. Draft identities:

| Draft input | SHA-256 |
|---|---|
| Plan | `90dfdbea0a0e7d87904f020110926dd0c8b4159c28c65d382dea14043df997d4` |
| Public interface | `cd8d6ee5a6558988111cc97a31c3d0fdac86f3be5eac2a8fd07f849028ef761a` |
| Rubric | `2b3b27d8fbc4a040f1c51140361601f7902ccd4c276576c9cc790819c5bc7643` |
| Protected creator test file | `c270eb0390dcb83546ac1be3482409280850fbe22d427268a18e6e82634bceb5` |
| Draft reviewer test file | `fd6edf4f673d67e8242e84c6aa02b7e65c1ee5c29c29d6ca6f4218c5496c6e3f` |

The agent proposed both sets of tests; this does **not** prove independent
reviewer derivation or custody. The draft reviewer package has not been frozen.
Local source-level checks, with a provisional direct-symbol adapter, showed five
creator and five reviewer tests passing on a known-good tree. A known-bad
floor-rounding tree failed one creator and two reviewer tests by assertion with
zero test errors. The target base seed failed two creator tests by assertion
with zero test errors. These checks are not G4 isolated-container receipts or the
required authenticated known-control record.

## Ordered qualification path and stop rules

1. **Approve inputs:** the creator's chat approval covers the exact draft plan
   and protected creator tests, with a $10 cap and 2026-09-26 23:59 Eastern
   deadline. Review the interface, rubric and complete
   child-owned paths, then obtain a signed creator approval for all required
   exact bytes and the base commit. A changed byte invalidates dependent
   approvals. An accountable
   reviewer must independently assess and take custody of the blind reviewer
   tests before the package is frozen; do not describe agent-authored drafts as
   independent evidence.
2. **Freeze and control:** freeze the reviewer package with the exact signed
   creator approval reference, bind each declared implementation tree, run
   known-good and assertion-only known-bad controls in the pinned immutable
   image, and replay their exact counts and test IDs. No candidate dispatch yet.
3. **Authenticate initial provenance:** after an approved child assignment,
   obtain a real or explicitly labelled seeded child result and a distinct
   base → child → final Git chain. Enroll and protect role keys; sign custody,
   child and VCS claims; replay the clean target tree. The current target is
   intentionally left at base, with **no** pre-approval child commit.
4. **Exercise correction:** only with fresh exact creator grants and a persistent
   private claim store, run two independently admitted failing candidate tests;
   adjudicate their identical assertion IDs; admit one bounded correction cycle;
   issue separate dispatch and production-broker grants. Reserve the full
   shared-ledger allowance before any provider call. No automatic retry after
   an uncertain send or consumed claim.
5. **Integrate and verify:** require a valid child-signed scoped proposal and a
   separate integration grant. Replay new custody/Git/candidate evidence, run
   the full protected creator and frozen reviewer suites in the pinned image,
   then obtain signed, citation-valid two-family critic quorum and judge verdict
   over the exact approved plan and full final diff. Resolve findings and ask
   the creator for a distinct final decision. An applicable G3 quality gate is
   still required before claiming G4 complete.

Stop on a stale hash or Git tree, source outside the allowlist, missing or
uncorroborated role custody, a failed/changed known control, non-assertion
candidate error, missing critic family, unresolved spend, failed cleanup, any
blocking finding, or an exhausted grant. Retain evidence; do not relabel failure
as acceptance. No live call, signature, private key, provider credential, budget
reservation, candidate claim, host source write or final acceptance was created
by this preparation.

## Current authorization gaps

- No creator-signed task plan/test approval, reviewer custody, child assignment,
  role-key enrollment or VCS attestation exists for this proposed target.
- No frozen reviewer package, implementation bindings, containerized control
  receipts, authenticated provenance, candidate receipt or final-suite receipt
  exists yet. Their validity depends on the approvals and exact later Git trees.
- The owner stated a $10 aggregate spend cap and a 2026-09-26 23:59 Eastern
  deadline; model, pricing policy, ledger, provider grant and
  live-call approval remain unset. The repository has an OpenAI live adapter,
  but no second live provider-family adapter; the independent-review gate needs
  two declared families and real external reviewer/provider evidence.
- The first controlled correction-path exercise may use a transparently seeded
  initial child result only after approval. That cannot qualify real *initial*
  child dispatch. A later separately approved real initial-child exercise is
  required before a whole creator-led-loop claim.

See the [qualification threat model](G4_QUALIFICATION_PREPARATION_THREAT_MODEL.md)
and [work note](../notes/G4_QUALIFICATION_PREPARATION.md). The next authority
boundary is completing exact creator approval and independent reviewer
custody—not a provider send.
