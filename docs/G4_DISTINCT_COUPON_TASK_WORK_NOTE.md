# Work note: distinct coupon allocation G4 task

- Status: distinct coupon task implemented and initial candidate passed; connected correction attempt closed without a reproducible defect
- Owner: Joshua Myers
- Started (UTC): 2026-09-28
- Risk: high, because later gates can spend money and write an isolated Git tree
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, and
  `templates/WORK_NOTE.md`

## Objective and completion evidence

Qualify a distinct real G4 task for the connected correction workflow. The
private task specifies exact integer coupon allocation across invoice lines,
separate from the previous progressive-tier quote task. A valid run requires
owner-approved plan and protected creator tests, a frozen reviewer package and
known controls, a real initial-child proposal, separately authorized isolated
integration and candidate execution, and an actual implementation assertion
failure reproduced twice before signed triage can admit correction. A passing
candidate ends this correction attempt; neither source nor test oracle may be
changed to manufacture a failure. Final whole suites, review, and acceptance
retain separate authority.

The initial task allowance is at most 50,000 micro-USD. A later correction
cycle, if qualified, can reserve at most a further 50,000 micro-USD under a
combined 100,000 micro-USD task ceiling. These are ceilings, not provider-call
grants. Every live call requires its own exact, one-use owner signature and
settled shared-ledger state. No provider call is authorized by preparation.

## First preparation and verification

The private task root is
`/Users/josh/.mos-eisley-g4-distinct-coupon-2026-09-28`. The isolated target
base is commit `00efe9771a7d9f5b2a7169b1949a408403a87f0a`. The only child-owned
file is `src/coupon_lab/allocation.py`; protected creator tests are committed
in `tests/test_allocation.py`; the seven separate reviewer tests are outside
the Git tree and import the declared reviewer adapter. The plan, interface,
rubric, brief, and acceptance criteria were written before any child call.

A separate local reference implementation passed all seven protected creator
tests and all seven reviewer tests, and matched an independent rational-number
oracle on 426 exhaustive small cases. The incomplete base seed failed four
protected tests and three reviewer tests on proportional allocation. These
checks validate the pre-dispatch test design; they are not candidate receipts.
The policy enrolls a new non-human child key under the existing single-operator
trust roster, with policy SHA-256
`16b37b8c6e4ca0162963c2abaa8530937c39628544a0699e2b1e7a4569d4a7a8`.
At that preparation point, no owner signature, dispatch claim, ledger hold,
provider call, Git integration, candidate run, or G4 acceptance existed.
Creator approval preflight passed against the clean base and exact plan,
interface, rubric, and test bytes. Private creator, custody, assignment, and
dispatch signers, a separate exact live-grant signer, and a one-use live runner
are prepared. The downstream steps depend on the preceding owner signatures
and have not yet preflighted. The task scripts passed Python syntax and import
checks, owner launchers passed shell syntax, the pinned controller and target
Git checks passed, private key and task root have owner-only modes, and the
target Git tree is clean. The shared G4 ledger snapshot showed 9,817,147
micro-USD available and zero unresolved entries; that snapshot is not a hold
or a grant.

## Threats and stopping rules

The [task threat model](G4_DISTINCT_COUPON_TASK_THREAT_MODEL.md) covers stale
source or tests, substituted reviewer bindings, owner-key misuse, duplicate
claims, overspending, malformed child source, and manufactured defects. Stop on
changed approved bytes, policy expiry, unresolved spending, invalid signatures,
non-implementation failures, exhausted allowance, or a passing candidate.
Do not infer a correction defect from the seed's pre-dispatch failures.

## First handoff (retired)

The first handoff asked Joshua to sign the plan, interface, rubric, protected
tests, and base revision. That signature was made, then the resulting task was
retired after the contained test-runner mismatch. This note grants no authority.

## Test-runner compatibility correction

Joshua signed the first coupon creator approval
`1e2ce865fcfa7b1b99c2bc62cf367a08a5eb80a9fe14ffdb01ffadef04c93ba1`,
freezing reviewer package
`7a8c31763677e8940e8c92145b335e6b2c89e0e568ea11b6e6522937186ad9b1`.
The first contained known-good control collected one import error instead of
seven tests. Inspection of the trusted worker showed that it uses standard
`unittest` discovery, while both original coupon suites used `pytest` style.
The first approval and package remain private evidence and are not repaired or
reused. No custody, assignment, dispatch, provider call, Git integration, or
candidate run occurred for that first coupon task. Its owner-facing launchers
were retired.

