# Initial-child review evidence remediation

Status: prepared for a fresh owner-authorized review of integrated commit
`d7237f5e8faf98322c5a3e330b40c674b1f1ac55`. The earlier signed `revise`
decision remains immutable.

## Objective and scope

The prior two-provider judge required the signed qualification lineage to be shown
to critics, rather than represented only by hashes. This change embeds canonical
signed approvals and the signed child and integration receipts in the exact critic
brief. The source commit, approved plan, full Git diff, and passing test receipts
remain fixed. The current review's critic, judge, and creator decisions are later
steps and are not claimed in their own input. Correction-only failed-candidate
steps do not apply to this real initial-child path.

## Boundary and controls

The evidence packet is built only after replay of the final whole-suite receipt,
which rechecks the child, VCS, package, candidate, controls, and suites. Each
included signed artifact has its canonical bytes and SHA-256 in the packet. The
remaining verified bindings and test outcomes are summarized. The packet has an
explicit 32,000 character ceiling and stays in a separately frozen review subject.
No signing key, API credential, raw provider response, or protected test source is
added. A fresh review authority, separate exact one-use provider grants, and a
new ledger are required for any live calls. One human signer does not establish
independent human review or G4 acceptance.

Selected guidance: `docs/PYTHON_ENGINEERING_GUIDE.md`,
`docs/AGENTIC_VERIFICATION_GUIDE.md`, `templates/AGENTIC_VERIFICATION_LOOP.md`,
`templates/THREAT_MODEL.md`, and `templates/WORK_NOTE.md`.

## Verification and stopping rule

Acceptance evidence is a deterministic replay of the new subject against the
original signed inputs, the bounded packet, repository quality checks, and a fresh
two-provider review with a separately signed creator decision. A new `accept`
verdict may close this evidence finding; a new `revise` remains open. Stop if a
signature, source revision, packet bound, or spending authorization fails. The
private prior review artifacts must not be overwritten or reused as authority.
