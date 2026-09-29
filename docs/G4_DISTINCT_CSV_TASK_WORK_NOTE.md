# Work note: distinct bounded CSV import G4 task

- Status: initial candidate passed 8/8; CSV correction attempt closed without a defect
- Owner: Joshua Myers
- Started (UTC): 2026-09-28
- Risk: high, because later gates can spend money and write an isolated Git tree
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, and
  `templates/WORK_NOTE.md`

## Objective, scope and stopping rule

Qualify one real connected initial-child-to-correction task under fresh G4
authority. The new task implements a bounded CSV record import parser, distinct
from the earlier progressive-tier quote and coupon-allocation tasks. Its
private plan fixes quoting, CRLF/LF, empty records, malformed input and size
limits before any child call. Only `src/csv_lab/parser.py` is child-owned.
Protected creator tests are committed in the isolated target; frozen reviewer
tests stay outside Git. A passing initial candidate closes this correction
attempt. Correction requires a genuine implementation assertion failure in two
separately authorized, matching candidate runs on unchanged source and tests,
followed by signed triage. Do not change the source or oracle to manufacture
a failure. Final suites, review, quality applicability and creator acceptance
retain separate authority.

The planned initial-child task allowance is at most 50,000 micro-USD. A later
correction cycle, if qualified, may reserve at most a further 50,000 micro-USD
under a combined 100,000 micro-USD task ceiling. These are proposed ceilings,
not spending grants. Every provider call requires a separate exact owner
signature and a settled shared ledger. No provider call is authorized by this
preparation.

## Preparation evidence

The private task root is
`/Users/josh/.mos-eisley-g4-distinct-csv-2026-09-28`. The clean target base is
`66c51d1ca5f8c00b969f7c9607679519701f5cae`. The task plan, interface,
rubric, initial brief, acceptance criteria, protected creator tests and blind
reviewer tests were fixed before any child call. Both suites contain eight
`unittest.TestCase` methods. A separate reference implementation passed all
eight creator and eight reviewer tests. The incomplete target seed failed
creator and reviewer assertions in direct local checks. These local checks
are design evidence, not G4 candidate receipts.

The actual no-network G4 worker ran an unsigned diagnostic package against
clean reference controls. Good: eight collected, zero failures or errors.
Bad: eight collected, one assertion failure and zero errors. Both control
expectations passed. The diagnostic is not an authoritative signed control
record and grants no downstream authority.

The first diagnostic could not bind local generated Python bytecode from the
direct checks; those bytecode files were moved outside both reference trees.
The worker exited nonzero on the initial incomplete-seed bad control, which
had many assertion failures in direct checks. The known-bad control was then
narrowed to a single field-limit off-by-one defect in an otherwise correct
reference implementation. The target seed, plan, protected tests and blind
reviewer tests did not change.

A fresh non-human child key was enrolled in policy
`ee14c6f6859d3f058a6d493533dd5c197523adb134d3d7c092b0b33b702b58fc`
under the existing disclosed single-operator roster. Creator approval
preflight passed against the exact clean base, plan, interface, rubric and
protected test bytes. No owner signature, custody, dispatch claim, ledger
hold, provider call, integration, candidate run or G4 acceptance exists yet.

## Current handoff

Joshua reviews and locally signs the exact creator approval with
`/Users/josh/g4-csv3-creator-sign`. That signer freezes the reviewer package
under the signed creator hash. The separate custody signature and contained
known-control record follow; neither is inferred from this preflight.

Joshua signed creator approval
`441280c538318e1fd56d82998091fa584955074580cb6feff8aa5082cad3814a`,
freezing reviewer package
`358fe7177e198de8fe4d58b6b43ef43e8eab93b7b9482f6c2b5cb29ed2f283ca`.
Both replayed against the clean approved base and exact test bytes. The
authoritative contained known-good receipt is
`0c3308062234bcb471abf0f0afe670c111ed88049f01be07a5378e4c77bcbac6`;
known-bad is
`6afb2f61e2f5f28a4112baab1157bd4dfea37d687431f8ee782c19146fa2ee6e`.
The validated control record is
`5ce399e5f49c562c2f76b81071257514a1f98bc1498d6a6962ed21748abb890b`.
No candidate or provider call occurred. Reviewer custody preflight passed
against the exact creator/package hashes and disclosed single-operator mode.
Joshua's next local step is `/Users/josh/g4-csv3-custody-sign`.

Joshua signed reviewer custody
`26cb35ffc613a7fd2b5a766063d771b0e92bb021f0c0bdd73100250b507a8583`.
Its local status replay verified the exact creator/package links, policy and
single-operator disclosure. The CSV target Git repository remains clean at
`66c51d1ca5f8c00b969f7c9607679519701f5cae`. Initial-child assignment
preflight passed for one owned source file, protected creator tests, brief,
criteria and a 50,000 micro-USD task allowance. No assignment signature,
dispatch claim, provider call, integration, candidate run or G4 acceptance
occurred in this preflight. Joshua's next local step is
`/Users/josh/g4-csv3-assignment-sign`.

