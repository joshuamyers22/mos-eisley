# G4 first qualification: offline preparation packet

Status: **creator approval and reviewer custody signed; reviewer package frozen;
no dispatch readiness**.
Owner: Joshua Myers. Exercise ID: `g4-q1-quote-half-up`. This packet follows
the [G4 roadmap](ROADMAP.md), [plan §26.2](mos-eisley-plan.md#262-review-loop-contract)
and the existing G4 gate contracts. The owner approved the independent-review
gate code at `752c350` in conversation; that earlier code-review approval alone
did not approve this task, any signed G4 artifact, provider spend, or final
implementation.

The owner subsequently approved the exact draft `PLAN.md` and protected creator
`tests/test_quote.py` identified below, and specified a **$10 task-wide spend
cap** (10,000,000 micro-USD) and a **2026-09-26T23:59:00-04:00** deadline
(America/Indiana/Indianapolis; 2026-09-27T03:59:00Z) in conversation.
Joshua then personally reviewed the interface, rubric and reviewer-test draft,
accepted single-operator self-review risk, and attested he had not seen the seed
implementation or child telemetry before that review or the package freeze.
The subsequent signatures and package freeze are recorded below; none grants a
child dispatch, provider spend, or acceptance.

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
`PLAN.md`, `INTERFACE.md`, `RUBRIC.md`, reviewer-test source, signed/frozen
artifacts and known-control trees. Do not send the reviewer tests to the coding
child. The plan defines a standard-library-only `quote_cents` function with
strict integer/range checks and half-up discounted-cent rounding. The target
repository contains five protected
creator tests and a deliberately failing seed implementation. Draft identities:

| Draft input | SHA-256 |
|---|---|
| Plan | `90dfdbea0a0e7d87904f020110926dd0c8b4159c28c65d382dea14043df997d4` |
| Public interface | `cd8d6ee5a6558988111cc97a31c3d0fdac86f3be5eac2a8fd07f849028ef761a` |
| Rubric | `2b3b27d8fbc4a040f1c51140361601f7902ccd4c276576c9cc790819c5bc7643` |
| Protected creator test file | `c270eb0390dcb83546ac1be3482409280850fbe22d427268a18e6e82634bceb5` |
| Draft reviewer test file | `fd6edf4f673d67e8242e84c6aa02b7e65c1ee5c29c29d6ca6f4218c5496c6e3f` |

The agent proposed both sets of tests; this does **not** prove independent
reviewer derivation. Joshua reviewed and adopted the reviewer draft as the
single operator, then signed custody over its frozen bytes with an explicit
no-independent-human-review claim. This is accountable self-review, not an
independent reviewer.

Local source-level checks, with a provisional direct-symbol adapter, showed five
creator and five reviewer tests passing on a known-good tree. A known-bad
floor-rounding tree failed one creator and two reviewer tests by assertion with
zero test errors. The target base seed failed two creator tests by assertion
with zero test errors. These checks are not G4 isolated-container receipts or the
required authenticated known-control record.

## Signed input and custody checkpoint

| Artifact | Verified identity and limit |
|---|---|
| Single-operator G4 trust policy | Canonical SHA-256 `5991c35542910d89fc6dc237f4b439014803d7209e9945b7fb8e19f58b63a4df`; Joshua's enrolled Ed25519 public key is shared across human roles, with a distinct task-scoped child key. The policy ends at the approved deadline. |
| Signed creator approval | Canonical artifact SHA-256 `419e2e0bfbc5840a7733b3af33913f5b505061f83de4f17a229df7645593ca17`; verified signature, exact plan/test/interface/rubric hashes and target base. All dispatch/write/correction/acceptance fields are false. |
| Frozen reviewer package | SHA-256 `dad5e14ad864cab85c05230fb7a4903e3df46fe968d47e7d74262f69e6d7bbb9`; payload SHA-256 `3f2bd652bd0f94bbc96e0881cf041e2931e8897bd6929c1431438a9a788926ac`. The signed creator artifact is an exact package reference. One reviewed test file, five expected executions, zero declared skip/xfail markers; freezer replay passed. No test execution or dispatch authority. |
| Signed reviewer custody | Canonical artifact SHA-256 `c5d9b2a7b362504e536b70011245a165e2f3fb29d5b910c856702d2224e4561c`; verified Ed25519 signature, UTC chronology, exact creator/package/payload links and schema-2 self-review disclosure. Independent human review is explicitly **not** claimed. All downstream authority fields are false. |

The private artifacts, public policy and task-scoped child key are held outside
both Git repositories in an owner-only directory; the human private key and
passphrase were never supplied to the assistant. The child key is unencrypted,
mode 0600, for later trusted-host signing. Signatures prove enrolled-key control
over exact bytes under local host/key custody assumptions, not physical identity
or independent judgment. The full G4 authenticated provenance record still
requires later assignment/result, binding, controls and VCS evidence.

## Ordered qualification path and stop rules

1. **Signed inputs and custody — complete:** the owner signed the creator
   approval for the exact inputs and target base, the reviewed package was
   frozen with that signed reference, and the owner separately signed custody
   under single-operator self-review mode. Any changed byte requires new
   dependent artifacts; agent-authored draft tests are not independent evidence.
2. **Bind and control — next:** bind each declared implementation tree, run
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
as acceptance. No live call, provider credential, budget reservation, candidate
claim, host source write or final acceptance was created.

## Current authorization gaps

- Creator approval, reviewer custody, role-key enrollment and reviewer-package
  freeze exist and verify, but no child assignment/result or VCS attestation
  exists for this target.
- No implementation bindings, containerized control receipts, assembled
  authenticated provenance, candidate receipt or final-suite receipt exists
  yet. Their validity depends on the exact later Git trees.
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
boundary is offline implementation binding and paired known controls—not a
provider send.
