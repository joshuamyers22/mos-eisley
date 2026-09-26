# G4 first qualification: offline preparation packet

Status: **offline seeded provenance and two independent failed-candidate
receipts replay-verified; both failures traced to one missing half-up term;
signed single-operator triage, zero-spend cycle-1 admission, one contained
agent-authored offline correction-child dispatch, separately authorized
isolated Git integration, renewed authenticated provenance, a passing
corrected-revision candidate receipt and separately authorized passing final
creator/reviewer whole suites replay-verified**.
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
The subsequent signatures, corrected package freeze, paired controls, offline
dispatch, isolated integration, corrected candidate and final whole-suite tests
are recorded below; none grants provider spend or acceptance.

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
or independent judgment. The later seeded assignment/result and completed
offline provenance are described below.

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
policy; the earlier pretty file was preserved. Joshua signed the exact Git
claim separately; signed artifact SHA-256
`ad35ad0bc7b0fc20eec63c201e5e205fa3b4081dfc6671b6f294b23808c0a903`
verified against his enrolled VCS key and matched the unsigned claim. The
assembled, mode-0600 authenticated record SHA-256
`cb4dc4fbff681372ceb877d88db122e857de5366b5dd131695cd8d9a51d00ec3`
replayed against the current clean target, v2 package, final-source binding
and paired controls. Its custody/VCS/E2 fields are true; candidate, child,
provider, write, correction and acceptance authority fields remain false.
That provenance checkpoint itself supplied no real initial child or candidate
receipt. The separately approved first candidate test is recorded below; no
provider call, correction integration or acceptance is claimed.

## Ordered qualification path and stop rules

1. **Signed inputs and custody — complete:** the owner signed the creator
   approval for the exact inputs and target base, the reviewed package was
   frozen with that signed reference, and the owner separately signed custody
   under single-operator self-review mode. Any changed byte requires new
   dependent artifacts; agent-authored draft tests are not independent evidence.
2. **Bind and control — complete:** distinct implementation trees, immutable
   bindings and assertion-only paired controls replay-verify in the pinned
   image. No candidate dispatch was authorized.
3. **Authenticate seeded provenance — complete:** signed seeded
   assignment/result and distinct base → child → source lineage, Joshua's VCS
   signature, assembled record and current Git replay verify. This cannot
   qualify a real initial coding-child dispatch.
4. **Exercise correction — two candidate reproductions complete:** two fresh
   exact creator grants and the same persistent private claim store yielded
   independently admitted failed candidate receipts. Each ran 5/5 tests with
   the same two assertion failures and zero errors; the correction-gate pair
   check accepted their distinct identities and matching observations.
   Source-level assessment traces both to one rounding defect. Joshua's signed
   single-operator triage now covers both IDs. Joshua separately signed bounded
   cycle 1, and its one-use claim was admitted. A separate zero-spend offline
   child-dispatch grant was later signed and consumed; no production-broker
   grant or provider use followed.
   Reserve the full shared-ledger allowance before any provider call. No
   automatic retry after an uncertain send or consumed claim.

5. **Integrate and verify — whole suites complete, review open:** the
   child-signed scoped offline proposal and separate integration grant produced
   a detached corrected revision. Renewed binding, signed Git provenance and a
   passing candidate receipt replay-verify. A separate creator grant authorized
   the full protected creator and frozen reviewer suites in the pinned image;
   both passed and replay-verified. Next obtain a signed, citation-valid
   two-family critic quorum and judge verdict
   over the exact approved plan and full final diff. Resolve findings and ask
   the creator for a distinct final decision. An applicable G3 quality gate is
   still required before claiming G4 complete.

Stop on a stale hash or Git tree, source outside the allowlist, missing or
uncorroborated role custody, a failed/changed known control, non-assertion
candidate error, missing critic family, unresolved spend, failed cleanup, any
blocking finding, or an exhausted grant. Retain evidence; do not relabel failure
as acceptance. No live call, provider credential, budget reservation, production
host source write or final acceptance was created. Three candidate claims were
consumed; none may be reset or bypassed. The
disposable fixture target alone received the two disclosed commits above.

## Source-level failure adjudication

The signed creator approval names plan SHA-256 `90dfdbea…`, whose lines 12–14
require `(numerator + 5_000) // 10_000`. The frozen reviewer file SHA-256 is
`fd6edf4f…`; the bound source file SHA-256 is `496e2a33…` at revision
`6f2551d`. Source line 20 instead returns `numerator // 10_000`.

