# Work note: connected G4 initial-to-correction run

- Status: first live attempt failed source decoding; fresh attempt required
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