The corrected private task root is
`/Users/josh/.mos-eisley-g4-distinct-coupon-v2-2026-09-28`. Its new clean base
commit `4458dfb7eca9d8c8cec2ebb2bcefcc1fa90c5579` replaces both suites
with seven `unittest.TestCase` methods each, leaving the functional plan and
owned implementation seed unchanged. Standard `unittest` discovery collected
all seven creator and reviewer tests. Both suites passed on clean known-good
source; the incomplete seed failed four creator and three reviewer assertions
with no collection errors. The new policy enrolled a fresh child key with
SHA-256 `1ee5dd02e36628b8b185cc21cd6b1b8088a68b389819716a0614493ce4ea2e21`.
This is a new provenance chain. It has no owner signature or provider authority.
Before requesting its signature, an unsigned diagnostic package using the
corrected reviewer bytes ran in the actual no-network G4 container. The
known-good source collected and passed all seven tests with zero errors; the
known-bad seed collected all seven and produced three assertion failures with
zero errors. Both role expectations passed. This diagnostic package used an
explicit placeholder creator reference and grants no approval, candidate,
provider, or correction authority. The real package will be frozen only after
Joshua signs the corrected creator approval.
The corrected creator approval preflight passed against the exact new base,
approved plan, interface, rubric, seven protected creator tests, and seven
adapter-based reviewer tests. Private creator, custody, assignment, dispatch,
one-use live-grant, and locally credentialed call launchers are prepared for
the v2 root. Their Python syntax and imports, launcher shell syntax, pinned
controller revision, and clean target Git status passed. Downstream authority
checks await fresh owner signatures. No corrected-task owner signature, claim,
ledger hold, provider call, integration, candidate test, or acceptance exists.

## Current handoff

Joshua signed corrected creator approval
`61051ea8d2043503ac118f8d73e99ff1f9d1a10943d20674e83ba54b81127efe`,
freezing corrected reviewer package
`1de609a08ec6a77974c698fd9253344b5654916e03332c082a25d099ae5c1664`.
Both replayed against the clean base
`4458dfb7eca9d8c8cec2ebb2bcefcc1fa90c5579`, approved plan, and exact
protected creator and reviewer test bytes. The binding preflight passed for
both known-control trees. Authoritative no-network contained controls produced
known-good receipt
`afbf7b762aa235dd31498b5cb8ed490dc8f425c541a335bac230a080b7f1143c`
and known-bad receipt
`fd2eac82b34dc302e60d501ca48b11c31f99ae98ebfc3874bdc7f8fcc78e78a4`.
The validated control record is
`d9f1af57b2068606be233a7bcc0035ece8cf0495bf702e3e96d89d1b4bc5b8f3`.
No candidate, provider call, source write, or acceptance occurred.

Reviewer custody preflight passed with exact v2 creator and package hashes,
single-operator risk disclosure, and no dispatch or provider authority. The
prior coupon approval and package cannot be substituted into this chain.

Joshua signed reviewer custody
`99f0b0ccd8b0bdd5f330b5dc46d71f233314851e3ae9751c3c5a761f025ce931`.
Local status replay verified its signature, exact creator/package links, policy,
and single-operator disclosure. Fresh initial-child assignment preflight passed
against clean base `4458dfb7eca9d8c8cec2ebb2bcefcc1fa90c5579`, one owned
source path, one protected creator test path, approved brief and criteria, and
a 50,000 micro-USD task allowance. The private child claim store is empty.
Joshua signed initial-child assignment
`904ac111e0da78a287a18716963ae07b066d724c967d430ac32049e6f89a07b8`.
Local status replay verified that signature. The target repository remained
clean at the approved base, and the separate dispatch preflight passed for the
exact signed assignment, creator approval, custody, plan, protected tests, and
owned source path. That dispatch grants one child dispatch, without provider,
repository write, VCS write, or acceptance authority. No dispatch signature,
claim, provider call, integration, candidate run, or G4 acceptance occurred.
Joshua signed initial-child dispatch
`43645b66178ea317d2abf164d41b7a50479c1001c96516de6b43fcf3f4e14635`,
freezing exact offer
`59e0e41d4faf7f8cc0ff537b0279b221443713476f262a66633890c3d4c27a26`.
Local status replay verified both. The target repository remains clean at the
approved base. The separate live-grant preflight passed for this exact offer,
one GPT-5.6 Terra provider call with no retry, and a maximum hold of 49,750
micro-USD. The preflight made no signature, ledger hold, provider call, or
source write. Joshua's next local step is `/Users/josh/g4-coupon2-live-sign`.
Its live grant expires 20 minutes after signing; the one-use runner is
`/Users/josh/g4-coupon2-live-call` and prompts for the API key without saving it.