| Reproduced failed ID | Approved-plan value | Bound-source value | Source-level disposition |
|---|---:|---:|---|
| `test_half_cent_ties_round_up` | 2 and 3 for the two tie cases | 1 and 2 | Implementation defect: half-up increment omitted. |
| `test_discount_applies_to_whole_subtotal` | 601 for 707 cents discounted 15% | 600 | Same rounding defect; source does discount the whole subtotal. |

Both frozen assertions match the approved formula. The two receipts reproduced
exactly these IDs with 5/5 execution and zero errors; the known-good/known-bad
controls further support sensitivity. This is **one shared root cause**, not a
separate discount-order defect. The owner-only `SOURCE_ADJUDICATION.md` retains
full identities and arithmetic. The second tie assertion was not reached by
the failed reviewer method; its source result was checked separately offline.
The owner-only source assessment is bound into Joshua's signed judge triage,
artifact SHA-256 `aa87ff091b33aabb32ab6714bb7fc3af7bfd418daf5a85da4ea726b88ad166bf`.
Its signature verifies against the enrolled key and it names both independently
reproduced receipt hashes, the exact review policy and the critic artifact.
The policy discloses single-operator review; the critic pass is agent-authored,
not provider-backed or independent human review. The signed triage explicitly
denies correction dispatch and acceptance authority. It is not a correction
cycle approval.

Joshua separately signed cycle-1 creator approval SHA-256
`07e21f2c3e27011ffc5f41a5a65b09a750edafd6a3e60069db0b976d73f14492`.
It binds the exact triage, current source revision, plan/test/package claims,
one owned source path and existing child identity. The grant reserves 30,000
input tokens, 8,000 output tokens, 20 tool calls and 3,600 seconds on top of
the initial assignment's identical allowance, under the $10 task-wide ceiling
and 2026-09-26 23:59 Eastern deadline. Its own provider allowance is **zero**,
as required by the initial assignment. It expires 2026-09-26 19:30:42 UTC.
The pinned controller admitted it once in the private claim store; canonical
admission SHA-256
`ad4fb9e908bc4f05cabf217440c3e72f56ff366e74c66f95823705e8c710582c`
and exactly one owner-only claim replay-verify. No dispatch, provider, Git write
or acceptance authority follows from admission.

## Current authorization gaps

- Creator/reviewer custody, seeded assignment/result, Joshua-signed Git claim
  and assembled provenance record verify. No real initial-child result exists.
- Immutable fixture bindings and containerized paired-control receipts exist.
  The first candidate receipt `6d08b811…` and separately approved second
  receipt `43c2e9d8…` replay-verified against distinct claims in the same store
  and the exact current Git tree and inputs. Each ran 5/5 tests with failures
  `test_discount_applies_to_whole_subtotal` and `test_half_cent_ties_round_up`,
  zero errors or skips, and `candidate_tests_passed=false`. The exact pair
  validator accepted matching failure and collection identities. The source-
  level finding and signed triage are recorded above; the final-suite receipt
  remains absent.
- The separate creator-signed cycle-1 approval and one-use admission above
  verify. Their claim is spent; do not retry admission or change stores.
  One contained offline correction-child dispatch has now run under its separate
  signed grant, followed by separately authorized isolated Git integration.
  Final suites and review still require separate grants. Provider use is
  impossible under this zero-spend cycle; it would require a fresh authorized
  chain.
- Joshua signed separate offline correction-child dispatch grant SHA-256
  `da0f4a2e8d3893dcbf1a06befec74de92baf1464cac063e9529584fad1ad8ada`.
  It binds the exact admission, current revision, pinned image, one owned source
  file, reviewed brief/criteria and protected creator-test byte-view digest.
  Read-only offer preview SHA-256 `418e0181579f75f70f83048ec214c3221075b1bf553e4cd44778d47988c35a2d`
  replayed against current Git. One child-dispatch claim was later consumed,
  producing a signed, deterministic agent-authored proposal and contained
  worker receipt. No provider was called or original-checkout file changed.
  The grant expires with the cycle approval at 2026-09-26 19:30:42 UTC, but
  its claim is spent.
- The corrected detached revision has a fresh binding and signed, replayed
  VCS/E2 provenance. Its separately approved candidate receipt `3736d1b0…`
  passed and replay-verified against one new claim and clean Git. The earlier
  two failed receipts belong to `6f2551d` and cannot be reused for final-suite
  admission. The separate full-suite grant and passing receipt now exist and
  replay-verify; independent review remains open.
