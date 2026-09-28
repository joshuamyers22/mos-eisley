# Work note: connected G4 initial-to-correction run

- Status: fourth initial attempt passed; new tiered task prepared with corrected reviewer package, fresh custody pending
- Owner: Joshua Myers
- Started (UTC): 2026-09-28
- Risk: high, because this run can spend money and write an isolated target Git tree
- Selected guidance: `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, and
  `templates/WORK_NOTE.md`

## Objective and completion evidence

Qualify one connected G4 task from a real initial coding-child proposal through
an actual reproduced implementation defect, a separately authorized real
correction child, isolated integration, passing protected creator and frozen
reviewer whole suites, implementation review, and Joshua's separate decision.
The earlier `d7237f5` initial-child and `f54e815` correction-path decisions
remain separate evidence; their receipts cannot be spliced into this run.

The approved bounded-quote plan, creator tests, blind reviewer package, known
controls, and base commit `699f345` may be reused as exact inputs while the
current custody policy remains valid. This task needs a new child assignment,
initial dispatch, one-use provider grant, and private claims. The initial
child must receive the complete approved brief and may return a correct result.
If its integrated candidate passes, stop this attempt and record that no
correction was qualified. Do not alter a passing implementation or test oracle
to manufacture a failure. If it fails, require two separately authorized
reproductions of the same assertion failure and signed defect triage before a
correction cycle is eligible.

Reserve at most USD 0.050000 for the initial child and USD 0.050000 for one
correction child, with a combined task allowance of USD 0.100000. Each live
request needs its own exact signed grant; the allowance alone authorizes no
provider call. Offline tests, integration, review, and final acceptance require
their own gates. The attempt stops on an unresolved ledger, changed plan/tests,
expired policy, non-implementation failure, exhausted task allowance, or
unverified source provenance. A passing single path does not establish a
combined workflow or G3 comparative quality.

The reused plan's qualification-path paragraph describes the earlier seeded
correction exercise. The new brief and exact assignment describe this separate
real initial-child attempt without changing the plan's functional requirements
or frozen tests. A later connected-workflow claim must account for that scope
distinction explicitly; old path decisions do not resolve it.

## Context retrieved

- `docs/mos-eisley-plan.md` §§15.7, 26.2, 26.4
- `docs/G4_INITIAL_CHILD_ROUTE.md`, `docs/G4_BOUNDED_CORRECTION.md`
- `docs/G4_INITIAL_PATH_CREATOR_ACCEPTANCE_2026-09-27.md`
- `docs/G4_CORRECTION_PATH_ACCEPTANCE_2026-09-27.md`
- `src/mos_eisley/reviewer_initial_child.py`,
  `src/mos_eisley/reviewer_correction.py`

## Handoff

Joshua's fresh assignment artifact is
`4795a653cb62078fdfddf5f6934e8fe934b4633a8cde8e8ee10c481402634096`.
The signed one-use dispatch artifact is
`11e656e68a1116a50070f41584c1fbcf4733f9f544a4075c93900f5bbf2d9742`;
its exact offer is
`9fd490d495ff07c1e49b41b7c095820e39786755492d7f18856ce5ea35d5468a`.
Both signatures replayed against the clean approved base. The separately signed
live grant `6b8ca0864ce5…` was used once. OpenAI returned one malformed base64
field with a single ASCII space; the broker rejected it before child signing.
The response and audit remain private, and the ledger settled at 3,238
micro-USD. See the [incident review](G4_CONNECTED_INITIAL_CHILD_ENCODING_INCIDENT_2026-09-28.md).
No source integration or test run occurred. The spent grant and assignment will
not be reused; a fresh task needs separate signatures after the parser fix.
The saved response replays through the corrected parser without signing or
integrating it. Focused coding-broker (12) and initial-child (4) tests passed;
Ruff and Pyright passed. `make check` was started with dependency access but
stopped during the broad test suite after prolonged execution, so the full
gate is not claimed as passing. The parser change is not published or released.

## Connected initial attempt 2

Joshua signed fresh assignment `4ba8293e4a3a2125efade5e1d83e6fd1a7976c18f152cc54b813287076391631`,
dispatch `1cda26d8d19c758de75abdee35d406174c862624d78cde837a56cfd81655dec9`,
and one-use OpenAI grant `aa2111a9ede595a9914346a380f8a8e1e62b14e01c51e68a0717cf11aaf84dbb`.
The production child and initial dispatch receipts are respectively
`be33dad809966024731b4b395645bc9a5268cd93d389cc61d224b76a35972cd8`
and `dc4cd3478e39b771440274093246dd477149faf7e8962bf06e5404feab20ea47`.
The one-use ledger settled at 2,687 micro-USD. The child signed a change only
to `src/quote_lab/price.py`, but its proposal contains `discount_bps"` where a
valid Python identifier is required. No Git integration or candidate suite was
run. The correction gate in `reviewer_correction.py` requires successful test
collection and two matching assertion failures; a syntax or collection error
cannot satisfy it. This attempt remains auditable, and its spent grant and
assignment will not be reused.

