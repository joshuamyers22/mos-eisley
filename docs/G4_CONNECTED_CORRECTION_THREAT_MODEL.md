# Threat model: connected G4 correction qualification

## Scope and ownership

The subject is one fresh bounded-quote task starting with a real coding child
and continuing to a correction child only after reproducible implementation
failure. Joshua Myers owns creator, reviewer and VCS decisions in disclosed
single-operator mode; a separately enrolled machine child key signs proposals.
The trust policy, frozen package, immutable test image, target Git base, private
ledger, and host clock are in scope. No production release is in scope.

## Assets and boundaries

| Asset | Integrity need | Boundary |
|---|---|---|
| Approved plan, creator tests and blind reviewer package | Exact bytes and custody | Signed approval, package and Git replay |
| Child proposal and target source | Owned-path scope and exact lineage | One-use dispatch, machine signature and isolated Git broker |
| Candidate failures and correction triage | Genuine repeatable implementation defect | Two independent test executions and signed adjudication |
| API credential and spend ledger | Private key handling and bounded settlement | Local hidden prompt, one-use grant and pre-reserved ledger |
| Final review and creator decision | Exact commit, evidence and scope | Frozen subject, signed review and separate acceptance |

## Abuse cases and controls

| Abuse case | Impact | Control | Residual risk |
|---|---|---|---|
| Splice prior seeded correction into a new initial run | False end-to-end claim | Fresh assignment, task ID, source and receipt linkage | Same human controls roles |
| Force or invent a failed candidate | False correction claim | Frozen reviewer package, exact counts, two signed one-use executions | Oracle can itself be wrong; triage must check it |
| Change source or tests after approval | Invalid quality claim | Git/manifest/hash replay and renewed approval on change | Trusted local host and Git executable |
| Replay a grant or exceed task budget | Duplicate charge or work | Exclusive claims, aggregate allowance and ledger | Crash may leave uncertain hold requiring disposition |
| Expose credential or provider payload | Secret or private-data loss | Hidden local key entry, private audit, bounded model offer | Same-UID host remains trusted |
| Normalize untrusted model encoding into a different source | Unexpected signed bytes | Permit at most 16 ASCII spaces, then require strict base64 decoding and canonical re-encoding; retain exact raw response in private audit | Provider can still return an incorrect implementation |
| Infer full G4 from path acceptances | Unsupported milestone claim | Separate connected-run evidence and scoped creator decision | Independent human review remains unproven in one-human mode |

## Decisions and verification

Stop if the first genuine candidate passes: there is no correction to qualify.
Do not weaken tests or request deliberately bad child output. Before any live
call, replay current signatures, source, image and ledger, then obtain Joshua's
exact one-use grant. Review spend separately. The final decision must disclose
the single-human trust model, G3 applicability and any unresolved evidence.