Joshua signed initial-child assignment
`e2ff82b90b3ff08e0f900865af07d2bf2dc59f6c8dc7ebacb3bc619fa94d41f3`.
Status replay passed, and the target remained clean at the approved base.
Separate dispatch preflight passed for the exact assignment, creator approval,
custody, protected test bundle, image and sole owned path. It grants one child
dispatch but no provider spending, Git write or acceptance. No dispatch
signature, claim, provider call or candidate run occurred in this preflight.
Joshua's next local step is `/Users/josh/g4-csv3-dispatch-sign`.

Joshua signed initial-child dispatch
`48553b5d4babf1d81fda7ac6ef302fabf67f88c3ed1383edfa3e371ba0325407`,
freezing exact offer
`cd0fffd6a19d92d3ab77f30e6f443c540ddd020aa8622fa988c13f8c025eebc6`.
Local status replay verified both and the target remains clean. Official
OpenAI GPT-5.6 Terra documentation was fetched on 2026-09-28 and supports
the task's $2 per million input, $12 per million output and 1.25-times cache
write rates. The separate live-grant preflight passed for the exact offer and
provider request `5932ee74d25ee18f3c54cbed872b6e8a0da94a180df5119047477cee453634fe`:
one call, no tools or retry, maximum hold 49,750 micro-USD. No live
signature, ledger hold, provider call, source write or candidate run occurred.
Joshua's next local step is `/Users/josh/g4-csv3-live-sign`, followed promptly
by the one-use `/Users/josh/g4-csv3-live-call` before that grant expires.

Joshua signed live grant
`626d7d39c03055067f830800c4c6a59e1ae0df0bd9255deff3d5dd0f08444983`
and ran the one-use provider child. The settled charge was 19,927 micro-USD.
Signed initial-child dispatch receipt
`480ad09f1a63278e13e32fcaa3ee942ca39e9c1a853340192459492c29cb74fb`
and production receipt
`8f4f09d436ef1973d58c751b38517bb9ed9ac7ce086678e46ea6d9ac6d4f9723`
replay-verified against the exact assignment, package, clean base, private
claim and shared ledger. The complete proposal changes only
`src/csv_lab/parser.py` and declares zero unresolved issues. No source write,
candidate test or acceptance occurred.

The separate isolated integration preflight passed, displaying the exact
child source diff and binding both receipts, the approved base, one owned path
and private integration store. It grants one isolated Git commit, with no
provider, test or acceptance authority. Joshua's next local step is
`/Users/josh/g4-csv3-integration-sign`.

Joshua signed isolated integration grant
`cb9b2cf333de70daba92c802507ed41a70e433ae491432348ee8eac54be13548`.
Status replay passed. Its one-use broker created isolated commit
`a8d6857863e02cc04f5543030473e63722d45494` and unsigned integration
record `9e4609df4206376ddad65540880768d3a7b30cf8e88e583df7884a8d19027291`.
The original checkout remained unchanged. Separate VCS-record preflight
replayed the signed child and exact Git patch and passed. Joshua's next local
step is `/Users/josh/g4-csv3-integration-record-sign`. No candidate test or
G4 acceptance occurred.

Joshua signed the exact integration VCS record. Its signed artifact is
`ddca942caa949c90875a1f28ee8057909c0a2a59353bc2ad155718b9856c3260`;
the integrated commit remains `a8d6857863e02cc04f5543030473e63722d45494`.
Local status replay passed. The first candidate binding was frozen to this
commit and the unchanged reviewer package: binding
`719b5706f6210db8a2c6c3618c7f4cbf7343f53f6152d5c663369662c628e417`,
job `fe6ce5fd0a5091e6f6681ce877d3cc90900b9535d0144f921f9de43606a1e65c`,
and request `26e0be5ebae573c28a9a37714b170856a27f90cddb2a5ca16c441385c4938ca7`.
The separate first candidate approval preflight replayed the signed chain and
validated control record
`5ce399e5f49c562c2f76b81071257514a1f98bc1498d6a6962ed21748abb890b`.
It authorizes one offline reviewer suite run only after Joshua signs it with
`/Users/josh/g4-csv3-candidate-sign`. No candidate test, provider call, Git
write or G4 acceptance occurred in this preflight.

Joshua signed candidate approval
`951de08a8e74b3377e65b5fded31753d316d4da81a1576c685f87a04d09f1d95`.
Status replay verified its signature, the integrated commit, frozen reviewer
job and validated controls. The one authorized offline run produced candidate
receipt `dc4ecb6ca8b99e9bed5025f7b2fc5a45dacf04c0095b77f31cd342a1b449439b`:
eight tests collected and executed, eight passed. The receipt reports that
the original and integrated source remained unchanged. No provider call, Git
write or G4 acceptance occurred during candidate testing. Under the fixed
stopping rule, this CSV attempt closes without a reproducible assertion
failure or correction grant. It does not qualify the connected correction
workflow.