## Connected initial attempt 3

Joshua signed assignment `a38d824c879ad7f910fd75affd519f6490cfafe90a7bbf9a14e0e834c56709d5`,
dispatch `fe2030586006d37b40e5f74eda8186a8dbb0fcbc7d218ee72f1f1b745626d3a8`,
and one-use OpenAI grant `f4ba7cbc6b338b9526a348965a3e06f10e546cc3d49ac8edf8b36600bd255b23`.
The production child and dispatch receipts are respectively
`1fcf3da1f2de0935a2fb1a8f07ac21eece72b51192988bd8c73bca730570213d`
and `669921d5a1928e4a4f69058dfb867b4c66a69ff89aae7b189f0c541de637d6b2`.
The ledger settled at 2,503 micro-USD. The signed proposal changed the owned
source file but disclosed one unresolved implementation issue. The exact
initial integration contract requires zero unresolved issues, so no Git
integration or candidate suite ran. The spent task and grant will not be
reused.

## Connected initial attempt 4

Joshua signed assignment `944c430afe2159f99ad037dbe711cbf62628b44ec9634fac1571fafca01bfdc6`,
dispatch `4212ab9b059399bdd7ed00881707d1966e4c60b60864809beac5b34b3c3de8ec`,
and one-use OpenAI grant `005003fae8e6a9b233042abeb5914bc8b4d848eb2cca109297fb48ebe21f5a7b`.
The production child and dispatch receipts are respectively
`ca9ed65287d6978221201f3542a95e17f2d575b2fb79b2c9014d561ab1248281`
and `dca82e2fb4da794da960faf8f2c168a2c75ae370307e9acea995a268aed3dca4`.
The ledger settled at 2,202 micro-USD. The signed proposal reported zero
unresolved issues and was integrated in isolated commit
`08026fdef4d8a80ea9cdfe6f7e613971159561cf` under signed grant
`7f35705eb57ccb91c2300deb747b2f34546b4dd66f7bfd3b84e3831080985608`.
The initial integration record is
`be15c86df680c15f6ee0f9d382b4af84f26a8f7c8a387b605bd145339ed10de1`,
and Joshua separately signed its VCS record. The frozen reviewer candidate
ran once under exact approval
`aa9900eac35b147b11d10dd076c8784d0d22c003ba338a4a85297636e3870a05`.
Receipt `d8d8fe6b4ff47ab1f47ecf9847cc815d9d54fac435300a55ed95a425d48282ad`
reports 5 collected and 5 executed tests, all passing. Therefore this attempt
cannot enter correction triage; no defect may be introduced to force one.

## Fresh tiered task preparation

A new, more demanding progressive-tier quote task was prepared before any
child call in the private `tiered-task` directory. The isolated base commit is
`ac5d3ca974a25c89aa59080afeb42e91fce16fed`; its source remains a known
incomplete seed. The approved plan defines exact integer validation, three
progressive quantity tiers, one coupon application, and one final half-up
rounding. Seven protected creator and seven frozen reviewer tests were written
before a model call and pass against a separately implemented local integer
oracle. This direct local check is design validation, not a G4 candidate
receipt. Joshua signed creator approval
`bfe06b9f9feb3bfbcd40b3cc8be41761878f49d4687e4a8f63a4ebb969c1ef31`.
The frozen reviewer package is
`dd8da0b162dd2bb5835ff7b998f56cdc88ba41389e52a7e9e019d50309c81527`,
and Joshua signed single-operator custody
`b72f7e9e98f4a869f22def969e91f5255571f73ffa77ccc33567cf92299635c7`.
Independent human review is not claimed. Initial assignment, dispatch, live
spending, integration, candidate tests, and correction remain separate gates.

The first tiered package was found unusable before its signed OpenAI grant was
called: its reviewer test imported the implementation directly, whereas the
G4 binding requires `mos_eisley_reviewer_adapter`. The binding preflight
rejected it. No child claim or provider charge exists for that grant, and its
user-facing live-call wrapper was retired. The original signed artifacts remain
private and auditable. A corrected reviewer package was frozen before any
tiered child call at
`8f2aded1439a10b9f2269090715c336c4e4155eb83503be47e4c9de8b0a801e7`.
Its known-good and known-bad implementation bindings pass structural preflight.
It requires fresh reviewer custody, assignment, dispatch, and live grant; none
of the prior task-specific signatures may be applied to this new package.