Joshua signed live grant
`1a718361d9393c5d5ff3a8d3002b2d8a1a355bc5a835752d05ca3d22c32fccfa`.
Status replay and the one-use runner preflight passed against exact offer
`59e0e41d4faf7f8cc0ff537b0279b221443713476f262a66633890c3d4c27a26`.
The grant expires at `2026-09-28T22:40:28.671573Z`. The preflight made no
claim, ledger hold, provider call, or source write. Joshua's next local step
is `/Users/josh/g4-coupon2-live-call` before that expiry.

Joshua ran the one-use initial child. Signed dispatch receipt
`b16d203ed1ffa6e158db738a94b3cd60ea4d3354e8dae17c3353fe8077682fcf`
and production receipt
`2778c013071aa4c47de93fcbbc4a0731a5836d9e2cd7c3a9a76f559e80c40ad6`
replay-verified against the exact assignment, custody, frozen offer, clean
base, private claim and settled shared ledger. The ledger charged 15,451
micro-USD. The complete proposal changes only
`src/coupon_lab/allocation.py` and declares zero unresolved issues. Its source
implements input validation and integer largest-remainder allocation with
lower-index tie breaking. No source write, candidate test, or acceptance
occurred.

The isolated integration grant preflight passed. It displays the full proposed
diff and binds the two receipts, source base, one owned path, private
integration store, and one isolated Git commit. It authorizes no test, provider
call, checked-out worktree write, or acceptance. Joshua's next local step is
`/Users/josh/g4-coupon2-integration-sign`; the prepared one-use runner is
`/Users/josh/g4-coupon2-integration-run` after the exact grant is signed and
verified.

Joshua signed isolated integration grant
`3f346f8fa854ddf6669efe924276c11389f341b32253253d9876014095c93d79`.
Its status replay passed. The one-use integration created isolated commit
`939d54257216776ee1a4462b43d16135e5b4d6f2` and unsigned record
`5a1e4e1f0b6f78b85f747d4a8a46dfef7ff0b98a47d15060952fe32cd081333c`.
The original checkout remained at the approved base. Separate VCS-record
preflight replayed the signed child and exact Git patch and passed. Joshua's
next local step is `/Users/josh/g4-coupon2-integration-record-sign`. No
candidate test or acceptance occurred.

Joshua signed the VCS record for isolated commit
`939d54257216776ee1a4462b43d16135e5b4d6f2`. The record SHA is
`5a1e4e1f0b6f78b85f747d4a8a46dfef7ff0b98a47d15060952fe32cd081333c`;
the signed artifact SHA is
`8e2a6a879ef3f1def798385a221922706a7b715abbbcd466cdab8eec3a30c406`.
Status replay verified the exact Git patch. The candidate binding was frozen
at `e83fa2714ec2f5d9b7903ec2cecc71a3c864c0cdfa74028d9f227eb3237e8065`,
with request
`94a3198f65e270c1242621914e70d9b0737f989f1b09f03b0688fe81c39fc89e`
and offline job
`8a88764aa5caeec1419ed3871c415c6cccac10b34b7d434034f864140c66808f`.
The one-use candidate approval preflight passed against the prior validated
controls `d9f1af57b2068606be233a7bcc0035ece8cf0495bf702e3e96d89d1b4bc5b8f3`.
Joshua's next local step is `/Users/josh/g4-coupon2-candidate-sign`. This
preflight made no test run, provider call, source write, or acceptance.

Joshua signed candidate approval
`9a3ab286ae90a74ece0f96898e71b331607d1b364575ba8e8f5887c4f95149a4`.
Status replay passed, then its one-use offline reviewer run produced receipt
`11c61bb3772dbf141ea2c0ce45dc590f516c6821ebc26edd371c0ae29357e78c`.
The runner replay-verified that receipt. All seven frozen reviewer tests were
collected and executed, with zero failures, errors, skips, expected failures,
or unexpected successes. The original checkout is clean at
`4458dfb7eca9d8c8cec2ebb2bcefcc1fa90c5579`; the isolated worktree is clean
at integrated commit `939d54257216776ee1a4462b43d16135e5b4d6f2`.
No provider call, Git write, or acceptance occurred during candidate execution.
The passing candidate ends this connected correction attempt under the approved
plan. There is no implementation assertion failure to reproduce or triage, so
this distinct task does not qualify a connected correction cycle. No final
whole-suite approval or G4 acceptance was issued.