- The owner stated a $10 aggregate spend cap and a 2026-09-26 23:59 Eastern
  deadline; model, pricing policy, ledger, provider grant and
  live-call approval remain unset. The repository has an OpenAI live adapter,
  but no second live provider-family adapter; the independent-review gate needs
  two declared families and real external reviewer/provider evidence.
- The first controlled correction-path exercise now has a transparently seeded
  initial child result. It cannot qualify real *initial* child dispatch. A
  later separately approved real initial-child exercise is
  required before a whole creator-led-loop claim.

The one-use offline dispatch receipt is canonical SHA-256
`d3c30c126bd32a9f11c3ba05340bd10038b74a1282b340799842c10319833446`,
with signed proposal artifact `31a7aa29528db38156ad98ab104d2014ec82dab373dc5728d4ff478203b971bd`.
The pinned no-network/no-mount worker accepted a replacement of only
`src/quote_lab/price.py`; the proposal reports zero provider tokens, calls and
micro-USD. The claim and enrolled child signature replay-verified, and the
target remains clean at `6f2551d`. This tests containment with an expressly
agent-authored deterministic offline proposal; it does not qualify a real
provider child or establish final correctness.

Joshua then signed a separate creator integration grant, SHA-256
`90a794b7e2cde4864d5a78d348af0f96e7b2c3b0777931182541f3c38da12482`,
binding the exact dispatch receipt, source revision and only
`src/quote_lab/price.py`. After read-only preflight, one private task/cycle
integration claim was consumed and the broker created detached commit
`0cc84190f443732424f327cc5f543325f3627dd1`, a direct child of
`6f2551df8256b6744f010d0b7e31655541ca2163`. Its one-file patch adds the
plan's half-up term. The original target branch remained clean and unmoved.
The canonical integration record SHA-256 is
`54d8a7053c6b2a32f00c42c6c85cc8cadc7f5b48ba61f3616e7f09394fdc3234`.
Joshua separately signed the VCS attestation, artifact SHA-256
`f50a4cea8f3611a2dc287be8bce63a152480298df889e275262e8caca38a4728`.
Independent replay verified both enrolled signatures, the claim, parent,
worktree, paths, blobs, patch and unchanged original checkout. The integrated
commit is an isolated proposal result, not a final test pass or acceptance.

The pinned controller renewed and replay-verified the immutable implementation
binding for the clean detached `0cc8419` tree: manifest SHA-256
`cd8be4309ae13d42a5f302d9ad4fd64ff591ac4152cfc035f5a239aafd15fb14`,
binding SHA-256
`964f53fe967ef0b98be34b81d65635612daf1f008cfe7760d34b6313c35ed2b2`.
The frozen reviewer package and direct-symbol adapter are unchanged; only the
source revision and corrected `price.py` declaration changed. Read-only Git
reconstruction produced unsigned claim `e291e6b4…`; Joshua signed it as VCS
artifact SHA-256
`fb0ed5258c679a63b566a8194bde8555d3e7dfb423087c739f451e69cbb7436e`.
The assembled authenticated provenance SHA-256
`7f6bee4ca25ed84f521f0e2f38f0a19c15c0082d4164085bb59be64269421cfd`
replay-verified against current clean Git. A separate cross-check matched its
source commit and tree to the signed integration record. This retains the
disclosed *seeded* initial-child ancestry; it does not establish a real
provider child, another correction, or acceptance.

## Corrected-revision candidate test

On 2026-09-26 UTC, Joshua signed one separate offline candidate approval for
the clean detached revision `0cc8419`. Its canonical artifact SHA-256 is
`36cc69a11a78edf73661502e1cf60779fa8d537bea71bd56c4536f0baf839f42`.
The request SHA-256 is
`7d598953023399212e43fab2bf997e5c2df7663abfaba202bcd8467056ebf9d7`;
it binds the renewed source binding, same frozen reviewer package and pinned
image, with no network, provider or write authority. Read-only preflight
replayed signed provenance and current Git. The pinned controller admitted the
approval at SHA-256
`484515e02c744212185dfc816404a0ae010ca2d54ee1f0ce916e4f2d95200521`.

