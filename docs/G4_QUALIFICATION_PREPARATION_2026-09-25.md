# G4 first qualification: offline preparation packet

Status: **signed creator/reviewer custody, v2 package, paired controls and
seeded assignment/result verified; Git claim recorded, VCS signature pending;
no real child dispatch readiness**.
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
The subsequent signatures, corrected package freeze and paired controls are
recorded below; none grants a child dispatch, provider spend, or acceptance.

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
| Frozen reviewer package v2 | SHA-256 `c2058daa7ee358a7d75a538990a926c2b4dcdb134deb1ea6698e0eea8ba3d933`; payload SHA-256 `412ef086c9b717450c264516c20291831ea00b767fd8b14112f1ff7b21f4d951`. The signed creator artifact is an exact package reference. One reviewed test file, five expected executions, zero declared skip/xfail markers; freezer replay passed. No dispatch authority. |
| Signed reviewer custody v2 | Canonical artifact SHA-256 `4b6eb3faf110543ac2e15c9a20e3a0a960e045641c81648daaa917690b067b9d`; verified Ed25519 signature, UTC chronology, exact creator/package/payload links and schema-2 self-review disclosure. Independent human review is explicitly **not** claimed. All downstream authority fields are false. |

The private artifacts, public policy and task-scoped child key are held outside
both Git repositories in an owner-only directory; the human private key and
passphrase were never supplied to the assistant. The child key is unencrypted,
mode 0600, for later trusted-host signing. Signatures prove enrolled-key control
over exact bytes under local host/key custody assumptions, not physical identity
or independent judgment. The later seeded assignment/result are described
below; full authenticated provenance still needs a separate VCS signature.

## Immutable binding and paired-control checkpoint

The v1 package and custody remain historical evidence. The first isolated
known-good attempt exited without a receipt: its frozen `unittest` collection
used `start_directory=tests`, `top_level_directory=.` without an importable
`tests` package. The v2 manifest changed only `top_level_directory` to `tests`;
reviewer test bytes, creator references and expected count remained unchanged.
The v1 lifecycle record was retained, not counted as a control. Joshua signed
new custody for the v2 package; v1 custody was not reused.

Distinct, clean local-only fixture Git commits `31f82d8` (good) and `f1b34db`
(bad) have replay-verified immutable bindings
`c54cf3e580d6612de50349e38f5003efc4bf86c476b518725880fbbdc8dac9d3`
and `f75f7e4238029811d1bf65b67923568a0aece83b88462ebfe69aebb758687bbb`.
The allowlisted adapter identity is identical. In the pinned image, with
network, credentials, provider dispatch, VCS and repository writes denied,
both controls collected and executed the same five reviewer tests. The
known-good receipt `93fc50e1c7aa4ee8b147764642561097f8f858d8068b0f6740d59c8931d379c7`
records zero failures/errors; the known-bad receipt
`1fb31b4f162e77dbb79f21101e5b6758d1746f557a8e5e8f5ce0c585086e9a8d`
records two assertion failures and zero errors. Both share executed-test-ID
SHA-256 `2770a24ad78d46c7913c801f244d84ec88d2346841782058ee55627924ec16f9`.
Each receipt replay-verified against exact inputs. Paired record
`ad304e1531ebcfc3c967ea4eb7f903667dea83be606a5510c784dd021c67d8fc`
validated and replay-verified the control relationship. These are offline
control results, not candidate qualification, provider authorization, or final
acceptance.

## Offline seeded E2 and Git-provenance checkpoint

Joshua chose a clearly labelled offline seeded initial result, not a real
coding-child dispatch. He locally signed a zero-provider-spend assignment,
artifact SHA-256
`63cbd8e5351ee1f62489b9d2cdb65a991875c4a6bb990b8343851f1a8b43f116`,
binding the approved base, complete `tests/test_quote.py` creator-test
inventory, only `src/quote_lab/price.py` as child-owned, v2 custody/package,
brief and criteria. Its dispatch, write and acceptance fields are false.

On target branch `fixture/g4-seeded-e2-provenance`, the exact lineage is base
`699f345eeab3a663b8372c01220972af2ab62842` → assistant-authored partial
child fixture `89dc94d7594e9b408254a38ebe10450f955772c9` → host-authored
README handoff `6f2551df8256b6744f010d0b7e31655541ca2163`. The child patch
changes only the owned source and matches the known-bad fixture bytes. A local
creator-test run executed five tests, with one half-up assertion failure and
zero errors. A separate task-scoped key signed the *seeded* child result at
`dd4e16e299e3dacbea7362843e38b54aa1a42e27f9e56c611631181d6e8f97cd`;
the custody chain verified. This does not prove that a model child worked or
that the implementation passes.

Final-source binding
`97eee7ad647dbac0a44bf619cea0c5654ebb90512813795a9123d368048343af`
replay-verified. The pinned read-only Git recorder reconstructed the three
commits, exact owned patch, committed bound blobs and clean source tree. Its
unsigned claim SHA-256 is
`d59411ecaebe81a50e8f4fecae001716918cb3f0b712fe74efde96a0dcdcc5ad`.
The strict recorder needed a separate canonical encoding of the *same* trust
policy; the earlier pretty file was preserved. Joshua's separate VCS signature
and final assembly/replay are pending. No candidate receipt, provider call,
correction integration or acceptance is claimed.

## Ordered qualification path and stop rules

1. **Signed inputs and custody — complete:** the owner signed the creator
   approval for the exact inputs and target base, the reviewed package was
   frozen with that signed reference, and the owner separately signed custody
   under single-operator self-review mode. Any changed byte requires new
   dependent artifacts; agent-authored draft tests are not independent evidence.
2. **Bind and control — complete:** distinct implementation trees, immutable
   bindings and assertion-only paired controls replay-verify in the pinned
   image. No candidate dispatch was authorized.
3. **Authenticate seeded provenance — VCS signature pending:** signed seeded
   assignment/result and distinct base → child → source lineage verify. Joshua
   must sign the exact read-only Git claim, then assemble and replay the full
   record. This cannot qualify a real initial coding-child dispatch.
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
claim, production host source write or final acceptance was created. The
disposable fixture target alone received the two disclosed commits above.

## Current authorization gaps

- Creator/reviewer custody, seeded assignment/result and read-only Git claim
  exist and verify, but Joshua's VCS signature and assembled provenance record
  remain pending. No real initial-child result exists.
- Immutable fixture bindings and containerized paired-control receipts exist,
  but no assembled authenticated provenance, candidate receipt or final-suite
  receipt exists. Their validity depends on the exact later Git trees.
- The owner stated a $10 aggregate spend cap and a 2026-09-26 23:59 Eastern
  deadline; model, pricing policy, ledger, provider grant and
  live-call approval remain unset. The repository has an OpenAI live adapter,
  but no second live provider-family adapter; the independent-review gate needs
  two declared families and real external reviewer/provider evidence.
- The first controlled correction-path exercise now has a transparently seeded
  initial child result. It cannot qualify real *initial* child dispatch. A
  later separately approved real initial-child exercise is
  required before a whole creator-led-loop claim.

See the [qualification threat model](G4_QUALIFICATION_PREPARATION_THREAT_MODEL.md)
and [work note](../notes/G4_QUALIFICATION_PREPARATION.md). The next boundary
is Joshua's exact VCS signature followed by final provenance assembly/replay,
with separate authorization before any provider send.
