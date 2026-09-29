# Work note: distinct bounded JSON Patch G4 task

- Status: creator approval signed and controls validated; reviewer custody signature pending
- Owner: Joshua Myers
- Started (UTC): 2026-09-28
- Risk: high, because later gates may spend money and write an isolated Git tree
- Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`,
  `templates/AGENTIC_VERIFICATION_LOOP.md`, `templates/THREAT_MODEL.md`, and
  `templates/WORK_NOTE.md`

## Objective, scope and stopping rule

Qualify a real connected G4 initial-child-to-correction cycle on a new bounded
JSON Patch task, distinct from the earlier quote, coupon and CSV tasks. The
private approved plan defines exact tree types and limits, JSON Pointer escape
decoding, nested object and array edits, ordered operations, and source/value
isolation. Only `src/json_patch_lab/patch.py` is child-owned. Protected creator
tests are committed in the isolated target; blind reviewer tests are outside
Git. The initial child may return a correct result. If its authorized candidate
passes, close this attempt. A correction needs the same genuine implementation
assertion failure in two separately authorized runs on unchanged source/tests,
followed by signed triage. Do not alter a passing source or oracle to induce a
failure. Final suites, review, applicable quality gate and creator acceptance
retain separate authority.

The initial-child task allowance is at most 50,000 micro-USD. If a real defect
qualifies, one later correction cycle may reserve at most a further 50,000
micro-USD under a combined 100,000 micro-USD task ceiling. These are ceilings,
not grants. Each provider call requires an exact owner-signed one-use grant and
a settled shared ledger. No provider call is authorized by this preparation.

## Fixed preparation evidence

The private task root is
`/Users/josh/.mos-eisley-g4-distinct-jsonpatch-2026-09-28`. The clean seed
commit is `13b9be2e1a5ea11fe57fd1e4e07fc0e465f5aa58`. The plan, interface,
rubric, initial brief, acceptance criteria, protected creator suite and blind
reviewer suite were written before any child call. The reference implementation
passed nine protected creator tests and twelve blind reviewer tests in direct
local checks. A separate known-bad reference has exactly one `replace` missing
object-key defect; it produced one assertion failure and zero errors in the
twelve reviewer tests. The incomplete target seed is not a control.

The actual no-network G4 worker ran an unsigned diagnostic package against
the two clean reference trees. Good: twelve collected, zero failures/errors.
Bad: twelve collected, one assertion failure, zero errors. Both role
expectations passed. This diagnostic grants no candidate or downstream
authority; signed control records must follow creator approval and custody.

A fresh non-human child key was enrolled in canonical policy
`b3d3a1d2d81d84a59672f833668be199d78c07f98120c9a66ea816307114d1d0`
under the previously disclosed single-operator human roster. Creator approval
preflight passed against exact base, plan, interface, rubric and protected test
bytes. Its approved-plan hash is
`73575f890e915d07af3f571cd52fcc83e9cb4f9651e7d00037a8789ec525e0ad`;
the protected test hash is
`256160570498ce20ea9dd3a5d51be1b74c0e90ce31d04ba8b5a44ba3093a71da`.
The blind reviewer test bytes are
`e4b9b8a21c5e813a3c7fc7845b4044e3048029ffccb4a43b48a477f2e9ab986b`.
No owner signature, custody, authoritative known-control record, dispatch
claim, ledger hold, provider call, integration, candidate run or G4 acceptance
exists yet.

## Current handoff

Joshua reviews and locally signs the exact creator approval with
`/Users/josh/g4-patch4-creator-sign`. That signer freezes the reviewer package
under the signed creator hash. Reviewer custody, authoritative contained
controls, assignment, dispatch and live authorization remain separate gates.

Joshua signed creator approval
`a22d7a2cf4a9e2261094e664bb202b332c56cfde4a67ae19b400c7212eb06a0c`,
freezing reviewer package
`c1c43286990b63192b24dee85a0d7d9e737674d6c124273a7084289868b6eb21`.
Both replayed against the clean approved base and exact input bytes. The
authoritative contained known-good receipt is
`606ccd708907fe74f0825b3c628d4f340289d9060d235fca44bfe1854b6d1758`;
known-bad is
`85f8b92a73bb328245520d492513989bffcb6c145a95c7b2b36913279679fac2`.
Good collected and executed twelve tests with no failure/error; bad collected
and executed twelve with one assertion failure and no error. The validated
control record is
`d120c437a87b49c44a70208775d394a222520f9f526f42a8afaedeaf6c244c84`.
No candidate or provider call occurred. Reviewer custody preflight passed
against the exact creator/package hashes and disclosed single-operator mode.
Joshua's next local step is `/Users/josh/g4-patch4-custody-sign`.