One dispatch consumed a third claim in the same persistent private candidate
store. The no-mount, no-network worker executed all five frozen reviewer tests
on the corrected source: five collected, started and executed; zero failures,
errors, skips or expected failures; matching test-ID digest `2770a24a…`.
The canonical passing receipt SHA-256 is
`3736d1b0c7f87e69689e7317e6e04e2b4938c128b9ee54441d26902add12a9ce`.
Receipt replay verified the exact claim, signed inputs and unchanged clean Git;
the worker lifecycle ended `removed`. No provider call, original-checkout write,
final whole-suite result, independent review or acceptance occurred.

## Final creator and reviewer whole suites

On 2026-09-26 UTC, the pinned controller froze the complete protected creator
inventory, exactly `tests/test_quote.py`, into a private package SHA-256
`ad56be737b8aefbab0caec5be20eafbd661f9280e7b62cde94a48476360deb1e`.
Its test bytes match the original signed creator-suite digest `c270eb03…`,
base and corrected Git blobs and clean checkout. The reviewer package remains
`c2058daa…`. Distinct creator and reviewer requests have SHA-256
`95210343a107eb6c7dc816d39ff6e635fdb7ea8e414d12142357a1b92dd06f7c`
and `11bc30693e08fe4b46144fd6e00202910d4048f1335ae0958dfda1435e5cacf2`.
Both package replays, the passing candidate receipt, source binding and current
Git preflight passed before any final claim was spent.

Joshua separately signed the exact one-use final-suite grant, canonical SHA-256
`dba1f401035f5d85172c0fb0596a75256e18247fef3c1778d747d30400b827a5`.
The read-only signed preflight verified it. One claim in a new private
final-suite store was consumed before two no-mount, no-network worker runs.
The creator and reviewer suites each collected, started and executed five
tests, with zero failures, errors or skips. The creator executed-ID digest is
`005b969e…`; the reviewer digest `2770a24a…` matches the passing candidate.
Both worker lifecycles ended `removed`, and the corrected Git checkout remains
clean. The combined receipt SHA-256
`a277193353b714aa00f4ef16d554ebaa528e065e450e72368ae840acd4f120fe`
replay-verified the signed grant, exact packages, claim, counts, reviewer-test
identity and current Git. It records `final_suites_passed=true`,
`independent_review_passed=false` and `acceptance_authorized=false`.

## Owner-reported review decision

The read-only G4 review subject reconstructed from the approved plan, complete
base-to-`0cc8419` Git diff and passing final-suite receipt has SHA-256
`5cb27a5c74984a639af8ca13440000fe9220e1e7e02d74e74744a281e24e509d`.
Its full-diff SHA-256 is
`d73936eb108b84f572be357d3b82a8c1a6cbfb8ac640f3ea8954584f98d797ef`.
After that subject was described in conversation, the user reported that
Joshua Myers reviewed it and decided **pass**. This records an owner-reported
review decision; no separate signed owner-review artifact was provided. It
does not supply the gate's distinct signed two-family critic assessments,
signed judge verdict or independent-human-review proof, and grants no
acceptance authority.

On 2026-09-26 the owner specified that only one human signer will be available
and selected preparation of a separate single-operator review path using both
OpenAI and Anthropic as critic provider families. The current
G4 independent-review gate requires distinct critic and judge identities and
keys, each disjoint from the creator and existing custody roles, so it cannot
pass under that constraint. ADR-0005's single-operator policy applies to the
earlier live-review workflow; it does not silently change the G4 gate. Any G4
one-human-signer result must explicitly retain
`independent_review_evidence_passed=false`, disclose self-review risk and keep
`acceptance_authorized=false`. The owner reported that a local non-generating
Anthropic Models API check returned HTTP 200 for `claude-sonnet-5`. This
verifies model availability only; no Anthropic critic call, provider
conformance, spend grant or signed G4
review result exists. The private preparation folder now has bounded, offline
OpenAI and Anthropic critic requests for this exact subject.

See the [qualification threat model](G4_QUALIFICATION_PREPARATION_THREAT_MODEL.md)
and [work note](../notes/G4_QUALIFICATION_PREPARATION.md). The selected next
boundary is a separately approved single-operator two-provider review of the
exact plan, full Git diff and passing final-suite receipt. A future formal
independent review still requires its distinct signer roster. This
offline suite result does not establish real provider-child lineage, reviewer
independence or the applicable G3 quality gate. All three candidate claims,
the final-suite claim, and the correction-child and integration claims are spent;
do not retry or switch stores. Separate authorization is required before any
provider send.
